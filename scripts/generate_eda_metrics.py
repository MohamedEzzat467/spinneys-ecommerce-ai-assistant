# -*- coding: utf-8 -*-
"""
scripts/generate_eda_metrics.py
================================
Spinneys Product Intelligence — EDA Metrics & Chart Generator
Queries MySQL (spinneys_database), computes all statistics,
saves 5 charts to reports/assets/, and returns a metrics dict as JSON.

Usage:
    python scripts/generate_eda_metrics.py
"""

import os, sys, json, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import seaborn as sns
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

# ── Config ────────────────────────────────────────────────────────────────────
ASSETS = ROOT / "reports" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

DB_CFG = dict(
    host=os.getenv("MYSQL_HOST", "localhost"),
    port=int(os.getenv("MYSQL_PORT", 3306)),
    user=os.getenv("MYSQL_USER", "root"),
    password=os.getenv("MYSQL_PASSWORD", "1234"),
    database=os.getenv("MYSQL_DATABASE", "spinneys_database"),
    charset="utf8mb4",
    connect_timeout=30,
)

# ── Corporate palette ─────────────────────────────────────────────────────────
NAVY   = "#1B365D"
TEAL   = "#008080"
SLATE  = "#4A6FA5"
MINT   = "#52B788"
AMBER  = "#F4A261"
RED    = "#C62828"
LGRAY  = "#F5F5F5"
MGRAY  = "#9E9E9E"
WHITE  = "#FFFFFF"
PALETTE = [NAVY, TEAL, SLATE, MINT, AMBER, RED, "#7B1FA2", "#00695C", "#E65100", "#0277BD"]

plt.rcParams.update({
    "figure.facecolor": WHITE,
    "axes.facecolor":   LGRAY,
    "axes.edgecolor":   MGRAY,
    "axes.labelcolor":  NAVY,
    "axes.titlecolor":  NAVY,
    "axes.titlesize":   13,
    "axes.labelsize":   11,
    "xtick.color":      NAVY,
    "ytick.color":      NAVY,
    "text.color":       NAVY,
    "font.family":      "DejaVu Sans",
    "grid.color":       "#E0E0E0",
    "grid.linewidth":   0.8,
})


def conn():
    return pymysql.connect(**DB_CFG)


def q(sql, params=None):
    with conn() as c:
        return pd.read_sql(sql, c, params=params)


print("🔌  Connecting to MySQL …")

# =============================================================================
# SECTION 1 — CATALOG SCALE
# =============================================================================
print("📊  [1/7] Catalog scale …")

total_products   = q("SELECT COUNT(*) AS n FROM catalog_product").iloc[0,0]
total_skus       = q("SELECT COUNT(DISTINCT sku) AS n FROM catalog_product").iloc[0,0]

tables_df = q("""
    SELECT TABLE_NAME, TABLE_ROWS
    FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = 'spinneys_database'
    ORDER BY TABLE_ROWS DESC
""")
total_tables = len(tables_df)

price_sources  = q("SELECT COUNT(*) AS n FROM catalog_product WHERE default_price > 0").iloc[0,0]
stock_sources  = q("SELECT COUNT(DISTINCT source_code) AS n FROM catalog_productstock").iloc[0,0]
stock_sku_cnt  = q("SELECT COUNT(DISTINCT sku) AS n FROM catalog_productstock").iloc[0,0]

# =============================================================================
# SECTION 2 — CANONICAL AVAILABILITY & STOCK
# =============================================================================
print("📦  [2/7] Stock analysis …")

stock_df = q("""
    SELECT p.id AS product_id, p.sku,
           COALESCE(SUM(ps.quantity),0) AS total_qty,
           COUNT(DISTINCT ps.source_code)          AS src_count
    FROM catalog_product p
    LEFT JOIN catalog_productstock ps ON p.sku = ps.sku
    WHERE p.default_price > 0
    GROUP BY p.id, p.sku
""")

in_stock_cnt  = int((stock_df["total_qty"] > 0).sum())
out_stock_cnt = int((stock_df["total_qty"] == 0).sum())
no_stock_rec  = int((stock_df["src_count"] == 0).sum())
valid_products = len(stock_df)

