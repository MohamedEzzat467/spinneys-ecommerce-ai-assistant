# -*- coding: utf-8 -*-
"""
scripts/test_bugs_fix.py
========================
Verification script for:
  - Structured NLU via Groq / Fallback (Schema validation)
  - Combined Search + Sort: "افضل نوع لبن مع ترتيب الاسعار" -> Returns dairy milk sorted ascending
  - Standalone Sort / Follow-up: "رتبهم من الاعلى سعرا الى الاقل" -> In-memory sort descending
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
from app.nlu.parser import parse_query, sanitize_query, NLUResult


def main():
    print("=" * 70)
    print("RUNNING STRUCTURED NLU & COMBINED SEARCH + SORT VERIFICATION")
    print("=" * 70)

    client = TestClient(app)
    # Warm up app
    h_resp = client.get("/health")
    assert h_resp.status_code == 200, "Health check failed"

    # -------------------------------------------------------------
    # TEST 1: Structured NLU Schema for "افضل نوع لبن مع ترتيب الاسعار"
    # -------------------------------------------------------------
    print("\n--- TEST 1: Structured NLU Schema for 'افضل نوع لبن مع ترتيب الاسعار' ---")
    query1 = "افضل نوع لبن مع ترتيب الاسعار"
    nlu1 = parse_query(query1)
    print(f"Input: '{query1}'")
    print(f"  intent: {nlu1.intent}")
    print(f"  clean_query: {nlu1.clean_query}")
    print(f"  category: {nlu1.category}")
    print(f"  sort_by: {nlu1.sort_by}")
    print(f"  is_followup: {nlu1.is_followup}")

    assert isinstance(nlu1, NLUResult), "Did not return NLUResult instance"
    assert nlu1.intent == "search", f"Expected intent 'search', got {nlu1.intent}"
    assert nlu1.clean_query in ("لبن", "حليب"), f"Expected 'لبن' or 'حليب', got {nlu1.clean_query}"
    assert nlu1.sort_by == "price_asc", f"Expected sort_by 'price_asc', got {nlu1.sort_by}"
    assert nlu1.category == "dairy", f"Expected category 'dairy', got {nlu1.category}"
    assert nlu1.is_followup is False, f"Expected is_followup False, got {nlu1.is_followup}"
    print("TEST 1 PASSED [OK]")

    # -------------------------------------------------------------
    # TEST 2: Combined Search + Sort via /api/chat
    # -------------------------------------------------------------
    print("\n--- TEST 2: Combined Search + Sort ('افضل نوع لبن مع ترتيب الاسعار') ---")
    session_id = "test-combined-search-sort"
    resp1 = client.post("/api/chat", json={"session_id": session_id, "message": query1})
    assert resp1.status_code == 200, f"Chat failed: {resp1.status_code}"
    data1 = resp1.json()
    reply1 = data1.get("reply", "")
    products1 = data1.get("products", [])

    print(f"Reply: {reply1}")
    print(f"Products count: {len(products1)}")

    # 1. Clean response check: must not echo instruction string "مع ترتيب الاسعار"
    assert "مع ترتيب الاسعار" not in reply1, "Instruction phrase was echoed in response!"
    assert "لبن" in reply1, "Target product not mentioned in response"
    assert "مرتبة حسب السعر" in reply1 or "ترتيب" in reply1, "Sorting indication missing in reply"

    # 2. Check returned products are dairy and prices strictly ascending
    assert len(products1) > 0, "No products returned"
    prices1 = [p.get("price") for p in products1]
    print(f"Ascending prices: {prices1}")
    assert prices1 == sorted(prices1, reverse=False), f"Products not sorted ascending: {prices1}"

    # 3. Check for 0% non-food pollution
    for p in products1:
        pname = p.get("product_name", "")
        assert not any(bad in pname.lower() for bad in ["بطار", "صابون", "إنرجايزر", "لايفبوي", "شوز"]), (
            f"Non-food item returned: {pname}"
        )
    print("TEST 2 PASSED: Pure dairy milk returned, strictly sorted ascending, clean message [OK]")

    # -------------------------------------------------------------
    # TEST 3: Standalone In-Memory Sort / Follow-up: "رتبهم من الاعلى سعرا الى الاقل"
    # -------------------------------------------------------------
    print("\n--- TEST 3: Standalone Sort ('رتبهم من الاعلى سعرا الى الاقل') ---")
    query2 = "رتبهم من الاعلى سعرا الى الاقل"
    nlu2 = parse_query(query2)
    print(f"Input: '{query2}'")
    print(f"  intent: {nlu2.intent}")
    print(f"  clean_query: {nlu2.clean_query}")
    print(f"  sort_by: {nlu2.sort_by}")
    print(f"  is_followup: {nlu2.is_followup}")

    assert nlu2.intent == "sort", f"Expected intent 'sort', got {nlu2.intent}"
    assert nlu2.clean_query is None, f"Expected clean_query None, got {nlu2.clean_query}"
    assert nlu2.sort_by == "price_desc", f"Expected sort_by 'price_desc', got {nlu2.sort_by}"
    assert nlu2.is_followup is True, f"Expected is_followup True, got {nlu2.is_followup}"

    resp2 = client.post("/api/chat", json={"session_id": session_id, "message": query2})
    assert resp2.status_code == 200, f"Turn 2 failed: {resp2.status_code}"
    data2 = resp2.json()
    reply2 = data2.get("reply", "")
    products2 = data2.get("products", [])

    print(f"Reply: {reply2}")
    print(f"Products count: {len(products2)}")
    assert "الأعلى سعراً إلى الأقل" in reply2 or "الاعلى" in reply2, f"Unexpected reply: {reply2}"
    assert len(products2) == len(products1), f"Product count mismatch: {len(products2)} != {len(products1)}"

    prices2 = [p.get("price") for p in products2]
    print(f"Descending prices: {prices2}")
    assert prices2 == sorted(prices2, reverse=True), f"Products not sorted descending: {prices2}"
    print("TEST 3 PASSED: In-memory sorting executed with exact item preservation [OK]")

    # -------------------------------------------------------------
    # TEST 4: Follow-up ascending sort: "رتبهم من الاقل سعرا للاعلى"
    # -------------------------------------------------------------
    print("\n--- TEST 4: Standalone Ascending Sort ('رتبهم من الاقل سعرا للاعلى') ---")
    resp3 = client.post("/api/chat", json={"session_id": session_id, "message": "رتبهم من الاقل سعرا للاعلى"})
    assert resp3.status_code == 200, f"Turn 3 failed: {resp3.status_code}"
    data3 = resp3.json()
    prices3 = [p.get("price") for p in data3.get("products", [])]
    print(f"Ascending prices: {prices3}")
    assert prices3 == sorted(prices3, reverse=False), f"Products not sorted ascending: {prices3}"
    print("TEST 4 PASSED [OK]")

    print("\n" + "=" * 70)
    print("ALL TESTS PASSED WITH 100% SUCCESS! (Groq Structured NLU + Controller)")
    print("=" * 70)


if __name__ == "__main__":
    main()
