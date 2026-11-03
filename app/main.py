"""
app/main.py
===========
Spinneys Conversational Shopping Assistant — FastAPI Application

Endpoints
---------
GET  /health          → system health check (DB connectivity + vector store size)
POST /api/search/debug → raw vector search with optional metadata filters (debug use)
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional, Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── Load .env before importing internal modules ────────────────────────────────
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from app.retrieval.vector_store import VectorStore, SearchFilters, SearchResult
from app.retrieval.retriever import ProductRetriever
from app.nlu.parser import ParseRequest, ParseResult, parse_query, sanitize_query
from app.state.context import SessionManager, SessionState
from app.store.service import StoreService

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
    ],
)
log = logging.getLogger("spinneys.api")


# ─────────────────────────────────────────────────────────────────────────────
# Application state (singleton VectorStore)
# ─────────────────────────────────────────────────────────────────────────────

class AppState:
    vector_store: Optional[VectorStore] = None
    retriever: Optional[ProductRetriever] = None
    session_manager: Optional[SessionManager] = None


state = AppState()


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan (startup / shutdown)
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise shared resources on startup; release on shutdown."""
    log.info("🚀 Starting Spinneys Shopping Assistant API …")

    state.vector_store = VectorStore()
    log.info(
        "VectorStore ready — collection contains %d items",
        state.vector_store.collection_size() if state.vector_store.is_ready() else 0,
    )
    state.retriever = ProductRetriever(vector_store=state.vector_store)
    log.info("ProductRetriever & In-Memory Hybrid Engine ready.")
    state.session_manager = SessionManager()
    log.info("SessionManager ready for multi-turn conversational context.")

    yield  # ← application runs here

    log.info("👋 Shutting down …")
    state.vector_store = None
    state.retriever = None
    state.session_manager = None


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Spinneys Conversational Shopping Assistant",
    description=(
        "AI-powered product search API for the Spinneys grocery platform. "
        "Supports semantic vector search with metadata filtering."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS for local development and cloud hosting (Vercel, Netlify, Render, GitHub Pages)
allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "*").strip()
if allowed_origins_raw == "*" or not allowed_origins_raw:
    origins = ["*"]
    allow_credentials = False
else:
    origins = [orig.strip() for orig in allowed_origins_raw.split(",") if orig.strip()]
    allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.vercel\.app|https://.*\.netlify\.app|https://.*\.github\.io|http://localhost:.*" if origins != ["*"] else None,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Schemas
# ─────────────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    vector_store_ready: bool
    collection_size: int
    embedding_model: str
    retrieval_mode: str


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, examples=["خبز أبيض طازج"])
    top_k: Optional[int] = Field(None, ge=1, le=100, description="Override default TOP_K")

    # Optional metadata filters
    brand: Optional[str] = Field(None, examples=["Spinneys"])
    price_max: Optional[float] = Field(None, gt=0, examples=[50.0])
    in_stock: Optional[bool] = Field(None, description="True → in-stock only")


class ProductResult(BaseModel):
    product_id: str
    product_name: str
    brand: str
    category: str
    price: float
    in_stock: bool
    similarity_score: float   # 1 - cosine_distance, higher = more similar


class SearchDebugResponse(BaseModel):
    query: str
    filters_applied: dict
    total_results: int
    results: list[ProductResult]


class SearchQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, examples=["حليب المراعي اقل من 60 متاح"])
    limit: Optional[int] = Field(10, ge=1, le=100)
    mode: Optional[str] = Field("auto", pattern="^(auto|rules|hybrid|bm25|vector)$")


class CatalogProductItem(BaseModel):
    product_id: int
    name_ar: str
    name_en: str
    brand: str
    price: float
    regular_price: float
    has_discount: bool
    availability: bool
    image_url: str


class SearchResponse(BaseModel):
    query: str
    total_matched: Optional[int] = None
    execution_time_ms: Optional[float] = None
    applied_filters: Optional[dict[str, Any]] = None
    products: Optional[list[CatalogProductItem]] = None

    # Recipe / Smart Cart fields
    intent: Optional[str] = None
    dish: Optional[str] = None
    cart: Optional[list[dict[str, Any]]] = None


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=100, examples=["demo-1"])
    message: str = Field(..., min_length=1, max_length=1000, examples=["عايز لبن شوفان"])


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    intent: str
    filters: dict[str, Any]
    products: list[CatalogProductItem] = Field(default_factory=list)
    dish: Optional[str] = None
    cart: Optional[list[dict[str, Any]]] = None


