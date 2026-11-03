# -*- coding: utf-8 -*-
"""
app/core/normalizer.py
======================
Spinneys Conversational Shopping Assistant — Shared Text & Entity Normalizer.

Single source of truth for text normalization and brand resolution across
ingestion, retrieval, and NLU layers.

Functions
---------
normalize_text(text: str) -> str
    Full bilingual (Arabic & English) text normalization.
normalize_brand(brand: str) -> str
    Normalizes dirty brand names / aliases to their canonical brand representation.
find_known_brand(text: str) -> Optional[str]
    Scans a text string for known brand occurrences (longest match first).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

# ── Regex patterns for Arabic normalization ──────────────────────────────────
# Arabic diacritics / Tashkeel: Fatha, Damma, Kasra, Sukun, Shadda, Tanween, Superscript Alef
ARABIC_DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670]")

# Arabic Tatweel / Kashida
ARABIC_TATWEEL_RE = re.compile(r"\u0640")

# Arabic Alef variations: أ, إ, آ, ٱ -> ا
ARABIC_ALEF_RE = re.compile(r"[أإآٱ]")

# Taa Marbuta to Haa: ة -> ه
ARABIC_TAA_MARBUTA_RE = re.compile(r"ة")

# Multiple whitespace collapse
WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: Optional[str]) -> str:
    """
    Apply standard Week 2/3 bilingual text normalization:
      1. Lowercase English characters.
      2. Unify Arabic Alef forms (أ / إ / آ / ٱ -> ا).
      3. Remove Arabic diacritics / Tashkeel (َ ً ُ ٌ ِ ٍ ّ ْ).
      4. Remove Tatweel / Kashida (ـ).
      5. Unify Taa Marbuta and Haa (ة -> ه).
      6. Collapse multiple whitespace and trim ends.

    Parameters
    ----------
    text : Optional[str]
        Raw input string.

    Returns
    -------
    str
        Clean normalized string. Returns empty string if input is None or whitespace.
    """
    if not text:
        return ""

    # Ensure string type
    normalized = str(text)

    # 1. Lowercase English characters
    normalized = normalized.lower()

    # 2. Unify Alef forms
    normalized = ARABIC_ALEF_RE.sub("ا", normalized)

    # 3. Remove Arabic Diacritics / Tashkeel
    normalized = ARABIC_DIACRITICS_RE.sub("", normalized)

    # 4. Remove Tatweel / Kashida
    normalized = ARABIC_TATWEEL_RE.sub("", normalized)

    # 5. Unify Taa Marbuta to Haa
    normalized = ARABIC_TAA_MARBUTA_RE.sub("ه", normalized)

    # 6. Collapse and trim whitespace
    normalized = WHITESPACE_RE.sub(" ", normalized).strip()

    return normalized


# ─────────────────────────────────────────────────────────────────────────────
# Canonical Brand Normalization Map
# Mapping from normalized/lowercase variant -> Canonical catalog brand name
# ─────────────────────────────────────────────────────────────────────────────
BRAND_NORMALIZATION: dict[str, str] = {
    # Domty variants
    "domtty":                   "Domty",
    "domty":                    "Domty",
    "domtey":                   "Domty",
    "دومتي":                    "Domty",
    "جبنة دومتي":               "Domty",

    # Migos variants
    "migo' s":                  "Migos",
    "migos":                    "Migos",
    "migo's":                   "Migos",
    "ميجوز":                    "Migos",
    "ميجوس":                    "Migos",

    # Almarai variants
    "al marai":                 "Almarai",
    "almarai":                  "Almarai",
    "al-marai":                 "Almarai",
    "المراعي":                  "Almarai",
    "مراعي":                    "Almarai",

    # Juhayna variants
    "juhayna":                  "Juhayna",
    "juhaina":                  "Juhayna",
    "juhyna":                   "Juhayna",
    "جهينة":                    "Juhayna",
    "جهينه":                    "Juhayna",

    # Spinneys
    "spinneys":                 "Spinneys",
    "spinney's":                "Spinneys",
    "spinneys egypt":           "Spinneys",
    "سبينيس":                   "Spinneys",
    "سبينس":                    "Spinneys",

    # Americana variants
    "americana":                "Americana",
    "american":                 "Americana",
    "امريكانا":                 "Americana",

    # Nescafé variants
    "nescafe":                  "Nescafé",
    "nescafé":                  "Nescafé",
    "نسكافيه":                  "Nescafé",
    "نسكافيه":                  "Nescafé",

    # Nestlé variants
    "nestle":                   "Nestlé",
    "nestlé":                   "Nestlé",
    "nestle egypt":             "Nestlé",
    "نستله":                    "Nestlé",
    "نستلا":                    "Nestlé",

    # Pepsi
    "pepsi":                    "Pepsi",
    "pepsi co":                 "Pepsi",
    "pepsico":                  "Pepsi",
    "بيبسي":                    "Pepsi",

    # Coca-Cola
    "coca cola":                "Coca-Cola",
    "coca-cola":                "Coca-Cola",
    "coke":                     "Coca-Cola",
    "كوكاكولا":                 "Coca-Cola",
    "كوكا كولا":                "Coca-Cola",

    # Baraka
    "baraka":                   "Baraka",
    "baraka water":             "Baraka",
    "بركة":                     "Baraka",

    # BiscoMisr
    "bisco misr":               "BiscoMisr",
    "biscomisr":                "BiscoMisr",
    "بسكو مصر":                 "BiscoMisr",
    "بسك مصر":                  "BiscoMisr",

    # Lamar
    "lamar":                    "Lamar",
    "la mar":                   "Lamar",
    "لمار":                     "Lamar",

    # Seara
    "seara":                    "Seara",
    "sierra":                   "Seara",
    "سيارا":                    "Seara",

    # Carrefour
    "carrefour":                "Carrefour",
    "كارفور":                   "Carrefour",

    # El Maleka
    "el maleka":                "El Maleka",
    "elmaleka":                 "El Maleka",
    "الملكة":                   "El Maleka",
    "الملكه":                   "El Maleka",

    # Puck
    "puck":                     "Puck",
    "بوك":                      "Puck",

    # Kiri
    "kiri":                     "Kiri",
    "كيري":                     "Kiri",

    # Président
    "president":                "Président",
    "président":                "Président",
    "بريزيدون":                 "Président",
    "بريزيدنت":                 "Président",

    # Nespresso
    "nespresso":                "Nespresso",
    "نسبريسو":                  "Nespresso",

    # Lotus
    "lotus":                    "Lotus",
    "lotus bakeries":           "Lotus",
    "لوتس":                     "Lotus",

    # Good Food
    "good food":                "Good Food",
    "goodfood":                 "Good Food",

    # Master
    "master":                   "Master",
    "ماستر":                    "Master",

    # Regina
    "regina":                   "Regina",
    "ريجينا":                   "Regina",

    # Abu Auf
    "abu auf":                  "Abu Auf",
    "abuauf":                   "Abu Auf",
    "ابو عوف":                  "Abu Auf",
    "أبو عوف":                  "Abu Auf",

    # Bake Mate
    "bake mate":                "Bake Mate",
    "bakemate":                 "Bake Mate",

    # Chipsy
    "chipsy":                   "Chipsy",
    "شيبسي":                    "Chipsy",

    # Lay's
    "lay's":                    "Lay's",
    "lays":                     "Lay's",
    "ليز":                      "Lay's",

    # Pringles
    "pringles":                 "Pringles",
    "برينجلز":                  "Pringles",

    # Kellogg's
    "kelloggs":                 "Kellogg's",
    "kellogg's":                "Kellogg's",
    "كيلوجز":                   "Kellogg's",

    # Quaker
    "quaker":                   "Quaker",
    "كويكر":                    "Quaker",

    # El Doha
    "el doha":                  "El Doha",
    "eldoha":                   "El Doha",
    "الضحى":                    "El Doha",

    # Halwani
    "halwani":                  "Halwani",
    "حلواني":                   "Halwani",
    "حلواني اخوان":             "Halwani",

    # Dettol
    "dettol":                   "Dettol",
    "ديتول":                    "Dettol",

    # Dove
    "dove":                     "Dove",
    "دوف":                      "Dove",

    # Nivea
    "nivea":                    "Nivea",
    "نيفيا":                    "Nivea",

    # Heinz
    "heinz":                    "Heinz",
    "هاينز":                    "Heinz",

    # Knorr
    "knorr":                    "Knorr",
    "فاين فودز":                "Knorr",
    "كنور":                     "Knorr",

    # Lipton
    "lipton":                   "Lipton",
    "ليبتون":                   "Lipton",

    # Cadbury
    "cadbury":                  "Cadbury",
    "كادبوري":                  "Cadbury",

    # Nutella
    "nutella":                  "Nutella",
    "نوتيلا":                   "Nutella",

    # Oreo
    "oreo":                     "Oreo",
    "اوريو":                    "Oreo",

    # Ariel
    "ariel":                    "Ariel",
    "اريال":                    "Ariel",

    # Persil
    "persil":                   "Persil",
    "برسيل":                    "Persil",

    # Tide
    "tide":                     "Tide",
    "تايد":                     "Tide",

    # Fairy
    "fairy":                    "Fairy",
    "فيري":                     "Fairy",

    # Tornado
    "tornado":                  "Tornado",
    "تورنيدو":                  "Tornado",

    # Nouval
    "nouval":                   "Nouval",
    "نوفال":                    "Nouval",

    # Fresh
    "fresh":                    "Fresh",
    "فريش":                     "Fresh",

    # Elhelal
    "elhelal":                  "Elhelal",
    "الهلال والنجمة":           "Elhelal",
}

# ─────────────────────────────────────────────────────────────────────────────
# Known Brand Lookup List (Sorted longest first for greedy matching)
# ─────────────────────────────────────────────────────────────────────────────
TOP_KNOWN_BRANDS: list[str] = sorted([
    "Spinneys", "Almarai", "Juhayna", "Domty", "Americana",
    "Nestlé", "Nestle", "Nescafé", "Nescafe", "Pepsi", "Coca-Cola", "Coke",
    "Baraka", "BiscoMisr", "Bisco Misr", "Lamar", "Seara", "Puck",
    "Kiri", "Président", "President", "Nespresso", "Lotus",
    "Good Food", "Master", "Regina", "Abu Auf", "Bake Mate",
    "Chipsy", "Lays", "Lay's", "Pringles", "Kellogg's", "Kelloggs",
    "Quaker", "Migos", "El Maleka", "Carrefour", "El Doha", "Halwani",
    "Oldenburger", "Philadelphia", "Lurpak", "Anchor",
    "Danone", "Activia", "Lactel", "Devondale",
    "Del Monte", "Delmonte", "Heinz", "Knorr",
    "Lipton", "Brooke Bond", "Tetley", "Ahmad Tea", "Ahmed Tea",
    "San Pellegrino", "Evian", "Volvic", "Perrier",
    "Fayrouz", "Rani", "Cappy", "Tropicana",
    "Cadbury", "Ferrero", "Nutella", "Kinder",
    "Oreo", "Digestive", "McVitie's", "McVities",
    "Ariel", "Tide", "Persil", "OMO", "Fairy", "Clorox", "Oxi",
    "Dove", "Pantene", "Head & Shoulders", "Lux", "Rexona", "Axe", "Nivea",
    "Colgate", "Oral-B", "Sensodyne", "Dettol", "Eva", "Bobana", "Garnier",
    "Tornado", "Nouval", "Fresh", "Elhelal", "Mintra", "Pasabahce",
    # Arabic brand forms
    "المراعي", "جهينة", "دومتي", "سبينيس", "امريكانا", "نسكافيه", "نستله",
    "بيبسي", "كوكاكولا", "بركة", "بسكو مصر", "لمار", "سيارا", "الملكة",
    "بوك", "كيري", "بريزيدون", "نسبريسو", "لوتس", "ابو عوف", "شيبسي",
    "ليز", "برينجلز", "كيلوجز", "كويكر", "الضحى", "حلواني", "هاينز",
    "كنور", "ليبتون", "كادبوري", "نوتيلا", "اوريو", "اريال", "برسيل",
    "تايد", "فيري", "دوف", "نيفيا", "ديتول", "تورنيدو", "نوفال", "فريش",
], key=len, reverse=True)


def normalize_brand(brand: Optional[str]) -> Optional[str]:
    """
    Resolve and canonicalize a brand name.
    Returns None if brand is empty or in invalid list.
    """
    if not brand:
        return None

    norm = normalize_text(brand)
    if not norm or norm in {"generic / unbranded", "generic", "unbranded", "please select a brand.", "false", "none", "n/a", "unknown", "0"}:
        return None

    # Check exact normalization map
    if norm in BRAND_NORMALIZATION:
        return BRAND_NORMALIZATION[norm]

    # Check case-insensitive raw
    raw_lower = brand.strip().lower()
    if raw_lower in BRAND_NORMALIZATION:
        return BRAND_NORMALIZATION[raw_lower]

    # Return capitalized clean version if not explicitly mapped
    return brand.strip().title()


def find_known_brand(text: Optional[str]) -> Optional[str]:
    """
    Scan normalized text for known brand tokens (longest match first).
    Returns canonical brand name or None.
    """
    if not text:
        return None

    norm = normalize_text(text)
    # Check word boundaries for clean matching
    padded_norm = f" {norm} "

    for candidate in TOP_KNOWN_BRANDS:
        cand_norm = normalize_text(candidate)
        if not cand_norm:
            continue
        # Check as whole word / token
        pattern = rf"(?:\b|\s|^){re.escape(cand_norm)}(?:\b|\s|$)"
        if re.search(pattern, padded_norm):
            return normalize_brand(candidate)

    return None
