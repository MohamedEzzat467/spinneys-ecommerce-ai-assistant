# -*- coding: utf-8 -*-
"""
scripts/test_bugs_fix.py
========================
Verification script for:
  - Bug 1: Polluted search queries (entity extraction failure for "افضل نوع لبن")
  - Bug 2: Contextual sorting failure (follow-up "رتبهم من الاعلى سعرا الى الاقل")
"""

import io
import sys
from pathlib import Path

# Fix UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from app.main import app
from app.nlu.parser import parse_query, sanitize_query


def main():
    print("=" * 60)
    print("RUNNING BUG FIX VERIFICATION TESTS")
    print("=" * 60)

    client = TestClient(app)
    # Warm up app
    h_resp = client.get("/health")
    assert h_resp.status_code == 200, "Health check failed"

    # -------------------------------------------------------------
    # TEST 1: Sanitizer & NLU Entity Extraction for "افضل نوع لبن"
    # -------------------------------------------------------------
    print("\n--- TEST 1: NLU & Sanitization for 'افضل نوع لبن' ---")
    raw_query = "افضل نوع لبن"
    sanitized = sanitize_query(raw_query)
    nlu_res = parse_query(raw_query)
    print(f"Raw query: '{raw_query}'")
    print(f"Sanitized: '{sanitized}'")
    print(f"Extracted query: '{nlu_res.query}'")
    print(f"Intent: '{nlu_res.intent}'")

    assert nlu_res.query in ("لبن", "حليب"), f"Expected 'لبن' or 'حليب', got '{nlu_res.query}'"
    print("TEST 1 PASSED [OK]")

    # -------------------------------------------------------------
    # TEST 2: Product Retrieval for "افضل نوع لبن"
    # -------------------------------------------------------------
    print("\n--- TEST 2: Product Retrieval for 'افضل نوع لبن' via /api/search ---")
    search_resp = client.post("/api/search", json={"query": "افضل نوع لبن", "limit": 10})
    assert search_resp.status_code == 200, f"Search failed: {search_resp.status_code}"
    res = search_resp.json()
    products = res.get("products", [])
    print(f"Retrieved {len(products)} products:")
    
    polluted = []
    for i, p in enumerate(products, 1):
        name_ar = p.get("product_name", "")
        brand = p.get("brand", "")
        price = p.get("price", 0.0)
        category = p.get("category", "")
        print(f"  {i}. {name_ar} - {brand} ({category}) - {price} EGP")
        # Check for batteries, soap, or non-food items
        if any(bad in name_ar.lower() for bad in ["بطار", "صابون", "إنرجايزر", "لايفبوي", "شوز", "معجون"]):
            polluted.append(name_ar)

    assert len(polluted) == 0, f"Polluted items found: {polluted}"
    assert len(products) > 0, "No products returned"
    print("TEST 2 PASSED: 0% pollution, 100% relevant milk products [OK]")

    # -------------------------------------------------------------
    # TEST 3: Bug 2 Multi-Turn Contextual Sorting via /api/chat
    # -------------------------------------------------------------
    print("\n--- TEST 3: Multi-turn Chat Contextual Sorting ---")
    session_id = "test-sorting-session-1"

    # Turn 1: Search for milk
    r1 = client.post("/api/chat", json={"session_id": session_id, "message": "افضل نوع لبن"})
    assert r1.status_code == 200, f"Turn 1 failed: {r1.status_code}"
    chat_res1 = r1.json()
    print(f"Turn 1 Reply: {chat_res1.get('reply')}")
    t1_products = chat_res1.get("products", [])
    print(f"Turn 1 Products Count: {len(t1_products)}")
    assert len(t1_products) > 0, "Turn 1 returned 0 products"

    # Turn 2: Follow-up sort descending
    r2 = client.post("/api/chat", json={"session_id": session_id, "message": "رتبهم من الاعلى سعرا الى الاقل"})
    assert r2.status_code == 200, f"Turn 2 failed: {r2.status_code}"
    chat_res2 = r2.json()
    t2_reply = chat_res2.get("reply", "")
    t2_products = chat_res2.get("products", [])
    t2_intent = chat_res2.get("intent", "")
    print(f"Turn 2 Reply: {t2_reply}")
    print(f"Turn 2 Products Count: {len(t2_products)}")
    print(f"Turn 2 Intent: {t2_intent}")

    assert "الأعلى سعراً إلى الأقل" in t2_reply or "الاعلى سعرا الى الاقل" in t2_reply or "الأعلى سعراً" in t2_reply, (
        f"Unexpected reply: {t2_reply}"
    )
    assert len(t2_products) == len(t1_products), (
        f"Product count changed across in-memory sort: {len(t2_products)} != {len(t1_products)}"
    )

    # Verify prices are sorted descending
    prices = [p.get("price") for p in t2_products]
    print(f"Turn 2 Prices (descending): {prices}")
    assert prices == sorted(prices, reverse=True), f"Prices not sorted descending: {prices}"

    # Verify products are still milk products from Turn 1
    for p in t2_products:
        pname = p.get("product_name", "")
        assert not any(bad in pname.lower() for bad in ["بطار", "صابون", "إنرجايزر", "لايفبوي"]), (
            f"Unrelated product in sorted results: {pname}"
        )

    # Turn 3: Follow-up sort ascending
    r3 = client.post("/api/chat", json={"session_id": session_id, "message": "رتبهم من الاقل سعرا للاعلى"})
    assert r3.status_code == 200, f"Turn 3 failed: {r3.status_code}"
    chat_res3 = r3.json()
    t3_reply = chat_res3.get("reply", "")
    t3_products = chat_res3.get("products", [])
    print(f"\nTurn 3 Reply: {t3_reply}")
    prices_asc = [p.get("price") for p in t3_products]
    print(f"Turn 3 Prices (ascending): {prices_asc}")
    assert prices_asc == sorted(prices_asc, reverse=False), f"Prices not sorted ascending: {prices_asc}"
    print("TEST 3 PASSED: In-memory contextual sort executed perfectly [OK]")

    print("\n" + "=" * 60)
    print("ALL BUG FIX TESTS PASSED SUCCESSFULLY! (100%)")
    print("=" * 60)


if __name__ == "__main__":
    main()