class CartItemInput(BaseModel):
    product_id: int
    quantity: int = Field(1, ge=1)


class CartValidationRequest(BaseModel):
    items: list[CartItemInput] = Field(default_factory=list)


class CheckoutRequest(BaseModel):
    customer_name: str = Field(..., min_length=2, max_length=150)
    customer_phone: str = Field(..., min_length=6, max_length=50)
    delivery_address: str = Field(..., min_length=5, max_length=500)
    delivery_notes: Optional[str] = None
    payment_method: str = Field("Cash on Delivery")
    items: list[CartItemInput] = Field(..., min_length=1)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def result_to_schema(r: SearchResult) -> ProductResult:
    return ProductResult(
        product_id=r.product_id,
        product_name=r.product_name,
        brand=r.brand,
        category=r.category,
        price=r.price,
        in_stock=r.in_stock,
        similarity_score=round(1.0 - r.distance, 4),
    )


def require_vector_store() -> VectorStore:
    if state.vector_store is None or not state.vector_store.is_ready():
        raise HTTPException(
            status_code=503,
            detail=(
                "Vector store is not ready. "
                "Please run `python scripts/ingest.py` first to populate the product database."
            ),
        )
    return state.vector_store


def require_retriever() -> ProductRetriever:
    if state.retriever is None:
        state.retriever = ProductRetriever(vector_store=state.vector_store)
    return state.retriever


def require_session_manager() -> SessionManager:
    if state.session_manager is None:
        state.session_manager = SessionManager()
    return state.session_manager


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    tags=["System"],
)
async def health_check() -> HealthResponse:
    """
    Returns the current health status of the API including:
    - Vector store readiness and item count
    - Active embedding model
    - Configured retrieval mode
    """
    vs = state.vector_store
    ready = vs is not None and vs.is_ready()
    size = vs.collection_size() if ready else 0

    return HealthResponse(
        status="ok" if ready else "degraded",
        vector_store_ready=ready,
        collection_size=size,
        embedding_model=os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-base"),
        retrieval_mode=os.getenv("RETRIEVAL_MODE", "vector"),
    )


