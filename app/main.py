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
import re
from contextlib import asynccontextmanager
from typing import Optional, Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse
from pydantic import BaseModel, Field

# ── Load .env before importing internal modules ────────────────────────────────
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"
load_dotenv(ROOT / ".env")

from app.retrieval.vector_store import VectorStore, SearchFilters, SearchResult
from app.retrieval.retriever import ProductRetriever
from app.nlu.parser import ParseRequest, ParseResult, parse_query, sanitize_query, ADVISORY_RE, PRODUCT_ENTITY_RE
from app.state.context import SessionManager, SessionState
from app.store.service import StoreService
from app.core.llm import get_llm_client

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
        # Step 1: Retrieve Session State, Visible Products, and History
        state = session_mgr.get_session(request.session_id)
        visible_products = state.last_results or []
        history = getattr(state, "history", [])

        # Step 2: Invoke the LLM Central Controller
        nlu = parse_query(
            raw_text=request.message,
            session_context=state.to_filters(),
            visible_products=visible_products,
            conversation_history=history,
        )

        # Record user turn in dialog history
        history.append({"role": "user", "content": request.message})

        # Update session state filters
        state = session_mgr.update_state(request.session_id, nlu)
        active_filters = state.to_filters()

        # Step 3: Route based on LLM Action / Intent

        # === ROUTE 0: COUNT & AGGREGATION INQUIRY ===
        if nlu.is_count_query or nlu.action == "count_inquiry" or nlu.intent == "count_inquiry":
            target_entity = nlu.clean_query or "فول"
            agg = retriever.get_entity_aggregation(target_entity)
            total_count = agg["total_count"]
            varieties = agg["varieties"]
            rep_products = agg["products"]

            # Save representative products to session context
            state.last_results = rep_products

            var_text = "، ".join(varieties)
            entity_label = "الفول" if "فول" in target_entity else target_entity
            reply = f"يوجد في المتجر حوالي {total_count} أصناف من {entity_label} مقسمة إلى: ({var_text}). إليك أبرزها:"

            history.append({"role": "assistant", "content": reply})
            return ChatResponse(
                session_id=request.session_id,
                reply=reply,
                intent="count_inquiry",
                filters=active_filters,
                products=[CatalogProductItem(**p) for p in rep_products],
            )

        # === ROUTE 1: RECIPE & COOKING INQUIRIES ===
        if nlu.action == "recipe" or nlu.intent == "recipe":
            target_ingredient = nlu.primary_ingredient or nlu.clean_query or "لحم"
            retrieval_mode = "hybrid" if (retriever.hybrid_engine.vector_store and retriever.hybrid_engine.vector_store.is_ready()) else "auto"

            # Retrieve real store items for the primary ingredient
            retrieval_res = retriever.retrieve(
                query=target_ingredient,
                limit=nlu.limit or 5,
                mode=retrieval_mode,
                is_internal=True,
            )
            matched_products = [
                p for p in retrieval_res.get("products", [])
                if float(p.get("price", 0.0)) > 0.0
            ][: (nlu.limit or 5)]

            # Save real meat/ingredient products to session context
            state.last_results = matched_products

            reply = nlu.recipe_advice or (
                f"إليك مقادير وطريقة تحضير أشهى وجبة باستخدام {target_ingredient} مع أبرز المنتجات المتاحة في المتجر:"
            )
            history.append({"role": "assistant", "content": reply})

            return ChatResponse(
                session_id=request.session_id,
                reply=reply,
                intent="recipe",
                filters=active_filters,
                products=[CatalogProductItem(**p) for p in matched_products],
            )

        # === ROUTE 2: CONVERSATIONAL & NUTRITIONAL Q&A ===
        elif nlu.action == "advisory_qa" or nlu.intent == "advisory":
            # STRICT GUARD: DO NOT execute any database, vector, or keyword search!
            # Grounded solely in visible products from state.last_results
            reply = nlu.conversational_reply
            if not reply:
                if state.last_results:
                    titles = [p.get("name_ar") or p.get("name_en", "") for p in state.last_results[:4]]
                    reply = f"بالمقارنة بين المنتجات المعروضة ({' و'.join(titles)})، يُعد الخيار الأول الأكثر ملاءمة لجودة المكونات والقيمة الغذائية."
                else:
                    reply = "يسعدني تقديم المشورة الغذائية لك! من فضلك ابحث أولاً عن المنتجات التي تود مقارنتها وسأوضح لك الفروق والقيمة الغذائية."

            history.append({"role": "assistant", "content": reply})
            return ChatResponse(
                session_id=request.session_id,
                reply=reply,
                intent="advisory",
                filters=active_filters,
                products=[CatalogProductItem(**p) for p in state.last_results],
            )

        # === ROUTE 3: STANDALONE SORT ===
        elif nlu.action == "sort" or nlu.intent == "sort":
            if state.last_results:
                sort_desc = (nlu.sort_by == "price_desc")
                sorted_products = sorted(
                    state.last_results,
                    key=lambda p: float(p.get("price", 0.0)),
                    reverse=sort_desc,
                )
                state.last_results = sorted_products
                reply = "تم ترتيب المنتجات من الأعلى سعراً إلى الأقل:" if sort_desc else "تم ترتيب المنتجات من الأقل سعراً إلى الأعلى:"
                history.append({"role": "assistant", "content": reply})
                return ChatResponse(
                    session_id=request.session_id,
                    reply=reply,
                    intent="sort",
                    filters=active_filters,
                    products=[CatalogProductItem(**p) for p in sorted_products],
                )

        # === ROUTE 4: OUT OF SCOPE ===
        elif nlu.action == "out_of_scope" or nlu.intent in ("out_of_scope", "out-of-scope"):
            reply = nlu.conversational_reply or "أنا مساعد سبينيس الذكي للتسوق، أقدر أساعدك في البحث عن المنتجات والأسعار والوصفات في السوبرماركت."
            history.append({"role": "assistant", "content": reply})
            return ChatResponse(
                session_id=request.session_id,
                reply=reply,
                intent="out-of-scope",
                filters=active_filters,
                products=[],
            )

        # === ROUTE 5: CATALOG SEARCH & REFINEMENTS ===
        target_query = nlu.clean_query or nlu.semantic_expansion or state.query or request.message
        req_limit = nlu.limit or 10

        retrieval_mode = "hybrid" if (retriever.hybrid_engine.vector_store and retriever.hybrid_engine.vector_store.is_ready()) else "auto"
        overrides = dict(active_filters)
        overrides["query"] = target_query
        if nlu.category:
            overrides["category"] = nlu.category
        if nlu.attribute_focus:
            overrides["attribute_focus"] = nlu.attribute_focus

        retrieval_res = retriever.retrieve(
            query=target_query,
            limit=max(req_limit * 3, 20),
            mode=retrieval_mode,
            filter_overrides=overrides,
        )

        matched_products = [
            p for p in retrieval_res.get("products", [])
            if float(p.get("price", 0.0)) > 0.0
        ]

        # Apply in-memory sort if requested
        if nlu.sort_by != "relevance" and matched_products:
            sort_desc = (nlu.sort_by == "price_desc")
            matched_products = sorted(
                matched_products,
                key=lambda p: float(p.get("price", 0.0)),
                reverse=sort_desc,
            )

        # Apply exact limit slicing
        if req_limit and matched_products:
            matched_products = matched_products[:req_limit]

        state.last_results = matched_products
        count = len(matched_products)

        # Formulate clean conversational reply
        if count == 0:
            filter_desc = []
            if state.brand:
                filter_desc.append(f"ماركة {state.brand}")
            if state.price_max:
                filter_desc.append(f"أقل من {state.price_max} جنيه")
            if state.in_stock:
                filter_desc.append("المتوفر فقط")
            suffix = f" مع فلاتر: {', '.join(filter_desc)}" if filter_desc else ""
            reply = f"للأسف لم أجد منتجات تطابق بحثك عن '{target_query}'{suffix}."
        elif nlu.attribute_focus == "protein":
            reply = "إليك أبرز المنتجات عالية البروتين المتاحة في المتجر (مثل صدور الدواجن والتونة):"
        elif nlu.conversational_reply:
            reply = nlu.conversational_reply
        elif nlu.attribute_focus in ("low_fat", "low_cal", "diet"):
            reply = "إليك أبرز المنتجات الصحية وقليلة السعرات في المتجر:"
        elif nlu.attribute_focus == "cheap" or nlu.sort_by == "price_asc":
            clean_item = nlu.clean_query or "منتجات تناسب طلبك"
            reply = f"وجدت لك {count} منتجات {clean_item} مرتبة حسب السعر:"
        elif nlu.sort_by == "price_desc":
            clean_item = nlu.clean_query or "منتجات تناسب طلبك"
            reply = f"وجدت لك {count} منتجات {clean_item} مرتبة من الأعلى سعراً إلى الأقل:"
        else:
            clean_item = nlu.clean_query or "منتجات تناسب طلبك"
            reply = f"وجدت لك {count} منتجات {clean_item} متاحة في الكتالوج:"

        history.append({"role": "assistant", "content": reply})

        return ChatResponse(
            session_id=request.session_id,
            reply=reply,
            intent="search",
            filters=active_filters,
            products=[CatalogProductItem(**p) for p in matched_products],
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
# Frontend Static Files & SPA Root Serving
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def serve_frontend_root():
    """
    Serves the main storefront and conversational AI assistant single-page application.
    """
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Spinneys Conversational Shopping Assistant API"}


if FRONTEND_DIR.exists():
    # Mount frontend directory to serve CSS, JS, images, icons without colliding with API routes
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ─────────────────────────────────────────────────────────────────────────────
# Dev entry point & Cloud Dynamic Port Binding
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )
