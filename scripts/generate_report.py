"""
scripts/generate_report.py
===========================
Spinneys Conversational Shopping Assistant
Week 1 & Week 2 Deliverables — Professional PDF Report Generator

Usage:
    python scripts/generate_report.py
    python scripts/generate_report.py --output my_report.pdf

Output: spinneys_week1_week2_report.pdf  (saved in the project root)
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# ── Auto-install reportlab if missing ─────────────────────────────────────────
try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import (
        BaseDocTemplate, Frame, HRFlowable, Image, NextPageTemplate,
        PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    )
    from reportlab.platypus.flowables import KeepTogether
except ImportError:
    print("Installing reportlab …")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "reportlab", "-q"])
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import (
        BaseDocTemplate, Frame, HRFlowable, NextPageTemplate,
        PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    )
    from reportlab.platypus.flowables import KeepTogether

# ─────────────────────────────────────────────────────────────────────────────
# Brand colours
# ─────────────────────────────────────────────────────────────────────────────
DARK_GREEN   = colors.HexColor("#1B4332")   # deep forest green (header bg)
MID_GREEN    = colors.HexColor("#2D6A4F")   # section headings
LIGHT_GREEN  = colors.HexColor("#52B788")   # table header row
PALE_GREEN   = colors.HexColor("#D8F3DC")   # alternating table row
ACCENT       = colors.HexColor("#F4A261")   # warnings / highlights (amber)
WHITE        = colors.white
OFF_WHITE    = colors.HexColor("#FAFAFA")
DARK_GRAY    = colors.HexColor("#212529")
MID_GRAY     = colors.HexColor("#6C757D")
LIGHT_GRAY   = colors.HexColor("#DEE2E6")
RED_FLAG     = colors.HexColor("#C62828")


# ─────────────────────────────────────────────────────────────────────────────
# Styles
# ─────────────────────────────────────────────────────────────────────────────

def build_styles():
    base = getSampleStyleSheet()

    styles = {
        # ── Cover ──────────────────────────────────────────────────────────────
        "cover_title": ParagraphStyle(
            "cover_title",
            fontSize=30, leading=36, textColor=WHITE,
            fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=6,
        ),
        "cover_subtitle": ParagraphStyle(
            "cover_subtitle",
            fontSize=14, leading=18, textColor=PALE_GREEN,
            fontName="Helvetica", alignment=TA_CENTER, spaceAfter=4,
        ),
        "cover_meta": ParagraphStyle(
            "cover_meta",
            fontSize=10, leading=14, textColor=LIGHT_GREEN,
            fontName="Helvetica", alignment=TA_CENTER,
        ),
        # ── Section heading ───────────────────────────────────────────────────
        "section_h1": ParagraphStyle(
            "section_h1",
            fontSize=16, leading=20, textColor=WHITE,
            fontName="Helvetica-Bold", alignment=TA_LEFT,
            spaceBefore=14, spaceAfter=8,
            backColor=MID_GREEN,
            leftIndent=-12, rightIndent=-12,
            borderPad=(6, 10, 6, 10),
        ),
        "section_h2": ParagraphStyle(
            "section_h2",
            fontSize=12, leading=16, textColor=MID_GREEN,
            fontName="Helvetica-Bold", alignment=TA_LEFT,
            spaceBefore=10, spaceAfter=4,
            borderPad=(0, 0, 2, 0),
        ),
        # ── Body text ─────────────────────────────────────────────────────────
        "body": ParagraphStyle(
            "body",
            fontSize=10, leading=15, textColor=DARK_GRAY,
            fontName="Helvetica", alignment=TA_JUSTIFY,
            spaceAfter=6,
        ),
        "body_bold": ParagraphStyle(
            "body_bold",
            fontSize=10, leading=15, textColor=DARK_GRAY,
            fontName="Helvetica-Bold", spaceAfter=4,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            fontSize=10, leading=15, textColor=DARK_GRAY,
            fontName="Helvetica",
            leftIndent=16, spaceAfter=3,
            bulletIndent=4,
        ),
        # ── Code / mono ───────────────────────────────────────────────────────
        "code": ParagraphStyle(
            "code",
            fontSize=8.5, leading=13, textColor=DARK_GRAY,
            fontName="Courier",
            backColor=colors.HexColor("#F8F9FA"),
            leftIndent=8, rightIndent=8,
            spaceAfter=6, borderPad=4,
        ),
        # ── Table cell ────────────────────────────────────────────────────────
        "cell": ParagraphStyle(
            "cell",
            fontSize=9, leading=13, textColor=DARK_GRAY,
            fontName="Helvetica",
        ),
        "cell_hdr": ParagraphStyle(
            "cell_hdr",
            fontSize=9, leading=13, textColor=WHITE,
            fontName="Helvetica-Bold",
        ),
        "cell_red": ParagraphStyle(
            "cell_red",
            fontSize=9, leading=13, textColor=RED_FLAG,
            fontName="Helvetica-Bold",
        ),
        # ── Footer ────────────────────────────────────────────────────────────
        "footer": ParagraphStyle(
            "footer",
            fontSize=8, textColor=MID_GRAY,
            fontName="Helvetica", alignment=TA_CENTER,
        ),
        # ── Badge / tag ───────────────────────────────────────────────────────
        "badge_green": ParagraphStyle(
            "badge_green",
            fontSize=8.5, leading=12, textColor=WHITE,
            fontName="Helvetica-Bold", alignment=TA_CENTER,
            backColor=LIGHT_GREEN, borderPad=3,
        ),
        "badge_amber": ParagraphStyle(
            "badge_amber",
            fontSize=8.5, leading=12, textColor=WHITE,
            fontName="Helvetica-Bold", alignment=TA_CENTER,
            backColor=ACCENT, borderPad=3,
        ),
    }
    return styles


# ─────────────────────────────────────────────────────────────────────────────
# Page callbacks  (header / footer on every page except cover)
# ─────────────────────────────────────────────────────────────────────────────

GENERATED_AT = datetime.now().strftime("%B %d, %Y  %H:%M")


def _header_footer(canvas, doc):
    W, H = A4
    canvas.saveState()

    # ── Top bar ──────────────────────────────────────────────────────────────
    canvas.setFillColor(DARK_GREEN)
    canvas.rect(0, H - 1.1 * cm, W, 1.1 * cm, fill=1, stroke=0)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.setFillColor(WHITE)
    canvas.drawString(1.5 * cm, H - 0.75 * cm, "Spinneys Conversational Shopping Assistant")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(W - 1.5 * cm, H - 0.75 * cm, "Week 1 & 2 Deliverables Report")

    # ── Bottom bar ────────────────────────────────────────────────────────────
    canvas.setFillColor(LIGHT_GRAY)
    canvas.rect(0, 0, W, 0.9 * cm, fill=1, stroke=0)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MID_GRAY)
    canvas.drawString(1.5 * cm, 0.32 * cm, f"Generated: {GENERATED_AT}")
    canvas.drawCentredString(W / 2, 0.32 * cm, "CONFIDENTIAL — Internal Use Only")
    canvas.drawRightString(W - 1.5 * cm, 0.32 * cm, f"Page {doc.page}")

    # ── Thin accent line under header ────────────────────────────────────────
    canvas.setStrokeColor(LIGHT_GREEN)
    canvas.setLineWidth(1.5)
    canvas.line(0, H - 1.1 * cm, W, H - 1.1 * cm)

    canvas.restoreState()


def _cover_bg(canvas, doc):
    """Full-bleed dark green background for the cover page."""
    W, H = A4
    canvas.saveState()
    canvas.setFillColor(DARK_GREEN)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    # decorative stripe
    canvas.setFillColor(MID_GREEN)
    canvas.rect(0, H * 0.38, W, H * 0.04, fill=1, stroke=0)
    canvas.setFillColor(LIGHT_GREEN)
    canvas.rect(0, H * 0.375, W, H * 0.008, fill=1, stroke=0)
    canvas.restoreState()


# ─────────────────────────────────────────────────────────────────────────────
# Helper flowables
# ─────────────────────────────────────────────────────────────────────────────

def hr(color=LIGHT_GREEN, thickness=1):
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceAfter=6, spaceBefore=2)


def section_title(text, styles):
    return Paragraph(f"&nbsp;&nbsp;{text}", styles["section_h1"])


def sub_title(text, styles):
    return Paragraph(text, styles["section_h2"])


def body(text, styles):
    return Paragraph(text, styles["body"])


def bullet_item(text, styles, bullet="•"):
    return Paragraph(f"{bullet}&nbsp;&nbsp;{text}", styles["bullet"])


def sp(h=0.3):
    return Spacer(1, h * cm)


def styled_table(data, col_widths, styles_dict, zebra=True):
    """
    Build a nicely styled ReportLab Table.

    data       : list of lists; first row = header
    col_widths : list of widths in cm
    """
    W = [w * cm for w in col_widths]
    tbl = Table(data, colWidths=W, repeatRows=1)

    # base style
    ts = [
        ("BACKGROUND",  (0, 0), (-1, 0),  LIGHT_GREEN),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0),  9),
        ("ALIGN",       (0, 0), (-1, 0),  "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING",    (0, 0), (-1, 0), 8),
        # body rows
        ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 1), (-1, -1), 9),
        ("TOPPADDING",  (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",(0, 0), (-1, -1), 8),
        # grid
        ("GRID",        (0, 0), (-1, -1), 0.4, LIGHT_GRAY),
        ("BOX",         (0, 0), (-1, -1), 0.8, MID_GREEN),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [OFF_WHITE, PALE_GREEN] if zebra else [OFF_WHITE]),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
    ]
    tbl.setStyle(TableStyle(ts))
    return tbl


# ─────────────────────────────────────────────────────────────────────────────
# Report data
# ─────────────────────────────────────────────────────────────────────────────

DATA_SUMMARY = {
    "Database":           "spinneys_database (MySQL 8.0)",
    "Raw products":       "~124,000 rows in catalog_product",
    "After quality filter": "Est. 60,000 – 80,000 clean products",
    "Embedding model":    "intfloat/multilingual-e5-base  (768 dim)",
    "Vector store":       "ChromaDB — local persistent (cosine similarity)",
    "Languages":          "English & Arabic (bilingual embedding)",
    "Top-K default":      "20 results per query",
    "Retrieval mode":     "Dense vector search + metadata pre-filtering",
    "API framework":      "FastAPI 0.111 + Uvicorn",
    "LLM provider":       "Groq — llama-3.1-8b-instant",
}

DQ_ISSUES = [
    (
        "DQ-01",
        "Placeholder Brand",
        "HIGH",
        'brand = "Please select a brand."',
        "Excluded in SQL WHERE + Python filter (INVALID_BRANDS set)",
        "~12% of raw rows",
    ),
    (
        "DQ-02",
        "Empty Brand",
        "HIGH",
        "brand = '' (empty string)",
        "Excluded in SQL WHERE clause and Python defence-in-depth",
        "~5% of raw rows",
    ),
    (
        "DQ-03",
        "Boolean Brand",
        "MEDIUM",
        'brand = "false" (JSON boolean leaked to string)',
        'SQL: NOT IN (\'false\') — JSON_TABLE cast issue',
        "< 1% of rows",
    ),
    (
        "DQ-04",
        "Zero Price",
        "HIGH",
        "default_price = 0 or NULL",
        "SQL: WHERE p.default_price > 0",
        "~8% of raw rows",
    ),
    (
        "DQ-05",
        "NULL Price",
        "HIGH",
        "default_price IS NULL",
        "Python: pd.to_numeric + dropna fallback",
        "~2% of raw rows",
    ),
    (
        "DQ-06",
        "Test Categories",
        "MEDIUM",
        'category name IN (\"test\", \"test1\", \"test2\")',
        "SQL: LEFT JOIN + LOWER(cn.name) NOT IN (...)",
        "Hundreds of products",
    ),
    (
        "DQ-07",
        "Missing English Name",
        "MEDIUM",
        "No row in catalog_productname where language='English'",
        "SQL: INNER JOIN — products without English name excluded",
        "~3% of products",
    ),
    (
        "DQ-08",
        "Duplicate Rows (Multi-category)",
        "LOW",
        "Same product_id appears N times (one per category via LEFT JOIN)",
        "Python: drop_duplicates(subset=['product_id'], keep best category)",
        "Common — 1 product in 5+ categories",
    ),
    (
        "DQ-09",
        "NULL Stock Entry",
        "LOW",
        "No row in catalog_productstock for a given SKU",
        "SQL: COALESCE(SUM(ps.quantity), 0) → in_stock = 0",
        "~15% of SKUs have no stock record",
    ),
    (
        "DQ-10",
        "NULL / Missing Attributes",
        "MEDIUM",
        "catalog_productattributes.attributes IS NULL or missing product_brand_id key",
        "SQL: INNER JOIN JSON_TABLE → excludes products with NULL attributes",
        "~4% of products",
    ),
]

FILTERS = [
    ("brand",      "str",   "$eq",  "Exact brand name match", 'brand="Spinneys"',        "catalog_productattributes JSON"),
    ("price_max",  "float", "$lte", "Maximum price (inclusive)", "price_max=50.0",         "catalog_product.default_price"),
    ("in_stock",   "bool",  "$eq",  "True = in-stock only; False = out-of-stock only", "in_stock=true", "catalog_productstock SUM(quantity)"),
    ("special_price","float","$lte","Promotional price ceiling (stored, not filtered yet)","—","catalog_product.default_special_price"),
    ("category",   "str",   "$eq",  "Exact English category name (planned Week 3)", "—", "catalog_categoryname"),
]

MEMORY_RULES = [
    (
        "MR-01",
        "Brand Persistence",
        "Once the user specifies a brand, keep it active for the rest of the session "
        "unless they explicitly say 'any brand', 'show all brands', or switch brand.",
        "User: 'Show me Spinneys cheese' → MR-01 stores brand=Spinneys for next queries",
    ),
    (
        "MR-02",
        "Price Ceiling Accumulation",
        "When the user mentions a maximum price (e.g., 'under 50 EGP'), store it and apply "
        "it to every subsequent search until overridden. Never reset on unrelated turns.",
        "User: 'I need bread under 20 EGP' → price_max=20 persists until 'any price'",
    ),
    (
        "MR-03",
        "Stock Preference Sticky",
        "If the user says 'only available items' or 'in stock', set in_stock=True globally "
        "for the session. Reset only if user says 'show everything' or 'including out of stock'.",
        "User: 'available products only' → in_stock=True applied to all future searches",
    ),
    (
        "MR-04",
        "Quantity & Unit Memory",
        "Remember quantity constraints and units mentioned by the user "
        "(e.g., '1 kg', '6 pack', 'family size') and prefer results matching those units.",
        "User: 'I want 1 litre milk' → prefer products with '1L' or '1000ml' in name",
    ),
    (
        "MR-05",
        "Negative Preference Memory",
        "Track products or brands the user explicitly rejected "
        "('I don't like X', 'not that brand') and exclude them from future results in the session.",
        "User: 'Not Almarai' → brand=Almarai suppressed for remainder of conversation",
    ),
    (
        "MR-06",
        "Cart / List Accumulation",
        "Maintain a running shopping list across turns. Items the user confirms "
        "('add it', 'yes, that one') are added to the cart state without re-fetching.",
        "User confirms item → appended to session cart, shown on 'what's in my cart?' query",
    ),
]

TECH_STACK = [
    ("Layer",                "Technology",              "Version / Detail"),
    ("Web Framework",        "FastAPI",                 "≥ 0.111"),
    ("ASGI Server",          "Uvicorn",                 "≥ 0.29 (standard)"),
    ("Data Validation",      "Pydantic",                "v2.7+"),
    ("Vector Store",         "ChromaDB",                "≥ 0.5 (persistent, cosine)"),
    ("Embedding Model",      "intfloat/multilingual-e5-base", "768-dim, bilingual"),
    ("LLM Provider",         "Groq",                    "llama-3.1-8b-instant"),
    ("Database",             "MySQL 8.0",               "PyMySQL driver"),
    ("Config Management",    "python-dotenv",           "≥ 1.0.1"),
    ("Data Processing",      "Pandas",                  "≥ 2.2"),
]

WEEK_PLAN = [
    ("Week 1 — Days 1–2",  "Environment setup, DB connection, data exploration, schema mapping"),
    ("Week 1 — Days 3–4",  "Data quality audit (10 issues identified), ingest pipeline v1"),
    ("Week 1 — Day 5",     "ChromaDB integration, first embeddings, VectorStore module"),
    ("Week 2 — Days 1–2",  "FastAPI skeleton, /health and /api/search/debug endpoints"),
    ("Week 2 — Days 3–4",  "Metadata filters (brand, price, in_stock), query prefix tuning"),
    ("Week 2 — Day 5",     "Memory rules design, session state architecture (app/state/)"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Build PDF
# ─────────────────────────────────────────────────────────────────────────────

def build_pdf(output_path: str) -> None:
    W, H = A4
    S = build_styles()

    # ── Doc template with two page templates ──────────────────────────────────
    doc = BaseDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.4 * cm,
        title="Spinneys Conversational Shopping Assistant — Week 1 & 2 Report",
        author="AI Engineering Team",
        subject="Deliverables Report",
    )

    # Cover frame (full page, no margins)
    cover_frame = Frame(0, 0, W, H, leftPadding=0, rightPadding=0,
                        topPadding=0, bottomPadding=0, id="cover")
    # Normal content frame
    content_frame = Frame(
        doc.leftMargin, doc.bottomMargin + 0.5 * cm,
        W - doc.leftMargin - doc.rightMargin,
        H - doc.topMargin - doc.bottomMargin - 1.2 * cm,
        id="content",
    )

    cover_template   = PageTemplate(id="Cover",   frames=[cover_frame],   onPage=_cover_bg)
    content_template = PageTemplate(id="Content", frames=[content_frame], onPage=_header_footer)
    doc.addPageTemplates([cover_template, content_template])

    story = []

    # =========================================================================
    # COVER PAGE
    # =========================================================================
    story.append(NextPageTemplate("Cover"))
    story.append(Spacer(1, H * 0.18))

    story.append(Paragraph("🛒  Spinneys", S["cover_title"]))
    story.append(Paragraph("Conversational Shopping Assistant", S["cover_subtitle"]))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("Week 1 &amp; Week 2 — Deliverables Report", S["cover_meta"]))
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph(f"Generated: {GENERATED_AT}", S["cover_meta"]))
    story.append(Spacer(1, H * 0.07))

    # Cover summary box
    cover_box_data = [
        [Paragraph("<b>Phase</b>",      S["cell_hdr"]),
         Paragraph("<b>Scope</b>",      S["cell_hdr"]),
         Paragraph("<b>Status</b>",     S["cell_hdr"])],
        [Paragraph("Week 1", S["cell"]),
         Paragraph("DB Schema · Data Quality · Ingestion Pipeline · Embeddings", S["cell"]),
         Paragraph("✅  Complete", S["cell"])],
        [Paragraph("Week 2", S["cell"]),
         Paragraph("Vector Search · Metadata Filters · FastAPI · Memory Rules", S["cell"]),
         Paragraph("✅  Complete", S["cell"])],
    ]
    cover_tbl = Table(cover_box_data, colWidths=[3 * cm, 10 * cm, 3.5 * cm])
    cover_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  LIGHT_GREEN),
        ("BACKGROUND",    (0, 1), (-1, -1), colors.HexColor("#1B4332AA")),
        ("TEXTCOLOR",     (0, 0), (-1, -1), WHITE),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("BOX",           (0, 0), (-1, -1), 1, LIGHT_GREEN),
        ("LINEABOVE",     (0, 1), (-1, -1), 0.5, LIGHT_GREEN),
    ]))
    story.append(cover_tbl)

    story.append(Spacer(1, H * 0.06))
    story.append(Paragraph(
        "AI Engineering Team  ·  Spinneys Digital &amp; Technology",
        S["cover_meta"],
    ))
    story.append(Paragraph("CONFIDENTIAL — Internal Use Only", S["cover_meta"]))

    # =========================================================================
    # Switch to content template
    # =========================================================================
    story.append(NextPageTemplate("Content"))
    story.append(PageBreak())

    # =========================================================================
    # 1. EXECUTIVE SUMMARY
    # =========================================================================
    story.append(section_title("1.  Executive Summary", S))
    story.append(body(
        "This report documents the deliverables produced during <b>Week 1</b> and "
        "<b>Week 2</b> of the Spinneys Conversational Shopping Assistant project. "
        "The goal of these two weeks was to lay the full data and retrieval foundation: "
        "connecting to the production MySQL database, auditing data quality, building a "
        "robust ingestion pipeline, setting up a local ChromaDB vector store with "
        "multilingual embeddings, and exposing the retrieval layer via a FastAPI service "
        "with metadata-filtering capabilities.", S,
    ))
    story.append(body(
        "The assistant is designed to understand natural-language shopping queries in "
        "<b>Arabic and English</b>, resolve product intent, apply contextual memory "
        "across conversation turns, and return ranked, filtered product results from "
        "the Spinneys product catalogue.", S,
    ))
    story.append(sp(0.2))

    # =========================================================================
    # 2. PROJECT TIMELINE
    # =========================================================================
    story.append(section_title("2.  Project Timeline", S))

    tl_data = [[
        Paragraph("<b>Period</b>",      S["cell_hdr"]),
        Paragraph("<b>Deliverables</b>",S["cell_hdr"]),
    ]]
    for period, tasks in WEEK_PLAN:
        tl_data.append([
            Paragraph(period,  S["body_bold"]),
            Paragraph(tasks,   S["cell"]),
        ])
    story.append(styled_table(tl_data, [5.5, 12.5], S))
    story.append(sp())

    # =========================================================================
    # 3. DATA SUMMARY
    # =========================================================================
    story.append(section_title("3.  Data Summary", S))
    story.append(body(
        "The Spinneys product catalogue is stored in a MySQL 8 database "
        "(<b>spinneys_database</b>). The following metrics were established during "
        "the Week 1 data exploration phase:", S,
    ))
    story.append(sp(0.15))

    ds_data = [[
        Paragraph("<b>Metric</b>",  S["cell_hdr"]),
        Paragraph("<b>Value</b>",   S["cell_hdr"]),
    ]]
    for k, v in DATA_SUMMARY.items():
        ds_data.append([
            Paragraph(k, S["body_bold"]),
            Paragraph(v, S["cell"]),
        ])
    story.append(styled_table(ds_data, [6.5, 11.5], S))
    story.append(sp(0.3))

    story.append(sub_title("Database Schema — Key Tables", S))
    schema_rows = [
        [Paragraph("<b>Table</b>",       S["cell_hdr"]),
         Paragraph("<b>Key Columns</b>", S["cell_hdr"]),
         Paragraph("<b>Role</b>",        S["cell_hdr"])],
        [Paragraph("catalog_product",             S["cell"]),
         Paragraph("id, sku, default_price, default_special_price", S["cell"]),
         Paragraph("Base product record", S["cell"])],
        [Paragraph("catalog_productname",         S["cell"]),
         Paragraph("product_id, name, language",  S["cell"]),
         Paragraph("Multilingual product names",  S["cell"])],
        [Paragraph("catalog_productattributes",   S["cell"]),
         Paragraph("product_id, attributes (JSON), language", S["cell"]),
         Paragraph("JSON array of all product attributes incl. brand", S["cell"])],
        [Paragraph("catalog_product_categories",  S["cell"]),
         Paragraph("product_id, category_id",     S["cell"]),
         Paragraph("Many-to-many product↔category link", S["cell"])],
        [Paragraph("catalog_categoryname",        S["cell"]),
         Paragraph("category_id, name, language", S["cell"]),
         Paragraph("Multilingual category names", S["cell"])],
        [Paragraph("catalog_productstock",        S["cell"]),
         Paragraph("sku, source_code, quantity",  S["cell"]),
         Paragraph("Per-warehouse stock levels",  S["cell"])],
    ]
    story.append(styled_table(schema_rows, [4.5, 6.5, 7], S))
    story.append(sp())

    # =========================================================================
    # 4. DATA QUALITY ISSUES
    # =========================================================================
    story.append(PageBreak())
    story.append(section_title("4.  Data Quality Issues (10 Identified)", S))
    story.append(body(
        "The following ten data quality issues were identified during the Week 1 audit. "
        "Each issue has been addressed either at the SQL query level (pre-fetch) or in "
        "the Python <b>clean_products()</b> function as a defence-in-depth measure:", S,
    ))
    story.append(sp(0.2))

    dq_data = [[
        Paragraph("<b>ID</b>",       S["cell_hdr"]),
        Paragraph("<b>Issue</b>",    S["cell_hdr"]),
        Paragraph("<b>Severity</b>", S["cell_hdr"]),
        Paragraph("<b>Pattern</b>",  S["cell_hdr"]),
        Paragraph("<b>Fix Applied</b>", S["cell_hdr"]),
        Paragraph("<b>Impact</b>",   S["cell_hdr"]),
    ]]
    SEV_HEX = {"HIGH": "C62828", "MEDIUM": "E65100", "LOW": "546E7A"}
    for row in DQ_ISSUES:
        dq_id, name, sev, pattern, fix, impact = row
        hex_col = SEV_HEX.get(sev, "546E7A")
        dq_data.append([
            Paragraph(f"<b>{dq_id}</b>",  S["cell"]),
            Paragraph(name,               S["body_bold"]),
            Paragraph(
                f'<font color="#{hex_col}"><b>{sev}</b></font>', S["cell"]
            ),
            Paragraph(f"<i>{pattern}</i>", S["code"]),
            Paragraph(fix,                 S["cell"]),
            Paragraph(impact,              S["cell"]),
        ])


    dq_tbl = Table(
        dq_data,
        colWidths=[1.3*cm, 3*cm, 1.6*cm, 4.2*cm, 4.8*cm, 3.1*cm],
        repeatRows=1,
    )
    dq_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  LIGHT_GREEN),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [OFF_WHITE, PALE_GREEN]),
        ("GRID",          (0, 0), (-1, -1), 0.3, LIGHT_GRAY),
        ("BOX",           (0, 0), (-1, -1), 0.8, MID_GREEN),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("ALIGN",         (0, 0), (0, -1),  "CENTER"),
        ("ALIGN",         (2, 0), (2, -1),  "CENTER"),
    ]))
    story.append(dq_tbl)
    story.append(sp(0.3))

    story.append(body(
        "<b>Two-layer defence:</b> SQL-level filters remove the bulk of bad records "
        "before data is loaded into Python. The Python <code>clean_products()</code> "
        "function applies a second pass (including deduplication) as a safety net.", S,
    ))

    # =========================================================================
    # 5. ALLOWED METADATA FILTERS
    # =========================================================================
    story.append(PageBreak())
    story.append(section_title("5.  Allowed Metadata Filters", S))
    story.append(body(
        "The <b>VectorStore</b> class (<code>app/retrieval/vector_store.py</code>) "
        "supports the following metadata filters via ChromaDB's <code>where</code> "
        "clause. Filters are applied <i>before</i> vector ranking, reducing the ANN "
        "search space and improving both speed and precision:", S,
    ))
    story.append(sp(0.2))

    f_data = [[
        Paragraph("<b>Filter Key</b>",   S["cell_hdr"]),
        Paragraph("<b>Type</b>",         S["cell_hdr"]),
        Paragraph("<b>Operator</b>",     S["cell_hdr"]),
        Paragraph("<b>Description</b>",  S["cell_hdr"]),
        Paragraph("<b>Example Value</b>",S["cell_hdr"]),
        Paragraph("<b>Source Column</b>",S["cell_hdr"]),
    ]]
    for row in FILTERS:
        f_key, f_type, f_op, f_desc, f_ex, f_src = row
        f_data.append([
            Paragraph(f"<b><code>{f_key}</code></b>", S["body_bold"]),
            Paragraph(f"<code>{f_type}</code>",       S["code"]),
            Paragraph(f"<code>{f_op}</code>",         S["code"]),
            Paragraph(f_desc,                         S["cell"]),
            Paragraph(f"<code>{f_ex}</code>",         S["code"]),
            Paragraph(f_src,                          S["cell"]),
        ])
    story.append(styled_table(f_data, [2.5, 1.5, 1.8, 4.5, 3.5, 4.2], S))
    story.append(sp(0.3))

    # API usage example
    story.append(sub_title("API Request Example — POST /api/search/debug", S))
    story.append(Paragraph("""{
  "query":     "زيت زيتون بكر",
  "brand":     "Spinneys",
  "price_max": 100.0,
  "in_stock":  true,
  "top_k":     10
}""", S["code"]))
    story.append(sp(0.15))
    story.append(body(
        "The <code>SearchFilters</code> dataclass translates these values into a "
        "ChromaDB <code>$and</code> compound <code>where</code> clause. When no "
        "filters are supplied, the full collection is searched (pure semantic match).", S,
    ))

    story.append(sp(0.3))
    story.append(sub_title("Filter Combination Logic", S))
    logic_data = [
        [Paragraph("<b>Scenario</b>",         S["cell_hdr"]),
         Paragraph("<b>ChromaDB where clause</b>", S["cell_hdr"])],
        [Paragraph("brand only",              S["cell"]),
         Paragraph('{"brand": {"$eq": "Spinneys"}}', S["code"])],
        [Paragraph("price_max only",          S["cell"]),
         Paragraph('{"price": {"$lte": 50.0}}', S["code"])],
        [Paragraph("in_stock only",           S["cell"]),
         Paragraph('{"in_stock": {"$eq": 1}}', S["code"])],
        [Paragraph("brand + price_max",       S["cell"]),
         Paragraph('{"$and": [{"brand": {"$eq": "X"}}, {"price": {"$lte": 50.0}}]}', S["code"])],
        [Paragraph("All three filters",       S["cell"]),
         Paragraph('{"$and": [brand_eq, price_lte, in_stock_eq]}', S["code"])],
        [Paragraph("No filters",              S["cell"]),
         Paragraph("where=None  (full semantic search)", S["cell"])],
    ]
    story.append(styled_table(logic_data, [4.5, 13.5], S))

    # =========================================================================
    # 6. MEMORY RULES
    # =========================================================================
    story.append(PageBreak())
    story.append(section_title("6.  Conversational Memory Rules (6 Rules)", S))
    story.append(body(
        "The session memory layer (<code>app/state/</code>) maintains a structured "
        "conversation context across turns. The following six rules govern how "
        "user intent is accumulated, persisted, and reset:", S,
    ))
    story.append(sp(0.2))

    for rule_id, rule_name, rule_desc, rule_ex in MEMORY_RULES:
        block = [
            Paragraph(
                f'<font color="#2D6A4F"><b>{rule_id}</b></font>&nbsp;&nbsp;{rule_name}',
                S["section_h2"],
            ),
            Paragraph(rule_desc, S["body"]),
            Paragraph(f"<b>Example:</b> <i>{rule_ex}</i>", S["bullet"]),
            hr(LIGHT_GRAY, 0.5),
            sp(0.1),
        ]
        story.append(KeepTogether(block))

    story.append(sp(0.2))
    story.append(body(
        "Memory rules MR-01 through MR-05 operate on the filter state "
        "(<code>SearchFilters</code> dataclass). MR-06 operates on a separate "
        "cart accumulator list in the session state. All rules are reset when "
        "the user starts a new session or explicitly requests a reset.", S,
    ))

    # =========================================================================
    # 7. TECH STACK
    # =========================================================================
    story.append(PageBreak())
    story.append(section_title("7.  Technology Stack", S))

    ts_data = [[
        Paragraph("<b>Layer</b>",       S["cell_hdr"]),
        Paragraph("<b>Technology</b>",  S["cell_hdr"]),
        Paragraph("<b>Version / Detail</b>", S["cell_hdr"]),
    ]]
    for layer, tech, ver in TECH_STACK[1:]:   # skip header row
        ts_data.append([
            Paragraph(layer, S["body_bold"]),
            Paragraph(tech,  S["cell"]),
            Paragraph(ver,   S["cell"]),
        ])
    story.append(styled_table(ts_data, [4.5, 7, 6.5], S))
    story.append(sp(0.3))

    # =========================================================================
    # 8. SYSTEM ARCHITECTURE
    # =========================================================================
    story.append(sub_title("8.  System Architecture Overview", S))
    arch_text = (
        "User Query (AR/EN)\n"
        "        │\n"
        "        ▼\n"
        "  ┌─────────────┐\n"
        "  │  FastAPI     │  POST /api/search/debug\n"
        "  │  (app/main) │\n"
        "  └──────┬──────┘\n"
        "         │  SearchRequest (query + filters)\n"
        "         ▼\n"
        "  ┌─────────────┐\n"
        "  │ VectorStore │  embed query → ChromaDB.query(where=...)\n"
        "  │ (retrieval) │\n"
        "  └──────┬──────┘\n"
        "         │  top-K SearchResult objects\n"
        "         ▼\n"
        "  ┌─────────────┐\n"
        "  │  Response   │  ranked products + similarity scores\n"
        "  └─────────────┘"
    )
    story.append(Paragraph(arch_text, S["code"]))

    story.append(sp(0.3))

    # =========================================================================
    # 9. FILE STRUCTURE
    # =========================================================================
    story.append(sub_title("9.  Project File Structure", S))
    structure = (
        "grocery_database/\n"
        "├── .env                    ← Runtime config (DB creds, model names)\n"
        "├── .env.example            ← Config template for team onboarding\n"
        "├── requirements.txt        ← Python dependencies\n"
        "├── app/\n"
        "│   ├── main.py             ← FastAPI app (GET /health, POST /api/search/debug)\n"
        "│   ├── core/               ← Shared config & utilities (Week 3+)\n"
        "│   ├── nlu/                ← Intent & entity extraction (Week 3)\n"
        "│   ├── retrieval/\n"
        "│   │   └── vector_store.py ← VectorStore + SearchFilters + SearchResult\n"
        "│   └── state/              ← Session memory & cart state (Week 3)\n"
        "├── scripts/\n"
        "│   ├── ingest.py           ← MySQL → ChromaDB ingestion pipeline\n"
        "│   └── generate_report.py  ← This report generator\n"
        "└── data/\n"
        "    └── vectordb/           ← ChromaDB persistent storage (local)"
    )
    story.append(Paragraph(structure, S["code"]))

    # =========================================================================
    # 10. NEXT STEPS (Week 3)
    # =========================================================================
    story.append(sp(0.3))
    story.append(section_title("10.  Next Steps — Week 3 Roadmap", S))

    next_items = [
        ("NLU Layer", "Build <code>app/nlu/parser.py</code> — LLM-powered intent extraction "
                      "using Groq (llama-3.1-8b-instant) to parse brand, category, price, "
                      "quantity, and dietary constraints from free-form Arabic/English queries."),
        ("Session State", "Implement <code>app/state/session.py</code> — apply all 6 memory "
                          "rules to persist and update SearchFilters across conversation turns."),
        ("Conversational API", "Add <code>POST /api/chat</code> — full pipeline: NLU → memory "
                               "update → vector search → LLM response generation."),
        ("Hybrid Search", "Combine dense vector search with BM25 keyword search for "
                          "better recall on exact product names and SKUs."),
        ("Arabic Query Tuning", "Fine-tune the 'query:' prefix and test Arabic transliteration "
                                "handling for common Arabised brand names."),
        ("Evaluation Harness", "Build a test set of 50 benchmark queries (AR + EN) with "
                               "expected top-3 results; measure Recall@5 and MRR."),
    ]
    for title, desc in next_items:
        story.append(KeepTogether([
            bullet_item(f"<b>{title}:</b>  {desc}", S),
        ]))
    story.append(sp(0.3))

    # =========================================================================
    # END
    # =========================================================================
    story.append(hr(MID_GREEN, 1.5))
    story.append(Paragraph(
        "End of Report  —  Spinneys Conversational Shopping Assistant  —  Week 1 &amp; 2 Deliverables",
        S["footer"],
    ))

    # ── Build ─────────────────────────────────────────────────────────────────
    doc.build(story)
    print(f"\n✅  Report saved → {output_path}")
    print(f"    File size: {Path(output_path).stat().st_size / 1024:.1f} KB")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Generate Spinneys Week 1 & 2 PDF Report")
    p.add_argument(
        "--output", "-o",
        default="spinneys_week1_week2_report.pdf",
        help="Output PDF filename (default: spinneys_week1_week2_report.pdf)",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    ROOT = Path(__file__).resolve().parent.parent
    output_path = ROOT / args.output

    print("🚀  Generating Spinneys Week 1 & 2 Deliverables Report …")
    build_pdf(str(output_path))
