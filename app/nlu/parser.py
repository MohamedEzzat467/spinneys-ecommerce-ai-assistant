# -*- coding: utf-8 -*-
"""
app/nlu/parser.py
=================
Natural Language Understanding (NLU) & Filter Parser for Spinneys Conversational Assistant.

Implements the official Week 3 specification:
  1. Strict 8 intents: search, refine, sort, recommend, compare, alternatives, cross-sell, out-of-scope.
  2. Canonical Filter Schema mapping strictly to catalog columns:
     - query, brand, category, price_min, price_max, in_stock, sort, follow_up_type,
       explicit_fields, unsupported_filters.
  3. Hybrid Strategy:
     - High-precision deterministic regex rules for price, stock, brand cancellation, sorting,
       references, and unsupported dietary attributes.
     - Groq LLM integration (llama-3.1-8b-instant, temp=0, compact prompt < 150 tokens) for
       semantic intent classification and entity refinement.
  4. Validation Layer:
     - Canonical brand normalization and validation against catalog taxonomy.
     - Isolates unsupported filters into `unsupported_filters` rather than polluting standard columns.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Literal, Optional

log = logging.getLogger("spinneys.nlu")

from pydantic import BaseModel, Field, model_validator

from app.core.llm import get_llm_client
from app.core.normalizer import (
    BRAND_NORMALIZATION,
    find_known_brand,
    normalize_brand,
    normalize_text,
)

# ── Supported official intents ────────────────────────────────────────────────
VALID_INTENTS = {
    "search",
    "refine",
    "sort",
    "recommend",
    "compare",
    "alternatives",
    "cross-sell",
    "out-of-scope",
}

# ── Supported follow-up types ─────────────────────────────────────────────────
VALID_FOLLOW_UP_TYPES = {
    "new_topic",
    "refinement",
    "cancellation",
    "reference",
}


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Schemas
# ─────────────────────────────────────────────────────────────────────────────

class ParseRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000, examples=["عايز لبن جهينة تحت 50 جنيه"])


class NLUResult(BaseModel):
    """
    Unified Structured NLU Result Schema.
    Strictly conforms to:
      - intent: search | sort | advisory | out_of_scope
      - clean_query: string | null (clean product entity only)
      - semantic_expansion: string | null (expanded keywords for attributes/nutrients)
      - limit: int (extracted item count, default: 10)
      - sort_by: price_asc | price_desc | relevance
      - attribute_focus: string | null (e.g. protein, low_fat, sugar_free, organic, cheap, bulk)
    """
    action: Literal["search", "recipe", "advisory_qa", "count_inquiry", "sort", "out_of_scope"] = "search"
    intent: Literal["search", "sort", "advisory", "filter", "out_of_scope", "recipe", "count_inquiry"] = "search"
    is_count_query: bool = False
    clean_query: Optional[str] = None
    primary_ingredient: Optional[str] = None
    recipe_advice: Optional[str] = None
    conversational_reply: Optional[str] = None
    semantic_expansion: Optional[str] = None
    limit: Optional[int] = 10
    sort_by: Literal["price_asc", "price_desc", "relevance"] = "relevance"
    attribute_focus: Optional[str] = None
    category: Optional[str] = None
    head_term: Optional[str] = None
    qualifiers: list[str] = Field(default_factory=list)
    target_category: Optional[str] = None
    price_max: Optional[float] = None
    price_min: Optional[float] = None
    is_followup: bool = False
    advisory_topic: Optional[str] = None

    # Backward compatibility attributes & aliases
    query: Optional[str] = None
    brand: Optional[str] = None
    in_stock: Optional[bool] = None
    sort: Optional[str] = None
    follow_up_type: str = "new_topic"
    raw_text: str = ""
    normalized_text: str = ""
    explicit_fields: list[str] = Field(default_factory=list)
    unsupported_filters: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    token_usage: Optional[dict[str, int]] = None

    @model_validator(mode="after")
    def sync_compatibility_fields(self) -> NLUResult:
        # Clamp limit
        if self.limit is None or self.limit <= 0:
            self.limit = 10
        else:
            self.limit = max(1, min(int(self.limit), 50))

        # Sync clean_query <-> query
        if self.clean_query and not self.query:
            self.query = self.clean_query
        elif self.query and not self.clean_query:
            self.clean_query = self.query

        # Sync sort_by <-> sort
        if self.sort_by != "relevance" and not self.sort:
            self.sort = self.sort_by
        elif self.sort and self.sort_by == "relevance":
            if self.sort in ("price_asc", "price_desc"):
                self.sort_by = self.sort

        # Sync is_followup <-> follow_up_type
        if self.is_followup and self.follow_up_type == "new_topic":
            self.follow_up_type = "refinement"
        elif self.follow_up_type in ("refinement", "cancellation", "reference") and not self.is_followup:
            self.is_followup = True

        # Sync action <-> intent
        if self.action == "recipe":
            self.intent = "recipe"
        elif self.action == "advisory_qa":
            self.intent = "advisory"
        elif self.action == "count_inquiry" or self.is_count_query:
            self.action = "count_inquiry"
            self.intent = "count_inquiry"
            self.is_count_query = True
        elif self.action == "sort":
            self.intent = "sort"
        elif self.action == "out_of_scope":
            self.intent = "out_of_scope"

        # Sync intent aliases if needed
        if str(self.intent) == "out-of-scope":
            self.intent = "out_of_scope"

        # Sync category <-> target_category
        if self.target_category and not self.category:
            self.category = self.target_category
        elif self.category and not self.target_category:
            self.target_category = self.category

        return self


# Backward-compatible alias
ParseResult = NLUResult


# ─────────────────────────────────────────────────────────────────────────────
# Universal Noun / Head-Entity Dictionaries & Extraction
# ─────────────────────────────────────────────────────────────────────────────

HEAD_TERM_SYNONYMS: dict[str, set[str]] = {
    "زيت": {"زيت", "زيوت", "oil", "oils"},
    "زيوت": {"زيت", "زيوت", "oil", "oils"},
    "حليب": {"حليب", "لبن", "milk"},
    "لبن": {"حليب", "لبن", "milk"},
    "جبنة": {"جبنة", "جبن", "جبنه", "اجبان", "أجبان", "cheese"},
    "جبن": {"جبنة", "جبن", "جبنه", "اجبان", "أجبان", "cheese"},
    "جبنه": {"جبنة", "جبن", "جبنه", "اجبان", "أجبان", "cheese"},
    "شاي": {"شاي", "شاى", "tea"},
    "شاى": {"شاي", "شاى", "tea"},
    "ارز": {"ارز", "أرز", "رز", "rice"},
    "أرز": {"ارز", "أرز", "رز", "rice"},
    "رز": {"ارز", "أرز", "رز", "rice"},
    "مكرونة": {"مكرونة", "مكرونه", "معكرونة", "معكرونه", "pasta", "macaroni"},
    "مكرونه": {"مكرونة", "مكرونه", "معكرونة", "معكرونه", "pasta", "macaroni"},
    "تونة": {"تونة", "تونه", "tuna"},
    "تونه": {"تونة", "تونه", "tuna"},
    "سكر": {"سكر", "sugar"},
    "ملح": {"ملح", "salt"},
    "مناديل": {"مناديل", "منديل", "tissues", "napkins", "wipes"},
    "منديل": {"مناديل", "منديل", "tissues", "napkins", "wipes"},
    "فول": {"فول", "foul", "beans", "ful"},
    "دجاج": {"دجاج", "فراخ", "دواجن", "chicken", "poultry"},
    "فراخ": {"دجاج", "فراخ", "دواجن", "chicken", "poultry"},
    "لحم": {"لحم", "لحمة", "لحمه", "لحوم", "meat", "beef"},
    "لحمة": {"لحم", "لحمة", "لحمه", "لحوم", "meat", "beef"},
    "لحمه": {"لحم", "لحمة", "لحمه", "لحوم", "meat", "beef"},
    "بيض": {"بيض", "بيضه", "بيضة", "eggs", "egg"},
    "عسل": {"عسل", "honey"},
    "زبدة": {"زبدة", "زبده", "butter"},
    "زبده": {"زبدة", "زبده", "butter"},
    "دقيق": {"دقيق", "طحين", "flour"},
    "طحين": {"دقيق", "طحين", "flour"},
    "شوفان": {"شوفان", "oats", "oat"},
    "قهوة": {"قهوة", "قهوه", "بن", "coffee"},
    "صلصة": {"صلصة", "صلصه", "sauce", "paste"},
    "خل": {"خل", "vinegar"},
    "صابون": {"صابون", "صابونة", "صابونه", "soap"},
    "مسحوق": {"مسحوق", "detergent", "powder"},
}

KNOWN_HEAD_NOUNS: set[str] = {
    "زيت", "سمن", "سمنة", "زبدة", "زبده", "حليب", "لبن", "جبن", "جبنة", "جبنه", "زبادي", "قشطة",
    "شاي", "شاى", "قهوة", "قهوه", "نسكافيه", "عصير", "مشروب", "مياه", "مية", "كولا", "سودا",
    "ارز", "أرز", "رز", "مكرونة", "مكرونه", "شعرية", "عدس", "فول", "حمص", "فاصوليا", "لوبيا",
    "سكر", "ملح", "دقيق", "طحين", "شوفان", "عسل", "مربى", "صلصة", "صلصه", "كاتشب", "مايونيز", "خل",
    "توابل", "بهارات", "كمون", "فلفل", "كركم", "بابريكا", "قرفة", "كسبرة", "كزبرة",
    "تونة", "تونه", "سمك", "سردين", "سلمون", "جمبري", "دجاج", "فراخ", "لحم", "لحمة", "لحمه", "كفتة", "برجر", "سجق", "بيض",
    "بسكويت", "بسكوت", "شوكولاتة", "شيكولاتة", "شيبس", "شيبسي", "سناك", "كيك", "ويفر",
    "مناديل", "منديل", "صابون", "صابونة", "صابونه", "شامبو", "بلسم", "شاور", "معجون", "فرشاة",
    "مسحوق", "منظف", "كلور", "ديتول", "ملمع", "مطهر", "أكياس", "اكياس", "فويل", "أطباق", "اطباق", "علب", "علبة",
    "حفاضات", "بامبرز"
}

CATEGORY_BY_HEAD_TERM: dict[str, str] = {
    "زيت": "Grocery",
    "سمن": "Grocery",
    "سمنة": "Grocery",
    "سكر": "Grocery",
    "ملح": "Grocery",
    "دقيق": "Grocery",
    "طحين": "Grocery",
    "ارز": "Grocery",
    "أرز": "Grocery",
    "رز": "Grocery",
    "مكرونة": "Grocery",
    "مكرونه": "Grocery",
    "شعرية": "Grocery",
    "صلصة": "Grocery",
    "صلصه": "Grocery",
    "خل": "Grocery",
    "توابل": "Grocery",
    "بهارات": "Grocery",
    "عسل": "Grocery",
    "مربى": "Grocery",
    "فول": "Grocery",
    "عدس": "Grocery",
    "حمص": "Grocery",
    "تونة": "Grocery",
    "تونه": "Grocery",
    "شوفان": "Grocery",
    "حليب": "Dairy",
    "لبن": "Dairy",
    "جبن": "Dairy",
    "جبنة": "Dairy",
    "جبنه": "Dairy",
    "زبادي": "Dairy",
    "قشطة": "Dairy",
    "زبدة": "Dairy",
    "زبده": "Dairy",
    "بيض": "Dairy",
    "شاي": "Beverages",
    "شاى": "Beverages",
    "قهوة": "Beverages",
    "قهوه": "Beverages",
    "نسكافيه": "Beverages",
    "عصير": "Beverages",
    "مشروب": "Beverages",
    "مياه": "Beverages",
    "مية": "Beverages",
    "كولا": "Beverages",
    "دجاج": "Meat & Poultry",
    "فراخ": "Meat & Poultry",
    "لحم": "Meat & Poultry",
    "لحمة": "Meat & Poultry",
    "لحمه": "Meat & Poultry",
    "سمك": "Meat & Poultry",
    "جمبري": "Meat & Poultry",
    "سجق": "Meat & Poultry",
    "برجر": "Meat & Poultry",
    "بسكويت": "Sweets & Snacks",
    "بسكوت": "Sweets & Snacks",
    "شوكولاتة": "Sweets & Snacks",
    "شيكولاتة": "Sweets & Snacks",
    "شيبس": "Sweets & Snacks",
    "شيبسي": "Sweets & Snacks",
    "كيك": "Sweets & Snacks",
    "ويفر": "Sweets & Snacks",
    "مناديل": "Households",
    "منديل": "Households",
    "صابون": "Households",
    "صابونة": "Households",
    "مسحوق": "Households",
    "منظف": "Households",
    "كلور": "Households",
    "ديتول": "Households",
    "أكياس": "Households",
    "اكياس": "Households",
    "أطباق": "Households",
    "اطباق": "Households",
    "علب": "Households",
    "علبة": "Households",
    "شامبو": "Beauty & Personal Care",
    "بلسم": "Beauty & Personal Care",
    "معجون": "Beauty & Personal Care",
    "فرشاة": "Beauty & Personal Care",
    "حفاضات": "Baby Care",
    "بامبرز": "Baby Care",
}


def get_head_term_variants(head_term: Optional[str]) -> set[str]:
    """
    Returns exhaustive bilingual lemmas, synonyms, and Arabic morphological variants
    for a given head term (e.g. 'حليب' -> {'حليب', 'لبن', 'الحليب', 'اللبن', 'milk'}).
    """
    if not head_term:
        return set()

    raw = head_term.strip().lower()
    norm = normalize_text(raw).strip().lower()
    variants = {raw, norm}

    # Add/strip definite article 'ال'
    for v in list(variants):
        if v.startswith("ال") and len(v) > 3:
            variants.add(v[2:])
        elif not v.startswith("ال") and len(v) >= 2:
            variants.add("ال" + v)

    # Check synonyms map
    for word in list(variants):
        clean_w = word[2:] if word.startswith("ال") and len(word) > 3 else word
        lookup_keys = [word, clean_w]
        for lk in lookup_keys:
            if lk in HEAD_TERM_SYNONYMS:
                for syn in HEAD_TERM_SYNONYMS[lk]:
                    syn_raw = syn.strip().lower()
                    syn_norm = normalize_text(syn_raw).strip().lower()
                    variants.add(syn_raw)
                    variants.add(syn_norm)
                    if syn_raw.startswith("ال") and len(syn_raw) > 3:
                        variants.add(syn_raw[2:])
                    elif not syn_raw.startswith("ال") and len(syn_raw) >= 2:
                        variants.add("ال" + syn_raw)

    return {v for v in variants if len(v) >= 2}


def extract_head_term_and_qualifiers(clean_query: Optional[str]) -> tuple[Optional[str], list[str], Optional[str]]:
    """
    Universally extracts:
      - head_term: Primary product noun
      - qualifiers: List of attribute or secondary modifier tokens
      - target_category: Inferred primary department
    """
    if not clean_query:
        return None, [], None

    words = clean_query.strip().split()
    if not words:
        return None, [], None

    # Check if any token matches a known head noun (skipping prepositional modifiers)
    head_idx = -1
    for idx, w in enumerate(words):
        w_norm = normalize_text(w)
        # Skip token if preceded by an ingredient/modifier preposition
        if idx > 0 and words[idx - 1] in ("في", "فى", "مع", "من", "بطعم", "بنكهة", "برائحة", "بخلاصة", "بمذاق", "in", "with"):
            continue
        # Skip token if it carries an attached preposition like بالـ or للـ or بـ
        if w_norm.startswith("بال") or w_norm.startswith("لل") or (w_norm.startswith("ب") and len(w_norm) > 3 and w_norm[1:] in KNOWN_HEAD_NOUNS):
            continue
        w_clean = w_norm[2:] if w_norm.startswith("ال") and len(w_norm) > 3 else w_norm
        if w_clean in KNOWN_HEAD_NOUNS or w_norm in KNOWN_HEAD_NOUNS:
            head_idx = idx
            break

    if head_idx != -1:
        head_term = words[head_idx]
        qualifiers = [w for i, w in enumerate(words) if i != head_idx]
    else:
        # Default Arabic construct: first noun is the head noun
        head_term = words[0]
        qualifiers = words[1:]

    # Clean head_term (remove definite article if present for canonical form)
    norm_head = normalize_text(head_term)
    canon_head = norm_head[2:] if norm_head.startswith("ال") and len(norm_head) > 3 else norm_head

    # Infer target category
    target_cat = CATEGORY_BY_HEAD_TERM.get(canon_head) or CATEGORY_BY_HEAD_TERM.get(norm_head)
    if not target_cat:
        if canon_head in ("زيت", "سمن", "سكر", "شاي", "ارز", "مكرونة", "صلصة", "فول", "عدس", "دقيق", "تونة"):
            target_cat = "Grocery"
        elif canon_head in ("لبن", "حليب", "جبن", "جبنة", "زبادي"):
            target_cat = "Dairy"
        elif canon_head in ("مناديل", "صابون", "منظف"):
            target_cat = "Households"

    return canon_head, qualifiers, target_cat


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic Rule Matching Helpers
# ─────────────────────────────────────────────────────────────────────────────

# Unsupported dietary & non-column filters
UNSUPPORTED_FILTER_PATTERNS = [
    (r"\b(خالي من السكر|بدون سكر|من غير سكر|زيرو سكر|sugar[- ]?free|zero sugar|no sugar)\b", "sugar-free"),
    (r"\b(خالي من الجلوتين|بدون جلوتين|من غير جلوتين|gluten[- ]?free)\b", "gluten-free"),
    (r"\b(اورجانيك|عضوي|عضويه|organic)\b", "organic"),
    (r"\b(نباتي|نباتيه|vegan|vegetarian)\b", "vegan"),
    (r"\b(خالي من اللاكتوز|بدون لاكتوز|lactose[- ]?free)\b", "lactose-free"),
    (r"\b(دايت|لايت|diet|light|low fat|قليل الدسم|خالي الدسم|skimmed)\b", "diet"),
]

# Brand cancellation phrases ("any brand", "اي ماركة", "ay brand mesh fare2")
BRAND_CANCELLATION_RE = re.compile(
    r"\b(اي (مارك[هة]|براند|شرك[هة])|مش فارق (المارك[هة]|البراند)|مش مهم (المارك[هة]|البراند)|"
    r"بدون تحديد (مارك[هة]|براند)|any brand|all brands|no brand|clear brand|remove brand|every brand|"
    r"ay brand|ay brand mesh fare2|mesh fare2 el brand|mesh mohem el brand)\b",
    re.IGNORECASE,
)

# Reference phrases ("اول واحد", "الارخص فيهم", "first one", "this cheese")
REFERENCE_RE = re.compile(
    r"\b(اول (واحد|منتج)|ثاني (واحد|منتج)|الاول|التاني|الارخص فيهم|الاخير|رقم (واحد|١|1)|"
    r"first (one|item|product)|second (one|item)|last one|cheapest of them|the first|this|that|ده|دي|دا|da|di)\b",
    re.IGNORECASE,
)

# Advisory / Comparison / Nutritional triggers
ADVISORY_RE = re.compile(
    r"\b("
    r"ايهم\s*(?:افضل|أفضل|احسن|أحسن|اعلى|أعلى|اقل|أقل|صحي|فيها|فيهم|منهم)|"
    r"ايهما\s*(?:افضل|أفضل|احسن|أحسن|اعلى|أعلى|اقل|أقل|صحي|فيها|فيهم|منهم)|"
    r"مين\s*(?:فيهم|منهم)?\s*(?:افضل|أفضل|احسن|أحسن|اعلى|أعلى|صحي)|"
    r"انهي\s*(?:فيهم|منهم|واحد)?\s*(?:افضل|أفضل|احسن|أحسن|صحي\s*اكتر|احسن\s*للصحة|اعلى|أعلى)|"
    r"مين\s*احسن|مين\s*افضل|مين\s*اعلى|"
    r"الفرق\s*(?:بينهم|ما\s*بينهم|بين\s*(?:الانواع|الأنواع|المنتجات)\s*دي)|"
    r"ما\s*الفرق\s*بينهم|ايه\s*الفرق\s*بينهم|"
    r"انصحني\s*(?:بينهم|فيهم)|ترشحلي\s*انهي|ترشح\s*انهي|انهي\s*واحد|"
    r"قارن\s*(?:بينهم|ما\s*بينهم)|"
    r"which\s*one\s*(?:is\s*better|to\s*buy|is\s*healthier|higher\s*in\s*protein|has\s*more\s*protein)|"
    r"difference\s*between\s*them|compare\s*them"
    r")\b",
    re.IGNORECASE,
)

# Known product entities (grocery items/categories)
PRODUCT_ENTITY_RE = re.compile(
    r"\b("
    r"جبن[هة]?|حليب|لبن(?:\s*بودر[هة])?|زباد[يى]|قشط[هة]|سمن[هة]|زبد[هة]|بيض|"
    r"زيت(?:\s*زيتون|\s*ذرة|\s*عباد)?|خل|"
    r"شاي|قهو[هة]|نسكافيه|سكر|عسل|مرب[يى]|شوكولات[هة]|بسكويت|شيبس|"
    r"ارز|أرز|رز|مكرون[هة]|صلص[هة]|تونا?|فول|عدس|حمص|لوبيا|فاصوليا|"
    r"دجاج|فراخ|لحم[هة]|سمك|جمبري|"
    r"منظف\w*|صابون|مسحوق|شامبو|معجون|مناديل|"
    r"مياه|عصير|مشروب|بيبسي|كولا|"
    r"cheese|milk|yogurt|butter|ghee|eggs|"
    r"oil|olive\s*oil|tea|coffee|sugar|honey|"
    r"rice|pasta|tuna|chicken|meat|beef|fish|"
    r"soap|shampoo|juice|water"
    r")\b",
    re.IGNORECASE,
)

# Out-of-scope triggers
OUT_OF_SCOPE_RE = re.compile(
    r"\b(الجو|طقس|درج[هة] الحوار[هة]|تاكسي|اوبر|كريم|حجز|طيران|فندق|ماتش|كوره|اهلي|زمالك|"
    r"نكته|joke|weather|taxi|flight|hotel|match|who are you|انت مين|ساع[هة] كام|closing time|"
    r"open hours|مواعيد العمل|el gaw|e7jezly|e7jez|write me|code|python|كود|برمجة|اكتبلي كود)\b",
    re.IGNORECASE,
)

# Alternatives triggers
ALTERNATIVES_RE = re.compile(
    r"\b(بديل|بدائل|بديل لـ?|بديل ل|alternative|substitute|replacement|badeel|badeel le)\b",
    re.IGNORECASE,
)

# Compare triggers
COMPARE_RE = re.compile(
    r"\b(قارن|مقارن[هة]|الفرق بين|ايهما افضل|مين احسن|versus|vs|compare|difference between|2aren)\b",
    re.IGNORECASE,
)

# Cross-sell triggers
CROSS_SELL_RE = re.compile(
    r"\b(ينفع مع|يمشي مع|حاج[هة] مع|يليق مع|معاه ايه|goes well with|complement|pair with|pairs with|eh yenfa3 ma3|eh yenfa3)\b",
    re.IGNORECASE,
)

# Recommend triggers
RECOMMEND_RE = re.compile(
    r"\b(اقترح|اقتراح|رشح|ترشح\w*|افكار|ايه رايك|نصيح\w*|recommend\w*|suggest\w*|ideas for|what do you recommend|e2tra7\w*)\b",
    re.IGNORECASE,
)

# Sort triggers
SORT_DESC_RE = re.compile(
    r"\b("
    r"(?:مع\s*)?ترتيب\s*(?:هم|هن|ها)?\s*تنازلي|"
    r"مرتب(?:ين|ة|ات)?\s*تنازلي|"
    r"مرتب(?:ين|ة|ات)?\s*من\s*(?:الاعلى|الأعلى|الاغلى|الأغلى)|"
    r"مترتب(?:ين|ة|ات)?\s*من\s*(?:الاعلى|الأعلى|الاغلى|الأغلى)|"
    r"رتب\s*(?:هم|هن|ها)?\s*من\s*الاعلى\s*سعرا?\s*(?:(?:الى|الي|لـ?)\s*الاقل|للاقل)|"
    r"رتب\s*(?:هم|هن|ها)?\s*من\s*الأعلى\s*سعراً?\s*(?:(?:الى|الي|لـ?)\s*الأقل|للأقل)|"
    r"من\s*الاعلى\s*سعرا?\s*(?:(?:الى|الي|لـ?)\s*الاقل|للاقل)|"
    r"من\s*الأعلى\s*سعراً?\s*(?:(?:الى|الي|لـ?)\s*الأقل|للأقل)|"
    r"من\s*الاعلى\s*(?:(?:الى|الي|لـ?)\s*الاقل|للاقل)|"
    r"من\s*الأعلى\s*(?:(?:الى|الي|لـ?)\s*الأقل|للأقل)|"
    r"رتب\s*(?:هم|هن|ها)?\s*من\s*الاعلى|"
    r"رتب\s*(?:هم|هن|ها)?\s*من\s*الأعلى|"
    r"رتب\s*(?:هم|هن|ها)?\s*من\s*الاغلى\s*(?:(?:الى|الي|لـ?)\s*الارخص|للارخص)|"
    r"رتب\s*(?:هم|هن|ها)?\s*من\s*الأغلى\s*(?:(?:الى|الي|لـ?)\s*الأرخص|للأرخص)|"
    r"رتب\s*(?:هم|هن|ها)?\s*من\s*الاغلى|"
    r"رتب\s*(?:هم|هن|ها)?\s*من\s*الأغلى|"
    r"الاعلى\s*سعرا?|"
    r"الأعلى\s*سعراً?|"
    r"رتب بالسعر تنازلي|رتب تنازلي|سعر تنازلي|تنازلي|من الاغلى|من الأغلى|الاغلى|الأغلى|للاقل|للأقل|"
    r"highest price|most expensive|price high to low|sort desc|el aghla|men el aghla|aghla|rateb men el aghla"
    r")\b",
    re.IGNORECASE,
)

SORT_ASC_RE = re.compile(
    r"\b("
    r"(?:مع\s*)?ترتيب\s*(?:هم|هن|ها)?\s*حسب\s*(?:الاسعار|الأسعار|السعر)|"
    r"(?:مع\s*)?ترتيب\s*(?:هم|هن|ها)?\s*(?:بالاسعار|بالأسعار|بالسعر)|"
    r"(?:مع\s*)?ترتيب\s*(?:الاسعار|الأسعار|السعر)|"
    r"مرتب(?:ين|ة|ات)?\s*حسب\s*(?:الاسعار|الأسعار|السعر)|"
    r"مرتب(?:ين|ة|ات)?\s*(?:بالاسعار|بالأسعار|بالسعر)|"
    r"مترتب(?:ين|ة|ات)?\s*حسب\s*(?:الاسعار|الأسعار|السعر)|"
    r"مترتب(?:ين|ة|ات)?\s*(?:بالاسعار|بالأسعار|بالسعر)|"
    r"مرتب(?:ين|ة|ات)?|مترتب(?:ين|ة|ات)?|"
    r"حسب\s*(?:الاسعار|الأسعار|السعر)|"
    r"رتب\s*(?:هم|هن|ها)?\s*حسب\s*(?:الاسعار|الأسعار|السعر)|"
    r"رتب\s*(?:هم|هن|ها)?\s*(?:بالسعر|بالاسعار|بالأسعار|الاسعار|الأسعار)|"
    r"رتب\s*(?:هم|هن|ها)?\s*من\s*الاقل\s*سعرا?\s*(?:(?:الى|الي|لـ?)\s*الاعلى|للاعلى)|"
    r"رتب\s*(?:هم|هن|ها)?\s*من\s*الأقل\s*سعراً?\s*(?:(?:الى|الي|لـ?)\s*الأعلى|للأعلى)|"
    r"من\s*الاقل\s*سعرا?\s*(?:(?:الى|الي|لـ?)\s*الاعلى|للاعلى)|"
    r"من\s*الأقل\s*سعراً?\s*(?:(?:الى|الي|لـ?)\s*الأعلى|للأعلى)|"
    r"من\s*الاقل\s*(?:(?:الى|الي|لـ?)\s*الاعلى|للاعلى)|"
    r"من\s*الأقل\s*(?:(?:الى|الي|لـ?)\s*الأعلى|للأعلى)|"
    r"رتب\s*(?:هم|هن|ها)?\s*من\s*الاقل|"
    r"رتب\s*(?:هم|هن|ها)?\s*من\s*الأقل|"
    r"رتب\s*(?:هم|هن|ها)?\s*من\s*الارخص\s*(?:(?:الى|الي|لـ?)\s*الاغلى|للاغلى)|"
    r"رتب\s*(?:هم|هن|ها)?\s*من\s*الأرخص\s*(?:(?:الى|الي|لـ?)\s*الأغلى|للأغلى)|"
    r"رتب\s*(?:هم|هن|ها)?\s*من\s*الارخص للاغلى|رتب من الارخص للاغلى|رتب من الارخص|رتب بالسعر تصاعدي|رتب بالسعر|رتب تصاعدي|سعر تصاعدي|تصاعدي|"
    r"الاقل\s*سعرا?|"
    r"الأقل\s*سعراً?|"
    r"من الارخص|الارخص الاول|الارخص|ارخص|الأرخص|أرخص|للاعلى|للأعلى|"
    r"cheapest first|cheapest|cheap|lowest price|price low to high|"
    r"sort by price|sort by lowest|sort by el arkhas|sort by|sort asc|rateb bel se3r el arkhas|rateb bel se3r|"
    r"rateb men el arkhas|هات الارخص الاول|show cheapest first|el arkhas|arkhas"
    r")\b",
    re.IGNORECASE,
)

# Price range: "بين 20 و 50", "من 20 ل 50", "between 20 and 50", "between 30 w 70 pounds"
PRICE_BETWEEN_RE = re.compile(
    r"(?:بين|من|between)\s*(\d+(?:\.\d+)?)\s*(?:و|لـ?|الي|إلى|to|and|w|-)\s*(\d+(?:\.\d+)?)\s*(?:جنيه|egp|le|pounds?|pound|gneh|ج)?\b",
    re.IGNORECASE,
)
# Price max: "تحت 50", "اقل من 50", "under 50", "less than 50", "max 50", "ta7t 60 gneh"
PRICE_MAX_RE = re.compile(
    r"(?:تحت|اقل من|بحد اقصي|بحد اقصى|في حدود|مش اكتر من|under|less than|below|up to|max(?:imum)?|ta7t)\s*(\d+(?:\.\d+)?)\s*(?:جنيه|egp|le|pounds?|pound|gneh|ج)?\b",
    re.IGNORECASE,
)
# Price min: "اكتر من 100", "فوق 100", "over 100", "above 100", "min 100", "fo2 80 pounds", "more than 100"
PRICE_MIN_RE = re.compile(
    r"(?:فوق|اكتر من|اكثر من|اعلي من|اعلى من|بحد ادني|بحد ادنى|مش اقل من|over|above|more than|more then|at least|min(?:imum)?|fo2)\s*(\d+(?:\.\d+)?)\s*(?:جنيه|egp|le|pounds?|pound|gneh|ج)?\b",
    re.IGNORECASE,
)

# In-stock regex
STOCK_IN_RE = re.compile(
    r"\b(متوفر\w*|المتوفر\w*|متاح\w*|المتاح\w*|موجود\w*|الموجود\w*|في المخزن|in stock|available|only in stock|motawafer|el motawafer)\b",
    re.IGNORECASE,
)
STOCK_OUT_RE = re.compile(
    r"\b(غير متوفر|مش متوفر|مش متاح|out of stock|unavailable)\b",
    re.IGNORECASE,
)


def _extract_unsupported_filters(normalized: str) -> list[str]:
    """Identify customer criteria not represented as standard DB columns."""
    unsupported = []
    for pattern, tag in UNSUPPORTED_FILTER_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            if tag not in unsupported:
                unsupported.append(tag)
    return unsupported


QUANTIFIERS_PATTERN = (
    r"(?:انواع|نوع|أنواع|اصناف|أصناف|منتجات|عناصر|قطع|قطعة|علب|علبة|أكياس|كيس|حبات|حبة|"
    r"ازايز|ازازة|زجاجات|زجاجة|items?|types?|products?|packs?|bottles?|pieces?)"
)

ARABIC_COUNT_WORDS = {
    "واحد": 1, "واحدة": 1, "اتنين": 2, "اثنين": 2, "تلاتة": 3, "ثلاثة": 3,
    "اربعة": 4, "أربعة": 4, "خمسة": 5, "ستة": 6, "سبعة": 7, "تمانية": 8, "ثمانية": 8,
    "تسعة": 9, "عشرة": 10,
}


def extract_limit(text: str) -> Optional[int]:
    """
    Extracts explicit count/limit (e.g., '5 انواع فول', '3 علب لبن', 'top 5', '5 items').
    Ignores numbers that belong to price boundaries (e.g. 'تحت 50 جنيه').
    """
    norm = normalize_text(text)

    # 1. Check for digits in limit/count context (e.g. '5 انواع', 'افضل 5', 'top 5', '3 علب', '5 فول')
    m_digit = re.search(
        r"(?:top|أول|اول|افضل|أفضل|احسن|أحسن|عايز|عاوز|محتاج|هات)?\s*(\d+)\s*"
        rf"(?:{QUANTIFIERS_PATTERN})?(?!\s*(?:جنيه|egp|le|pound|ج\b))",
        norm,
        re.IGNORECASE,
    )
    if m_digit:
        val = int(m_digit.group(1))
        # Validate that this number is not part of a price constraint
        p_max = PRICE_MAX_RE.search(norm)
        p_min = PRICE_MIN_RE.search(norm)
        p_between = PRICE_BETWEEN_RE.search(norm)
        is_price_num = False
        if p_max and float(p_max.group(1)) == val:
            is_price_num = True
        if p_min and float(p_min.group(1)) == val:
            is_price_num = True
        if p_between and (float(p_between.group(1)) == val or float(p_between.group(2)) == val):
            is_price_num = True

        if not is_price_num and 1 <= val <= 100:
            return min(val, 50)

    # 2. Check for Arabic word numbers in count context
    for word, num in ARABIC_COUNT_WORDS.items():
        if re.search(
            rf"\b(?:top|أول|اول|افضل|أفضل|احسن|أحسن)?\s*{word}\s*(?:{QUANTIFIERS_PATTERN})?\b",
            norm,
            re.IGNORECASE,
        ):
            return num

    return None


def strip_brand_from_query(query: Optional[str], brand: Optional[str]) -> Optional[str]:
    """
    Strips brand name and all known bilingual aliases from query text,
    ensuring pure entity retrieval without brand query collisions.
    """
    if not query or not brand:
        return query

    canonical_b = normalize_brand(brand)
    aliases = {
        brand.lower(),
        canonical_b.lower(),
        normalize_text(brand).lower(),
        normalize_text(canonical_b).lower(),
    }
    for alias, canon in BRAND_NORMALIZATION.items():
        if canon.lower() == canonical_b.lower():
            aliases.add(alias.lower())
            aliases.add(normalize_text(alias).lower())

    cleaned = query
    for alias in sorted(aliases, key=len, reverse=True):
        if len(alias) >= 2:
            cleaned = re.sub(r"\b" + re.escape(alias) + r"\b", " ", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned if len(cleaned) >= 2 else None


def sanitize_query(raw_text: str) -> str:
    """
    Sanitizes customer queries by stripping generic action verbs, request stems,
    qualifiers/superlatives (افضل, نوع), availability/stock words, price inquiry stems,
    sorting expressions (including conjugated colloquial forms), numbers/quantifiers,
    conversational fillers (قصدى, فين), meal/item request stems, and punctuation,
    preserving strictly the core product entity.
    """
    text = raw_text.strip()
    # 1. Clean punctuation (Arabic question mark ؟, English ?, !, commas, etc.)
    text = re.sub(r"[?؟!\.,،;:~]+", " ", text)
    norm = normalize_text(text)

    # 2. Generic action verbs, request stems, and conversational fillers
    request_stems_re = re.compile(
        r"\b(اقترح\w*|اقتراح\w*|ورشح\w*|رشح\w*|ترشح\w*|عايز\w*|عاوز\w*|عايزين|محتاج\w*|ممكن|"
        r"لو سمحت|من فضلك|وريني|هاتلي|هات|اعرضلي|قولي|ابحث عن|دورلي على|دورلي|"
        r"قصد(?:ي|ى)|يعني|بقولك|فين|عندكم|عندك|موجود|متاح|هو في|هو فيه|"
        r"suggest\w*|recommend\w*|show me|find me|i want|i need|give me|please|where is|i mean|do you have)\b",
        re.IGNORECASE,
    )
    norm = request_stems_re.sub(" ", norm)

    # 2b. Strip conjugated and colloquial sorting phrases completely
    norm = SORT_DESC_RE.sub(" ", norm)
    norm = SORT_ASC_RE.sub(" ", norm)
    instruction_stems_re = re.compile(
        r"\b("
        r"مرتب(?:ين|ة|ات)?\s*حسب\s*(?:الاسعار|الأسعار|السعر)|"
        r"مرتب(?:ين|ة|ات)?\s*(?:بالاسعار|بالأسعار|بالسعر)|"
        r"مترتب(?:ين|ة|ات)?\s*حسب\s*(?:الاسعار|الأسعار|السعر)|"
        r"مترتب(?:ين|ة|ات)?\s*(?:بالاسعار|بالأسعار|بالسعر)|"
        r"مرتب(?:ين|ة|ات)?|مترتب(?:ين|ة|ات)?|"
        r"(?:مع\s*)?ترتيب\s*(?:الاسعار|الأسعار|السعر|بالسعر|بالاسعار|بالأسعار|حسب\s*السعر|حسب\s*الاسعار)|"
        r"رتب\s*(?:الاسعار|الأسعار|بالسعر|حسب\s*السعر)|"
        r"رتبهم|رتبهن|رتبها|رتب|"
        r"حسب\s*(?:الاسعار|الأسعار|السعر)|بالسعر|بالاسعار|بالأسعار|sort by price|sort by|مع\s*الترتيب|"
        r"من\s*الارخص|من\s*الأرخص|من\s*الاغلى|من\s*الأغلى|من\s*الاعلى|من\s*الأعلى|من\s*الاقل|من\s*الأقل|"
        r"الارخص|الأرخص|الاغلى|الأغلى|الاعلى|الأعلى|الاقل|الأقل|تصاعدي|تنازلي"
        r")\b",
        re.IGNORECASE,
    )
    norm = instruction_stems_re.sub(" ", norm)

    # 3. Superlatives, comparatives, and generic qualifiers (افضل, احسن, نوع, انواع)
    qualifiers_re = re.compile(
        r"\b(و?افضل\w*|و?أفضل\w*|و?احسن\w*|و?أحسن\w*|و?اجود\w*|و?أجود\w*|"
        r"و?نوع\w*|و?انواع\w*|و?أنواع\w*|و?صنف\w*|و?اصناف\w*|و?أصناف\w*|"
        r"best|top|finest|types?|kinds?)\b",
        re.IGNORECASE,
    )
    norm = qualifiers_re.sub(" ", norm)

    # 4. Strip numbers and quantifiers / count nouns (e.g. "5", "خمسة", "انواع", "علب")
    norm = re.sub(r"\b\d+\b", " ", norm)
    arabic_num_words = r"\b(واحد|واحدة|اتنين|اثنين|تلاتة|ثلاثة|اربعة|أربعة|خمسة|ستة|سبعة|تمانية|ثمانية|تسعة|عشرة)\b"
    norm = re.sub(arabic_num_words, " ", norm, flags=re.IGNORECASE)
    quantifiers_re = re.compile(
        rf"\b{QUANTIFIERS_PATTERN}\b",
        re.IGNORECASE,
    )
    norm = quantifiers_re.sub(" ", norm)

    # 5. Stock and availability tokens (موجود, متاح, متوفر)
    stock_re = re.compile(
        r"\b(موجود\w*|الموجود\w*|متاح\w*|المتاح\w*|متوفر\w*|المتوفر\w*|in\s*stock|available)\b",
        re.IGNORECASE,
    )
    norm = stock_re.sub(" ", norm)

    # 6. Price inquiry words (اسعار, أسعار, سعر)
    price_inquiry_re = re.compile(
        r"\b(اسعار|أسعار|سعر|كام\s*سعر|بكام|prices?|price\s*of)\b",
        re.IGNORECASE,
    )
    norm = price_inquiry_re.sub(" ", norm)

    # 7. Generic meal/item words when used as requests
    meal_stems_re = re.compile(
        r"\b(وجب[هة]|اكل[هة]|اكل|طبيخ|حاج[هة]|منتج\w*|عناصر|meal|food|dish|items?)\b",
        re.IGNORECASE,
    )
    norm = meal_stems_re.sub(" ", norm)

    norm = re.sub(r"\s+", " ", norm).strip()

    # Normalize definite article Al- for key grocery nouns ("الزيت" -> "زيت", "الزيت طعام" -> "زيت طعام")
    words = norm.split()
    cleaned_words = []
    for w in words:
        if w.startswith("ال") and len(w) >= 4 and w in (
            "الزيت", "الجبن", "الجبنة", "اللبن", "الحليب", "الشاي", "السكر", "الفول",
            "الارز", "الأرز", "المكرونة", "الدجاج", "اللحم", "البيض", "العسل", "الزبدة",
            "الدقيق", "الشوفان", "القهوة", "التونة", "الصلصة", "الخل"
        ):
            cleaned_words.append(w[2:])
        else:
            cleaned_words.append(w)
    norm = " ".join(cleaned_words)

    return norm if len(norm) >= 2 else normalize_text(text).strip()


def _clean_query_string(raw: str, brand: Optional[str], unsupported: list[str]) -> Optional[str]:
    """Clean the target product search keyword by stripping filter tokens."""
    # First apply query sanitization
    cleaned = sanitize_query(raw)

    # Remove price phrases
    cleaned = PRICE_BETWEEN_RE.sub(" ", cleaned)
    cleaned = PRICE_MAX_RE.sub(" ", cleaned)
    cleaned = PRICE_MIN_RE.sub(" ", cleaned)

    # Remove standalone currency
    cleaned = re.sub(r"\b(جنيه|egp|le|pounds?|pound|gneh|ج)\b", " ", cleaned, flags=re.IGNORECASE)

    # Strip brand in all known variants
    if brand:
        for k, v in BRAND_NORMALIZATION.items():
            if v == brand:
                cleaned = re.sub(rf"(?:\b|\s|^){re.escape(k)}(?:\b|\s|$)", " ", cleaned, flags=re.IGNORECASE)
                cleaned = re.sub(rf"(?:\b|\s|^){re.escape(normalize_text(k))}(?:\b|\s|$)", " ", cleaned, flags=re.IGNORECASE)

    # Remove brand cancellation phrases
    cleaned = BRAND_CANCELLATION_RE.sub(" ", cleaned)

    # Remove stock phrases
    cleaned = STOCK_IN_RE.sub(" ", cleaned)
    cleaned = STOCK_OUT_RE.sub(" ", cleaned)

    # Remove sort phrases (desc first, then asc)
    cleaned = SORT_DESC_RE.sub(" ", cleaned)
    cleaned = SORT_ASC_RE.sub(" ", cleaned)

    # Remove conversational filler words and constraint modifier words
    fillers = [
        r"\b(عايز|عاوز|محتاج|ابحث عن|ابحث|دورلي على|دورلي|هاتلي|هات|اعرضلي|وريني|فين|من فضلك|لو سمحت|بس|فقط)\b",
        r"\b(show me|find me|i want|i need|looking for|search for|give me|please|only|just|where is the|where is|show)\b",
        r"\b(3ayez|hatly|warini|please|feen el|feen|first)\b",
        r"\b(مارك[هة]|براند|brand|items?|منتجات?|في الفرع|in store|store|branch|price|سعر|اي|مش فارق|معايا|remove|filter|fine|is fine|all|any|bas|el|rateb|رتب|رتبهم|رتبهن|رتبها)\b",
        r"\b(بديل لـ?|بديل ل|بديل|alternative for|alternative|substitute for|substitute|badeel le|badeel)\b",
        r"\b(الفرق بين|قارن بين|قارن|مقارنة|difference between|compare|versus|vs|2aren ben|2aren)\b",
        r"\b(ينفع مع|يمشي مع|goes well with|eh yenfa3 ma3|this|that|ده|دي|دا|da|di)\b",
        r"\b(اقترح عليا|اقترح|اقتراح|رشح|ترشحهولي|ترشحهالي|ترشحلي|ترشح|recommend|suggest|what do you recommend for|what do you recommend|ideas for|e2tra7 3alaya|e2tra7|ايه احسن)\b",
        r"\b(افضل|أفضل|احسن|أحسن|اجود|أجود|نوع|انواع|أنواع|صنف|اصناف|أصناف|best|top|types?|kinds?)\b",
        r"\b(للاعلى|للأعلى|للاقل|للأقل|للارخص|للأرخص|للاغلى|للأغلى|الاعلى|الأعلى|الاقل|الأقل|الاغلى|الأغلى|الارخص|الأرخص|سعرا|سعر|من|الى|الي|لـ)\b",
    ]
    for filler in fillers:
        cleaned = re.sub(filler, " ", cleaned, flags=re.IGNORECASE)

    # Remove unsupported tags
    for _, tag in UNSUPPORTED_FILTER_PATTERNS:
        cleaned = re.sub(rf"\b{re.escape(tag)}\b", " ", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned if len(cleaned) >= 2 else None
    return cleaned if len(cleaned) >= 2 else None


def _rule_based_parse(raw_text: str, normalized: str) -> dict[str, Any]:
    """
    Deterministic rule engine that provides baseline parsing.
    High accuracy for prices, stock, brand cancellation, sorting, and specific intents.
    """
    explicit_fields: list[str] = []
    unsupported_filters = _extract_unsupported_filters(normalized)
    follow_up_type = "new_topic"
    intent = "search"
    brand: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    in_stock: Optional[bool] = None
    sort: Optional[str] = None

    # 1. Check Brand Cancellation
    is_cancellation = bool(BRAND_CANCELLATION_RE.search(normalized))
    if is_cancellation:
        brand = None
        follow_up_type = "cancellation"
        explicit_fields.append("brand")
    else:
        # Check explicit brand
        detected_brand = find_known_brand(raw_text) or find_known_brand(normalized)
        if detected_brand:
            brand = normalize_brand(detected_brand)
            explicit_fields.append("brand")

    # 2. Check Price ranges
    p_between = PRICE_BETWEEN_RE.search(normalized)
    if p_between:
        price_min = float(p_between.group(1))
        price_max = float(p_between.group(2))
        explicit_fields.extend(["price_min", "price_max"])
    else:
        p_max = PRICE_MAX_RE.search(normalized)
        if p_max:
            price_max = float(p_max.group(1))
            explicit_fields.append("price_max")

        p_min = PRICE_MIN_RE.search(normalized)
        if p_min:
            price_min = float(p_min.group(1))
            explicit_fields.append("price_min")

    # 3. Check Stock
    if STOCK_IN_RE.search(normalized):
        in_stock = True
        explicit_fields.append("in_stock")
    elif STOCK_OUT_RE.search(normalized):
        in_stock = False
        explicit_fields.append("in_stock")

    # 4. Check Sort (Desc first, then Asc)
    if SORT_DESC_RE.search(normalized):
        sort = "price_desc"
        explicit_fields.append("sort")
    elif SORT_ASC_RE.search(normalized):
        sort = "price_asc"
        explicit_fields.append("sort")

    # 5. Check References
    if REFERENCE_RE.search(normalized):
        follow_up_type = "reference"

    # Query extraction
    query = _clean_query_string(raw_text, brand, unsupported_filters)

    # Healthy / Diet intent detection
    healthy_kw_match = bool(
        re.search(
            r"\b(و?صح[يية][هة]?|و?قليل[هة]\w*|و?قليله\w*|و?منخفض[هة]\w*|و?سعرات\w*|دايت|رجيم|كيتو|رشاق[هة]|healthy|low[- ]?cal(?:orie)?|diet)\b",
            normalized,
            re.IGNORECASE,
        )
    )
    meal_request_match = bool(
        re.search(
            r"\b(و?وجب[هة]\w*|و?غداء|و?غذاء|و?عشاء|و?فطار|و?افطار|و?سناك\w*|و?اكل\w*|lunch|dinner|breakfast|snack|meal|food)\b",
            normalized,
            re.IGNORECASE,
        )
    )

    # 6. Intent Classification Rules
    if OUT_OF_SCOPE_RE.search(normalized):
        intent = "out-of-scope"
        follow_up_type = "new_topic"
        query = None
        brand = None
        explicit_fields = []
        price_min = price_max = in_stock = sort = None
        unsupported_filters = []
    elif ALTERNATIVES_RE.search(normalized):
        intent = "alternatives"
        follow_up_type = "new_topic"
        brand = None
    elif COMPARE_RE.search(normalized):
        intent = "compare"
        follow_up_type = "new_topic"
        brand = None
        if query in {"juhayna", "almarai", "domty", "president", "جهينة", "المراعي", "دومتي", "بريزيدون", "و", "and", "w"}:
            query = None
    elif CROSS_SELL_RE.search(normalized):
        intent = "cross-sell"
        follow_up_type = "reference"
        brand = None
    elif RECOMMEND_RE.search(normalized) or (healthy_kw_match and meal_request_match):
        intent = "recommend"
        follow_up_type = "new_topic"
        brand = None
        if healthy_kw_match and "diet" not in unsupported_filters:
            unsupported_filters.append("diet")
    elif sort is not None:
        intent = "sort"
        follow_up_type = "refinement" if not query else "new_topic"
    elif is_cancellation or ((price_max is not None or price_min is not None or in_stock is not None or brand is not None) and not query):
        intent = "refine"
        if not is_cancellation:
            follow_up_type = "refinement"
        query = None
    else:
        intent = "search"
        follow_up_type = "new_topic"

    # Reconstruct explicit fields accurately
    explicit = set()
    if brand:
        explicit.add("brand")
    elif is_cancellation:
        explicit.add("brand")

    if price_max is not None:
        explicit.add("price_max")
    if price_min is not None:
        explicit.add("price_min")
    if in_stock is not None:
        explicit.add("in_stock")
    if sort is not None:
        explicit.add("sort")
    if query:
        explicit.add("query")

    return {
        "intent": intent,
        "follow_up_type": follow_up_type,
        "query": query,
        "brand": brand,
        "category": None,
        "price_min": price_min,
        "price_max": price_max,
        "in_stock": in_stock,
        "sort": sort,
        "explicit_fields": sorted(list(explicit)),
        "unsupported_filters": unsupported_filters,
    }


# ─────────────────────────────────────────────────────────────────────────────
# LLM Integration & Compact System Prompt (< 150 tokens)
# ─────────────────────────────────────────────────────────────────────────────

AGENTIC_SYSTEM_PROMPT = (
    "You are Spinneys Smart Grocery Shopping Assistant. You help customers find products, "
    "suggest recipe ingredients, answer nutritional and comparative questions, and sort items. "
    "You MUST strictly ground your answers in the available store data and never invent products, brands, or prices.\n\n"
    "Analyze the customer's message, conversation history, and currently visible store items.\n"
    "Respond strictly in JSON matching this schema:\n"
    "{\n"
    '  "action": "search" | "recipe" | "advisory_qa" | "count_inquiry" | "sort" | "out_of_scope",\n'
    '  "intent": "search" | "recipe" | "advisory" | "count_inquiry" | "sort" | "out_of_scope",\n'
    '  "clean_query": string | null,\n'
    '  "head_term": string | null,\n'
    '  "qualifiers": [string],\n'
    '  "target_category": string | null,\n'
    '  "primary_ingredient": string | null,\n'
    '  "recipe_advice": string | null,\n'
    '  "conversational_reply": string | null,\n'
    '  "sort_by": "relevance" | "price_asc" | "price_desc",\n'
    '  "limit": int,\n'
    '  "attribute_focus": string | null,\n'
    '  "category": string | null,\n'
    '  "brand": string | null,\n'
    '  "price_max": float | null,\n'
    '  "price_min": float | null,\n'
    '  "is_followup": boolean,\n'
    '  "is_count_query": boolean\n'
    "}\n\n"
    "Strict Decision Rules:\n"
    "0. UNIVERSAL HEAD-ENTITY & QUALIFIER EXTRACTION (MANDATORY FOR SEARCH & RECIPES):\n"
    "   - head_term: The primary single product noun (e.g., 'زيت' for 'زيت طعام', 'ملح' for 'ملح طعام', 'حليب' for 'حليب جهينة', 'شاي' for 'شاي أخضر', 'مناديل' for 'مناديل مائدة', 'جبنة' for 'جبنة بيضاء').\n"
    "   - qualifiers: List of attributes or secondary modifier nouns (e.g., ['طعام'], ['أخضر'], ['بيضاء'], ['مائدة']).\n"
    "   - target_category: Store department ('Grocery', 'Dairy', 'Beverages', 'Households', 'Beauty & Personal Care', 'Meat & Poultry', 'Sweets & Snacks').\n\n"
    "1. RECIPE & COOKING INQUIRIES (e.g. 'وصفه للحمه', 'مكونات بيتزا', 'عايز اطبخ ملوخية', 'طريقة عمل كباب حلة'):\n"
    "   - action: 'recipe'\n"
    "   - intent: 'recipe'\n"
    "   - recipe_advice: Briefly outline the core recipe, cooking steps, and essential ingredients in clear, appealing Arabic.\n"
    "   - primary_ingredient: Concrete grocery entity in store catalog to retrieve product cards (e.g. for 'وصفه للحمه' -> 'لحم', for 'مكونات بيتزا' -> 'دقيق' or 'جبنة موتزاريلا').\n"
    "   - clean_query: Same as primary_ingredient.\n"
    "   - head_term: Primary ingredient noun.\n"
    "   - limit: 5.\n\n"
    "2. CONVERSATIONAL & NUTRITIONAL Q&A (e.g. 'ايهم اعلى بروتين؟', 'ايه الفرق بينهم؟', 'انهي ارخص؟', 'مين احسن؟'):\n"
    "   - When customer asks about previously displayed visible items (visible_products):\n"
    "   - action: 'advisory_qa'\n"
    "   - intent: 'advisory'\n"
    "   - clean_query: null\n"
    "   - head_term: null\n"
    "   - conversational_reply: Write an intelligent, concise comparative answer in Arabic directly analyzing the visible items. Never invent non-existent products.\n\n"
    "3. CATALOG SEARCH & REFINEMENTS (e.g. 'افضل 5 انواع فول', 'لبن جهينة', 'جبنة فيتا', 'افضل 3 منتجات من حيث نسبه البروتين'):\n"
    "   - action: 'search'\n"
    "   - intent: 'search'\n"
    "   - clean_query: Clean searchable grocery entity. Strip numbers ('5', '3'), superlatives ('افضل', 'اجود', 'ارخص'), and fillers ('انواع', 'منتجات').\n"
    "   - head_term: Primary product noun.\n"
    "   - qualifiers: Secondary attributes.\n"
    "   - For protein queries ('بروتين'): clean_query='تونة صدور دجاج', head_term='تونة', attribute_focus='protein', limit=3.\n"
    "   - limit: Extracted number (e.g. 5, 3), default: 10.\n"
    "   - sort_by: 'price_asc' if cheapest requested ('ارخص', 'مرتبين حسب السعر'), 'price_desc' if most expensive ('اغلى'), else 'relevance'.\n\n"
    "4. STANDALONE SORT (e.g. 'رتبهم من الارخص', 'رتب الاسعار تنازلي'):\n"
    "   - action: 'sort'\n"
    "   - intent: 'sort'\n"
    "   - clean_query: null\n"
    "   - head_term: null\n"
    "   - sort_by: 'price_asc' | 'price_desc'\n"
    "   - is_followup: true\n\n"
    "5. COUNT & AGGREGATION INQUIRIES (e.g. 'كم نوع فول موجود', 'كم عدد انواع اللبن', 'how many types of...'):\n"
    "   - action: 'count_inquiry'\n"
    "   - intent: 'count_inquiry'\n"
    "   - clean_query: Target product entity only (e.g. 'فول', 'لبن', 'زيت'). Strip question phrases ('كم نوع', 'كم عدد', 'موجود', 'أنواع').\n"
    "   - head_term: Primary product entity.\n"
    "   - is_count_query: true\n\n"
    "6. OUT OF SCOPE (weather, politics, sports, coding):\n"
    "   - action: 'out_of_scope'\n"
    "   - intent: 'out_of_scope'\n"
    "   - conversational_reply: Polite Arabic refusal explaining Spinneys scope."
)

COMPACT_SYSTEM_PROMPT = AGENTIC_SYSTEM_PROMPT  # backwards compatibility

COUNT_INQUIRY_RE = re.compile(
    r"\b(كم\s*نوع|كم\s*عدد|كم\s*صنف|عدد\s*انواع|عدد\s*الاصناف|عندكم\s*كم\s*نوع|في\s*كم\s*نوع|how many types|how many kinds|how many varieties|count of)\b",
    re.IGNORECASE,
)


def _fast_fallback_parse(raw_text: str, normalized: str) -> dict[str, Any]:
    """
    Deterministic fallback parser used if Groq LLM is unavailable or fails.
    Extracts strictly: intent, clean_query, semantic_expansion, limit, sort_by, attribute_focus,
    category, price_max, price_min, is_followup, advisory_topic.
    """
    if OUT_OF_SCOPE_RE.search(normalized):
        return {
            "action": "out_of_scope",
            "intent": "out_of_scope",
            "clean_query": None,
            "head_term": None,
            "qualifiers": [],
            "target_category": None,
            "primary_ingredient": None,
            "recipe_advice": None,
            "conversational_reply": "أنا مساعد سبينيس الذكي للتسوق، أقدر أساعدك في البحث عن المنتجات والأسعار والوصفات في السوبرماركت.",
            "semantic_expansion": None,
            "limit": 10,
            "sort_by": "relevance",
            "attribute_focus": None,
            "category": None,
            "price_max": None,
            "price_min": None,
            "is_followup": False,
            "is_count_query": False,
            "advisory_topic": None,
        }

    # Count / Aggregation inquiry check
    if COUNT_INQUIRY_RE.search(normalized):
        cleaned_entity = COUNT_INQUIRY_RE.sub(" ", normalized)
        cleaned_entity = re.sub(r"\b(موجود|متوفر|عندكم|في المتجر|في الفرع|أنواع|انواع|اصناف|أصناف|available|in store)\b", " ", cleaned_entity, flags=re.IGNORECASE)
        cleaned_entity = sanitize_query(cleaned_entity)
        if not cleaned_entity:
            cleaned_entity = "فول" if "فول" in normalized else "منتجات"
        ht, qs, tc = extract_head_term_and_qualifiers(cleaned_entity)
        return {
            "action": "count_inquiry",
            "intent": "count_inquiry",
            "clean_query": cleaned_entity,
            "head_term": ht,
            "qualifiers": qs,
            "target_category": tc,
            "primary_ingredient": None,
            "recipe_advice": None,
            "conversational_reply": None,
            "semantic_expansion": None,
            "limit": 10,
            "sort_by": "relevance",
            "attribute_focus": None,
            "category": tc,
            "price_max": None,
            "price_min": None,
            "is_followup": False,
            "is_count_query": True,
            "advisory_topic": None,
        }

    # Recipe check
    recipe_m = re.search(r"\b(وصف[هة]|طريقة عمل|طريقة تحضير|مكونات|مقادير|طبخ|اطبخ|recipe|cook)\s*(?:لـ?|لل)?\s*(.*)", normalized, re.IGNORECASE)
    if recipe_m and any(w in normalized for w in ["لحم", "فراخ", "دجاج", "كيك", "بيتزا", "مكرون", "كباب", "سمك"]):
        dish_raw = recipe_m.group(2).strip() or "لحم"
        dish_raw = re.sub(r"\b(من فضلك|لو سمحت|عايز|عاوز|please)\b", "", dish_raw, flags=re.IGNORECASE).strip()
        clean_dish = "لحم" if any(w in dish_raw for w in ["لحم", "لحمه", "لحمة"]) else (dish_raw or "لحم")
        rec_cat = "Meat & Poultry" if any(w in clean_dish for w in ["لحم", "فراخ", "دجاج", "كباب", "سمك"]) else "Grocery"
        return {
            "action": "recipe",
            "intent": "recipe",
            "clean_query": clean_dish,
            "head_term": clean_dish,
            "qualifiers": [],
            "target_category": rec_cat,
            "primary_ingredient": clean_dish,
            "recipe_advice": f"إليك مقادير وطريقة تحضير أشهى {clean_dish} من منتجات سبينيس المتوفرة:",
            "conversational_reply": None,
            "semantic_expansion": None,
            "limit": 5,
            "sort_by": "relevance",
            "attribute_focus": None,
            "category": rec_cat,
            "price_max": None,
            "price_min": None,
            "is_followup": False,
            "advisory_topic": None,
        }

    # 0. Advisory check - ONLY when no explicit product entity is being queried
    has_prod = bool(PRODUCT_ENTITY_RE.search(normalized))
    if ADVISORY_RE.search(normalized) and not has_prod:
        advisory_topic = "quality"
        if re.search(r"غذائ|سعرات|صحي|دايت|سكر|بروتين|calor|nutrit|protein", normalized, re.IGNORECASE):
            advisory_topic = "nutrition"
        elif re.search(r"فرق|مقارن|compare|diff", normalized, re.IGNORECASE):
            advisory_topic = "comparison"
        elif re.search(r"سعر|ارخص|اغلى|value|price", normalized, re.IGNORECASE):
            advisory_topic = "price_value"
        return {
            "action": "advisory_qa",
            "intent": "advisory",
            "clean_query": None,
            "head_term": None,
            "qualifiers": [],
            "target_category": None,
            "primary_ingredient": None,
            "recipe_advice": None,
            "conversational_reply": None,
            "semantic_expansion": None,
            "limit": 10,
            "sort_by": "relevance",
            "attribute_focus": None,
            "category": None,
            "price_max": None,
            "price_min": None,
            "is_followup": True,
            "advisory_topic": advisory_topic,
        }

    limit = extract_limit(raw_text) or 10
    sort_by = "relevance"
    if SORT_DESC_RE.search(normalized):
        sort_by = "price_desc"
    elif SORT_ASC_RE.search(normalized):
        sort_by = "price_asc"

    attribute_focus = None
    category = None
    mapped_query = None

    if re.search(r"\b(بروتين|البروتين|protein)\b", normalized, re.IGNORECASE):
        attribute_focus = "protein"
        mapped_query = "تونة صدور دجاج"
        category = "meat,poultry,seafood,canned food"
        if not extract_limit(raw_text):
            limit = 3
    elif re.search(r"\b(سعرات|قليلة السعرات|قليل السعرات|منخفض السعرات|دايت|رجيم|low cal|low fat)\b", normalized, re.IGNORECASE):
        attribute_focus = "low_fat"
        mapped_query = "شوفان زبادي لايت سكر دايت تونة دايت"
    elif re.search(r"\b(دهون صحية|دهون مفيدة|healthy fats)\b", normalized, re.IGNORECASE):
        attribute_focus = "healthy_fats"
        mapped_query = "زيت زيتون مكسرات سلمون"
    elif re.search(r"\b(الياف|ألياف|fiber)\b", normalized, re.IGNORECASE):
        attribute_focus = "fiber"
        mapped_query = "شوفان فاصوليا عدس تفاح خضار"
    elif re.search(r"\b(خالي من السكر|بدون سكر|sugar free)\b", normalized, re.IGNORECASE):
        attribute_focus = "sugar_free"
        mapped_query = "ستيفيا شاي بسكويت خالي من السكر"
    elif re.search(r"\b(طاقة|energy)\b", normalized, re.IGNORECASE):
        attribute_focus = "energy"
        mapped_query = "تمر مكسرات عسل موز شوفان"
    elif re.search(r"\b(ارخص|أرخص|الارخص|الأرخص|cheap)\b", normalized, re.IGNORECASE):
        attribute_focus = "cheap"
        sort_by = "price_asc"

    # Price boundaries
    price_min = None
    price_max = None
    p_between = PRICE_BETWEEN_RE.search(normalized)
    if p_between:
        price_min = float(p_between.group(1))
        price_max = float(p_between.group(2))
    else:
        p_max = PRICE_MAX_RE.search(normalized)
        if p_max:
            price_max = float(p_max.group(1))
        p_min = PRICE_MIN_RE.search(normalized)
        if p_min:
            price_min = float(p_min.group(1))

    # In-stock
    in_stock = None
    if STOCK_IN_RE.search(normalized):
        in_stock = True
    elif STOCK_OUT_RE.search(normalized):
        in_stock = False

    # Brand
    detected_brand = find_known_brand(raw_text) or find_known_brand(normalized)
    brand = normalize_brand(detected_brand) if detected_brand else None

    # Clean product query extraction
    cleaned = sanitize_query(raw_text)
    cleaned = SORT_DESC_RE.sub(" ", cleaned)
    cleaned = SORT_ASC_RE.sub(" ", cleaned)
    cleaned = PRICE_BETWEEN_RE.sub(" ", cleaned)
    cleaned = PRICE_MAX_RE.sub(" ", cleaned)
    cleaned = PRICE_MIN_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\b(جنيه|egp|le|pounds?|pound|gneh|ج)\b", " ", cleaned, flags=re.IGNORECASE)

    # Strip conversational filler words and constraint modifier words
    fillers = [
        r"\b(مع\s*ترتيب\s*الاسعار|ترتيب\s*الاسعار|ترتيب\s*بالسعر|رتب\s*الاسعار|رتبهم\s*بالسعر|رتب\s*بالسعر|رتبهم|رتبهن|رتبها|رتب|بالسعر|sort by price|sort by|مع\s*الترتيب)\b",
        r"\b(عايز|عاوز|محتاج|ابحث عن|ابحث|دورلي على|دورلي|هاتلي|هات|اعرضلي|وريني|فين|من فضلك|لو سمحت|بس|فقط)\b",
        r"\b(show me|find me|i want|i need|looking for|search for|give me|please|only|just|where is the|where is|show)\b",
        r"\b(3ayez|hatly|warini|please|feen el|feen|first)\b",
        r"\b(مارك[هة]|براند|brand|items?|منتجات?|في الفرع|in store|store|branch|price|سعر|اي|مش فارق|معايا|remove|filter|fine|is fine|all|any|bas|el|rateb)\b",
        r"\b(بديل لـ?|بديل ل|بديل|alternative for|alternative|substitute for|substitute|badeel le|badeel)\b",
        r"\b(الفرق بين|قارن بين|قارن|مقارنة|difference between|compare|versus|vs|2aren ben|2aren)\b",
        r"\b(ينفع مع|يمشي مع|goes well with|eh yenfa3 ma3|this|that|ده|دي|دا|da|di)\b",
        r"\b(اقترح عليا|اقترح|اقتراح|رشح|ترشحهولي|ترشحهالي|ترشحلي|ترشح|recommend|suggest|what do you recommend for|what do you recommend|ideas for|e2tra7 3alaya|e2tra7|ايه احسن)\b",
        r"\b(افضل|أفضل|احسن|أحسن|اجود|أجود|نوع|انواع|أنواع|صنف|اصناف|أصناف|best|top|types?|kinds?)\b",
        r"\b(للاعلى|للأعلى|للاقل|للأقل|للارخص|للأرخص|للاغلى|للأغلى|الاعلى|الأعلى|الاقل|الأقل|الاغلى|الأغلى|الارخص|الأرخص|سعرا|سعر|من|الى|الي|لـ)\b",
    ]
    for filler in fillers:
        cleaned = re.sub(filler, " ", cleaned, flags=re.IGNORECASE)

    if mapped_query:
        clean_query = mapped_query
    else:
        if brand and cleaned:
            cleaned = strip_brand_from_query(cleaned, brand) or ""
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        clean_query = cleaned if len(cleaned) >= 2 else None

    # Category heuristic if not already set
    if not category:
        if re.search(r"\b(لبن|حليب|زبادي|زبادو|جبن|جبنة|قشطة|milk|yogurt|dairy|cheese|laban)\b", normalized, re.IGNORECASE):
            category = "dairy"
        elif re.search(r"\b(شاي|قهوة|عصير|مشروب|بيبسي|كولا|tea|coffee|juice|soda)\b", normalized, re.IGNORECASE):
            category = "beverages"

    # Follow-up and intent detection
    is_followup = bool(REFERENCE_RE.search(normalized)) or (clean_query is None and (sort_by != "relevance" or price_max is not None or price_min is not None))

    if clean_query is None and sort_by != "relevance":
        intent = "sort"
    elif clean_query is None and (price_max is not None or price_min is not None):
        intent = "filter"
    elif clean_query is not None:
        intent = "search"
    else:
        intent = "search"

    explicit_fields = []
    if brand:
        explicit_fields.append("brand")
    if price_max is not None:
        explicit_fields.append("price_max")
    if price_min is not None:
        explicit_fields.append("price_min")
    if limit is not None:
        explicit_fields.append("limit")
    if in_stock is not None:
        explicit_fields.append("in_stock")
    if sort_by != "relevance":
        explicit_fields.append("sort")
    if clean_query:
        explicit_fields.append("query")

    # Universal head_term, qualifiers, target_category extraction
    head_term, qualifiers, inferred_cat = extract_head_term_and_qualifiers(clean_query)
    if not category:
        category = inferred_cat
    target_category = inferred_cat or category

    return {
        "intent": intent,
        "clean_query": clean_query,
        "head_term": head_term,
        "qualifiers": qualifiers,
        "target_category": target_category,
        "semantic_expansion": None,
        "limit": limit,
        "sort_by": sort_by,
        "attribute_focus": attribute_focus,
        "category": category,
        "price_max": price_max,
        "price_min": price_min,
        "is_followup": is_followup,
        "brand": brand,
        "in_stock": in_stock,
        "explicit_fields": explicit_fields,
        "unsupported_filters": _extract_unsupported_filters(normalized),
    }


def parse_query(
    raw_text: str,
    session_context: Optional[dict[str, Any]] = None,
    visible_products: Optional[list[dict[str, Any]]] = None,
    conversation_history: Optional[list[dict[str, str]]] = None,
) -> NLUResult:
    """
    Main Agentic Controller & NLU entry point using Groq (llama-3.1-8b-instant / llama-3.3-70b-versatile)
    with seamless deterministic fallback.
    """
    t0 = time.perf_counter()
    normalized = normalize_text(raw_text)
    llm = get_llm_client()

    if llm.is_available:
        try:
            user_prompt_parts = []
            if visible_products:
                items_summary = []
                for idx, p in enumerate(visible_products[:6], 1):
                    name = p.get("name_ar") or p.get("name_en") or p.get("product_name", "")
                    price = p.get("price") or p.get("effective_price", 0.0)
                    brand = p.get("brand", "")
                    items_summary.append(f"{idx}. {name} (Brand: {brand}, Price: {price} EGP)")
                user_prompt_parts.append("Currently visible store items:\n" + "\n".join(items_summary))

            if conversation_history:
                recent_history = conversation_history[-4:]
                history_lines = [f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in recent_history]
                user_prompt_parts.append("Conversation history:\n" + "\n".join(history_lines))

            user_prompt_parts.append(f"Customer query: '{raw_text}'")
            full_user_prompt = "\n\n".join(user_prompt_parts)

            resp = llm.complete_json(
                system_prompt=AGENTIC_SYSTEM_PROMPT,
                user_prompt=full_user_prompt,
                temperature=0.0,
            )
            content = resp.content
            if isinstance(content, dict):
                # Normalize action & intent
                raw_action = str(content.get("action", "search")).lower().replace("-", "_")
                if raw_action not in ("search", "recipe", "advisory_qa", "count_inquiry", "sort", "out_of_scope"):
                    raw_action = "search"
                content["action"] = raw_action

                raw_intent = str(content.get("intent", raw_action)).lower().replace("-", "_")
                if raw_intent not in ("search", "recipe", "advisory", "count_inquiry", "sort", "out_of_scope"):
                    if raw_action == "recipe":
                        raw_intent = "recipe"
                    elif raw_action == "advisory_qa":
                        raw_intent = "advisory"
                    elif raw_action == "count_inquiry":
                        raw_intent = "count_inquiry"
                    else:
                        raw_intent = raw_action
                content["intent"] = raw_intent

                # Normalize sort_by
                s_by = str(content.get("sort_by", "relevance")).lower()
                if s_by not in ("price_asc", "price_desc", "relevance"):
                    if "asc" in s_by or "low" in s_by or "arkhas" in s_by:
                        content["sort_by"] = "price_asc"
                    elif "desc" in s_by or "high" in s_by or "aghla" in s_by:
                        content["sort_by"] = "price_desc"
                    else:
                        content["sort_by"] = "relevance"

                # 1. Action: RECIPE
                if content["action"] == "recipe":
                    content["intent"] = "recipe"
                    clean_ing = content.get("primary_ingredient") or content.get("clean_query")
                    if not clean_ing or len(clean_ing.strip()) < 2:
                        clean_ing = "لحم" if any(w in normalized for w in ["لحم", "لحمة", "لحمه", "كباب"]) else "دقيق"
                    content["clean_query"] = clean_ing
                    content["primary_ingredient"] = clean_ing
                    content["limit"] = content.get("limit") or 5
                    content["is_followup"] = False

                # 2. Action: ADVISORY_QA
                elif content["action"] == "advisory_qa":
                    content["intent"] = "advisory"
                    content["clean_query"] = None
                    content["primary_ingredient"] = None
                    content["is_followup"] = True
                    content["advisory_topic"] = "comparison"

                # 3. Action: COUNT_INQUIRY
                elif content["action"] == "count_inquiry" or content.get("is_count_query") or (COUNT_INQUIRY_RE.search(normalized) and content["action"] not in ("recipe", "advisory_qa")):
                    content["action"] = "count_inquiry"
                    content["intent"] = "count_inquiry"
                    content["is_count_query"] = True
                    cq = content.get("clean_query")
                    if not cq or any(w in cq for w in ["كم", "نوع", "عدد", "موجود"]):
                        cleaned_cq = COUNT_INQUIRY_RE.sub(" ", normalized)
                        cleaned_cq = re.sub(r"\b(موجود|متوفر|عندكم|في المتجر|في الفرع|أنواع|انواع|اصناف|أصناف|available|in store)\b", " ", cleaned_cq, flags=re.IGNORECASE)
                        cleaned_cq = sanitize_query(cleaned_cq)
                        content["clean_query"] = cleaned_cq or ("فول" if "فول" in normalized else "منتجات")
                    content["primary_ingredient"] = None
                    content["is_followup"] = False

                # 3. Action: STANDALONE SORT
                elif content["action"] == "sort":
                    content["intent"] = "sort"
                    content["clean_query"] = None
                    content["primary_ingredient"] = None
                    content["is_followup"] = True

                # 4. Action: OUT_OF_SCOPE
                elif content["action"] == "out_of_scope":
                    content["intent"] = "out_of_scope"
                    content["clean_query"] = None
                    content["primary_ingredient"] = None

                # 5. Action: SEARCH
                else:
                    content["action"] = "search"
                    content["intent"] = "search"

                    # Check if protein or health attribute
                    if not content.get("attribute_focus"):
                        if re.search(r"\b(بروتين|البروتين|protein)\b", normalized, re.IGNORECASE):
                            content["attribute_focus"] = "protein"
                        elif re.search(r"\b(سعرات|قليلة السعرات|قليل السعرات|منخفض السعرات|دايت|رجيم|low cal|low fat)\b", normalized, re.IGNORECASE):
                            content["attribute_focus"] = "low_fat"

                    af = content.get("attribute_focus")
                    if af == "protein":
                        content["clean_query"] = "تونة صدور دجاج"
                        content["category"] = "meat,poultry,seafood,canned food"
                        if not extract_limit(raw_text):
                            content["limit"] = 3
                        content["is_followup"] = False

                    # Clean query sanity check
                    cq = content.get("clean_query")
                    if cq:
                        cq_cleaned = sanitize_query(cq)
                        content["clean_query"] = cq_cleaned if len(cq_cleaned) >= 2 else None
                        if content["clean_query"] is None and content["sort_by"] != "relevance":
                            content["action"] = "sort"
                            content["intent"] = "sort"
                            content["is_followup"] = True

                    # Deterministic limit check
                    det_limit = extract_limit(raw_text)
                    if det_limit is not None and (content.get("limit") is None or content.get("limit") == 10):
                        content["limit"] = det_limit
                    elif content.get("limit") is None:
                        content["limit"] = 10

                content["raw_text"] = raw_text
                content["normalized_text"] = normalized
                content["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
                if resp.usage:
                    content["token_usage"] = {
                        "prompt_tokens": resp.usage.prompt_tokens,
                        "completion_tokens": resp.usage.completion_tokens,
                        "total_tokens": resp.usage.total_tokens,
                    }

                # Canonicalize brand and strip from clean_query to prevent brand collision
                extracted_brand = content.get("brand") or find_known_brand(raw_text) or find_known_brand(content.get("clean_query") or "")
                if extracted_brand:
                    canonical_brand = normalize_brand(extracted_brand)
                    content["brand"] = canonical_brand
                    if content.get("clean_query"):
                        stripped_cq = strip_brand_from_query(content["clean_query"], canonical_brand)
                        content["clean_query"] = stripped_cq if stripped_cq and len(stripped_cq) >= 2 else None

                # Normalize and ensure head_term, qualifiers, target_category
                cq = content.get("clean_query")
                ht = content.get("head_term")
                qs = content.get("qualifiers")
                tc = content.get("target_category") or content.get("category")

                if cq:
                    auto_ht, auto_qs, auto_tc = extract_head_term_and_qualifiers(cq)
                    if not ht:
                        ht = auto_ht
                    if not qs:
                        qs = auto_qs
                    if not tc:
                        tc = auto_tc
                if ht and content.get("brand"):
                    stripped_ht = strip_brand_from_query(ht, content["brand"])
                    if stripped_ht:
                        ht = stripped_ht

                content["head_term"] = ht
                content["qualifiers"] = qs if isinstance(qs, list) else ([str(qs)] if qs else [])
                content["target_category"] = tc
                if not content.get("category"):
                    content["category"] = tc

                explicit_fields = []
                if content.get("brand"):
                    explicit_fields.append("brand")
                if content.get("price_max") is not None:
                    explicit_fields.append("price_max")
                if content.get("price_min") is not None:
                    explicit_fields.append("price_min")
                if content.get("limit") is not None:
                    explicit_fields.append("limit")
                if content.get("in_stock") is not None:
                    explicit_fields.append("in_stock")
                if content.get("sort_by") != "relevance":
                    explicit_fields.append("sort")
                if content.get("clean_query"):
                    explicit_fields.append("query")
                content["explicit_fields"] = explicit_fields

                return NLUResult.model_validate(content)
        except Exception as exc:
            log.warning("Groq structured NLU parsing failed (%s). Using fallback parser.", exc)

    # Fast deterministic fallback parser
    fallback = _fast_fallback_parse(raw_text=raw_text, normalized=normalized)
    fallback["raw_text"] = raw_text
    fallback["normalized_text"] = normalized
    fallback["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
    return NLUResult.model_validate(fallback)
