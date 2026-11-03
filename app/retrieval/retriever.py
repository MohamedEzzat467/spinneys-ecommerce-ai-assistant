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
from app.nlu.parser import parse_query as nlu_parse_query, sanitize_query
from app.retrieval.hybrid_search import HybridSearchEngine
from app.retrieval.recipe_engine import RecipeEngine

log = logging.getLogger("spinneys.retriever")
ROOT = Path(__file__).resolve().parent.parent.parent

# Negation detection pattern
NEGATION_RE = re.compile(
    r"\b(مش|مش عايز|بدون|من غير|غير|بلاش|not|without|except|no|excluding)\s+([A-Za-z\u0621-\u064A0-9]+)",
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
        mode: str = "auto",  # "auto", "rules", "hybrid", "bm25"
        filter_overrides: Optional[dict[str, Any]] = None,
        is_internal: bool = False,
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
                "min_price": nlu.price_min,
                "max_price": nlu.price_max,
                "in_stock": nlu.in_stock,
                "sort": nlu.sort,
            }

        # Apply any explicit filter overrides
        if filter_overrides:
            filters.update(filter_overrides)

        brand = filters.get("brand")
        exclude_brands = filters.get("exclude_brands", [])
        category = filters.get("category")
        min_price = filters.get("min_price")
        max_price = filters.get("max_price")
        in_stock = filters.get("in_stock")
        sort_order = filters.get("sort")
        keyword = filters.get("query")

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

        # 1. Brand filter
        if brand:
            b_norm = brand.strip().lower()
            mask &= (df["_brand_lower"] == b_norm)

        # 2. Exclude brands
        if exclude_brands:
            ex_set = {b.strip().lower() for b in exclude_brands if b}
            if ex_set:
                mask &= (~df["_brand_lower"].isin(ex_set))

        # 3. Category filter
        if category:
            cat_norm = category.strip().lower()
            mask &= (df["_category_lower"] == cat_norm) | (df["_category_lower"].str.startswith(cat_norm))

        # 4. Price filters
        if max_price is not None:
            mask &= (df["effective_price"] <= float(max_price))
        if min_price is not None:
            mask &= (df["effective_price"] >= float(min_price))

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
                        avail = p_rec["availability"] if p_rec else False
                        final_score = score + (0.5 if avail else 0.0)
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
                        avail = p_rec["availability"] if p_rec else False
                        final_score = score + (0.01 if avail else 0.0)
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
                    # Boost in-stock candidates
                    scored_candidates = []
                    for pid, score in bm25_results:
                        p_rec = self.products_by_id.get(pid)
                        avail = p_rec["availability"] if p_rec else False
                        # +2.0 boost for in-stock items
                        final_score = score + (2.0 if avail else 0.0)
                        scored_candidates.append((pid, final_score))

                    scored_candidates.sort(key=lambda x: x[1], reverse=True)
                    ranked_product_ids = [pid for pid, _ in scored_candidates]

        # If no keyword matches or pure filter query, rank from candidate_df
        if not ranked_product_ids:
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
                matched_subset = candidate_df[candidate_df["product_id"].isin(ranked_product_ids)]
                is_asc = (sort_order == "price_asc")
                sorted_cands = matched_subset.sort_values(
                    by=["availability", "effective_price"],
                    ascending=[False, is_asc],
                )
                ranked_product_ids = sorted_cands["product_id"].to_list()

        # Step 4: Format Product Results
        selected_ids = ranked_product_ids[:limit]
        final_products = []
        for pid in selected_ids:
            rec = self.products_by_id.get(pid)
            if rec:
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
