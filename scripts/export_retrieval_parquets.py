# -*- coding: utf-8 -*-
"""
scripts/export_retrieval_parquets.py
====================================
Fast catalog export to Parquet files for Week 4 Search & Retrieval layer:
  1. data/retrieval_meta.parquet: Full 25,881 products with all metadata fields:
     product_id, sku, name_en, name_ar, brand, category, default_price,
     effective_price, has_discount, availability, image_url.
  2. data/retrieval_docs.parquet: Concatenated normalized documents for BM25 and vector search:
     product_id, doc_text, normalized_doc_text.

Usage:
    python scripts/export_retrieval_parquets.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import pymysql
from dotenv import load_dotenv

from app.core.normalizer import (
    BRAND_NORMALIZATION,
    TOP_KNOWN_BRANDS,
    normalize_brand,
    normalize_text,
)

load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("export_parquets")

INVALID_BRANDS: set[str] = {
    "",
    "please select a brand.",
    "false",
    "true",
    "n/a",
    "unknown",
    "none",
    "null",
    "0",
    "undefined",
}


def get_connection() -> pymysql.Connection:
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", "1234"),
        database=os.getenv("MYSQL_DATABASE", "spinneys_database"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=30,
    )


def impute_brand(name_en: str, name_ar: str, raw_brand: str | None) -> str:
    raw = (raw_brand or "").strip()
    raw_lower = raw.lower()
    if raw_lower and raw_lower not in INVALID_BRANDS:
        return normalize_brand(raw)

    # Impute from English name
    combined_name = f"{name_en} {name_ar}".lower()
    for b in TOP_KNOWN_BRANDS:
        if b.lower() in combined_name:
            return normalize_brand(b)

    return "Generic / Unbranded"


def export() -> None:
    t0 = time.perf_counter()
    out_dir = ROOT / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "retrieval_meta.parquet"
    docs_path = out_dir / "retrieval_docs.parquet"

    conn = get_connection()
    log.info("Connected to MySQL. Fetching catalog data...")

    with conn.cursor() as cur:
        # 1. Base products + names (En & Ar)
        log.info("Fetching products and multilingual names...")
        cur.execute(
            """
            SELECT 
                p.id AS product_id,
                p.sku,
                p.image AS image_url,
                p.default_price,
                p.default_special_price,
                COALESCE(pn_en.name, '') AS name_en,
                COALESCE(pn_ar.name, '') AS name_ar
            FROM catalog_product p
            LEFT JOIN catalog_productname pn_en 
                ON pn_en.product_id = p.id AND pn_en.language = 'English'
            LEFT JOIN catalog_productname pn_ar 
                ON pn_ar.product_id = p.id AND pn_ar.language = 'Arabic'
            ORDER BY p.id
            """
        )
        products = cur.fetchall()
        log.info("Fetched %d catalog products.", len(products))

        # 2. Total stock per SKU
        log.info("Fetching stock aggregated by SKU...")
        cur.execute(
            """
            SELECT sku, SUM(quantity) as stock_qty 
            FROM catalog_productstock 
            GROUP BY sku
            """
        )
        stock_map = {r["sku"]: (r["stock_qty"] or 0) for r in cur.fetchall()}

        # 3. Primary English Category (excluding test categories)
        log.info("Fetching product categories...")
        cur.execute(
            """
            SELECT pc.product_id, cn.name AS category
            FROM catalog_product_categories pc
            JOIN catalog_categoryname cn 
                ON cn.category_id = pc.category_id AND cn.language = 'English'
            WHERE LOWER(cn.name) NOT IN ('test', 'test1', 'test2', 'test3', 'demo')
            """
        )
        cat_map: dict[int, str] = {}
        for r in cur.fetchall():
            pid = r["product_id"]
            if pid not in cat_map:
                cat_map[pid] = r["category"].strip()

        # 4. Product attributes for brand extraction
        log.info("Fetching brand attributes JSON...")
        cur.execute(
            """
            SELECT product_id, attributes
            FROM catalog_productattributes
            WHERE language = 'English'
            """
        )
        raw_brand_map: dict[int, str] = {}
        for r in cur.fetchall():
            pid = r["product_id"]
            attr_text = r.get("attributes")
            if attr_text:
                try:
                    attrs = json.loads(attr_text)
                    if isinstance(attrs, list):
                        for item in attrs:
                            if item.get("code") == "product_brand_id":
                                raw_brand_map[pid] = str(item.get("value", "")).strip()
                                break
                except Exception:
                    pass

    conn.close()
    log.info("Data extracted from MySQL in %.2fs. Processing rows...", time.perf_counter() - t0)

    meta_rows = []
    doc_rows = []

    for r in products:
        pid = int(r["product_id"])
        sku = str(r["sku"] or "")
        name_en = str(r["name_en"] or "").strip()
        name_ar = str(r["name_ar"] or "").strip()
        image_url = str(r["image_url"] or "").strip()

        # Category
        category = cat_map.get(pid, "General")
        if not category:
            category = "General"

        # Brand resolution (Pass 1-3)
        raw_b = raw_brand_map.get(pid)
        brand = impute_brand(name_en, name_ar, raw_b)

        # Pricing
        default_price = float(r["default_price"] or 0.0)
        special_price = float(r["default_special_price"] or 0.0)
        if 0 < special_price < default_price:
            effective_price = special_price
            has_discount = True
        else:
            effective_price = default_price
            has_discount = False

        # Stock / Availability
        stock_qty = stock_map.get(sku, 0)
        availability = bool(stock_qty > 0)

        meta_rows.append(
            {
                "product_id": pid,
                "sku": sku,
                "name_en": name_en,
                "name_ar": name_ar,
                "brand": brand,
                "category": category,
                "default_price": default_price,
                "effective_price": effective_price,
                "has_discount": has_discount,
                "availability": availability,
                "image_url": image_url,
            }
        )

        # Documents for BM25 and Lexical/Vector search: {name_en} {name_ar} {brand} {category}
        doc_text = f"{name_en} {name_ar} {brand} {category}".strip()
        normalized_doc = normalize_text(doc_text)

        doc_rows.append(
            {
                "product_id": pid,
                "doc_text": doc_text,
                "normalized_doc_text": normalized_doc,
            }
        )

    df_meta = pd.DataFrame(meta_rows)
    df_docs = pd.DataFrame(doc_rows)

    log.info("Saving %s (%d rows)...", meta_path, len(df_meta))
    df_meta.to_parquet(meta_path, index=False, engine="pyarrow")

    log.info("Saving %s (%d rows)...", docs_path, len(df_docs))
    df_docs.to_parquet(docs_path, index=False, engine="pyarrow")

    # Also save to data/processed for convenience
    proc_dir = ROOT / "data" / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    df_meta.to_parquet(proc_dir / "retrieval_meta.parquet", index=False, engine="pyarrow")
    df_docs.to_parquet(proc_dir / "retrieval_docs.parquet", index=False, engine="pyarrow")

    total_time = time.perf_counter() - t0
    log.info(
        "✅ Export complete in %.2fs! Meta rows: %d, Docs rows: %d",
        total_time,
        len(df_meta),
        len(df_docs),
    )


if __name__ == "__main__":
    export()
