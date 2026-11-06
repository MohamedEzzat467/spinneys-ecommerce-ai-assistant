# -*- coding: utf-8 -*-
"""
app/services/parser.py
======================
Compatibility facade re-exporting NLU parsing methods and models from app.nlu.parser.
"""

from __future__ import annotations

from app.nlu.parser import (
    AGENTIC_SYSTEM_PROMPT,
    CATEGORY_BY_HEAD_TERM,
    HEAD_TERM_SYNONYMS,
    KNOWN_HEAD_NOUNS,
    NLUResult,
    ParseRequest,
    ParseResult,
    extract_head_term_and_qualifiers,
    get_head_term_variants,
    parse_query,
    sanitize_query,
    strip_brand_from_query,
)

__all__ = [
    "parse_query",
    "sanitize_query",
    "strip_brand_from_query",
    "extract_head_term_and_qualifiers",
    "get_head_term_variants",
    "NLUResult",
    "ParseResult",
    "ParseRequest",
    "HEAD_TERM_SYNONYMS",
    "KNOWN_HEAD_NOUNS",
    "CATEGORY_BY_HEAD_TERM",
    "AGENTIC_SYSTEM_PROMPT",
]
