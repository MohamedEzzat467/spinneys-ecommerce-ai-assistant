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

import re
import time
from typing import Any, Optional

from pydantic import BaseModel, Field

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


class ParseResult(BaseModel):
    raw_text: str
    normalized_text: str
    intent: str
    follow_up_type: str
    query: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    in_stock: Optional[bool] = None
    sort: Optional[str] = None
    explicit_fields: list[str] = Field(default_factory=list)
    unsupported_filters: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    token_usage: Optional[dict[str, int]] = None


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
    r"\b(رتب بالسعر تنازلي|رتب تنازلي|سعر تنازلي|تنازلي|من الاغلى|الاغلى|highest price|most expensive|price high to low|sort desc|el aghla|men el aghla|aghla|rateb men el aghla)\b",
    re.IGNORECASE,
)

SORT_ASC_RE = re.compile(
    r"\b(رتب من الارخص للاغلى|رتب من الارخص|رتب بالسعر تصاعدي|رتب بالسعر|رتب تصاعدي|سعر تصاعدي|تصاعدي|"
    r"من الارخص|الارخص الاول|الارخص|ارخص|cheapest first|cheapest|cheap|lowest price|price low to high|"
    r"sort by price|sort by lowest|sort by el arkhas|sort by|sort asc|rateb bel se3r el arkhas|rateb bel se3r|"
    r"rateb men el arkhas|هات الارخص الاول|show cheapest first|el arkhas|arkhas)\b",
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
    r"\b(متوفر|المتوفر|متاح|المتاح|الموجود|في المخزن|in stock|available|only in stock|motawafer|el motawafer)\b",
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


def sanitize_query(raw_text: str) -> str:
    """
    Sanitizes customer queries by stripping generic action verbs, request stems,
    generic meal/item request stems, and punctuation, preserving the core entity/attribute.
    """
    text = raw_text.strip()
    # 1. Clean punctuation (Arabic question mark ؟, English ?, !, commas, etc.)
    text = re.sub(r"[?؟!\.,،;:~]+", " ", text)
    norm = normalize_text(text)

    # 2. Generic action verbs and request stems
    request_stems_re = re.compile(
        r"\b(اقترح\w*|اقتراح\w*|ورشح\w*|رشح\w*|ترشح\w*|عايز\w*|عاوز\w*|عايزين|محتاج\w*|ممكن|"
        r"لو سمحت|من فضلك|وريني|هاتلي|اعرضلي|قولي|ابحث عن|دورلي على|دورلي|"
        r"suggest\w*|recommend\w*|show me|find me|i want|i need|give me|please)\b",
        re.IGNORECASE,
    )
    norm = request_stems_re.sub(" ", norm)

    # 3. Generic meal/item words when used as requests
    meal_stems_re = re.compile(
        r"\b(وجب[هة]|اكل[هة]|اكل|طبيخ|حاج[هة]|منتج\w*|عناصر|meal|food|dish)\b",
        re.IGNORECASE,
    )
    norm = meal_stems_re.sub(" ", norm)

    norm = re.sub(r"\s+", " ", norm).strip()
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
        r"\b(عايز|عاوز|محتاج|ابحث عن|ابحث|دورلي على|دورلي|هاتلي|اعرضلي|وريني|فين|من فضلك|لو سمحت|بس|فقط)\b",
        r"\b(show me|find me|i want|i need|looking for|search for|give me|please|only|just|where is the|where is|show)\b",
        r"\b(3ayez|hatly|warini|please|feen el|feen|first)\b",
        r"\b(مارك[هة]|براند|brand|items?|منتجات?|في الفرع|in store|store|branch|price|سعر|اي|مش فارق|معايا|remove|filter|fine|is fine|all|any|bas|el|rateb|رتب)\b",
        r"\b(بديل لـ?|بديل ل|بديل|alternative for|alternative|substitute for|substitute|badeel le|badeel)\b",
        r"\b(الفرق بين|قارن بين|قارن|مقارنة|difference between|compare|versus|vs|2aren ben|2aren)\b",
        r"\b(ينفع مع|يمشي مع|goes well with|eh yenfa3 ma3|this|that|ده|دي|دا|da|di)\b",
        r"\b(اقترح عليا|اقترح|اقتراح|رشح|ترشحهولي|ترشحهالي|ترشحلي|ترشح|recommend|suggest|what do you recommend for|what do you recommend|ideas for|e2tra7 3alaya|e2tra7|ايه احسن)\b",
    ]
    for filler in fillers:
        cleaned = re.sub(filler, " ", cleaned, flags=re.IGNORECASE)

    # Remove unsupported tags
    for _, tag in UNSUPPORTED_FILTER_PATTERNS:
        cleaned = re.sub(rf"\b{re.escape(tag)}\b", " ", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
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
    elif sort is not None and not query:
        intent = "sort"
        follow_up_type = "refinement"
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

COMPACT_SYSTEM_PROMPT = (
    "Grocery NLU parser. Output JSON:\n"
    '{"intent":"search|refine|sort|recommend|compare|alternatives|cross-sell|out-of-scope",'
    '"follow_up_type":"new_topic|refinement|cancellation|reference",'
    '"query":str|null,"brand":str|null,"category":str|null,'
    '"price_min":float|null,"price_max":float|null,"in_stock":bool|null,"sort":"price_asc|price_desc"|null,'
    '"explicit_fields":[str],"unsupported_filters":[str]}\n'
    "Rules: brand canonical only. unsupported_filters: dietary (sugar-free, organic, etc)."
)


def parse_query(raw_text: str) -> ParseResult:
    """
    Main NLU entry point. Performs hybrid parsing:
      1. Normalize raw input via shared normalizer.
      2. Run deterministic rule extraction.
      3. If Groq LLM is available, consult LLM for semantic intent & complex phrasing.
      4. Validate, normalize brand, isolate unsupported filters, and return canonical ParseResult.
    """
    t0 = time.perf_counter()
    normalized = normalize_text(raw_text)

    # 1. Deterministic baseline
    rule_res = _rule_based_parse(raw_text, normalized)

    llm_client = get_llm_client()
    token_usage_dict: Optional[dict[str, int]] = None

    # 2. Invoke Groq LLM if available and needed
    if llm_client.is_available:
        try:
            llm_resp = llm_client.complete_json(
                system_prompt=COMPACT_SYSTEM_PROMPT,
                user_prompt=f"Customer query: {raw_text}\nNormalized: {normalized}",
            )
            llm_content = llm_resp.content

            if llm_resp.usage:
                token_usage_dict = {
                    "prompt_tokens": llm_resp.usage.prompt_tokens,
                    "completion_tokens": llm_resp.usage.completion_tokens,
                    "total_tokens": llm_resp.usage.total_tokens,
                }

            # Merge LLM semantic insight with deterministic ground-truth
            if llm_content.get("intent") in VALID_INTENTS:
                # Deterministic rules are authoritative for high-precision intents
                if rule_res["intent"] not in {"out-of-scope", "alternatives", "compare", "cross-sell", "sort", "refine"}:
                    rule_res["intent"] = llm_content["intent"]

            if llm_content.get("follow_up_type") in VALID_FOLLOW_UP_TYPES:
                if rule_res["follow_up_type"] not in {"cancellation", "refinement", "reference"}:
                    rule_res["follow_up_type"] = llm_content["follow_up_type"]

            # Merge unsupported filters
            llm_unsupported = llm_content.get("unsupported_filters", [])
            for u in llm_unsupported:
                if u and u not in rule_res["unsupported_filters"]:
                    rule_res["unsupported_filters"].append(u)

            # Check if LLM found brand if not already detected (suppressed for compare)
            if not rule_res["brand"] and rule_res["intent"] != "compare" and llm_content.get("brand"):
                canon_brand = normalize_brand(llm_content["brand"])
                if canon_brand:
                    rule_res["brand"] = canon_brand
                    if "brand" not in rule_res["explicit_fields"]:
                        rule_res["explicit_fields"].append("brand")

        except Exception as exc:
            # Fall back to deterministic rules on LLM failure
            pass

    # 3. Validation & Canonical Normalization Layer
    if rule_res["intent"] == "compare":
        rule_res["brand"] = None

    if rule_res["brand"]:
        rule_res["brand"] = normalize_brand(rule_res["brand"])

    # Ensure explicit_fields is accurate
    explicit = set(rule_res["explicit_fields"])
    if rule_res["brand"]:
        explicit.add("brand")
    if rule_res["price_max"] is not None:
        explicit.add("price_max")
    if rule_res["price_min"] is not None:
        explicit.add("price_min")
    if rule_res["in_stock"] is not None:
        explicit.add("in_stock")
    if rule_res["sort"] is not None:
        explicit.add("sort")
    if rule_res["query"]:
        explicit.add("query")

    rule_res["explicit_fields"] = sorted(list(explicit))

    latency = (time.perf_counter() - t0) * 1000.0

    return ParseResult(
        raw_text=raw_text,
        normalized_text=normalized,
        intent=rule_res["intent"],
        follow_up_type=rule_res["follow_up_type"],
        query=rule_res["query"],
        brand=rule_res["brand"],
        category=rule_res["category"],
        price_min=rule_res["price_min"],
        price_max=rule_res["price_max"],
        in_stock=rule_res["in_stock"],
        sort=rule_res["sort"],
        explicit_fields=rule_res["explicit_fields"],
        unsupported_filters=rule_res["unsupported_filters"],
        latency_ms=round(latency, 2),
        token_usage=token_usage_dict,
    )
