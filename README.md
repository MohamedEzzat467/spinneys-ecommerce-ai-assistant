# 🛒 Spinneys Conversational Shopping Assistant
### مساعد تسوق سبينيس الذكي — الإنتاج النهائي (Production Release)

[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat&logo=python)](https://python.org)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-VectorStore-orange?style=flat)](https://www.trychroma.com/)
[![License](https://img.shields.io/badge/License-Proprietary-red)]()

A high-performance, bilingual (Arabic & English) conversational AI shopping assistant and hybrid product retrieval engine powered by **FastAPI**, **In-Memory BM25**, **ChromaDB Dense Vectors**, and a compact **Llama 3 / Deterministic NLU Parser**. 

Built over the real Spinneys retail catalog of **25,881 products**, the assistant guarantees ultra-low retrieval latency (< 40 ms fast-path), 100% catalog grounding, active multi-turn context tracking, and an interactive Arabic-first Chat UI.

---

## 🏛 Architecture Overview

```
                                      +-----------------------------+
                                      |   Browser / Chat UI         |
                                      |   http://localhost:3000     |
                                      +--------------+--------------+
                                                     | HTTP / REST
                                                     v
                                      +-----------------------------+
                                      |   FastAPI Gateway (:8000)   |
                                      |   app/main.py               |
                                      +--------------+--------------+
                                                     |
                     +-------------------------------+-------------------------------+
                     |                                                               |
                     v                                                               v
       +----------------------------+                                  +----------------------------+
       |   Multi-Turn Session State |                                  |      NLU Hybrid Parser     |
       |   app/state/context.py     |                                  |      app/nlu/parser.py     |
       |   - Refinement             |                                  |   - Intent Classification  |
       |   - Topic Switch           |<---------------------------------|   - Filter Entity Parsing  |
       |   - Cancellation           |     Merged Context Filters       |   - Guardrail Detection    |
       |   - Item References        |                                  |   - Prompt: <= 150 Tokens  |
       +--------------+-------------+                                  +----------------------------+
                      |
                      v
       +--------------------------------------------------------------------------------------------+
       |                        Hybrid Product Retrieval Engine (app/retrieval/)                    |
       |                                                                                            |
       |  +-------------------------+    Reciprocal Rank Fusion (RRF)    +------------------------+ |
       |  |     BM25 Lexical        |                                    |   Dense Vector Search  | |
       |  |  (data/retrieval_docs)  | ---------------------------------> |   (ChromaDB Collection)| |
       |  +-------------------------+                                    +------------------------+ |
       |                                             |                                              |
       |                                             v                                              |
       |                       +------------------------------------------+                         |
       |                       | Metadata Layer (data/retrieval_meta.parquet)                      |
       |                       | 25,881 items: price, brand, stock, images|                         |
       |                       +------------------------------------------+                         |
       +--------------------------------------------------------------------------------------------+
```

---

## 🚀 Quick Start (Under 3 Minutes)

### 1. Prerequisites
- **Python 3.10+**
- Git & PowerShell (Windows) or Bash (macOS/Linux)

### 2. Setup Environment
```bash
# Clone the repository
git clone <repo_url> grocery_database
cd grocery_database

# Create & activate virtual environment
python -m venv venv

# Windows:
.\venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
*(Optional: Add your `GROQ_API_KEY` for LLM-enhanced NLU. If omitted, the system falls back seamlessly to deterministic regex rules).*

### 4. One-Command System Startup
Run the unified startup script:

**Windows:**
```cmd
start_all.bat
```

**Linux / macOS:**
```bash
chmod +x start_all.sh
./start_all.sh
```

### 5. Access Points
- 🌐 **Frontend Chat UI**: [http://localhost:3000](http://localhost:3000)
- 📖 **Interactive Swagger API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- 🩺 **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 📡 API Endpoints Reference

### Conversational AI & Search
| Endpoint | Method | Description | Request Example |
| :--- | :--- | :--- | :--- |
| `/health` | `GET` | Health check, vector store readiness, and embedding config | `curl http://localhost:8000/health` |
| `/api/chat` | `POST` | Multi-turn conversational shopping pipeline with context tracking | `{"session_id": "demo-1", "message": "عايز لبن شوفان"}` |
| `/api/search` | `POST` | Catalog retrieval endpoint (supports `hybrid`, `vector`, `bm25` modes) | `{"query": "زبادي يوناني", "limit": 10, "mode": "hybrid"}` |
| `/api/parse` | `POST` | NLU parser extracting intent and filters in strict JSON schema | `{"query": "شاي ليبتون اقل من 50 جنيه"}` |

### E-Commerce Storefront & Checkout
| Endpoint | Method | Description | Request Example |
| :--- | :--- | :--- | :--- |
| `/api/store/categories` | `GET` | List categories, icons, brand taxonomy, and catalog price range | `curl http://localhost:8000/api/store/categories` |
| `/api/store/products` | `GET` | Fast in-memory catalog browsing with filters, search, and pagination | `curl "http://localhost:8000/api/store/products?page=1&category=Beverages"` |
| `/api/store/cart/validate` | `POST` | Validates cart items against catalog and real-time MySQL inventory | `{"items": [{"product_id": 2401, "quantity": 2}]}` |
| `/api/store/checkout` | `POST` | Places order, persists in MySQL `store_orders`, and returns receipt | `{"customer_name": "Sarah", "items": [{"product_id": 2401, "quantity": 1}]}` |

---

## 📊 Retrieval Performance & Benchmark

Results from the 60-query annotated benchmark dataset (`scripts/evaluate_retrieval_week5.py`):

| Retrieval Mode | MRR@5 | Recall@5 | P95 Latency | Cold Start | Grounding Rate |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Keyword (BM25)** | 0.812 | 0.845 | ~12 ms | 350 ms | 100% |
| **Dense Vector (ChromaDB)** | 0.785 | 0.820 | ~85 ms | 1,200 ms | 100% |
| **Hybrid (BM25 + Vector + RRF)** | **0.894** | **0.932** | **~24 ms** | **450 ms** | **100%** |

- **Catalog Scale**: 25,881 unique active products.
- **Fast-path Latency Target**: Achieved < 40 ms average latency on filtered search queries.
- **Stock Awareness**: 100% adherence to `in_stock: true` constraints.

---

## 🧪 Acceptance Verification Checklist

Execute the automated acceptance verification suite:
```bash
python scripts/verify_acceptance_week6.py
```

### Verification Matrix (11 / 11 Criteria Passed)
```
==========================================================================================
#    | Acceptance Criteria Check              | Status       | Validation Detail
------------------------------------------------------------------------------------------
1    | Check 1: System Health                 | PASSED ✅     | Status: 200, DB Ready: Validated
2    | Check 2: English 8-Turn Demo Flow      | PASSED ✅     | 8/8 turns executed successfully (HTTP 200)
3    | Check 3: Arabic & Mixed Demo Flow      | PASSED ✅     | 8/8 Arabic turns executed successfully (HTTP 200)
4    | Check 4: Stock Awareness               | PASSED ✅     | 100% verified In-Stock (availability: True)
5    | Check 5: Multi-Turn Context Retention  | PASSED ✅     | Filters: {'max_price': 60.0} applied to topic
6    | Check 6: Retrieval Modes Switching     | PASSED ✅     | Vector mode: 200 | Hybrid mode: 200
7    | Check 7: Conversational Guardrails     | PASSED ✅     | Intent: out-of-scope | Friendly redirection
8    | Check 8: Graceful Failure Handling     | PASSED ✅     | HTTP 422 structured JSON validation errors
9    | Check 9: System & Request Logging      | PASSED ✅     | Log file active at logs/app.log
10   | Check 10: Prompt Budget Compliance     | PASSED ✅     | Prompt length: 476 chars, ~119 tokens (<= 150)
11   | Check 11: Fresh Start & Packaging      | PASSED ✅     | All 9 essential project files verified
==========================================================================================
FINAL VERIFICATION RESULT: ALL 11 ACCEPTANCE CHECKS PASSED ✅
```

---

## 🎯 8-Turn Demo Scenarios

See [`docs/live_demo_script.md`](docs/live_demo_script.md) for the complete turn-by-turn presentation script, covering:
1. **Initial Search**: `"عايز لبن شوفان"` (Oat milk discovery)
2. **Price Refinement**: `"اقل من 60 جنيه"` (Contextual price constraint)
3. **Attribute Filter**: `"قليل السكر"` (Sub-query refinement)
4. **Brand Filter**: `"عايز ماركة جهينة بس"` (Single brand restriction)
5. **Sort Order**: `"رتبهم من الارخص للاغلى"` (Price ascending sorting)
6. **Out-of-Stock Fallback**: `"لو مش متاح هات بديل"` (Alternative recommendations)
7. **Cross-Selling & Pairing**: `"ايه ينفع معاه؟"` (Complementary items discovery)
8. **Guardrails & Redirection**: `"اكتبلي كود بايثون"` (Polite redirection to groceries)

---

## 📁 Project Structure

```
grocery_database/
├── app/
│   ├── core/           # Config, logging, shared text normalizer
│   ├── nlu/            # Intent & filter parser (hybrid regex + compact LLM)
│   ├── retrieval/      # Hybrid BM25 + dense vector retriever & RRF ranker
│   ├── state/          # Multi-turn in-memory session context manager
│   └── main.py         # FastAPI application & REST endpoints
├── data/
│   ├── retrieval_meta.parquet   # 25,881 product metadata records
│   ├── retrieval_docs.parquet   # Searchable normalized product corpus
│   └── vectordb/                # ChromaDB vector store
├── frontend/
│   ├── index.html      # Responsive Chat UI interface
│   ├── styles.css      # Spinneys branded styling & RTL layout
│   └── app.js          # Client-side session, chat stream, & filter chips
├── scripts/
│   ├── verify_acceptance_week6.py  # Automated 11-point acceptance test
│   ├── evaluate_retrieval_week5.py # Retrieval benchmarking script
│   └── evaluate_parser.py          # NLU accuracy & F1 benchmark
├── docs/
│   ├── live_demo_script.md         # 8-turn presentation walkthrough
│   └── annotation_guide_w3.md      # Ground truth labeling guide
├── start_all.bat       # Windows one-command startup script
├── start_all.sh        # Linux/macOS one-command startup script
├── requirements.txt    # Project dependencies
└── README.md           # This documentation
```

---

## 👥 Authors & Team
Engineered for the **Spinneys Conversational AI Shopping Assistant Project**.
All rights reserved © 2026.
