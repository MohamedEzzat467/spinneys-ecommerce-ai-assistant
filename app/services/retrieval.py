# -*- coding: utf-8 -*-
"""
app/services/retrieval.py
=========================
Compatibility facade re-exporting ProductRetriever from app.retrieval.retriever.
"""

from __future__ import annotations

from app.retrieval.retriever import (
    NON_FOOD_CATEGORIES,
    ProductRetriever,
)

__all__ = [
    "ProductRetriever",
    "NON_FOOD_CATEGORIES",
]
