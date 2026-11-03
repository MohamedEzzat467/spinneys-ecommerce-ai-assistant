"""
app/retrieval/vector_store.py
==============================
Vector Search module for Spinneys Conversational Shopping Assistant.

Provides a VectorStore class that wraps ChromaDB and supports:
  • Semantic (dense) vector search using intfloat/multilingual-e5-base
  • Metadata filtering on: brand, price_max, in_stock
  • Configurable top-K results
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# ── Load .env from project root ───────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

log = logging.getLogger(__name__)

COLLECTION_NAME = "spinneys_products"


# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SearchFilters:
    """
    Optional metadata filters to narrow the vector search results.

    Attributes
    ----------
    brand : str | None
        Exact brand name match (case-insensitive prefix on Chroma's ``$eq``).
    price_max : float | None
        Maximum price (inclusive). Maps to ``$lte`` operator.
    in_stock : bool | None
        If True → only in-stock items (stock_qty > 0).
        If False → only out-of-stock items.
        If None → no restriction.
    """
    brand: Optional[str] = None
    price_max: Optional[float] = None
    in_stock: Optional[bool] = None


@dataclass
class SearchResult:
    """Single product returned by a vector search."""
    product_id: str
    product_name: str
    brand: str
    category: str
    price: float
    in_stock: bool
    distance: float                    # cosine distance (lower = more similar)
    document: str = field(repr=False)  # raw passage text stored in Chroma


# ─────────────────────────────────────────────────────────────────────────────
# VectorStore
# ─────────────────────────────────────────────────────────────────────────────

class VectorStore:
    """
    Thin wrapper around ChromaDB that provides semantic search
    with optional metadata pre-filtering.

    Parameters
    ----------
    db_path : str
        Filesystem path to the ChromaDB persistent directory.
    embedding_model : str
        HuggingFace model ID used to encode queries.
    top_k : int
        Default number of results to return.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        embedding_model: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> None:
        self._db_path = db_path or os.getenv("VECTOR_DB_PATH", "./data/vectordb")
        self._model_name = embedding_model or os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-base")
        self._top_k = top_k or int(os.getenv("TOP_K", 20))

        log.info("Initialising VectorStore | db=%s | model=%s | top_k=%d",
                 self._db_path, self._model_name, self._top_k)

        # Lazy-loaded members (initialised on first use)
        self._chroma_client: Optional[chromadb.PersistentClient] = None
        self._collection: Optional[chromadb.Collection] = None
        self._encoder: Optional[SentenceTransformer] = None

    # ── Private helpers ────────────────────────────────────────────────────────

    def _get_collection(self) -> chromadb.Collection:
        if self._collection is None:
            self._chroma_client = chromadb.PersistentClient(
                path=self._db_path,
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._chroma_client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            log.info("ChromaDB collection loaded — %d items", self._collection.count())
        return self._collection

    def _get_encoder(self) -> SentenceTransformer:
        if self._encoder is None:
            log.info("Loading encoder model: %s", self._model_name)
            self._encoder = SentenceTransformer(self._model_name)
        return self._encoder

    def _embed_query(self, query: str) -> list[float]:
        """
        Encode a user query.
        E5 models expect the 'query:' prefix for query text.
        """
        prefixed = f"query: {query}"
        encoder = self._get_encoder()
        vector = encoder.encode(prefixed, normalize_embeddings=True)
        return vector.tolist()

    @staticmethod
    def _build_where_clause(filters: SearchFilters) -> Optional[dict]:
        """
        Translate a SearchFilters object into a ChromaDB ``where`` dict.

        ChromaDB operators reference:
            $eq, $ne, $gt, $gte, $lt, $lte  (for scalars)
            $and, $or                        (logical combinators)
        """
        conditions: list[dict] = []

        if filters.brand:
            conditions.append({"brand": {"$eq": filters.brand}})

        if filters.price_max is not None:
            conditions.append({"price": {"$lte": float(filters.price_max)}})

        if filters.in_stock is not None:
            stock_val = 1 if filters.in_stock else 0
            conditions.append({"in_stock": {"$eq": stock_val}})

        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    @staticmethod
    def _parse_result(
        id_: str,
        document: str,
        metadata: dict,
        distance: float,
    ) -> SearchResult:
        return SearchResult(
            product_id=id_,
            product_name=metadata.get("product_name", ""),
            brand=metadata.get("brand", ""),
            category=metadata.get("category", ""),
            price=float(metadata.get("price", 0.0)),
            in_stock=bool(metadata.get("in_stock", 0)),
            distance=distance,
            document=document,
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        filters: Optional[SearchFilters] = None,
        top_k: Optional[int] = None,
    ) -> list[SearchResult]:
        """
        Perform a semantic vector search.

        Parameters
        ----------
        query : str
            Natural-language query (Arabic or English).
        filters : SearchFilters | None
            Optional metadata filters (brand, price_max, in_stock).
        top_k : int | None
            Override the default top-K for this call.

        Returns
        -------
        list[SearchResult]
            Ranked list of matching products (most similar first).
        """
        k = top_k or self._top_k
        query_vec = self._embed_query(query)
        collection = self._get_collection()

        where_clause = self._build_where_clause(filters) if filters else None

        log.debug("Querying ChromaDB | query=%r | where=%s | top_k=%d", query, where_clause, k)

        query_kwargs: dict = {
            "query_embeddings": [query_vec],
            "n_results": min(k, collection.count() or 1),
            "include": ["documents", "metadatas", "distances"],
        }
        if where_clause:
            query_kwargs["where"] = where_clause

        try:
            raw = collection.query(**query_kwargs)
        except Exception as exc:
            log.error("ChromaDB query failed: %s", exc)
            raise

        results: list[SearchResult] = []
        ids = raw["ids"][0]
        docs = raw["documents"][0]
        metas = raw["metadatas"][0]
        dists = raw["distances"][0]

        for id_, doc, meta, dist in zip(ids, docs, metas, dists):
            results.append(self._parse_result(id_, doc, meta, dist))

        log.debug("  → %d results returned", len(results))
        return results

    def collection_size(self) -> int:
        """Return the total number of items in the ChromaDB collection."""
        return self._get_collection().count()

    def is_ready(self) -> bool:
        """Return True if the collection exists and has at least one item."""
        try:
            return self.collection_size() > 0
        except Exception:
            return False
