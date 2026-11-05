# -*- coding: utf-8 -*-
"""
app/retrieval/hybrid_search.py
==============================
Hybrid Search Engine & Reciprocal Rank Fusion (RRF) for Spinneys Catalog.

Combines:
  1. Lexical Search (BM25):
     - In-memory BM25Okapi over retrieval_docs.parquet.
     - Optimized for exact keyword hits, pack sizes, and units (e.g. '1L', '500g', 'Almarai').
  2. Dense Vector Search:
     - Interfaces with ChromaDB vector store (intfloat/multilingual-e5-base) built in Week 2.
     - Captures synonyms, conceptual queries, and descriptive requests.
  3. Reciprocal Rank Fusion (RRF):
     - Standard formula: Score(d) = Σ [ 1 / (60 + rank_i(d)) ]
     - Returns a merged, deduplicated top-K candidate list.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from rank_bm25 import BM25Okapi

from app.core.normalizer import normalize_text

log = logging.getLogger("spinneys.hybrid_search")
ROOT = Path(__file__).resolve().parent.parent.parent


def tokenize_for_bm25(text: str) -> list[str]:
    """
    Tokenizes text for BM25 preserving numbers, units, English, and Arabic terms.
    E.g. "Almarai Milk 1L 500g" -> ['almarai', 'milk', '1l', '500g']
    """
    norm = normalize_text(text)
    # Split on whitespace and punctuation, keeping alphanumeric and unit strings
    tokens = re.findall(r"[\w\d]+", norm.lower())
    return tokens


class HybridSearchEngine:
    """
    Manages in-memory BM25 index and connects to ChromaDB vector store.
    Provides fast lexical, vector, and RRF-fused hybrid retrieval.
    """

    def __init__(
        self,
        docs_parquet_path: Optional[Path | str] = None,
        vector_store = None,
        rrf_k: int = 60,
    ):
        self.rrf_k = rrf_k
        self.vector_store = vector_store

        # Locate parquet file
        if docs_parquet_path is None:
            p1 = ROOT / "data" / "retrieval_docs.parquet"
            p2 = ROOT / "data" / "processed" / "retrieval_docs.parquet"
            docs_parquet_path = p1 if p1.exists() else p2

        self.docs_path = Path(docs_parquet_path)
        self.df_docs: pd.DataFrame = pd.DataFrame()
        self.product_ids: np.ndarray = np.array([], dtype=np.int64)
        self.id_to_idx: dict[int, int] = {}
        self.bm25: Optional[BM25Okapi] = None
        self._init_bm25()

    def _init_bm25(self) -> None:
        if not self.docs_path.exists():
            log.warning("Docs parquet not found at %s. BM25 will not be active.", self.docs_path)
            return

        t0 = time.perf_counter()
        log.info("Loading documents from %s ...", self.docs_path)
        df_docs = pd.read_parquet(self.docs_path)

        # Enforce permanent voucher and junk purge from BM25 corpus
        voucher_junk_re = re.compile(r"\b(?:voucher|gift\s*card|coupon|card)\b|قسيمة|خصم", re.IGNORECASE)
        junk_mask = df_docs["normalized_doc_text"].astype(str).str.contains(voucher_junk_re, regex=True, na=False)
        self.df_docs = df_docs[~junk_mask].copy().reset_index(drop=True)

        self.product_ids = self.df_docs["product_id"].to_numpy(dtype=np.int64)
        self.id_to_idx = {int(pid): idx for idx, pid in enumerate(self.product_ids)}

        # Build tokenized corpus
        log.info("Building in-memory BM25 index for %d products ...", len(self.df_docs))
        tokenized_corpus = [
            tokenize_for_bm25(doc) for doc in self.df_docs["normalized_doc_text"]
        ]
        self.bm25 = BM25Okapi(tokenized_corpus)
        log.info("BM25 index ready in %.2f ms", (time.perf_counter() - t0) * 1000)

    def search_bm25(
        self,
        query: str,
        top_k: int = 50,
        candidate_ids: Optional[set[int]] = None,
    ) -> list[tuple[int, float]]:
        """
        Runs BM25 lexical search.
        Returns: list of (product_id, bm25_score) sorted descending.
        """
        if self.bm25 is None or not query.strip():
            return []

        tokens = tokenize_for_bm25(query)
        if not tokens:
            return []

        scores = self.bm25.get_scores(tokens)

        # If candidate_ids filter is provided, mask out non-candidates
        if candidate_ids is not None:
            # Mask out non-candidate indices
            cand_mask = np.zeros(len(scores), dtype=bool)
            valid_indices = [self.id_to_idx[cid] for cid in candidate_ids if cid in self.id_to_idx]
            if not valid_indices:
                return []
            cand_mask[valid_indices] = True
            scores = scores * cand_mask

        # Filter strictly positive scores
        pos_mask = scores > 0
        num_pos = np.count_nonzero(pos_mask)
        if num_pos == 0:
            return []

        k = min(top_k, num_pos)
        part_idx = np.argpartition(scores, -k)[-k:]
        sorted_top_idx = part_idx[np.argsort(scores[part_idx])[::-1]]

        results = [
            (int(self.product_ids[idx]), float(scores[idx]))
            for idx in sorted_top_idx
            if scores[idx] > 0
        ]
        return results

    def search_vector(
        self,
        query: str,
        top_k: int = 50,
        candidate_ids: Optional[set[int]] = None,
    ) -> list[tuple[int, float]]:
        """
        Runs dense vector search via ChromaDB vector store.
        Returns: list of (product_id, similarity_score) sorted descending.
        """
        if self.vector_store is None:
            return []

        try:
            # Query vector store (handles query encoding with multilingual-e5)
            # Distance in Chroma is cosine distance (0 = identical, 1 = orthogonal)
            raw_res = self.vector_store.search(
                query=query,
                top_k=top_k * 2 if candidate_ids else top_k,
            )
            results = []
            for item in raw_res:
                try:
                    pid = int(item.product_id)
                except (ValueError, TypeError):
                    continue

                if candidate_ids is not None and pid not in candidate_ids:
                    continue

                sim = 1.0 - float(item.distance)
                results.append((pid, sim))
                if len(results) >= top_k:
                    break

            return results
        except Exception as exc:
            log.warning("Vector search query error: %s", exc)
            return []

    def search_hybrid(
        self,
        query: str,
        top_k: int = 20,
        candidate_ids: Optional[set[int]] = None,
        bm25_weight: float = 1.0,
        vector_weight: float = 1.0,
    ) -> list[tuple[int, float]]:
        """
        Combines BM25 and Vector Search using Reciprocal Rank Fusion (RRF):
        Score(d) = Σ [ w_i / (60 + rank_i(d)) ]
        """
        bm25_hits = self.search_bm25(query, top_k=50, candidate_ids=candidate_ids)
        vector_hits = self.search_vector(query, top_k=50, candidate_ids=candidate_ids)

        # If no vector search results (e.g. fast-path or no vector store), fall back to BM25
        if not vector_hits:
            return bm25_hits[:top_k]

        rrf_scores: dict[int, float] = {}

        # 1. Add BM25 RRF score
        for rank, (pid, _) in enumerate(bm25_hits, start=1):
            rrf_scores[pid] = rrf_scores.get(pid, 0.0) + (bm25_weight / (self.rrf_k + rank))

        # 2. Add Vector RRF score
        for rank, (pid, _) in enumerate(vector_hits, start=1):
            rrf_scores[pid] = rrf_scores.get(pid, 0.0) + (vector_weight / (self.rrf_k + rank))

        # Sort by RRF score descending
        sorted_rrf = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_rrf[:top_k]