@app.post(
    "/api/chat",
    response_model=ChatResponse,
    summary="Multi-turn Conversational Shopping Assistant",
    tags=["Chat"],
)
async def chat_conversation(request: ChatRequest) -> ChatResponse:
    """
    **Unified Multi-turn Conversational Shopping Assistant**
    
    Pipeline:
      a. Parses natural language message using NLU Parser (`app.nlu.parser`).
      b. Updates session context (`app.state.context.SessionManager`) retaining active filters.
      c. Executes hybrid retrieval (`app.retrieval.retriever.ProductRetriever`) with merged constraints.
      d. Returns natural conversational response with ranked products.
    """
    session_mgr = require_session_manager()
    retriever = require_retriever()

    try:
        # Step a: Parse user message
        nlu = parse_query(request.message)

        # Step b: Update session state
        state = session_mgr.update_state(request.session_id, nlu)
        active_filters = state.to_filters()

        # Step b.2: In-memory sorting for contextual follow-up sort requests
        is_sort_request = (
            nlu.intent == "sort"
            or (nlu.sort is not None and not nlu.query)
        )
        if is_sort_request and state.last_results:
            sort_desc = (nlu.sort == "price_desc")
            sorted_products = sorted(
                state.last_results,
                key=lambda p: float(p.get("price", 0.0)),
                reverse=sort_desc,
            )
            state.last_results = sorted_products
            reply = "تم ترتيب المنتجات من الأعلى سعراً إلى الأقل:" if sort_desc else "تم ترتيب المنتجات من الأقل سعراً إلى الأعلى:"
            return ChatResponse(
                session_id=request.session_id,
                reply=reply,
                intent="sort",
                filters=active_filters,
                products=[CatalogProductItem(**p) for p in sorted_products],
            )

        # Step c: Execute retrieval with merged session filters
        target_query = state.query if (nlu.intent in ("refine", "sort") and state.query) else request.message
        retrieval_res = retriever.retrieve(
            query=target_query,
            limit=10,
            mode="auto",
            filter_overrides=active_filters,
        )

        # Check if Recipe / Smart Cart response
        if retrieval_res.get("intent") == "recipe":
            dish_name = retrieval_res.get("dish", target_query)
            cart_items = retrieval_res.get("cart", [])
            reply = f"حضرت لك قائمة المكونات لتحضير {dish_name} مع المنتجات المقترحة من سبينيس:"
            return ChatResponse(
                session_id=request.session_id,
                reply=reply,
                intent="recipe",
                filters=active_filters,
                products=[],
                dish=dish_name,
                cart=cart_items,
            )

        # Check if Healthy Meal Recommendation response
        if retrieval_res.get("is_healthy_meal"):
            dish_name = retrieval_res.get("dish", "وجبة صحية قليلة السعرات")
            cart_items = retrieval_res.get("cart", [])
            matched_products = retrieval_res.get("products", [])
            state.last_results = matched_products
            reply = retrieval_res.get("reply") or f"اقترحت لك {dish_name} متوازنة وقليلة السعرات الحرارية من منتجات سبينيس:"
            return ChatResponse(
                session_id=request.session_id,
                reply=reply,
                intent="recommend",
                filters=active_filters,
                products=[CatalogProductItem(**p) for p in matched_products],
                dish=dish_name,
                cart=cart_items,
            )

        matched_products = retrieval_res.get("products", [])
        state.last_results = matched_products
        count = len(matched_products)

        # Step d: Formulate natural conversational reply
        if nlu.intent == "out-of-scope":
            reply = "أنا مساعد سبينيس الذكي للتسوق، أقدر أساعدك في البحث عن المنتجات والأسعار والوصفات في السوبرماركت."
        elif count == 0:
            filter_desc = []
            if state.brand:
                filter_desc.append(f"ماركة {state.brand}")
            if state.price_max:
                filter_desc.append(f"أقل من {state.price_max} جنيه")
            if state.in_stock:
                filter_desc.append("المتوفر فقط")
            suffix = f" مع فلاتر: {', '.join(filter_desc)}" if filter_desc else ""
            reply = f"للأسف لم أجد منتجات تطابق بحثك عن '{target_query}'{suffix}."
        else:
            clean_item = sanitize_query(target_query) if target_query else ""
            item_desc = clean_item if clean_item else "تناسب طلبك"
            reply = f"وجدت لك {count} منتجات {item_desc} متاحة في الكتالوج:"

        products_list = [
            CatalogProductItem(**p) for p in matched_products
        ]

        return ChatResponse(
            session_id=request.session_id,
            reply=reply,
            intent=nlu.intent,
            filters=active_filters,
            products=products_list,
        )
    except Exception as exc:
        log.exception("Chat conversation failed for session %r: %s", request.session_id, exc)
        raise HTTPException(status_code=500, detail=f"Chat error: {exc}")


@app.post(
    "/api/search",
    response_model=SearchResponse,
    summary="Catalog Product Retrieval & Hybrid Search",
    tags=["Search"],
)
async def search_products(request: SearchQueryRequest) -> SearchResponse:
    """
    **Product Retrieval Engine** — returns ranked products from the Spinneys catalog.
    
    Supports:
    - Ultra-low latency fast-path (< 40 ms)
    - Full filter parsing (brand, category, price_max, price_min, in_stock, sort)
    - Negation / exclusion arbitration (e.g., 'شاي بس مش ليبتون')
    - Recipe-to-cart decomposition (e.g., 'عايز اعمل مكرونة بشاميل')
    - Hybrid BM25 & dense vector search with Reciprocal Rank Fusion (RRF)
    """
    retriever = require_retriever()
    try:
        res = retriever.retrieve(
            query=request.query,
            limit=request.limit or 10,
            mode=request.mode or "auto",
        )
        return SearchResponse(**res)
    except Exception as exc:
        log.exception("Retrieval failed for query %r: %s", request.query, exc)
        raise HTTPException(status_code=500, detail=f"Retrieval error: {exc}")


