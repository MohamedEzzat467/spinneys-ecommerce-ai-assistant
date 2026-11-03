# -*- coding: utf-8 -*-
"""
scripts/ingest.py
=================
Spinneys Product Ingestion Pipeline  (v2 — Full Catalogue with Imputation)
---------------------------------------------------------------------------
Changes vs v1:
  • LEFT JOIN on attributes / JSON_TABLE  → no products lost due to missing brand
  • Brand Imputation:  corrupt brand → name-based lookup → 'Generic / Unbranded'
  • Brand Normalization: typo / alias map applied before indexing
  • Products without English name still excluded (INNER JOIN pn — required)
  • Target: ≥ 25,000 products indexed in ChromaDB

Usage:
    python scripts/ingest.py [--batch-size 64] [--reset]
"""

import os
import re
import sys
import argparse
import logging
from pathlib import Path

# ── Project root on sys.path ──────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql
import pandas as pd
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest")

# ── Constants ─────────────────────────────────────────────────────────────────
COLLECTION_NAME = "spinneys_products"

# Placeholder / corrupt brand values that trigger imputation
INVALID_BRANDS: set[str] = {
    "", "please select a brand.", "false", "true",
    "n/a", "unknown", "none", "null", "0", "undefined",
}

# ── Import Shared Normalizer (Single Source of Truth) ────────────────────────
from app.core.normalizer import (
    BRAND_NORMALIZATION,
    TOP_KNOWN_BRANDS,
    normalize_brand,
    normalize_text,
)   # longest first → greedy match avoids partial hits


# ─────────────────────────────────────────────────────────────────────────────
# 1. Database helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_connection() -> pymysql.Connection:
    """Return a live PyMySQL connection using .env credentials."""
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "spinneys_database"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=30,
    )


def fetch_products(conn: pymysql.Connection) -> pd.DataFrame:
    """
    Pull ALL products from spinneys_database using LEFT JOINs.

    Key change vs v1
    ----------------
    • catalog_productattributes   → LEFT JOIN  (products without attributes kept)
    • JSON_TABLE                  → LEFT JOIN  (NULL brand_value allowed)
    • Brand filter REMOVED from SQL WHERE  → imputation done in Python
    • Only hard filter kept: default_price > 0  +  English name exists

    Tables used
    -----------
    catalog_product              → p.id, p.sku, p.default_price
    catalog_productname          → English name (INNER JOIN — name is required)
    catalog_productattributes    → brand JSON array (LEFT JOIN)
    catalog_product_categories   → many-to-many link (LEFT JOIN)
    catalog_categoryname         → English category (LEFT JOIN)
    catalog_productstock         → SUM(quantity) per sku (LEFT JOIN)
    """
    query = """
        SELECT
            p.id                                        AS product_id,
            p.sku                                       AS sku,
            pn.name                                     AS product_name,
            CAST(jt.brand_value AS CHAR)                AS brand_raw,
            cn.name                                     AS category,
            p.default_price                             AS price,
            COALESCE(SUM(ps.quantity), 0)               AS stock_qty,
            p.default_special_price                     AS special_price

        FROM catalog_product p

        -- ── English product name (required) ───────────────────────────────────
        INNER JOIN catalog_productname pn
            ON pn.product_id = p.id
            AND pn.language  = 'English'

        -- ── Brand: LEFT JOIN so products without attributes are kept ──────────
        LEFT JOIN catalog_productattributes pa
            ON pa.product_id = p.id
            AND pa.language  = 'English'

        -- ── JSON_TABLE as LEFT JOIN to allow NULL brand_value ─────────────────
        LEFT JOIN JSON_TABLE(
            COALESCE(pa.attributes, '[]'),
            '$[*]'
            COLUMNS (
                attr_code   VARCHAR(100) PATH '$.code',
                brand_value TEXT         PATH '$.value'
            )
        ) AS jt ON jt.attr_code = 'product_brand_id'

        -- ── Category (first English, excluding test categories) ───────────────
        LEFT JOIN catalog_product_categories pc
            ON pc.product_id = p.id
        LEFT JOIN catalog_categoryname cn
            ON cn.category_id = pc.category_id
            AND cn.language   = 'English'
            AND LOWER(cn.name) NOT IN ('test', 'test1', 'test2', 'test3', 'demo')

        -- ── Stock: sum across all source codes ────────────────────────────────
        LEFT JOIN catalog_productstock ps
            ON ps.sku = p.sku

        WHERE
            p.default_price > 0

        GROUP BY
            p.id,
            p.sku,
            pn.name,
            jt.brand_value,
            cn.name,
            p.default_price,
            p.default_special_price

        ORDER BY p.id
    """
    log.info("Fetching products from MySQL (LEFT JOIN — full catalogue) …")
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()

    df = pd.DataFrame(rows)
    log.info("  → %d raw rows fetched", len(df))
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 2. Brand Imputation & Normalization
# ─────────────────────────────────────────────────────────────────────────────

