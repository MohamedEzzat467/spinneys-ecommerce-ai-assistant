# -*- coding: utf-8 -*-
"""
app/retrieval/recipe_engine.py
==============================
Smart Cart & Recipe-to-Cart Reasoning for Spinneys Assistant.

Workflow:
  1. Identifies recipe intent (e.g., "عايز اعمل مكرونة بشاميل", "how to make pancakes").
  2. Deconstructs dish into core grocery ingredients using Groq LLM (with robust built-in fallbacks).
  3. Executes retrieval for each ingredient independently against real catalog products.
  4. Assembles a Smart Cart response JSON grounded 100% in real Spinneys catalog items.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from app.core.llm import get_llm_client
from app.core.normalizer import normalize_text

log = logging.getLogger("spinneys.recipe_engine")

# Curated recipe templates for instant zero-latency decomposition & offline fallback
CURATED_RECIPES: dict[str, list[dict[str, str]]] = {
    "مكرونة بشاميل": [
        {"ingredient": "مكرونة قلم", "query": "مكرونة قلم", "category": "Pasta"},
        {"ingredient": "حليب", "query": "حليب", "category": "Milk"},
        {"ingredient": "دقيق", "query": "دقيق", "category": "Baking"},
        {"ingredient": "سمنة أو زبدة", "query": "زبدة", "category": "Dairy"},
        {"ingredient": "لحم مفروم", "query": "مفروم", "category": "Meat"},
    ],
    "كشري": [
        {"ingredient": "أرز مصري", "query": "أرز", "category": "Rice"},
        {"ingredient": "مكرونة", "query": "مكرونة", "category": "Pasta"},
        {"ingredient": "عدس بجبة", "query": "عدس", "category": "Legumes"},
        {"ingredient": "حمص", "query": "حمص", "category": "Canned Food"},
        {"ingredient": "صلصة طماطم", "query": "صلصة طماطم", "category": "Sauces"},
    ],
    "ملوخية": [
        {"ingredient": "ملوخية خضراء", "query": "ملوخية", "category": "Vegetables"},
        {"ingredient": "ثوم مفروم", "query": "ثوم", "category": "Spices"},
        {"ingredient": "كزبرة جافة", "query": "كزبرة", "category": "Spices"},
        {"ingredient": "سمنة بلدي", "query": "سمنة", "category": "Dairy"},
        {"ingredient": "مرقة دجاج", "query": "مرقة دجاج", "category": "Bouillon"},
    ],
    "بيتزا": [
        {"ingredient": "دقيق فاخر", "query": "دقيق", "category": "Baking"},
        {"ingredient": "جبنة موتزاريلا", "query": "موتزاريلا", "category": "Cheese"},
        {"ingredient": "صلصة بيتزا", "query": "صلصة", "category": "Sauces"},
        {"ingredient": "خميرة فورية", "query": "خميرة", "category": "Baking"},
        {"ingredient": "زيت زيتون", "query": "زيت زيتون", "category": "Oils"},
    ],
    "سلطة خضراء": [
        {"ingredient": "طماطم", "query": "طماطم", "category": "Vegetables"},
        {"ingredient": "خيار", "query": "خيار", "category": "Vegetables"},
        {"ingredient": "خس", "query": "خس", "category": "Vegetables"},
        {"ingredient": "زيت زيتون", "query": "زيت زيتون", "category": "Oils"},
        {"ingredient": "ليمون", "query": "ليمون", "category": "Fruits"},
    ],
    "وجبة صحية": [
        {"ingredient": "تونة دايت خفيفة (بروتين نقي)", "query": "تونة دايت", "category": "Canned Food"},
        {"ingredient": "صدور دجاج طازجة (بروتين قليل الدهون)", "query": "صدور دجاج", "category": "Meat & Poultry"},
        {"ingredient": "جبنة قريش طبيعية (بروتين كازين خفيف)", "query": "جبنة قريش", "category": "Dairy"},
        {"ingredient": "شوفان كامل الحبة (ألياف صحية مشبعة)", "query": "شوفان", "category": "Breakfast Cereals"},
        {"ingredient": "خضار مشكل مجهز (فيتامينات وسعرات منخفضة)", "query": "خضار مشكل", "category": "Vegetables"},
    ],
    "غداء صحي": [
        {"ingredient": "تونة دايت خفيفة (بروتين نقي)", "query": "تونة دايت", "category": "Canned Food"},
        {"ingredient": "صدور دجاج طازجة (بروتين قليل الدهون)", "query": "صدور دجاج", "category": "Meat & Poultry"},
        {"ingredient": "جبنة قريش طبيعية (بروتين كازين خفيف)", "query": "جبنة قريش", "category": "Dairy"},
        {"ingredient": "شوفان كامل الحبة (ألياف صحية مشبعة)", "query": "شوفان", "category": "Breakfast Cereals"},
        {"ingredient": "خضار مشكل مجهز (فيتامينات وسعرات منخفضة)", "query": "خضار مشكل", "category": "Vegetables"},
    ],
    "وجبة قليلة السعرات": [
        {"ingredient": "تونة دايت خفيفة (بروتين نقي)", "query": "تونة دايت", "category": "Canned Food"},
        {"ingredient": "صدور دجاج طازجة (بروتين قليل الدهون)", "query": "صدور دجاج", "category": "Meat & Poultry"},
        {"ingredient": "جبنة قريش طبيعية (بروتين كازين خفيف)", "query": "جبنة قريش", "category": "Dairy"},
        {"ingredient": "شوفان كامل الحبة (ألياف صحية مشبعة)", "query": "شوفان", "category": "Breakfast Cereals"},
        {"ingredient": "خضار مشكل مجهز (فيتامينات وسعرات منخفضة)", "query": "خضار مشكل", "category": "Vegetables"},
    ],
    "pancakes": [
        {"ingredient": "Flour", "query": "flour", "category": "Baking"},
        {"ingredient": "Milk", "query": "milk", "category": "Milk"},
        {"ingredient": "Eggs", "query": "eggs", "category": "Eggs"},
        {"ingredient": "Butter", "query": "butter", "category": "Dairy"},
        {"ingredient": "Sugar", "query": "sugar", "category": "Sugar"},
    ],
}


class RecipeEngine:
    """Decomposes dishes into ingredient queries and builds a smart grocery cart."""

    def __init__(self, retriever: Any):
        self.retriever = retriever
        self.llm = get_llm_client()

    def extract_dish_name(self, text: str) -> str:
        """Extracts dish keyword from conversational phrases."""
        norm = normalize_text(text)

        # Check for healthy meal / diet recommendation expressions
        healthy_kw = re.search(
            r"\b(و?صح[يية][هة]?|و?قليل[هة]\w*|و?قليله\w*|و?منخفض[هة]\w*|و?سعرات\w*|دايت|رجيم|كيتو|healthy|low[- ]?cal(?:orie)?|diet)\b",
            norm,
            re.IGNORECASE,
        )
        meal_req = re.search(
            r"\b(و?وجب[هة]\w*|و?غداء|و?غذاء|و?عشاء|و?فطار|و?افطار|و?سناك\w*|و?اكل\w*|lunch|dinner|breakfast|snack|meal|food)\b",
            norm,
            re.IGNORECASE,
        )
        if healthy_kw and meal_req:
            return "وجبة صحية قليلة السعرات"

        patterns = [
            r"(?:طريقة عمل|طريقة تحضير|عايز اعمل|عاوز اعمل|مكونات|مقادير|recipe for|how to make|make|cook)\s+(.+)",
        ]
        for p in patterns:
            m = re.search(p, norm, re.IGNORECASE)
            if m:
                dish = m.group(1).strip()
                # Remove filler words
                dish = re.sub(r"\b(من فضلك|لو سمحت|please)\b", "", dish, flags=re.IGNORECASE).strip()
                return dish
        return norm

    def decompose_dish(self, dish: str) -> list[dict[str, str]]:
        """
        Decomposes dish name into a list of ingredient specifications:
        [{"ingredient": "...", "query": "...", "category": "..."}]
        """
        dish_norm = normalize_text(dish).lower().strip()

        # 1. Check curated templates first (zero latency)
        for name, ingredients in CURATED_RECIPES.items():
            norm_name = normalize_text(name).lower().strip()
            if norm_name in dish_norm or dish_norm in norm_name:
                return ingredients

        # 2. Use Groq LLM if available
        if self.llm.is_available:
            prompt = (
                f"You are a grocery shopping assistant. Break down the dish '{dish}' into 3 to 6 essential grocery ingredients.\n"
                "Output JSON format only:\n"
                "[\n"
                '  {"ingredient": "ingredient name", "query": "catalog search keyword in Arabic or English", "category": "category name"}\n'
                "]"
            )
            try:
                resp = self.llm.complete_json(
                    system_prompt="You are a professional chef and grocery shopping assistant. Output pure JSON list only.",
                    user_prompt=prompt,
                )
                items = resp.content
                if isinstance(items, list) and len(items) > 0:
                    sanitized = []
                    for it in items:
                        if isinstance(it, dict) and "ingredient" in it and "query" in it:
                            sanitized.append({
                                "ingredient": str(it["ingredient"]),
                                "query": str(it.get("query", it["ingredient"])),
                                "category": str(it.get("category", "General")),
                            })
                    if sanitized:
                        return sanitized
            except Exception as exc:
                log.warning("LLM recipe decomposition failed: %s", exc)

        # 3. Fallback generic decomposition: search the dish name itself
        return [{"ingredient": dish, "query": dish, "category": "General"}]

    def generate_smart_cart(self, user_query: str, dish_override: Optional[str] = None) -> dict[str, Any]:
        """
        Main entry point for recipe-to-cart:
          1. Extracts dish.
          2. Decomposes into ingredients.
          3. Retrieves real Spinneys catalog items for each ingredient.
        """
        dish = dish_override or self.extract_dish_name(user_query)
        ingredients = self.decompose_dish(dish)

        cart = []
        for ing in ingredients:
            ing_name = ing["ingredient"]
            search_query = ing["query"]
            cat = ing.get("category", "General")

            # Retrieve top matching products from catalog
            retrieval_res = self.retriever.retrieve(
                query=search_query,
                limit=3,
                mode="auto",
                is_internal=True,
            )
            matched_products = retrieval_res.get("products", [])

            if matched_products:
                cart.append({
                    "ingredient": ing_name,
                    "category": cat,
                    "status": "in_stock",
                    "products": matched_products,
                })
            else:
                cart.append({
                    "ingredient": ing_name,
                    "category": cat,
                    "status": "out_of_stock",
                    "products": [],
                })

        return {
            "query": user_query,
            "intent": "recipe",
            "dish": dish,
            "cart": cart,
        }