@app.post(
    "/api/search/debug",
    response_model=SearchDebugResponse,
    summary="Debug vector search",
    tags=["Search"],
)
async def search_debug(request: SearchRequest) -> SearchDebugResponse:
    """
    **Debug endpoint** — performs a raw vector search and returns full results
    with similarity scores and applied filters.

    Useful for evaluating retrieval quality before wiring up the full
    conversational pipeline.

    ### Filter examples
    ```json
    {
        "query": "زيت زيتون",
        "brand": "Spinneys",
        "price_max": 100.0,
        "in_stock": true,
        "top_k": 10
    }
    ```
    """
    vs = require_vector_store()

    filters = SearchFilters(
        brand=request.brand,
        price_max=request.price_max,
        in_stock=request.in_stock,
    )

    filters_applied = {
        k: v for k, v in {
            "brand": request.brand,
            "price_max": request.price_max,
            "in_stock": request.in_stock,
        }.items()
        if v is not None
    }

    log.info(
        "DEBUG SEARCH | query=%r | filters=%s | top_k=%s",
        request.query, filters_applied, request.top_k,
    )

    try:
        raw_results = vs.search(
            query=request.query,
            filters=filters if any(v is not None for v in [request.brand, request.price_max, request.in_stock]) else None,
            top_k=request.top_k,
        )
    except Exception as exc:
        log.exception("Search failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Search error: {exc}")

    return SearchDebugResponse(
        query=request.query,
        filters_applied=filters_applied,
        total_results=len(raw_results),
        results=[result_to_schema(r) for r in raw_results],
    )


@app.post(
    "/api/parse",
    response_model=ParseResult,
    summary="Parse natural language customer query",
    tags=["NLU"],
)
async def parse_customer_query(request: ParseRequest) -> ParseResult:
    """
    **NLU Filter & Intent Parser** — parses natural language queries in
    Arabic, English, or Franco-Arabic.
    
    Returns:
    - Target search keyword (`query`)
    - Official 8 intents (`search`, `refine`, `sort`, `recommend`, `compare`, `alternatives`, `cross-sell`, `out-of-scope`)
    - Structured filter criteria (`brand`, `price_min`, `price_max`, `in_stock`, `sort`)
    - Isolated unsupported filters (`sugar-free`, `gluten-free`, `organic`, etc.)
    - Latency in milliseconds (`latency_ms`)
    """
    try:
        return parse_query(request.text)
    except Exception as exc:
        log.exception("NLU parsing failed for query %r: %s", request.text, exc)
        raise HTTPException(status_code=500, detail=f"Parsing error: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Storefront Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
    "/api/store/categories",
    summary="List store categories and brand taxonomy",
    tags=["Store"],
)
async def get_store_categories() -> dict[str, Any]:
    """Returns store categories, visual icons, top brands, and global price range."""
    retriever = require_retriever()
    return StoreService.get_categories_and_brands(retriever)


@app.get(
    "/api/store/products",
    summary="Paginated catalog browsing with multi-attribute filtering",
    tags=["Store"],
)
async def get_store_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    category: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    price_min: Optional[float] = Query(None, ge=0),
    price_max: Optional[float] = Query(None, ge=0),
    in_stock: Optional[bool] = Query(None),
    sort: Optional[str] = Query("popular"),
) -> dict[str, Any]:
    """
    Browses the Spinneys catalog in-memory with sub-20ms latency.
    Supports filtering by category, brand, price range, stock, search query, and sorting.
    """
    retriever = require_retriever()
    return StoreService.get_products(
        retriever=retriever,
        page=page,
        page_size=page_size,
        category=category,
        brand=brand,
        search=search,
        price_min=price_min,
        price_max=price_max,
        in_stock=in_stock,
        sort=sort,
    )


@app.post(
    "/api/store/cart/validate",
    summary="Validate shopping cart items and compute totals",
    tags=["Store"],
)
async def validate_cart_items(request: CartValidationRequest) -> dict[str, Any]:
    """
    Validates cart items against catalog pricing and real-time MySQL inventory.
    Returns computed subtotal, delivery fee, line totals, and item details.
    """
    retriever = require_retriever()
    items_dict = [item.model_dump() for item in request.items]
    return StoreService.validate_cart(retriever, items_dict)


@app.post(
    "/api/store/checkout",
    summary="Place checkout order and generate receipt",
    tags=["Store"],
)
async def store_checkout(request: CheckoutRequest) -> dict[str, Any]:
    """
    Finalizes checkout, stores order into MySQL `store_orders` table,
    and returns a confirmed receipt payload.
    """
    retriever = require_retriever()
    try:
        return StoreService.checkout_order(retriever, request.model_dump())
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as exc:
        log.exception("Checkout failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Checkout error: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Dev entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