def _impute_brand_from_name(product_name: str) -> str | None:
    """
    Scan product_name for a known brand token (longest match first).
    Returns the canonical brand name or None if not found.
    """
    name_lower = product_name.lower()
    for brand in TOP_KNOWN_BRANDS:
        if brand.lower() in name_lower:
            # Normalize through map if present, else return as-is
            return BRAND_NORMALIZATION.get(brand.lower(), brand)
    return None


def normalize_brand(brand: str) -> str:
    """Apply the normalization map (typo/alias correction)."""
    return BRAND_NORMALIZATION.get(brand.strip().lower(), brand.strip())


def impute_and_normalize_brands(df: pd.DataFrame) -> pd.DataFrame:
    """
    Three-pass brand resolution:
      Pass 1: Normalize known-good brands (fix typos/aliases)
      Pass 2: Attempt name-based imputation for corrupt/missing brands
      Pass 3: Fall back to 'Generic / Unbranded' — product IS KEPT
    """
    df = df.copy()
    df["brand_raw"] = df["brand_raw"].fillna("").astype(str).str.strip()

    # Metrics counters
    n_good = n_imputed = n_fallback = 0
    brands = []

    for idx, row in df.iterrows():
        raw = row["brand_raw"]
        raw_lower = raw.lower()

        if raw_lower and raw_lower not in INVALID_BRANDS:
            # ── Pass 1: Valid brand — normalize ──────────────────────────────
            brands.append(normalize_brand(raw))
            n_good += 1
        else:
            # ── Pass 2: Impute from product name ─────────────────────────────
            imputed = _impute_brand_from_name(row["product_name"])
            if imputed:
                brands.append(imputed)
                n_imputed += 1
            else:
                # ── Pass 3: Generic fallback ──────────────────────────────────
                brands.append("Generic / Unbranded")
                n_fallback += 1

    df["brand"] = brands

    log.info(
        "Brand resolution: %d normalized  |  %d imputed from name  |  %d → Generic / Unbranded",
        n_good, n_imputed, n_fallback,
    )
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 3. Data-quality cleaning
# ─────────────────────────────────────────────────────────────────────────────