# Mixed stock signals: product has some sources > 0 AND some == 0
mixed_stock_df = q("""
    SELECT ps.sku,
           SUM(CASE WHEN ps.quantity > 0 THEN 1 ELSE 0 END) AS pos_src,
           SUM(CASE WHEN ps.quantity = 0 THEN 1 ELSE 0 END) AS zero_src
    FROM catalog_productstock ps
    GROUP BY ps.sku
    HAVING pos_src > 0 AND zero_src > 0
""")
mixed_stock_cnt = len(mixed_stock_df)

# =============================================================================
# SECTION 3 — PRICING & DISCOUNTS
# =============================================================================
print("💰  [3/7] Pricing analysis …")

price_df = q("""
    SELECT p.id,
           p.default_price,
           p.default_special_price,
           CASE
               WHEN p.default_special_price IS NOT NULL
                    AND p.default_special_price > 0
                    AND p.default_special_price < p.default_price
               THEN p.default_special_price
               ELSE p.default_price
           END AS effective_price
    FROM catalog_product p
    WHERE p.default_price > 0
""")

buckets = [0, 50, 100, 250, 500, 1000, float("inf")]
labels  = ["≤50", "51–100", "101–250", "251–500", "501–1000", ">1000"]
price_df["bucket"] = pd.cut(price_df["effective_price"], bins=buckets, labels=labels, right=True)
bucket_counts = price_df["bucket"].value_counts().reindex(labels).fillna(0).astype(int)

valid_discount_df = price_df[
    (price_df["default_special_price"].notna()) &
    (price_df["default_special_price"] > 0) &
    (price_df["default_special_price"] < price_df["default_price"])
].copy()
valid_discount_df["disc_pct"] = (
    1 - valid_discount_df["default_special_price"] / valid_discount_df["default_price"]
) * 100

valid_discount_cnt  = len(valid_discount_df)
mean_discount_pct   = round(float(valid_discount_df["disc_pct"].mean()), 1) if len(valid_discount_df) else 0
median_discount_pct = round(float(valid_discount_df["disc_pct"].median()), 1) if len(valid_discount_df) else 0
extreme_disc_cnt    = int((valid_discount_df["disc_pct"] >= 80).sum()) if len(valid_discount_df) else 0
zero_price_cnt      = int(q("SELECT COUNT(*) AS n FROM catalog_product WHERE default_price = 0 OR default_price IS NULL").iloc[0,0])

mean_price   = round(float(price_df["effective_price"].mean()), 2)
median_price = round(float(price_df["effective_price"].median()), 2)
max_price    = round(float(price_df["effective_price"].max()), 2)

# =============================================================================
# SECTION 4 — TAXONOMY
# =============================================================================
print("🗂️  [4/7] Category analysis …")

cat_df = q("""
    SELECT pc.product_id, cn.name AS category
    FROM catalog_product_categories pc
    JOIN catalog_categoryname cn ON pc.category_id = cn.category_id
    WHERE cn.language = 'English'
      AND LOWER(cn.name) NOT IN ('test','test1','test2','test3','demo')
""")

products_with_cat   = int(cat_df["product_id"].nunique())
products_no_cat     = int(total_products - products_with_cat)
avg_cat_per_product = round(cat_df.groupby("product_id")["category"].count().mean(), 2) if len(cat_df) else 0
multi_cat_products  = int((cat_df.groupby("product_id")["category"].count() > 1).sum())

top_categories = (
    cat_df.groupby("category")["product_id"]
          .nunique()
          .sort_values(ascending=False)
          .head(10)
)

# =============================================================================
# SECTION 5 — BRAND ANALYSIS
# =============================================================================
print("🏷️  [5/7] Brand analysis …")

INVALID_BRANDS = {"", "please select a brand.", "false", "n/a", "unknown", "none", "0"}

brand_raw_df = q(r"""
    SELECT pa.product_id,
           jt.brand_val AS brand
    FROM catalog_productattributes pa
    JOIN JSON_TABLE(
        pa.attributes,
        '$[*]'
        COLUMNS (
            code      VARCHAR(200) PATH '$.code',
            brand_val VARCHAR(500) PATH '$.value'
        )
    ) jt ON jt.code = 'product_brand_id'
    WHERE pa.language = 'English'
""")

brand_raw_df["brand_clean"] = brand_raw_df["brand"].str.strip().str.lower()
brand_invalid_mask = brand_raw_df["brand_clean"].isin(INVALID_BRANDS) | brand_raw_df["brand_clean"].isna()

