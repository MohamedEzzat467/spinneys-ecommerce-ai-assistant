# -*- coding: utf-8 -*-
"""
scripts/test_advisory_pipeline.py
=================================
Verification script for:
  - Universal product searches across categories (olive oil, tea, cheese, etc.)
  - Contextual advisory, comparison, and nutritional inquiries (e.g. "ايهم افضل من حيث القيمه الغذائيه؟")
  - Zero voucher / zero irrelevant product pollution
  - Exact preservation of active session products in UI/response
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
from app.nlu.parser import parse_query, NLUResult


def main():
    print("=" * 75)
    print("RUNNING UNIVERSAL ADVISORY & COMPARISON PIPELINE VERIFICATION")
    print("=" * 75)

    client = TestClient(app)
    # Warm up app
    h_resp = client.get("/health")
    assert h_resp.status_code == 200, "Health check failed"

    # -------------------------------------------------------------
    # TEST 1: NLU Intent Classification on Advisory Queries
    # -------------------------------------------------------------
    print("\n--- TEST 1: NLU Intent Classification for Advisory Questions ---")
    advisory_queries = [
        ("ايهم افضل من حيث القيمه الغذائيه؟", "nutrition"),
        ("الفرق بين الانواع دي ايه؟", "comparison"),
        ("انهي صحي اكتر وللدايت؟", "nutrition"),
        ("which one is better for health?", "quality"),
    ]

    for q, expected_topic_hint in advisory_queries:
        res = parse_query(q)
        print(f"Query: '{q}' -> intent: '{res.intent}', clean_query: '{res.clean_query}', is_followup: {res.is_followup}, topic: '{res.advisory_topic}'")
        assert res.intent == "advisory", f"Expected intent 'advisory' for '{q}', got '{res.intent}'"
        assert res.clean_query is None, f"clean_query must be None for advisory, got '{res.clean_query}'"
        assert res.is_followup is True, f"is_followup must be True for advisory query '{q}'"
    print("TEST 1 PASSED [OK]")

    # -------------------------------------------------------------
    # TEST 2: Multi-turn Product Search + Advisory on Olive Oil
    # -------------------------------------------------------------
    print("\n--- TEST 2: Olive Oil Search -> Nutritional Comparison ---")
    session_id_oil = "test-advisory-oil-session"

    # Turn 1: Search for olive oil
    r1 = client.post("/api/chat", json={"session_id": session_id_oil, "message": "افضل زيت زيتون"})
    assert r1.status_code == 200, f"Turn 1 failed: {r1.status_code}"
    d1 = r1.json()
    products1 = d1.get("products", [])
    print(f"Turn 1 (Search): Found {len(products1)} olive oil products:")
    for p in products1[:4]:
        pname = p.get("name_ar") or p.get("name_en") or p.get("product_name", "")
        print(f"   - {pname} ({p['price']} EGP)")
    assert len(products1) > 0, "No olive oil products returned"
    for p in products1:
        pname = (p.get("name_ar") or p.get("name_en") or p.get("product_name", "")).lower()
        assert any(k in pname for k in ["زيت", "زيتون", "oil", "olive"]), f"Unexpected item: {pname}"

    # Turn 2: Ask nutritional advisory question
    advisory_msg = "ايهم افضل من حيث القيمه الغذائيه وللصحة؟"
    r2 = client.post("/api/chat", json={"session_id": session_id_oil, "message": advisory_msg})
    assert r2.status_code == 200, f"Turn 2 failed: {r2.status_code}"
    d2 = r2.json()
    reply2 = d2.get("reply", "")
    products2 = d2.get("products", [])

    print(f"\nTurn 2 (Advisory Question): '{advisory_msg}'")
    print(f"Turn 2 Intent: {d2.get('intent')}")
    print(f"Turn 2 Generated Advice:\n{reply2}\n")
    print(f"Turn 2 Product count: {len(products2)}")

    assert d2.get("intent") == "advisory", f"Expected intent 'advisory', got {d2.get('intent')}"
    # CRITICAL: Verify NO vouchers or 0.00 EGP items returned
    for p in products2:
        pname = (p.get("name_ar") or p.get("name_en") or p.get("product_name", "")).lower()
        price = p.get("price", 0.0)
        assert "voucher" not in pname and "قسيمة" not in pname, f"Voucher pollution found: {pname}"
        assert price > 0.0, f"Zero price item returned: {pname}"

    # Verify active products are preserved
    assert len(products2) == len(products1), f"Product cards lost: {len(products2)} != {len(products1)}"
    # Verify generated advice contains substantive reasoning
    assert len(reply2.strip()) > 30, "Generated advice too short"
    print("TEST 2 PASSED: Meaningful advisory generated, zero voucher pollution, product cards retained [OK]")

    # -------------------------------------------------------------
    # TEST 3: Multi-turn Feta Cheese Search -> Difference Question
    # -------------------------------------------------------------
    print("\n--- TEST 3: Cheese Search -> Difference Inquiry ---")
    session_id_cheese = "test-advisory-cheese-session"

    # Turn 1: Search for feta cheese
    r_ch1 = client.post("/api/chat", json={"session_id": session_id_cheese, "message": "جبنة فيتا"})
    assert r_ch1.status_code == 200
    d_ch1 = r_ch1.json()
    ch_products1 = d_ch1.get("products", [])
    print(f"Turn 1: Found {len(ch_products1)} cheese products")
    assert len(ch_products1) > 0

    # Turn 2: Ask difference question
    diff_msg = "الفرق بين الانواع دي ايه وانهي اقل دسم؟"
    r_ch2 = client.post("/api/chat", json={"session_id": session_id_cheese, "message": diff_msg})
    assert r_ch2.status_code == 200
    d_ch2 = r_ch2.json()
    reply_ch2 = d_ch2.get("reply", "")
    ch_products2 = d_ch2.get("products", [])

    print(f"Turn 2 Advice:\n{reply_ch2}\n")
    assert d_ch2.get("intent") == "advisory"
    assert len(ch_products2) == len(ch_products1)
    for p in ch_products2:
        pname = (p.get("name_ar") or p.get("name_en") or p.get("product_name", "")).lower()
        assert "voucher" not in pname and "قسيمة" not in pname
    print("TEST 3 PASSED [OK]")

    # -------------------------------------------------------------
    # TEST 4: Regression Check: Combined Search + Sort & Standalone Sort
    # -------------------------------------------------------------
    print("\n--- TEST 4: Regression Check (Search+Sort & Standalone Sort) ---")
    s_sort = "test-sort-regression"
    r_s1 = client.post("/api/chat", json={"session_id": s_sort, "message": "افضل نوع لبن مع ترتيب الاسعار"})
    assert r_s1.status_code == 200
    d_s1 = r_s1.json()
    prices1 = [p["price"] for p in d_s1.get("products", [])]
    assert prices1 == sorted(prices1, reverse=False), f"Not sorted ascending: {prices1}"
    assert "مع ترتيب الاسعار" not in d_s1.get("reply", "")

    r_s2 = client.post("/api/chat", json={"session_id": s_sort, "message": "رتبهم من الاعلى سعرا الى الاقل"})
    assert r_s2.status_code == 200
    d_s2 = r_s2.json()
    prices2 = [p["price"] for p in d_s2.get("products", [])]
    assert prices2 == sorted(prices2, reverse=True), f"Not sorted descending: {prices2}"
    print("TEST 4 PASSED [OK]")

    print("\n" + "=" * 75)
    print("ALL UNIVERSAL ADVISORY & COMPARISON TESTS PASSED (100% SUCCESS)")
    print("=" * 75)


if __name__ == "__main__":
    main()
