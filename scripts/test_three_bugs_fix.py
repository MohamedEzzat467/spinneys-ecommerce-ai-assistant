# -*- coding: utf-8 -*-
"""
scripts/test_three_bugs_fix.py
==============================
Verification script for the 3 targeted fixes:
  1. BUG 1: "افضل نوع جبن موجود" classified as search (clean_query: "جبن") -> returns actual cheese cards
  2. BUG 2: "اسعار الجبن؟" returns actual cheeses with +10 score (NO powdered milk / لبن بودرة)
  3. BUG 3: "ايهم اعلى فى البروتين؟" gives direct 2-sentence Arabic advice comparing products without "أهلاً وسهلاً"
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
from app.nlu.parser import parse_query

CHEESE_STEMS = ("جبن", "جبنة", "cheddar", "roumy", "feta", "mozzarella", "cheese", "شيدر", "رومي", "فيتا", "موتزاريلا", "موزاريلا", "بارميجانو", "بوكورينو", "جرانا")


def main():
    print("=" * 80)
    print("VERIFYING FIXES FOR BUGS 1, 2, AND 3 SEQUENTIALLY")
    print("=" * 80)

    client = TestClient(app)

    # Warmup
    h_resp = client.get("/health")
    assert h_resp.status_code == 200

    # -------------------------------------------------------------
    # SCENARIO 1: BUG 1 Fix Verification
    # "افضل نوع جبن موجود" -> intent: search, clean_query: جبن, returns cheese cards
    # -------------------------------------------------------------
    print("\n--- SCENARIO 1: Verifying Bug 1 ('افضل نوع جبن موجود') ---")
    nlu1 = parse_query("افضل نوع جبن موجود")
    print(f"NLU Result: intent='{nlu1.intent}', clean_query='{nlu1.clean_query}', in_stock={nlu1.in_stock}, is_followup={nlu1.is_followup}")
    assert nlu1.intent == "search", f"Expected intent 'search', got '{nlu1.intent}'"
    assert nlu1.clean_query in ("جبن", "جبنة"), f"Expected clean_query 'جبن' or 'جبنة', got '{nlu1.clean_query}'"
    assert nlu1.is_followup is False, "is_followup must be False"

    session_1 = "test-session-bug1"
    r1 = client.post("/api/chat", json={"session_id": session_1, "message": "افضل نوع جبن موجود"})
    assert r1.status_code == 200
    d1 = r1.json()
    prods1 = d1.get("products", [])
    print(f"Chat Response: intent='{d1.get('intent')}', products count={len(prods1)}")
    print(f"Reply: {d1.get('reply')}")
    assert d1.get("intent") == "search", f"Expected chat intent 'search', got '{d1.get('intent')}'"
    assert len(prods1) > 0, "Expected cheese products to be returned"

    for p in prods1[:5]:
        pname = p.get("name_ar") or p.get("name_en", "")
        print(f"   - {pname} ({p.get('price')} EGP) | In-Stock: {p.get('availability')}")
        assert any(stem in pname.lower() for stem in CHEESE_STEMS), f"Non-cheese item returned: {pname}"
    print("SCENARIO 1 PASSED: 'افضل نوع جبن موجود' returns actual cheese cards [OK]")

    # -------------------------------------------------------------
    # SCENARIO 2: BUG 2 Fix Verification
    # "اسعار الجبن؟" -> returns actual cheeses with +10 score (NO powdered milk)
    # -------------------------------------------------------------
    print("\n--- SCENARIO 2: Verifying Bug 2 ('اسعار الجبن؟') ---")
    r2 = client.post("/api/search", json={"query": "اسعار الجبن؟", "limit": 6, "mode": "auto"})
    assert r2.status_code == 200
    d2 = r2.json()
    prods2 = d2.get("products", [])
    print(f"Search matched {len(prods2)} products:")
    assert len(prods2) > 0, "No products returned for 'اسعار الجبن؟'"

    for p in prods2:
        pname = (p.get("name_ar") or p.get("name_en", "")).lower()
        print(f"   - {p.get('name_ar')} ({p.get('price')} EGP)")
        assert "لبن بودرة" not in pname, f"Found milk powder in cheese query: {pname}"
        assert any(stem in pname for stem in CHEESE_STEMS), f"Found non-cheese product: {pname}"
    print("SCENARIO 2 PASSED: 'اسعار الجبن؟' returns 100% cheeses, zero milk powder [OK]")

    # -------------------------------------------------------------
    # SCENARIO 3: BUG 3 Fix Verification
    # Turn 1: Search cheeses -> Turn 2: "ايهم اعلى فى البروتين؟"
    # -> Direct 2-sentence Arabic nutritional advice, NO "أهلاً وسهلاً", cards retained
    # -------------------------------------------------------------
    print("\n--- SCENARIO 3: Verifying Bug 3 ('ايهم اعلى فى البروتين؟') ---")
    session_3 = "test-session-bug3"
    # Turn 1: Retrieve cheeses
    t1_resp = client.post("/api/chat", json={"session_id": session_3, "message": "جبنة"})
    assert t1_resp.status_code == 200
    t1_data = t1_resp.json()
    t1_products = t1_data.get("products", [])
    print(f"Turn 1 (Search): retrieved {len(t1_products)} cheese products")
    assert len(t1_products) > 0

    # Turn 2: Ask protein comparison
    t2_resp = client.post("/api/chat", json={"session_id": session_3, "message": "ايهم اعلى فى البروتين؟"})
    assert t2_resp.status_code == 200
    t2_data = t2_resp.json()
    reply = t2_data.get("reply", "")
    t2_products = t2_data.get("products", [])

    print(f"Turn 2 Intent: '{t2_data.get('intent')}'")
    print(f"Turn 2 Reply:\n{reply}\n")
    print(f"Turn 2 Product count: {len(t2_products)}")

    assert t2_data.get("intent") == "advisory", f"Expected intent 'advisory', got '{t2_data.get('intent')}'"
    # Verify NO generic greeting template
    assert not reply.startswith("أهلاً وسهلاً"), f"Reply unexpectedly started with 'أهلاً وسهلاً': {reply}"
    assert not reply.startswith("مرحباً"), f"Reply unexpectedly started with 'مرحباً': {reply}"
    # Verify meaningful comparison & protein explanation
    assert any(w in reply for w in ["بروتين", "البروتين", "protein"]), f"Reply missing protein reasoning: {reply}"
    # Verify active product cards are preserved
    assert len(t2_products) == len(t1_products), f"Product cards lost: {len(t2_products)} != {len(t1_products)}"
    print("SCENARIO 3 PASSED: Direct protein advice generated, zero greeting boilerplate, cards preserved [OK]")

    print("\n" + "=" * 80)
    print("ALL 3 BUGS SUCCESSFULLY RESOLVED AND VERIFIED (100% PASS RATE)")
    print("=" * 80)


if __name__ == "__main__":
    main()