usable_brands_df   = brand_raw_df[~brand_invalid_mask]
unusable_brands_df = brand_raw_df[brand_invalid_mask]

total_with_brand_raw   = len(brand_raw_df)
total_usable_brand_rows = len(usable_brands_df)
total_unique_usable_brands = usable_brands_df["brand"].str.strip().nunique()

top_brands = (
    usable_brands_df.groupby(usable_brands_df["brand"].str.strip())["product_id"]
                    .nunique()
                    .sort_values(ascending=False)
                    .head(10)
)

usable_brand_pct = round(total_usable_brand_rows / total_with_brand_raw * 100, 1) if total_with_brand_raw else 0

# =============================================================================
# SECTION 6 — ATTRIBUTES COVERAGE
# =============================================================================
print("🔬  [6/7] Attribute coverage …")

attr_df = q(r"""
    SELECT pa.product_id,
           jt.code,
           jt.val
    FROM catalog_productattributes pa
    JOIN JSON_TABLE(
        pa.attributes,
        '$[*]'
        COLUMNS (
            code VARCHAR(200) PATH '$.code',
            val  VARCHAR(1000) PATH '$.value'
        )
    ) jt ON 1=1
    WHERE pa.language = 'English'
""")

def attr_coverage(code_name):
    sub = attr_df[(attr_df["code"] == code_name) & attr_df["val"].notna() & (attr_df["val"].str.strip() != "")]
    n = sub["product_id"].nunique()
    pct = round(n / total_products * 100, 1)
    return n, pct

attr_codes = {
    "Pack":             "product_pack",
    "Size / Unit":      "product_size",
    "Product Type":     "product_type",
    "Measurement Type": "product_measurement_type",
    "Image":            "product_image",
    "Description":      "product_description",
}
# Try common attribute code names
attr_coverage_results = {}
for label, code in attr_codes.items():
    n, pct = attr_coverage(code)
    attr_coverage_results[label] = {"count": n, "pct": pct, "code": code}

# Also measure English name coverage
eng_name_cnt = int(q("SELECT COUNT(DISTINCT product_id) FROM catalog_productname WHERE language='English'").iloc[0,0])
attr_coverage_results["English Name"] = {"count": eng_name_cnt, "pct": round(eng_name_cnt/total_products*100,1), "code": "catalog_productname"}

# =============================================================================
# SECTION 7 — GOLDEN QUERIES
# =============================================================================
print("💬  [7/7] Golden queries metadata …")

golden_queries = [
    # SEARCH (10)
    ("Q01", "Show me olive oil products",                                  "EN", "Search"),
    ("Q02", "What cheeses do you have?",                                   "EN", "Search"),
    ("Q03", "أريد أن أشتري عصير برتقال",                                   "AR", "Search"),
    ("Q04", "ابحث عن منتجات الخبز",                                        "AR", "Search"),
    ("Q05", "Show me Spinneys brand items",                                 "EN", "Search"),
    ("Q06", "I need breakfast cereals",                                     "EN", "Search"),
    ("Q07", "عندك منتجات نباتية؟",                                          "AR", "Search"),
    ("Q08", "Find me yogurt products",                                      "EN", "Search"),
    ("Q09", "حليب قليل الدسم",                                              "AR", "Search"),
    ("Q10", "I'm looking for pasta",                                        "EN", "Search"),
    # REFINE (8)
    ("Q11", "Show me only items under 50 EGP",                             "EN", "Refine"),
    ("Q12", "Only Almarai brand please",                                    "EN", "Refine"),
    ("Q13", "فقط المنتجات المتوفرة",                                        "AR", "Refine"),
    ("Q14", "Filter by Spinneys brand under 100",                          "EN", "Refine"),
    ("Q15", "بس اللي تحت 200 جنيه",                                        "AR", "Refine"),
    ("Q16", "Show available Almarai products under 80 EGP",                "EN", "Refine"),
    ("Q17", "عايز ماركة Nespresso",                                        "AR", "Refine"),
    ("Q18", "Only show items that are in stock",                            "EN", "Refine"),
    # SORT / COMPARE (6)
    ("Q19", "Sort by lowest price",                                         "EN", "Sort"),
    ("Q20", "What's the cheapest option?",                                  "EN", "Sort"),
    ("Q21", "رتب من الأرخص للأغلى",                                        "AR", "Sort"),
    ("Q22", "Compare olive oil brands",                                     "EN", "Sort"),
    ("Q23", "What's on sale?",                                              "EN", "Sort"),
    ("Q24", "اعرضلي المنتجات اللي فيها خصم",                               "AR", "Sort"),
    # RECOMMEND (6)
    ("Q25", "What do you recommend for a healthy breakfast?",               "EN", "Recommend"),
    ("Q26", "I need items for a salad recipe",                              "EN", "Recommend"),
    ("Q27", "ايه أحسن زيت للطبخ؟",                                         "AR", "Recommend"),
    ("Q28", "Suggest dairy alternatives",                                   "EN", "Recommend"),
    ("Q29", "اقترح لي منتجات للأطفال",                                     "AR", "Recommend"),
    ("Q30", "What snacks are popular?",                                     "EN", "Recommend"),
    # OUT OF SCOPE (5)
    ("Q31", "What's the weather like today?",                               "EN", "Out of Scope"),
    ("Q32", "Can you book me a taxi?",                                      "EN", "Out of Scope"),
    ("Q33", "احجز لي طاولة في مطعم",                                       "AR", "Out of Scope"),
    ("Q34", "Tell me a joke",                                               "EN", "Out of Scope"),
    ("Q35", "What time does the store close?",                              "EN", "Out of Scope"),
]

