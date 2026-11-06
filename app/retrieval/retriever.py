# -*- coding: utf-8 -*-
"""
app/retrieval/retriever.py
=========================
Fast-Path Rule Filtering & LLM Arbitration Retriever for Spinneys.

Key Capabilities:
  1. Ultra-low Latency Fast-Path (< 40 ms):
     - Uses in-memory metadata DataFrame with pre-indexed vectorized masks.
     - Deterministic rule extraction (brand, category, price_min, price_max, in_stock, sort).
     - Hybrid BM25/Vector ranking with in-stock candidate boosting.
  2. LLM Arbitration Layer:
     - Triggered ONLY on:
       * Negation / Exclusion ("شاي بس مش ليبتون", "بدون سكر").
       * Complex / tangled queries (> 4 tokens with multiple constraints).
       * Advanced intents (compare, alternatives, recommend).
       * Ambiguity (competing brand tokens in same utterance).
     - Outputs strict JSON filters to never hallucinate or invent catalog products.
  3. Recipe / Smart Cart Routing:
     - Delegates dish queries ("عايز اعمل مكرونة بشاميل") to RecipeEngine.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.core.llm import get_llm_client
from app.core.normalizer import (
    BRAND_NORMALIZATION,
    TOP_KNOWN_BRANDS,
    find_known_brand,
    normalize_brand,
    normalize_text,
)
from app.nlu.parser import (
    extract_head_term_and_qualifiers,
    get_head_term_variants,
    parse_query as nlu_parse_query,
    sanitize_query,
    strip_brand_from_query,
)
from app.retrieval.hybrid_search import HybridSearchEngine
from app.retrieval.recipe_engine import RecipeEngine

log = logging.getLogger("spinneys.retriever")
ROOT = Path(__file__).resolve().parent.parent.parent

# Negation detection pattern
NEGATION_RE = re.compile(
    r"\b(مش|مش عايز|بدون|من غير|غير|بلاش|not|without|except|no|excluding)\s+([A-Za-z\u0621-\u064A0-9]+)",
    re.IGNORECASE,
)

# Permanent voucher and junk purge pattern
VOUCHER_JUNK_RE = re.compile(
    r"\b(?:voucher|gift\s*card|coupon|card)\b|قسيمة|خصم",
    re.IGNORECASE,
)

# Recipe intent pattern
RECIPE_RE = re.compile(
    r"\b(طريقة عمل|طريقة تحضير|عايز اعمل|عاوز اعمل|اعمل|مكونات|مقادير|طبخ|recipe for|how to make|make|cook)\b",
    re.IGNORECASE,
)

# Complex query connector pattern
COMPLEX_CONNECTOR_RE = re.compile(
    r"\b(ولكن|لكن|بس بشرط|معادا|ما عدا|instead of|but not)\b",
    re.IGNORECASE,
)

# Healthy / Diet intent patterns
HEALTHY_KW_RE = re.compile(
    r"\b(و?صح[يية][هة]?|و?قليل[هة]\w*|و?قليله\w*|و?منخفض[هة]\w*|و?سعرات\w*|دايت|رجيم|كيتو|رشاق[هة]|healthy|low[- ]?cal(?:orie)?|diet)\b",
    re.IGNORECASE,
)
MEAL_REQ_RE = re.compile(
    r"\b(و?وجب[هة]\w*|و?غداء|و?غذاء|و?عشاء|و?فطار|و?افطار|و?سناك\w*|و?اكل\w*|lunch|dinner|breakfast|snack|meal|food)\b",
    re.IGNORECASE,
)
SWEETENER_EXPLICIT_RE = re.compile(
    r"\b(سكر|محلي|مُحلّي|ستيفيا|شوجر ماتش|سويتنر|sweetener|stevia|sugar)\b",
    re.IGNORECASE,
)
SWEETENER_TERMS_RE = re.compile(
    r"محلي|مُحلّي|ستيفيا|شوجر ماتش|سويتنر|أقراص الستيفيا|سكر دايت|بدائل السكر|sweetener|stevia|sugar match|diet sugar",
    re.IGNORECASE,
)
DAIRY_TERMS_RE = re.compile(
    r"\b(لبن|حليب|زبادي|زبادو|جبن|جبنة|قشطة|milk|yogurt|dairy|cheese|laban)\b",
    re.IGNORECASE,
)
NON_FOOD_CATEGORIES = {
    "beauty & personal care",
    "households",
    "electronics",
    "stationery",
    "home & garden",
    "toys",
    "baby care",
    "appliances",
}

FOUL_LEGUME_STEMS = (
    "مدمس", "تدميس", "مجروش", "حب", "حصى", "صحيح", "بلدي", "مقشور", "طعمية", "بصارة",
    "fava", "foul", "beans", "ful", "medames", "medammes"
)

FOUL_NON_LEGUME_TERMS = (
    "سوداني", "سودانى", "peanut", "peanuts", "صويا", "soy", "soya",
    "اوتوماتيك", "automatic", "full hd", "اتش دي", "فل اتش دي", "فولا", "fulla",
    "تتبيلة", "تتبيله", "بهارات", "seasoning"
)

CHEESE_STEMS = (
    "جبن", "جبنة", "cheddar", "roumy", "feta", "mozzarella", "cheese",
    "شيدر", "رومي", "فيتا", "موتزاريلا", "موزاريلا", "كيري", "قريش",
    "براميلي", "اسطنبولي", "مثلثات", "ريكوتا", "حلوم", "بارميزان", "بارميجانو", "جودا", "فلمنك"
)

PROTEIN_STEMS = (
    "صدور دجاج", "دجاج", "تونة", "تونه", "بيض", "لحم", "لحوم", "رومي",
    "اسماك", "سمك", "فيليه", "chicken", "tuna", "turkey", "beef", "meat", "fish", "eggs"
)

PROCESSED_CHEESE_STEMS = (
    "مطبوخ", "مطبوخة", "كريمي", "سبريد", "مثلثات", "مربعات", "شيدر سبريد",
    "جبن خضار", "جبنة خضار", "spread", "creamy", "cream cheese", "processed",
    "triangles", "portions"
)

COOKING_OIL_STEMS = (
    "عباد", "ذرة", "ذره", "خليط", "طعام", "قلي", "طبخ", "زيتون", "صويا", "نباتي", "كانولا",
    "sunflower", "corn", "olive", "cooking", "frying", "vegetable", "canola"
)

COSMETIC_OIL_STEMS = (
    "شعر", "بشرة", "مساج", "حمام زيت", "كوبرا", "تدليك", "لحية", "سيروم",
    "hair", "body", "skin", "massage", "cosmetic", "serum", "بديل الزيت"
)

ANCHOR_NOUNS = (
    "زيت", "حليب", "لبن", "جبن", "جبنة", "فول", "شاي", "سكر", "ارز", "أرز",
    "مكرونة", "تونة", "صلصة", "دجاج", "لحم", "بيض", "عسل", "زبدة", "دقيق",
    "شوفان", "قهوة", "نسكافيه", "خل", "صابون", "مسحوق", "مناديل",
    "oil", "milk", "cheese", "tea", "rice", "pasta", "sugar", "tuna", "coffee",
    "butter", "honey", "flour", "eggs", "chicken", "meat"
)

# ─────────────────────────────────────────────────────────────────────────────
# Commodity Taxonomy & Prepositional Disqualification
# ─────────────────────────────────────────────────────────────────────────────

COMMODITY_PRIMARY_CATEGORIES: dict[str, tuple[str, ...]] = {
    "زيت": ("grocery", "cooking oil & ghee", "oil", "marina offers", "spinneys products", "suhoor ramadan", "top selling products", "online deals"),
    "زيوت": ("grocery", "cooking oil & ghee", "oil", "marina offers", "spinneys products", "suhoor ramadan", "top selling products", "online deals"),
    "حليب": ("cheese, dairy & eggs", "milk", "full cream milk", "speciality milk", "dairy", "beverages", "grocery", "top selling products", "suhoor ramadan", "online deals"),
    "لبن": ("cheese, dairy & eggs", "milk", "full cream milk", "speciality milk", "dairy", "beverages", "grocery", "top selling products", "suhoor ramadan", "online deals"),
    "شاي": ("beverages", "grocery", "tea", "hot beverages", "top selling products", "suhoor ramadan", "online deals"),
    "شاى": ("beverages", "grocery", "tea", "hot beverages", "top selling products", "suhoor ramadan", "online deals"),
    "شوكولاتة": ("sweets & snacks", "chocolate", "confectionery", "grocery", "top selling products", "online deals"),
    "شيكولاتة": ("sweets & snacks", "chocolate", "confectionery", "grocery", "top selling products", "online deals"),
    "فراولة": ("fresh fruits & vegetables", "produce", "frozen food", "grocery"),
}

COMMODITY_FORBIDDEN_CATEGORIES: dict[str, set[str]] = {
    "زيت": {
        "beauty & personal care", "hair care", "face & body skincare", "baby care",
        "electronics", "households", "cleaning products", "fashion & textiles",
        "sweets & snacks", "biscuits", "seafood & fish", "canned food",
    },
    "زيوت": {
        "beauty & personal care", "hair care", "face & body skincare", "baby care",
        "electronics", "households", "cleaning products", "fashion & textiles",
        "sweets & snacks", "biscuits", "seafood & fish", "canned food",
    },
    "حليب": {
        "sweets & snacks", "biscuits", "chocolate", "confectionery",
        "beauty & personal care", "hair care", "face & body skincare",
        "households", "baby care", "cleaning products",
    },
    "لبن": {
        "sweets & snacks", "biscuits", "chocolate", "confectionery",
        "beauty & personal care", "hair care", "face & body skincare",
        "households", "baby care", "cleaning products",
    },
    "شاي": {
        "beauty & personal care", "hair care", "face & body skincare",
        "households", "cleaning products", "fashion & textiles",
        "sweets & snacks", "biscuits",
    },
    "شاى": {
        "beauty & personal care", "hair care", "face & body skincare",
        "households", "cleaning products", "fashion & textiles",
        "sweets & snacks", "biscuits",
    },
    "شوكولاتة": {
        "cheese, dairy & eggs", "milk", "full cream milk", "dairy",
        "beauty & personal care", "households",
    },
    "شيكولاتة": {
        "cheese, dairy & eggs", "milk", "full cream milk", "dairy",
        "beauty & personal care", "households",
    },
    "فراولة": {
        "cheese, dairy & eggs", "milk", "dairy",
        "beauty & personal care", "households", "sweets & snacks",
    },
}

COMMODITY_FORBIDDEN_HEAD_NOUNS: dict[str, set[str]] = {
    "زيت": {
        "ماكريل", "تونة", "تونه", "سردين", "رنجة", "رنجه", "فسيخ", "بطارخ", "فول",
        "شامبو", "بلسم", "كريم", "لوشن", "سيروم", "غسول", "صابون", "شاور",
        "جل", "مقرمشات", "شيبس", "بسكويت", "معجون", "بيك رولز", "بريك", "فن داي",
        "دومتي سندوتش", "سندوتش", "جبنة بيضاء زيتون", "mackerel", "tuna", "sardine",
    },
    "زيوت": {
        "ماكريل", "تونة", "تونه", "سردين", "رنجة", "رنجه", "فسيخ", "بطارخ", "فول",
        "شامبو", "بلسم", "كريم", "لوشن", "سيروم", "غسول", "صابون", "شاور",
        "جل", "مقرمشات", "شيبس", "بسكويت", "معجون", "بيك رولز", "بريك", "فن داي",
        "دومتي سندوتش", "سندوتش", "mackerel", "tuna", "sardine",
    },
    "حليب": {
        "شوكولاتة", "شيكولاتة", "شيكولاته", "بسكويت", "بسكوت", "كيك", "ويفر",
        "سمن", "سمنة", "شامبو", "شاور", "جل", "لوشن", "كريم", "صابون", "معجون",
        "شوكولاته", "chocolate", "biscuit", "cake", "ghee", "wafer",
    },
    "لبن": {
        "شوكولاتة", "شيكولاتة", "شيكولاته", "بسكويت", "بسكوت", "كيك", "ويفر",
        "سمن", "سمنة", "شامبو", "شاور", "جل", "لوشن", "كريم", "صابون", "معجون",
        "شوكولاته", "chocolate", "biscuit", "cake", "ghee", "wafer",
    },
    "شاي": {
        "غسول", "ماسك", "قناع", "لصاقات", "كريم", "سيروم", "شامبو", "لبان", "علكة",
        "فوط", "مناديل", "مصفاة", "كوب", "مج", "wash", "mask", "patches", "cream", "gum",
    },
    "شاى": {
        "غسول", "ماسك", "قناع", "لصاقات", "كريم", "سيروم", "شامبو", "لبان", "علكة",
        "فوط", "مناديل", "مصفاة", "كوب", "مج", "wash", "mask", "patches", "cream", "gum",
    },
    "شوكولاتة": {
        "حليب", "لبن", "زبادي", "كيك", "بسكويت", "كورن فليكس", "ايس كوفي", "شامبو",
    },
    "شيكولاتة": {
        "حليب", "لبن", "زبادي", "كيك", "بسكويت", "كورن فليكس", "ايس كوفي", "شامبو",
    },
    "فراولة": {
        "زبادي", "لبن", "حليب", "عصير", "مشروب", "شوكولاتة", "بسكويت", "ويفر", "جيلي", "ايس كريم",
    },
}


def _get_stem_variants(w: str) -> set[str]:
    res = {w}
    if w.startswith("بال") and len(w) > 4:
        res.add(w[3:])
    elif w.startswith("ال") and len(w) > 3:
        res.add(w[2:])
    elif w.startswith("لل") and len(w) > 3:
        res.add(w[2:])
    elif w.startswith("ب") and len(w) > 2:
        res.add(w[1:])
    return res


def is_prepositional_modifier_only(name_ar: str, name_en: str, head_term: Optional[str]) -> bool:
    """
    Determines if the head_term appears ONLY in prepositional, preservative, or flavoring contexts
    (e.g., 'ماكريل في زيت', 'بسكويت بالحليب', 'كيك بالشوكولاتة', 'غسول بالشاي') without a standalone
    occurrence as the primary noun.
    """
    if not head_term:
        return False
    norm_ht = normalize_text(head_term).strip().lower()
    ht_clean = norm_ht[2:] if norm_ht.startswith("ال") and len(norm_ht) > 3 else norm_ht

    targets = {ht_clean, norm_ht}
    if ht_clean in ("حليب", "لبن"):
        targets |= {"حليب", "لبن", "الحليب", "اللبن", "milk"}
    elif ht_clean in ("زيت", "زيوت"):
        targets |= {"زيت", "الزيت", "زيوت", "الزيوت", "oil", "oils"}
    elif ht_clean in ("شاي", "شاى"):
        targets |= {"شاي", "شاى", "الشاي", "الشاى", "tea"}
    elif ht_clean in ("شوكولاتة", "شيكولاتة", "شيكولاته", "شوكولاته"):
        targets |= {"شوكولاتة", "شيكولاتة", "شيكولاته", "شوكولاته", "chocolate"}
    elif ht_clean in ("فراولة", "فراوله"):
        targets |= {"فراولة", "فراوله", "strawberry"}

    text_ar = normalize_text(name_ar or "").lower()
    text_en = str(name_en or "").lower()
    combined_raw = f"{text_ar} {text_en}"

    def has_target_occurrence(txt: str) -> bool:
        words = re.findall(r"\b[a-zA-Z0-9_\u0600-\u06FF]+\b", txt)
        for w in words:
            stems = _get_stem_variants(w)
            for s in stems:
                s_norm = normalize_text(s)
                s_clean = s_norm[2:] if s_norm.startswith("ال") and len(s_norm) > 3 else s_norm
                if s in targets or s_norm in targets or s_clean in targets:
                    return True
        return False

    if not has_target_occurrence(combined_raw):
        return False

    masked = combined_raw
    # 1. Arabic detached preposition phrases
    prep_ar_detached = r"\b(?:في|فى|مع|من|بطعم|بنكهة|برائحة|بخلاصة|بمذاق|خالي\s+من|خالٍ\s+من|خالية\s+من|بدون|من\s+غير)\s+(?:ال)?(?:[^\s]+\s+){0,6}"
    for t in targets:
        esc_t = re.escape(t)
        masked = re.sub(prep_ar_detached + r"(?:ال)?" + esc_t + r"\b", " ", masked)

    # 2. Arabic attached prepositions: بال, ب, لل
    for t in targets:
        esc_t = re.escape(t)
        masked = re.sub(r"\b(?:بال|ب|لل)" + esc_t + r"\b", " ", masked)

    # 3. English preposition phrases
    prep_en = r"\b(?:in|with|flavored\s+with|flavoured\s+with|flavor\s+of|flavour\s+of|taste\s+of|scented\s+with|extract\s+of|free\s+of|free\s+from)\s+(?:the\s+)?(?:[a-z0-9]+\s+){0,6}"
    for t in targets:
        esc_t = re.escape(t)
        masked = re.sub(prep_en + esc_t + r"\b", " ", masked)

    # 4. Commodity composite modifiers
    if ht_clean in ("حليب", "لبن"):
        masked = re.sub(r"\b(?:شوكولاتة|شيكولاتة|شيكولاته|بسكويت|بسكوت|كيك|ويفر|سمن|سمنة)\s+(?:ديري\s+)?(?:ال)?(?:حليب|لبن)\b", " ", masked)
        masked = re.sub(r"\b(?:milk\s+(?:chocolate|biscuit|cake|candy|bar)|dairy\s+milk)\b", " ", masked)
    elif ht_clean in ("زيت", "زيوت"):
        masked = re.sub(r"\b(?:ماكريل|تونة|تونه|سردين|رنجة|رنجه|فسيخ|بطارخ)\s+(?:[^\s]+\s+){0,3}(?:في|فى|ب|بال)?\s*(?:ال)?زيت\b", " ", masked)
        masked = re.sub(r"\b(?:tuna|mackerel|sardine|herring)\s+(?:[a-z0-9]+\s+){0,4}oil\b", " ", masked)
    elif ht_clean in ("شوكولاتة", "شيكولاتة", "شيكولاته"):
        masked = re.sub(r"\b(?:كيك|بسكويت|بسكوت|ويفر|ايس\s+كريم|آيس\s+كريم|حليب|لبن|زبادي)\s+(?:[^\s]+\s+){0,3}(?:ال)?(?:شوكولاتة|شيكولاتة|شيكولاته)\b", " ", masked)

    words_remaining = re.findall(r"\b[a-zA-Z0-9_\u0600-\u06FF]+\b", masked)
    still_has_primary = False
    for w in words_remaining:
        w_norm = normalize_text(w)
        w_clean = w_norm[2:] if w_norm.startswith("ال") and len(w_norm) > 3 else w_norm
        if w in targets or w_norm in targets or w_clean in targets:
            still_has_primary = True
            break

    return not still_has_primary


def is_disqualified_commodity_candidate(
    rec: Optional[dict[str, Any]],
    head_term: Optional[str],
    head_variants: set[str],
    explicit_keyword: Optional[str] = None,
) -> bool:
    """
    Checks if a candidate is disqualified based on:
      1. Conflicting category taxonomy (e.g. seafood or cosmetics for cooking oil).
      2. Conflicting head noun (e.g. 'ماكريل', 'تونة' for 'زيت'; 'شوكولاتة' for 'حليب').
      3. Prepositional modifier only (e.g. 'في زيت', 'بالحليب').
    """
    if not rec or not head_term:
        return False
    norm_ht = normalize_text(head_term).strip().lower()
    ht_clean = norm_ht[2:] if norm_ht.startswith("ال") and len(norm_ht) > 3 else norm_ht

    # If the user explicitly searched for the composite term, do not disqualify
    if explicit_keyword:
        norm_kw = normalize_text(explicit_keyword).lower()
        if ht_clean in ("زيت", "زيوت") and any(k in norm_kw for k in ("ماكريل", "تونة", "تونه", "سردين", "شعر")):
            return False
        if ht_clean in ("حليب", "لبن") and any(k in norm_kw for k in ("شوكولاتة", "شيكولاتة", "بسكويت", "كيك", "سمن")):
            return False

    # 1. Category taxonomy alignment check
    cat_lower = str(rec.get("category", "")).strip().lower()
    forb_cats = COMMODITY_FORBIDDEN_CATEGORIES.get(ht_clean) or COMMODITY_FORBIDDEN_CATEGORIES.get(norm_ht)
    if forb_cats and cat_lower in forb_cats:
        return True

    # 2. Conflicting primary head noun check
    forb_heads = COMMODITY_FORBIDDEN_HEAD_NOUNS.get(ht_clean) or COMMODITY_FORBIDDEN_HEAD_NOUNS.get(norm_ht)
    if forb_heads:
        p_nar = normalize_text(str(rec.get("name_ar", "")))
        p_nen = str(rec.get("name_en", "")).lower()
        title_words = re.findall(r"\b[a-zA-Z0-9_\u0600-\u06FF]+\b", f"{p_nar} {p_nen}")
        for w in title_words:
            w_norm = normalize_text(w)
            w_clean = w_norm[2:] if w_norm.startswith("ال") and len(w_norm) > 3 else w_norm
            if w in forb_heads or w_norm in forb_heads or w_clean in forb_heads:
                return True

    # 3. Prepositional modifier only check
    if is_prepositional_modifier_only(rec.get("name_ar", ""), rec.get("name_en", ""), head_term):
        return True

    return False


class ProductRetriever:
    """
    Core retrieval engine for Spinneys 25,881 product catalog.
    Executes fast-path filter execution in < 40 ms with selective LLM arbitration.
    """

    def __init__(
        self,
        meta_parquet_path: Optional[Path | str] = None,
        docs_parquet_path: Optional[Path | str] = None,
        vector_store = None,
    ):
        # Locate metadata parquet
        if meta_parquet_path is None:
            p1 = ROOT / "data" / "retrieval_meta.parquet"
            p2 = ROOT / "data" / "processed" / "retrieval_meta.parquet"
            meta_parquet_path = p1 if p1.exists() else p2

        self.meta_path = Path(meta_parquet_path)
        self.df_meta: pd.DataFrame = pd.DataFrame()
        self.products_by_id: dict[int, dict[str, Any]] = {}
        self._load_metadata()

        # Initialize Hybrid Search Engine (BM25 + Vector + RRF)
        self.hybrid_engine = HybridSearchEngine(
            docs_parquet_path=docs_parquet_path,
            vector_store=vector_store,
        )

        # Initialize Recipe Engine & LLM Client
        self.recipe_engine = RecipeEngine(retriever=self)
        self.llm = get_llm_client()

    def _load_metadata(self) -> None:
        if not self.meta_path.exists():
            log.warning("Metadata parquet not found at %s. Fast-path filtering inactive.", self.meta_path)
            return

        t0 = time.perf_counter()
        log.info("Loading catalog metadata from %s ...", self.meta_path)
        df = pd.read_parquet(self.meta_path)

        # Ensure correct types and pre-compute lowercased columns for rapid vectorized matching
        df["product_id"] = df["product_id"].astype(np.int64)
        df["_brand_lower"] = df["brand"].fillna("").astype(str).str.lower()
        df["_category_lower"] = df["category"].fillna("").astype(str).str.lower()
        df["effective_price"] = df["effective_price"].astype(np.float64)
        df["default_price"] = df["default_price"].astype(np.float64)
        df["availability"] = df["availability"].astype(bool)

        # Enforce permanent voucher, zero-price, and non-grocery junk purge
        junk_mask = (
            (df["effective_price"] <= 0.0)
            | (df["default_price"] <= 0.0)
            | df["name_en"].astype(str).str.contains(VOUCHER_JUNK_RE, regex=True, na=False)
            | df["name_ar"].astype(str).str.contains(VOUCHER_JUNK_RE, regex=True, na=False)
            | df["category"].astype(str).str.contains(VOUCHER_JUNK_RE, regex=True, na=False)
        )
        purged_count = int(junk_mask.sum())
        df = df[~junk_mask].copy().reset_index(drop=True)
        log.info("Purged %d zero-price, voucher, and junk items from catalog.", purged_count)

        # Precompute sweetener/sugar substitute mask for rapid negative filtering
        df["_is_sweetener"] = (
            df["name_ar"].astype(str).str.contains(SWEETENER_TERMS_RE, regex=True, na=False) |
            df["name_en"].astype(str).str.contains(SWEETENER_TERMS_RE, regex=True, na=False)
        )

        self.df_meta = df

        # Build fast O(1) product record dictionary
        records = df.to_dict(orient="records")
        self.products_by_id = {int(r["product_id"]): r for r in records}
        log.info("Loaded %d catalog products in memory in %.2f ms", len(df), (time.perf_counter() - t0) * 1000)

    def _check_arbitration_triggers(self, raw_query: str) -> tuple[bool, str]:
        """
        Determines whether the query requires Groq LLM arbitration.
        Returns: (needs_arbitration: bool, reason: str)
        """
        # 1. Negation or exclusion detected
        if NEGATION_RE.search(raw_query):
            return True, "negation_exclusion"

        # 2. Recipe intent
        if RECIPE_RE.search(raw_query):
            return True, "recipe"

        # 3. Complex criteria connectors
        if COMPLEX_CONNECTOR_RE.search(raw_query):
            return True, "complex_criteria"

        # 4. Long / tangled queries (> 5 tokens with mixed attributes)
        tokens = raw_query.split()
        if len(tokens) > 5 and any(w in raw_query for w in ["و", "مع", "and", "or"]):
            return True, "tangled_criteria"

        # 5. Ambiguity: multiple brand tokens
        found_brands = []
        q_lower = raw_query.lower()
        for b in TOP_KNOWN_BRANDS:
            if b.lower() in q_lower:
                found_brands.append(b)
        if len(found_brands) > 1:
            return True, "multiple_competing_brands"

        return False, "fast_path"

    def _arbitrate_with_llm(self, query: str) -> dict[str, Any]:
        """
        Uses Groq LLM to safely arbitrate complex/negation queries into strict JSON filters.
        Never invents catalog products.
        """
        if not self.llm.is_available:
            return self._fallback_rule_arbitration(query)

        prompt = (
            f"User query: '{query}'\n"
            "Analyze the query and extract catalog search criteria in JSON format only:\n"
            "{\n"
            '  "query": "core search keyword or null",\n'
            '  "brand": "target brand or null",\n'
            '  "exclude_brands": ["brands explicitly rejected or excluded"],\n'
            '  "category": "category name or null",\n'
            '  "min_price": float or null,\n'
            '  "max_price": float or null,\n'
            '  "in_stock": true or null,\n'
            '  "sort": "price_asc", "price_desc", or null\n'
            "}"
        )

        try:
            resp = self.llm.complete_json(
                system_prompt="You are a precise grocery retrieval query arbitrator. Output JSON filters only.",
                user_prompt=prompt,
            )
            content = resp.content
            if isinstance(content, dict):
                # Sanitize extracted filters
                if content.get("brand"):
                    content["brand"] = normalize_brand(content["brand"])
                if content.get("exclude_brands"):
                    content["exclude_brands"] = [normalize_brand(b) for b in content["exclude_brands"]]
                return content
        except Exception as exc:
            log.warning("LLM arbitration failed: %s", exc)

        return self._fallback_rule_arbitration(query)

    def _fallback_rule_arbitration(self, query: str) -> dict[str, Any]:
        """Deterministic rule-based arbitration when LLM is unavailable."""
        nlu = nlu_parse_query(query)
        filters: dict[str, Any] = {
            "query": nlu.query,
            "brand": nlu.brand,
            "exclude_brands": [],
            "category": nlu.category,
            "min_price": nlu.price_min,
            "max_price": nlu.price_max,
            "in_stock": nlu.in_stock,
            "sort": nlu.sort,
        }

        # Check for negation: "مش ليبتون" -> exclude Lipton
        m = NEGATION_RE.search(query)
        if m:
            negated_term = m.group(2)
            # Check if negated term is a known brand
            detected = find_known_brand(negated_term)
            if detected:
                filters["exclude_brands"].append(normalize_brand(detected))
                # If the brand was mistakenly assigned as positive brand, clear it
                if filters["brand"] == normalize_brand(detected):
                    filters["brand"] = None

            # Remove negation clause from core search query
            cleaned_q = NEGATION_RE.sub(" ", query)
            cleaned_q = re.sub(r"\b(بس|فقط|only|just|please)\b", " ", cleaned_q, flags=re.IGNORECASE)
            cleaned_q = re.sub(r"\s+", " ", cleaned_q).strip()
            if cleaned_q and len(cleaned_q) >= 2:
                filters["query"] = cleaned_q

        return filters

    def retrieve(
        self,
        query: str,
        limit: int = 10,
        mode: str = "auto",  # "auto", "rules", "hybrid", "bm25", "vector"
        filter_overrides: Optional[dict[str, Any]] = None,
        is_internal: bool = False,
        head_term: Optional[str] = None,
        qualifiers: Optional[list[str]] = None,
        target_category: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Main retrieval method:
          1. Checks for Recipe intent -> routes to RecipeEngine.
          2. Runs Fast-Path extraction or LLM Arbitration.
          3. Applies sub-millisecond filtering on in-memory DataFrame.
          4. Ranks candidates via BM25 / RRF with availability boosting.
          5. Returns formatted products and execution stats.
        """
        t0 = time.perf_counter()

        norm_q = query.strip()
        # 0. Check Healthy Meal Recommendation Intent
        if not is_internal and HEALTHY_KW_RE.search(norm_q) and MEAL_REQ_RE.search(norm_q):
            smart_cart_res = self.recipe_engine.generate_smart_cart(norm_q, dish_override="وجبة صحية قليلة السعرات")
            flat_products = []
            seen_pids = set()
            for group in smart_cart_res.get("cart", []):
                for p in group.get("products", []):
                    pid = p["product_id"]
                    if pid not in seen_pids:
                        seen_pids.add(pid)
                        flat_products.append(p)
            exec_time = (time.perf_counter() - t0) * 1000
            return {
                "query": query,
                "total_matched": len(flat_products),
                "execution_time_ms": round(exec_time, 2),
                "applied_filters": {"intent": "healthy_meal"},
                "intent": "recommend",
                "is_healthy_meal": True,
                "dish": "وجبة صحية قليلة السعرات",
                "reply": "اقترحت لك وجبة غداء صحية ومتوازنة وقليلة السعرات الحرارية غنية بالبروتين والألياف:",
                "cart": smart_cart_res.get("cart", []),
                "products": flat_products[:limit],
            }

        # Check Recipe Intent
        if not is_internal and RECIPE_RE.search(query):
            return self.recipe_engine.generate_smart_cart(query)

        # Step 1: Arbitration / Parameter Extraction
        needs_llm, reason = self._check_arbitration_triggers(query)
        if mode == "rules":
            filters = self._fallback_rule_arbitration(query)
        elif mode == "hybrid" or (mode == "auto" and needs_llm):
            if self.llm.is_available:
                filters = self._arbitrate_with_llm(query)
            else:
                filters = self._fallback_rule_arbitration(query)
        else:
            # Fast-path deterministic parsing (< 2 ms)
            nlu = nlu_parse_query(query)
            filters = {
                "query": nlu.query,
                "brand": nlu.brand,
                "exclude_brands": [],
                "category": nlu.category,
                "target_category": nlu.target_category,
                "head_term": nlu.head_term,
                "qualifiers": nlu.qualifiers,
                "min_price": nlu.price_min,
                "max_price": nlu.price_max,
                "in_stock": nlu.in_stock,
                "sort": nlu.sort,
            }

        # Apply any explicit filter overrides
        if filter_overrides:
            filters.update(filter_overrides)

        head_term = head_term or filters.get("head_term")
        qualifiers = qualifiers if qualifiers is not None else filters.get("qualifiers", [])
        target_category = target_category or filters.get("target_category") or filters.get("category")
        brand = filters.get("brand")
        exclude_brands = filters.get("exclude_brands", [])
        category = filters.get("category")
        min_price = filters.get("min_price")
        max_price = filters.get("max_price")
        in_stock = filters.get("in_stock")
        sort_order = filters.get("sort")
        keyword = filters.get("query") or query
        if keyword:
            keyword = sanitize_query(keyword)

        # Infer head_term and qualifiers universally if not yet set
        if not head_term and keyword:
            inferred_head, inferred_quals, inferred_cat = extract_head_term_and_qualifiers(keyword)
            head_term = inferred_head
            if not qualifiers:
                qualifiers = inferred_quals
            if not target_category:
                target_category = inferred_cat

        # Step 2: In-Memory Fast Filtering (Vectorized Numpy / Pandas)
        df = self.df_meta
        if df.empty:
            return {
                "query": query,
                "total_matched": 0,
                "execution_time_ms": (time.perf_counter() - t0) * 1000,
                "applied_filters": filters,
                "products": [],
            }

        # Start with all rows True
        mask = np.ones(len(df), dtype=bool)

        # 1. Brand filter (Bilingual canonical + raw mapping)
        if brand:
            canon_b = normalize_brand(brand).strip().lower()
            raw_b = brand.strip().lower()
            valid_brands = {canon_b, raw_b}
            for alias, canon in BRAND_NORMALIZATION.items():
                if canon.strip().lower() == canon_b:
                    valid_brands.add(alias.strip().lower())
                    valid_brands.add(normalize_text(alias).strip().lower())
            mask &= (df["_brand_lower"].isin(valid_brands))

            # Strip brand tokens from search keyword if present to avoid query collision
            if keyword:
                stripped_kw = strip_brand_from_query(keyword, brand)
                if stripped_kw:
                    keyword = stripped_kw

        # 2. Exclude brands
        if exclude_brands:
            ex_set = {b.strip().lower() for b in exclude_brands if b}
            if ex_set:
                mask &= (~df["_brand_lower"].isin(ex_set))

        # 3. Category filter: only apply strict hard mask if explicitly requested in filter_overrides
        explicit_cat = filter_overrides.get("category") if filter_overrides else None
        if explicit_cat:
            cat_tokens = [c.strip().lower() for c in re.split(r"[,/|]", explicit_cat) if c.strip()]
            if cat_tokens:
                cat_mask = np.zeros(len(df), dtype=bool)
                for cat_norm in cat_tokens:
                    cat_mask |= (
                        (df["_category_lower"] == cat_norm)
                        | (df["_category_lower"].str.startswith(cat_norm))
                        | (df["_category_lower"].str.contains(cat_norm, regex=False, na=False))
                    )
                if any(k in explicit_cat.lower() for k in ["legumes", "canned food", "poultry", "dairy"]):
                    cat_mask |= (df["_category_lower"] == "grocery")
                mask &= cat_mask

        # 4. Price filters
        if max_price is not None:
            mask &= (df["effective_price"] <= float(max_price))
        if min_price is not None:
            mask &= (df["effective_price"] >= float(min_price))
        else:
            # Enforce minimum price threshold (>= 2.00 EGP) for adult nutrition / grocery queries to prevent herbs/parsley garnish
            is_nutrition_search = (
                bool(filters.get("attribute_focus"))
                or any(w in norm_q.lower() for w in ["بروتين", "دايت", "سعرات", "طاقة", "دهون", "تونة", "دجاج", "بيض", "شوفان"])
                or (bool(keyword) and any(w in keyword.lower() for w in ["بروتين", "دايت", "سعرات", "طاقة", "دهون", "تونة", "دجاج", "بيض", "شوفان"]))
            )
            if is_nutrition_search:
                mask &= (df["effective_price"] >= 2.00)

        # 5. In-stock filter
        if in_stock is True:
            mask &= (df["availability"] == True)
        elif in_stock is False:
            mask &= (df["availability"] == False)

        # 6. Negative sweetener filter: exclude sweeteners/sugar substitutes unless explicitly requested
        is_diet_or_healthy = bool(HEALTHY_KW_RE.search(query))
        is_explicit_sweetener = bool(SWEETENER_EXPLICIT_RE.search(query))
        if is_diet_or_healthy and not is_explicit_sweetener and "_is_sweetener" in df.columns:
            mask &= (~df["_is_sweetener"])

        # 7. Exclude non-food categories for food, dairy, and nutrition queries
        is_dairy_query = bool(DAIRY_TERMS_RE.search(norm_q)) or (bool(keyword) and bool(DAIRY_TERMS_RE.search(keyword)))
        is_cheese_query = any(k in norm_q.lower() for k in ("جبن", "جبنة", "cheese")) or (bool(keyword) and any(k in keyword.lower() for k in ("جبن", "جبنة", "cheese")))
        is_milk_query = any(k in norm_q.lower() for k in ("لبن", "حليب", "milk")) or (bool(keyword) and any(k in keyword.lower() for k in ("لبن", "حليب", "milk")))
        is_protein_query = (
            filters.get("attribute_focus") == "protein"
            or any(w in norm_q.lower() for w in ["بروتين", "البروتين", "protein"])
            or any(w in keyword.lower() for w in ["تونة صدور دجاج", "بروتين", "protein"])
        )
        is_foul_query = (
            bool(re.search(r"\b(فول|الفول|foul|ful|fava)\b", norm_q, re.IGNORECASE))
            or (bool(keyword) and bool(re.search(r"\b(فول|الفول|foul|ful|fava)\b", keyword, re.IGNORECASE)))
        )
        is_explicit_peanut = (
            any(w in norm_q.lower() for w in ("سودان", "سوداني", "سودانى", "peanut"))
            or (bool(keyword) and any(w in keyword.lower() for w in ("سودان", "سوداني", "سودانى", "peanut")))
        )
        is_explicit_soy = (
            any(w in norm_q.lower() for w in ("صويا", "soy", "soya"))
            or (bool(keyword) and any(w in keyword.lower() for w in ("صويا", "soy", "soya")))
        )

        is_oil_query = (
            bool(re.search(r"\b(زيت|الزيت|oil|oils)\b", norm_q, re.IGNORECASE))
            or (bool(keyword) and bool(re.search(r"\b(زيت|الزيت|oil|oils)\b", keyword, re.IGNORECASE)))
        )
        is_explicit_cosmetic_oil = (
            any(w in norm_q.lower() for w in ("شعر", "بشرة", "مساج", "تدليك", "لحية", "سيروم", "حمام زيت", "hair", "skin", "body", "massage", "beard", "serum"))
            or (bool(keyword) and any(w in keyword.lower() for w in ("شعر", "بشرة", "مساج", "تدليك", "لحية", "سيروم", "حمام زيت", "hair", "skin", "body", "massage", "beard", "serum")))
        )

        is_nutrition_query = bool(filters.get("attribute_focus")) or any(w in norm_q.lower() for w in ["بروتين", "دايت", "سعرات", "طاقة", "دهون", "تونة", "دجاج", "بيض", "شوفان"])

        # Check if query is for consumable/food vs household/personal care
        is_food_head = False
        is_explicit_household = False
        if head_term:
            norm_ht = normalize_text(head_term).strip().lower()
            ht_clean = norm_ht[2:] if norm_ht.startswith("ال") and len(norm_ht) > 3 else norm_ht
            food_heads = {
                "زيت", "سمن", "سمنة", "سكر", "ملح", "دقيق", "طحين", "ارز", "أرز", "رز", "مكرونة", "مكرونه",
                "شعرية", "صلصة", "خل", "توابل", "بهارات", "عسل", "مربى", "فول", "عدس", "حمص", "تونة", "تونه",
                "شوفان", "حليب", "لبن", "جبن", "جبنة", "جبنه", "زبادي", "قشطة", "زبدة", "زبده", "بيض", "شاي", "شاى",
                "قهوة", "قهوه", "نسكافيه", "عصير", "مشروب", "دجاج", "فراخ", "لحم", "لحمة", "لحمه", "سمك", "سجق", "برجر",
                "بسكويت", "شوكولاتة", "شيبس", "سناك", "طعام"
            }
            household_heads = {
                "مناديل", "منديل", "صابون", "صابونة", "مسحوق", "منظف", "كلور", "ديتول", "أكياس", "اكياس",
                "أطباق", "اطباق", "علب", "علبة", "شامبو", "بلسم", "معجون", "فرشاة", "حفاضات", "بامبرز"
            }
            is_food_head = (ht_clean in food_heads) or (norm_ht in food_heads)
            is_explicit_household = (ht_clean in household_heads) or (norm_ht in household_heads)

        target_cat_lower = (target_category or "").strip().lower()
        is_food_target = is_food_head or any(k in target_cat_lower for k in ("grocery", "dairy", "beverage", "meat", "bakery", "produce", "food"))

        # Explicit household tokens in query
        if any(w in norm_q.lower() for w in ("مناديل", "صابون", "مسحوق", "كلور", "شامبو", "علب", "اطباق", "أطباق")):
            is_explicit_household = True

        if (is_food_target or is_dairy_query or is_nutrition_query or (is_foul_query and not is_explicit_peanut and not is_explicit_soy) or (is_oil_query and not is_explicit_cosmetic_oil)) and not is_explicit_household:
            mask &= (~df["_category_lower"].isin(NON_FOOD_CATEGORIES))

        # Enforce Category Taxonomy Alignment for tracked commodities
        if head_term:
            norm_ht = normalize_text(head_term).strip().lower()
            ht_clean = norm_ht[2:] if norm_ht.startswith("ال") and len(norm_ht) > 3 else norm_ht
            forb_cats = COMMODITY_FORBIDDEN_CATEGORIES.get(ht_clean) or COMMODITY_FORBIDDEN_CATEGORIES.get(norm_ht)
            if forb_cats:
                mask &= (~df["_category_lower"].isin(forb_cats))

        if (head_term == "زيت" or is_oil_query) and not is_explicit_cosmetic_oil:
            cosmetic_pat = r"شعر|بشرة|مساج|حمام زيت|كوبرا|تدليك|لحية|سيروم|hair|body|skin|massage|cosmetic|serum|بديل الزيت"
            mask &= (~df["name_ar"].str.contains(cosmetic_pat, case=False, na=False))
            mask &= (~df["name_en"].str.contains(cosmetic_pat, case=False, na=False))
            fish_cheese_oil_pat = r"خالية من الزيت|خالي من الزيت|رنجه|سردين|تونة|بطارخ|فسيخ|فيليه فى الزيت"
            mask &= (~df["name_ar"].str.contains(fish_cheese_oil_pat, regex=True, na=False))

        candidate_df = df[mask]
        total_matched = len(candidate_df)

        if total_matched == 0:
            exec_time = (time.perf_counter() - t0) * 1000
            return {
                "query": query,
                "total_matched": 0,
                "execution_time_ms": round(exec_time, 2),
                "applied_filters": {k: v for k, v in filters.items() if v is not None and v != []},
                "products": [],
            }

        candidate_ids = set(candidate_df["product_id"].to_list())

        # Step 3: Candidate Ranking
        ranked_product_ids: list[int] = []

        head_variants: set[str] = get_head_term_variants(head_term) if head_term else set()

        def _has_head_term_match(p_rec: Optional[dict[str, Any]]) -> bool:
            if not head_variants or not p_rec:
                return True
            nar = normalize_text(str(p_rec.get("name_ar", "")))
            nen = str(p_rec.get("name_en", "")).lower()
            title_words = re.findall(r"\b[a-zA-Z0-9_\u0600-\u06FF]+\b", f"{nar} {nen}")
            for w in title_words:
                w_norm = normalize_text(w)
                w_clean = w_norm[2:] if w_norm.startswith("ال") and len(w_norm) > 3 else w_norm
                if w in head_variants or w_norm in head_variants or w_clean in head_variants:
                    return True
            cat_words = re.findall(r"\b[a-zA-Z0-9_\u0600-\u06FF]+\b", normalize_text(str(p_rec.get("category", ""))))
            for w in cat_words:
                w_norm = normalize_text(w)
                w_clean = w_norm[2:] if w_norm.startswith("ال") and len(w_norm) > 3 else w_norm
                if w in head_variants or w_norm in head_variants or w_clean in head_variants:
                    return True
            return False

        def _calc_item_bonus(p_rec: Optional[dict[str, Any]], p_name: str, p_cat: str) -> float:
            extra = 0.0

            # 1. Mandatory Head-Term Filter & Disqualification Check
            if head_variants and not _has_head_term_match(p_rec):
                return -1000.0
            if is_disqualified_commodity_candidate(p_rec, head_term, head_variants, keyword):
                return -1000.0

            # 2. Qualifiers match boosting (+30.0 for matching qualifier token)
            if qualifiers:
                for q in qualifiers:
                    q_norm = normalize_text(q).strip().lower()
                    if q_norm and len(q_norm) >= 2 and q_norm in p_name:
                        extra += 30.0

            # 3. Target Department / Commodity Alignment Boosting (+25.0)
            if head_term:
                norm_ht = normalize_text(head_term).strip().lower()
                ht_clean = norm_ht[2:] if norm_ht.startswith("ال") and len(norm_ht) > 3 else norm_ht
                pri_cats = COMMODITY_PRIMARY_CATEGORIES.get(ht_clean) or COMMODITY_PRIMARY_CATEGORIES.get(norm_ht)
                if pri_cats and any(c in p_cat for c in pri_cats):
                    extra += 25.0
            elif target_category and target_category.strip().lower() in p_cat:
                extra += 20.0

            # 4. Cooking Oil Category Boosting & Cosmetic Demotion
            if (head_term == "زيت" or is_oil_query) and not is_explicit_cosmetic_oil:
                if any(term in p_name for term in COSMETIC_OIL_STEMS):
                    extra -= 50.0
                elif any(stem in p_name for stem in COOKING_OIL_STEMS):
                    extra += 30.0
                if p_cat in ("oil", "grocery"):
                    extra += 15.0

            # 5. Foul Legume Handling
            elif is_foul_query and not is_explicit_peanut and not is_explicit_soy:
                p_nar = normalize_text(str(p_rec.get("name_ar", ""))) if p_rec else ""
                p_nen = str(p_rec.get("name_en", "")).lower() if p_rec else ""
                p_words_ar = set(p_nar.split())
                p_words_en = set(p_nen.split())
                has_foul_token = bool(p_words_ar & {"فول", "الفول"}) or bool(p_words_en & {"foul", "ful", "fava"})
                if not has_foul_token:
                    extra -= 50.0
                elif any(term in p_name for term in FOUL_NON_LEGUME_TERMS):
                    extra -= 30.0
                elif any(stem in p_name for stem in FOUL_LEGUME_STEMS):
                    extra += 20.0
            elif is_cheese_query:
                if any(stem in p_name for stem in CHEESE_STEMS):
                    extra += 10.0
                else:
                    extra -= 10.0
            elif is_protein_query:
                if any(stem in p_name for stem in PROCESSED_CHEESE_STEMS):
                    extra -= 20.0
                elif any(k in p_cat for k in ("meat", "poultry", "seafood", "canned seafood", "tuna", "fish", "eggs")) or any(stem in p_name for stem in PROTEIN_STEMS):
                    extra += 10.0
            elif is_dairy_query:
                if any(k in p_cat for k in ("dairy", "cheese", "beverage")):
                    extra += 3.0
                if is_milk_query and any(k in p_name for k in ("لبن", "حليب", "milk")):
                    extra += 5.0
            return extra

        if keyword and keyword.strip():
            # If diet/healthy query and auto mode, prioritize hybrid search when vector store is ready
            active_mode = mode
            if active_mode == "auto" and is_diet_or_healthy and self.hybrid_engine.vector_store and self.hybrid_engine.vector_store.is_ready():
                active_mode = "hybrid"

            if active_mode == "vector":
                # Dense Vector Search only
                vector_results = self.hybrid_engine.search_vector(
                    query=keyword,
                    top_k=min(limit * 5, len(candidate_ids)),
                    candidate_ids=candidate_ids,
                )
                if vector_results:
                    scored_candidates = []
                    for pid, score in vector_results:
                        p_rec = self.products_by_id.get(pid)
                        if not p_rec:
                            continue
                        if head_variants and not _has_head_term_match(p_rec):
                            continue
                        if is_disqualified_commodity_candidate(p_rec, head_term, head_variants, keyword):
                            continue
                        avail = p_rec["availability"]
                        p_name = normalize_text(str(p_rec.get("name_ar", "")) + " " + str(p_rec.get("name_en", ""))).lower()
                        p_cat = str(p_rec.get("category", "")).lower()
                        bonus = _calc_item_bonus(p_rec, p_name, p_cat)
                        if bonus < -500.0:
                            continue
                        final_score = score + (0.5 if avail else 0.0) + bonus
                        scored_candidates.append((pid, final_score))
                    scored_candidates.sort(key=lambda x: x[1], reverse=True)
                    ranked_product_ids = [pid for pid, _ in scored_candidates]
            elif active_mode == "hybrid":
                # Hybrid RRF Search
                hybrid_results = self.hybrid_engine.search_hybrid(
                    query=keyword,
                    top_k=min(limit * 5, len(candidate_ids)),
                    candidate_ids=candidate_ids,
                )
                if hybrid_results:
                    scored_candidates = []
                    for pid, score in hybrid_results:
                        p_rec = self.products_by_id.get(pid)
                        if not p_rec:
                            continue
                        if head_variants and not _has_head_term_match(p_rec):
                            continue
                        if is_disqualified_commodity_candidate(p_rec, head_term, head_variants, keyword):
                            continue
                        avail = p_rec["availability"]
                        p_name = normalize_text(str(p_rec.get("name_ar", "")) + " " + str(p_rec.get("name_en", ""))).lower()
                        p_cat = str(p_rec.get("category", "")).lower()
                        bonus = _calc_item_bonus(p_rec, p_name, p_cat)
                        if bonus < -500.0:
                            continue
                        final_score = score + (0.01 if avail else 0.0) + bonus
                        scored_candidates.append((pid, final_score))
                    scored_candidates.sort(key=lambda x: x[1], reverse=True)
                    ranked_product_ids = [pid for pid, _ in scored_candidates]
            else:
                # Default fast-path: BM25 lexical search over candidate subset
                bm25_results = self.hybrid_engine.search_bm25(
                    query=keyword,
                    top_k=min(limit * 5, len(candidate_ids)),
                    candidate_ids=candidate_ids,
                )
                if bm25_results:
                    scored_candidates = []
                    for pid, score in bm25_results:
                        p_rec = self.products_by_id.get(pid)
                        if not p_rec:
                            continue
                        if head_variants and not _has_head_term_match(p_rec):
                            continue
                        if is_disqualified_commodity_candidate(p_rec, head_term, head_variants, keyword):
                            continue
                        avail = p_rec["availability"]
                        p_name = normalize_text(str(p_rec.get("name_ar", "")) + " " + str(p_rec.get("name_en", ""))).lower()
                        p_cat = str(p_rec.get("category", "")).lower()
                        bonus = _calc_item_bonus(p_rec, p_name, p_cat)
                        if bonus < -500.0:
                            continue
                        final_score = score + (2.0 if avail else 0.0) + bonus
                        scored_candidates.append((pid, final_score))

                    scored_candidates.sort(key=lambda x: x[1], reverse=True)
                    ranked_product_ids = [pid for pid, _ in scored_candidates]

        # If no keyword matches or pure filter query, rank from candidate_df
        if not ranked_product_ids:
            if head_variants:
                valid_cand_pids = [
                    pid for pid in candidate_df["product_id"].to_list()
                    if _has_head_term_match(self.products_by_id.get(pid))
                    and not is_disqualified_commodity_candidate(self.products_by_id.get(pid), head_term, head_variants, keyword)
                ]
                candidate_df = candidate_df[candidate_df["product_id"].isin(valid_cand_pids)]
            # Sort candidate_df
            if sort_order == "price_asc":
                sorted_cands = candidate_df.sort_values(
                    by=["availability", "effective_price"],
                    ascending=[False, True],
                )
            elif sort_order == "price_desc":
                sorted_cands = candidate_df.sort_values(
                    by=["availability", "effective_price"],
                    ascending=[False, False],
                )
            else:
                # Default: in-stock first, then id
                sorted_cands = candidate_df.sort_values(
                    by=["availability", "effective_price"],
                    ascending=[False, True],
                )
            ranked_product_ids = sorted_cands["product_id"].to_list()
        else:
            # If explicit sort order requested, re-sort the matched items by price
            if sort_order in ("price_asc", "price_desc"):
                valid_pids = [
                    pid for pid in ranked_product_ids
                    if not is_disqualified_commodity_candidate(self.products_by_id.get(pid), head_term, head_variants, keyword)
                ]
                matched_subset = candidate_df[candidate_df["product_id"].isin(valid_pids)]
                is_asc = (sort_order == "price_asc")
                sorted_cands = matched_subset.sort_values(
                    by=["availability", "effective_price"],
                    ascending=[False, is_asc],
                )
                ranked_product_ids = sorted_cands["product_id"].to_list()

        # Step 4: Format Product Results
        selected_ids = ranked_product_ids[:limit * 2]
        final_products = []
        for pid in selected_ids:
            rec = self.products_by_id.get(pid)
            if not rec or float(rec.get("effective_price", 0.0)) <= 0.0:
                continue
            if is_disqualified_commodity_candidate(rec, head_term, head_variants, keyword):
                continue
            final_products.append(
                {
                    "product_id": int(rec["product_id"]),
                    "name_ar": str(rec["name_ar"]),
                    "name_en": str(rec["name_en"]),
                    "brand": str(rec["brand"]),
                    "price": float(rec["effective_price"]),
                    "regular_price": float(rec["default_price"]),
                    "has_discount": bool(rec["has_discount"]),
                    "availability": bool(rec["availability"]),
                    "image_url": str(rec["image_url"]),
                }
            )
            if len(final_products) >= limit:
                break

        exec_time = (time.perf_counter() - t0) * 1000

        # Construct clean applied_filters dict
        applied = {}
        if brand:
            applied["brand"] = brand
        if exclude_brands:
            applied["exclude_brands"] = exclude_brands
        if category:
            applied["category"] = category
        if max_price is not None:
            applied["max_price"] = max_price
        if min_price is not None:
            applied["min_price"] = min_price
        if in_stock is not None:
            applied["in_stock"] = in_stock
        if sort_order is not None:
            applied["sort"] = sort_order

        return {
            "query": query,
            "total_matched": total_matched,
            "execution_time_ms": round(exec_time, 2),
            "applied_filters": applied,
            "products": final_products,
        }

    def get_entity_aggregation(self, entity: str) -> dict[str, Any]:
        """
        Calculates catalog aggregation for count and variety inquiries (e.g. 'كم نوع فول موجود').
        Returns total count of matching products, variety breakdown, and representative products.
        """
        norm_entity = normalize_text(entity).strip().lower()
        df = self.df_meta
        if df.empty:
            return {
                "entity": entity,
                "total_count": 0,
                "varieties": [],
                "products": [],
            }

        # Filter out 0 price and non-food categories
        valid_mask = (df["effective_price"] > 0) & (~df["_category_lower"].isin(NON_FOOD_CATEGORIES))
        candidate_df = df[valid_mask]

        is_foul = bool(re.search(r"\b(فول|الفول|foul|ful|fava)\b", norm_entity, re.IGNORECASE))

        if is_foul:
            def match_foul_item(row) -> bool:
                nar = normalize_text(str(row.get("name_ar", "")))
                nen = str(row.get("name_en", "")).lower()
                full_text = f"{nar} {nen}"
                raw_ar = str(row.get("name_ar", "")).lower()
                if any(term in full_text or term in raw_ar for term in FOUL_NON_LEGUME_TERMS):
                    return False
                words_ar = set(nar.split())
                words_en = set(nen.split())
                return bool(words_ar & {"فول", "الفول"}) or bool(words_en & {"foul", "ful", "fava"})

            matched_df = candidate_df[candidate_df.apply(match_foul_item, axis=1)]
            total_count = len(matched_df)

            varieties = [
                "فول مدمس معلب",
                "فول تدميس حب",
                "فول مجروش",
            ]

            # Representative products: select top in-stock products across categories
            canned_rows = matched_df[
                matched_df["name_ar"].str.contains(r"مدمس|خلط|سادة|طحين|صلص|كمون|زيت", regex=True, na=False)
                | matched_df["name_en"].str.contains(r"fava|medames|plain", case=False, na=False)
            ].sort_values(by=["availability", "effective_price"], ascending=[False, True])

            raw_rows = matched_df[
                matched_df["name_ar"].str.contains(r"تدميس|حب|حصى|صحيح|بلدي", regex=True, na=False)
                | matched_df["name_en"].str.contains(r"whole|raw", case=False, na=False)
            ].sort_values(by=["availability", "effective_price"], ascending=[False, True])

            split_rows = matched_df[
                matched_df["name_ar"].str.contains(r"مجروش|طعمي|بصار", regex=True, na=False)
                | matched_df["name_en"].str.contains(r"split", case=False, na=False)
            ].sort_values(by=["availability", "effective_price"], ascending=[False, True])

            selected_pids = []
            for sub_df, count in [(canned_rows, 3), (raw_rows, 2), (split_rows, 2)]:
                for pid in sub_df["product_id"].to_list()[:count]:
                    if pid not in selected_pids:
                        selected_pids.append(pid)

            # If still need more to make ~6-8 items
            for pid in matched_df.sort_values(by=["availability", "effective_price"], ascending=[False, True])["product_id"].to_list():
                if len(selected_pids) >= 6:
                    break
                if pid not in selected_pids:
                    selected_pids.append(pid)

            products = []
            for pid in selected_pids:
                rec = self.products_by_id.get(pid)
                if rec:
                    products.append(
                        {
                            "product_id": int(rec["product_id"]),
                            "name_ar": str(rec["name_ar"]),
                            "name_en": str(rec["name_en"]),
                            "brand": str(rec["brand"]),
                            "price": float(rec["effective_price"]),
                            "regular_price": float(rec["default_price"]),
                            "has_discount": bool(rec["has_discount"]),
                            "availability": bool(rec["availability"]),
                            "image_url": str(rec["image_url"]),
                        }
                    )

            return {
                "entity": "فول",
                "total_count": total_count,
                "varieties": varieties,
                "products": products,
            }
        else:
            # Generic entity aggregation
            target_kw = norm_entity
            def match_generic(row) -> bool:
                nar = normalize_text(str(row.get("name_ar", "")))
                nen = str(row.get("name_en", "")).lower()
                return target_kw in nar or target_kw in nen

            matched_df = candidate_df[candidate_df.apply(match_generic, axis=1)]
            total_count = len(matched_df)
            sorted_items = matched_df.sort_values(by=["availability", "effective_price"], ascending=[False, True])
            selected_pids = sorted_items["product_id"].to_list()[:6]
            products = []
            for pid in selected_pids:
                rec = self.products_by_id.get(pid)
                if rec:
                    products.append(
                        {
                            "product_id": int(rec["product_id"]),
                            "name_ar": str(rec["name_ar"]),
                            "name_en": str(rec["name_en"]),
                            "brand": str(rec["brand"]),
                            "price": float(rec["effective_price"]),
                            "regular_price": float(rec["default_price"]),
                            "has_discount": bool(rec["has_discount"]),
                            "availability": bool(rec["availability"]),
                            "image_url": str(rec["image_url"]),
                        }
                    )
            return {
                "entity": entity,
                "total_count": total_count,
                "varieties": [entity],
                "products": products,
            }