def clean_products(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply data-quality rules and return a clean, 1-row-per-product DataFrame.

    Rules
    -----
    1. Normalize string columns (strip / fillna)
    2. Price > 0 (defence-in-depth — SQL already filtered)
    3. Product name must be non-empty (defence-in-depth)
    4. Dedup by product_id — keep row with best (non-empty) category
       (LEFT JOIN categories causes fan-out)
    5. Normalize stock_qty to int
    """
    original = len(df)

    # ── 1. Normalize strings ──────────────────────────────────────────────────
    for col in ["product_name", "brand", "category", "sku"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()

    # ── 2. Price ──────────────────────────────────────────────────────────────
    before = len(df)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df[df["price"].notna() & (df["price"] > 0)]
    log.info("  [price filter]   removed %d rows", before - len(df))

    # ── 3. Name ───────────────────────────────────────────────────────────────
    before = len(df)
    df = df[df["product_name"] != ""]
    log.info("  [name filter]    removed %d rows", before - len(df))

    # ── 4. Dedup by product_id ────────────────────────────────────────────────
    before = len(df)
    df["_cat_rank"] = df["category"].apply(lambda c: 0 if c else 1)
    df = (
        df.sort_values("_cat_rank")
          .drop_duplicates(subset=["product_id"], keep="first")
          .drop(columns=["_cat_rank"])
    )
    log.info("  [dedup]          removed %d duplicate rows  →  %d unique products", before - len(df), len(df))

    # ── 5. Stock qty ──────────────────────────────────────────────────────────
    df["stock_qty"] = pd.to_numeric(df["stock_qty"], errors="coerce").fillna(0).astype(int)

    log.info(
        "Cleaning complete: %d / %d rows kept (%.1f%%)",
        len(df), original, 100 * len(df) / max(original, 1),
    )
    return df.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Document builder
# ─────────────────────────────────────────────────────────────────────────────

def build_document(row: pd.Series) -> str:
    """
    Build a text passage for embedding (multilingual-e5-base 'passage:' prefix).
    Includes brand even if 'Generic / Unbranded' — helps semantic recall.
    """
    parts = [f"passage: {row['product_name']}"]

    if row.get("sku"):
        parts.append(f"SKU: {row['sku']}")

    brand = row.get("brand", "Generic / Unbranded")
    parts.append(f"Brand: {brand}")

    if row.get("category"):
        parts.append(f"Category: {row['category']}")

    price = float(row["price"])
    special = row.get("special_price")
    if special and pd.notna(special) and float(special) > 0 and float(special) < price:
        parts.append(f"Price: {price:.2f} EGP (Special: {float(special):.2f} EGP)")
    else:
        parts.append(f"Price: {price:.2f} EGP")

    stock_label = "In Stock" if int(row.get("stock_qty", 0) or 0) > 0 else "Out of Stock"
    parts.append(f"Availability: {stock_label}")

    return " | ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Embedding
# ─────────────────────────────────────────────────────────────────────────────

def load_embedding_model(model_name: str) -> SentenceTransformer:
    import torch
    num_threads = os.cpu_count() or 8
    torch.set_num_threads(num_threads)
    log.info("Loading embedding model: %s (torch threads=%d)", model_name, num_threads)
    model = SentenceTransformer(model_name)
    log.info("  Model ready — dim: %d", model.get_sentence_embedding_dimension())
    return model


def embed_documents(
    model: SentenceTransformer,
    docs: list[str],
    batch_size: int,
) -> list[list[float]]:
    log.info("Embedding %d documents (batch=%d) …", len(docs), batch_size)
    vectors = model.encode(
        docs,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    return vectors.tolist()


# ─────────────────────────────────────────────────────────────────────────────
# 6. ChromaDB helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_chroma_collection(db_path: str, reset: bool = False) -> chromadb.Collection:
    Path(db_path).mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=db_path,
        settings=Settings(anonymized_telemetry=False),
    )
    if reset:
        log.warning("--reset: deleting existing collection '%s'", COLLECTION_NAME)
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    log.info("ChromaDB collection '%s' — %d existing items", COLLECTION_NAME, collection.count())
    return collection


def upsert_to_chroma(
    collection: chromadb.Collection,
    df: pd.DataFrame,
    embeddings: list[list[float]],
) -> None:
    """
    Upsert all products to ChromaDB.

    Metadata schema
    ---------------
    product_name   : str
    sku            : str
    brand          : str   (normalized; 'Generic / Unbranded' for unknown)
    category       : str   ('' if uncategorized)
    price          : float
    special_price  : float (0.0 if none)
    in_stock       : int   (1 / 0)
    brand_imputed  : int   (1 = imputed from name or fallback; 0 = original)
    """
    ids: list[str]   = []
    docs: list[str]  = []
    metas: list[dict]= []

    for _, row in df.iterrows():
        ids.append(str(row["product_id"]))
        docs.append(build_document(row))

        special = row.get("special_price")
        sp_val  = float(special) if (special is not None and pd.notna(special) and float(special) > 0) else 0.0

        raw_lower = str(row.get("brand_raw", "")).strip().lower()
        is_imputed = 1 if (not raw_lower or raw_lower in INVALID_BRANDS) else 0

        metas.append({
            "product_name":  str(row["product_name"]),
            "sku":           str(row.get("sku", "")),
            "brand":         str(row.get("brand", "Generic / Unbranded")),
            "category":      str(row.get("category", "")),
            "price":         float(row["price"]),
            "special_price": sp_val,
            "in_stock":      1 if int(row.get("stock_qty", 0) or 0) > 0 else 0,
            "brand_imputed": is_imputed,
        })

    CHUNK = 512
    for start in range(0, len(ids), CHUNK):
        end = start + CHUNK
        collection.upsert(
            ids=ids[start:end],
            embeddings=embeddings[start:end],
            documents=docs[start:end],
            metadatas=metas[start:end],
        )
        log.info("  Upserted chunk %d–%d", start, min(end, len(ids)))

    log.info("✓ Total items in collection: %d", collection.count())


# ─────────────────────────────────────────────────────────────────────────────
# 7. Main
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Spinneys product ingestion pipeline v2")
    p.add_argument("--batch-size", type=int, default=64, help="Embedding batch size (default: 64)")
    p.add_argument("--reset", action="store_true", help="Delete existing ChromaDB collection first")
    return p.parse_args()


def main() -> None:
    args  = parse_args()
    embed = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-base")
    vdb   = os.getenv("VECTOR_DB_PATH",  "./data/vectordb")

    # Step 1 — Fetch (LEFT JOIN, no brand filter in SQL)
    conn = get_connection()
    try:
        raw_df = fetch_products(conn)
    finally:
        conn.close()

    if raw_df.empty:
        log.error("No products returned. Aborting.")
        sys.exit(1)

    # Step 2 — Brand imputation + normalization
    imputed_df = impute_and_normalize_brands(raw_df)

    # Step 3 — Clean (dedup, price, name)
    clean_df = clean_products(imputed_df)
    if clean_df.empty:
        log.error("All rows filtered out. Aborting.")
        sys.exit(1)

    # Step 4 — Brand coverage report
    total = len(clean_df)
    branded   = (clean_df["brand"] != "Generic / Unbranded").sum()
    imputed   = ((clean_df.get("brand_raw", pd.Series([""])).fillna("").str.strip().str.lower().isin(INVALID_BRANDS) |
                  clean_df.get("brand_raw", pd.Series([""])).fillna("").str.strip() == "") &
                 (clean_df["brand"] != "Generic / Unbranded")).sum()
    generic   = (clean_df["brand"] == "Generic / Unbranded").sum()
    log.info("── Brand coverage after imputation ─────────────────────")
    log.info("  Total products  : %d", total)
    log.info("  With brand      : %d (%.1f%%)", branded, 100*branded/total)
    log.info("  Generic         : %d (%.1f%%)", generic, 100*generic/total)

    # Step 5 — Build documents
    documents = [build_document(row) for _, row in clean_df.iterrows()]

    # Step 6 — Embed
    model      = load_embedding_model(embed)
    embeddings = embed_documents(model, documents, batch_size=args.batch_size)

    # Step 7 — Persist
    collection = get_chroma_collection(vdb, reset=args.reset)
    upsert_to_chroma(collection, clean_df, embeddings)

    final_count = collection.count()
    log.info("🎉 Ingestion complete!  ChromaDB: %d products indexed", final_count)
    if final_count < 25000:
        log.warning("⚠️  Count < 25,000 — check LEFT JOIN logic or DB connection")
    else:
        log.info("✅  Target of >25,000 products achieved!")


if __name__ == "__main__":
    main()