gq_df = pd.DataFrame(golden_queries, columns=["ID","Query","Language","Intent"])
intent_counts  = gq_df["Intent"].value_counts()
lang_counts    = gq_df["Language"].value_counts()

# Memory chain (Q25–Q30 used as 6-turn follow-up)
memory_chain = [
    ("Turn 1", "Q25", "What do you recommend for a healthy breakfast?",  "EN", "INIT",     "→ intent=Recommend, category=breakfast, no filters"),
    ("Turn 2", "Q12", "Only Almarai brand please",                        "EN", "PRESERVE", "→ brand=Almarai added; category=breakfast preserved"),
    ("Turn 3", "Q11", "Show me only items under 50 EGP",                  "EN", "PRESERVE", "→ price_max=50 added; brand & category preserved"),
    ("Turn 4", "Q13", "فقط المنتجات المتوفرة",                           "AR", "PRESERVE", "→ in_stock=True added; all prior filters preserved"),
    ("Turn 5", "Q05", "Show me Spinneys brand items",                     "EN", "CHANGE",   "→ brand CHANGED to Spinneys; price & in_stock preserved"),
    ("Turn 6", "—",   "Show everything (reset)",                          "EN", "REMOVE",   "→ all filters CLEARED; session reset to default state"),
]

# =============================================================================
# CHARTS
# =============================================================================
print("\n🎨  Generating charts …")

def save_fig(name):
    path = ASSETS / name
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=WHITE)
    plt.close()
    print(f"   ✓  {name}")
    return path

# ── Chart 1: Top 10 Categories ────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 6))
top_cat_vals = top_categories.sort_values()
colors_c1 = [TEAL if i < 3 else SLATE for i in range(len(top_cat_vals))]
bars = ax.barh(top_cat_vals.index, top_cat_vals.values, color=colors_c1, edgecolor="white", height=0.7)
for bar, val in zip(bars, top_cat_vals.values):
    ax.text(bar.get_width() + max(top_cat_vals)*0.01, bar.get_y() + bar.get_height()/2,
            f"{val:,}", va="center", fontsize=9, color=NAVY, fontweight="bold")
ax.set_xlabel("Unique Products", labelpad=8)
ax.set_title("Top 10 Product Categories\n(by Unique Product Count)", pad=14, fontweight="bold", fontsize=13)
ax.set_facecolor(LGRAY)
fig.patch.set_facecolor(WHITE)
ax.spines[["top","right"]].set_visible(False)
ax.grid(axis="x", alpha=0.4)
ax.set_xlim(0, top_cat_vals.max() * 1.15)
plt.tight_layout()
save_fig("top_categories.png")

# ── Chart 2: Top 10 Brands ────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 6))
top_brand_vals = top_brands.sort_values()
colors_c2 = [NAVY if i < 3 else SLATE for i in range(len(top_brand_vals))]
bars2 = ax.barh(top_brand_vals.index, top_brand_vals.values, color=colors_c2, edgecolor="white", height=0.7)
for bar, val in zip(bars2, top_brand_vals.values):
    ax.text(bar.get_width() + max(top_brand_vals)*0.01, bar.get_y() + bar.get_height()/2,
            f"{val:,}", va="center", fontsize=9, color=NAVY, fontweight="bold")
ax.set_xlabel("Unique Products", labelpad=8)
ax.set_title("Top 10 Brands by Product Count\n(Clean / Usable Brands Only)", pad=14, fontweight="bold", fontsize=13)
ax.set_facecolor(LGRAY)
fig.patch.set_facecolor(WHITE)
ax.spines[["top","right"]].set_visible(False)
ax.grid(axis="x", alpha=0.4)
ax.set_xlim(0, top_brand_vals.max() * 1.15)
plt.tight_layout()
save_fig("top_brands.png")

# ── Chart 3: Price Distribution ───────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 5))
bucket_colors = [TEAL, SLATE, NAVY, MINT, AMBER, RED]
bars3 = ax.bar(labels, bucket_counts.values, color=bucket_colors, edgecolor="white", width=0.65)
for bar, val in zip(bars3, bucket_counts.values):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(bucket_counts)*0.01,
            f"{val:,}", ha="center", fontsize=9, color=NAVY, fontweight="bold")
ax.set_xlabel("Price Range (EGP)", labelpad=8)
ax.set_ylabel("Number of Products", labelpad=8)
ax.set_title("Product Price Distribution\n(Effective Price — EGP Buckets)", pad=14, fontweight="bold", fontsize=13)
ax.set_facecolor(LGRAY)
fig.patch.set_facecolor(WHITE)
ax.spines[["top","right"]].set_visible(False)
ax.grid(axis="y", alpha=0.4)
ax.set_ylim(0, bucket_counts.max() * 1.18)
plt.tight_layout()
save_fig("price_distribution.png")

# ── Chart 4: Availability ─────────────────────────────────────────────────────
avail_labels = ["In Stock", "Out of Stock", "No Record"]
avail_vals   = [in_stock_cnt, out_stock_cnt - no_stock_rec, no_stock_rec]
avail_colors = [TEAL, RED, MGRAY]
# clamp negatives
avail_vals = [max(0, v) for v in avail_vals]

fig, (ax_bar, ax_pie) = plt.subplots(1, 2, figsize=(12, 5))

# Bar
bars4 = ax_bar.bar(avail_labels, avail_vals, color=avail_colors, edgecolor="white", width=0.55)
for bar, val in zip(bars4, avail_vals):
    ax_bar.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(avail_vals)*0.02,
                f"{val:,}", ha="center", fontsize=10, color=NAVY, fontweight="bold")
ax_bar.set_ylabel("Products", labelpad=8)
ax_bar.set_title("Canonical Availability\n(Products with valid price)", pad=12, fontweight="bold")
ax_bar.set_facecolor(LGRAY)
ax_bar.spines[["top","right"]].set_visible(False)
ax_bar.grid(axis="y", alpha=0.4)
ax_bar.set_ylim(0, max(avail_vals) * 1.2)

# Donut
total_shown = sum(avail_vals)
pcts = [v/total_shown*100 if total_shown else 0 for v in avail_vals]
wedge_labels = [f"{l}\n{p:.1f}%" for l, p in zip(avail_labels, pcts)]
wedges, texts = ax_pie.pie(avail_vals, labels=wedge_labels, colors=avail_colors,
                            startangle=90, pctdistance=0.8,
                            wedgeprops=dict(width=0.55, edgecolor="white", linewidth=2))
for text in texts:
    text.set_fontsize(9)
    text.set_color(NAVY)
ax_pie.set_title("Availability Distribution\n(Donut View)", pad=12, fontweight="bold")
fig.patch.set_facecolor(WHITE)
plt.tight_layout()
save_fig("canonical_availability.png")

# ── Chart 5: Intent Distribution ─────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(9, 5))
intent_order = ["Search", "Refine", "Sort", "Recommend", "Out of Scope"]
intent_vals  = [intent_counts.get(i, 0) for i in intent_order]
intent_colors = [TEAL, SLATE, NAVY, MINT, AMBER]
bars5 = ax.bar(intent_order, intent_vals, color=intent_colors, edgecolor="white", width=0.6)
for bar, val in zip(bars5, intent_vals):
    pct = val / sum(intent_vals) * 100
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
            f"{val}\n({pct:.0f}%)", ha="center", fontsize=9.5, color=NAVY, fontweight="bold")
ax.set_ylabel("Number of Queries", labelpad=8)
ax.set_title("Golden Query Set — Intent Distribution\n(35 Curated Queries)", pad=14, fontweight="bold", fontsize=13)
ax.set_facecolor(LGRAY)
fig.patch.set_facecolor(WHITE)
ax.spines[["top","right"]].set_visible(False)
ax.grid(axis="y", alpha=0.4)
ax.set_ylim(0, max(intent_vals) * 1.25)
plt.tight_layout()
save_fig("intent_distribution.png")

# =============================================================================
# SAVE METRICS JSON
# =============================================================================
metrics = {
    "catalog": {
        "total_products":      int(total_products),
        "total_skus":          int(total_skus),
        "total_tables":        int(total_tables),
        "valid_priced":        int(len(price_df)),
        "price_sources":       int(price_sources),
        "stock_sources":       int(stock_sources),
        "stock_sku_count":     int(stock_sku_cnt),
        "zero_price_count":    int(zero_price_cnt),
    },
    "availability": {
        "in_stock":            int(in_stock_cnt),
        "out_of_stock":        int(out_stock_cnt),
        "no_stock_record":     int(no_stock_rec),
        "mixed_stock":         int(mixed_stock_cnt),
        "total_valid_products":int(valid_products),
    },
    "pricing": {
        "mean_price":          float(mean_price),
        "median_price":        float(median_price),
        "max_price":           float(max_price),
        "valid_discounts":     int(valid_discount_cnt),
        "mean_discount_pct":   float(mean_discount_pct),
        "median_discount_pct": float(median_discount_pct),
        "extreme_discounts":   int(extreme_disc_cnt),
        "bucket_counts":       {str(k): int(v) for k, v in bucket_counts.items()},
    },
    "taxonomy": {
        "products_with_category":    int(products_with_cat),
        "products_no_category":      int(products_no_cat),
        "avg_categories_per_product":float(avg_cat_per_product),
        "multi_category_products":   int(multi_cat_products),
        "top_categories":            {str(k): int(v) for k, v in top_categories.items()},
    },
    "brands": {
        "total_with_brand_raw":         int(total_with_brand_raw),
        "total_usable_brand_rows":      int(total_usable_brand_rows),
        "total_unique_usable_brands":   int(total_unique_usable_brands),
        "usable_brand_pct":             float(usable_brand_pct),
        "top_brands":                   {str(k): int(v) for k, v in top_brands.items()},
    },
    "attributes": {k: v for k, v in attr_coverage_results.items()},
    "golden_queries": {
        "total":               len(golden_queries),
        "intent_counts":       intent_counts.to_dict(),
        "lang_counts":         lang_counts.to_dict(),
    },
    "tables": tables_df.to_dict(orient="records"),
}

metrics_path = ROOT / "reports" / "assets" / "metrics.json"
with open(metrics_path, "w", encoding="utf-8") as f:
    json.dump(metrics, f, indent=2, ensure_ascii=False)

print(f"\n✅  Metrics saved  → {metrics_path}")
print(f"📁  Charts saved   → {ASSETS}")
print("\n── Quick Summary ──────────────────────────────────────────")
print(f"   Total products       : {total_products:,}")
print(f"   Total SKUs           : {total_skus:,}")
print(f"   In Stock             : {in_stock_cnt:,}  ({in_stock_cnt/valid_products*100:.1f}%)")
print(f"   With valid brand     : {total_usable_brand_rows:,}  ({usable_brand_pct}%)")
print(f"   Unique usable brands : {total_unique_usable_brands:,}")
print(f"   With category        : {products_with_cat:,}  ({products_with_cat/total_products*100:.1f}%)")
print(f"   Valid discounts      : {valid_discount_cnt:,}")
print(f"   Mixed stock signals  : {mixed_stock_cnt:,}")
print("──────────────────────────────────────────────────────────")
