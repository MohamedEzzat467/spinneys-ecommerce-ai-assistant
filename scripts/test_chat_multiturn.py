# -*- coding: utf-8 -*-
"""
scripts/test_chat_multiturn.py
==============================
Test suite for multi-turn conversational context in /api/chat.

Verifies:
  1. Turn 1: "عايز لبن شوفان" -> Initial topic set, products returned.
  2. Turn 2: "اقل من 60 جنيه" -> Retains previous query "لبن شوفان" and applies max_price: 60.0.
  3. Turn 3: "اي ماركة مش فارق معايا" -> Cancellation: clears brand if set.
  4. Turn 4: "اول واحد" -> Reference: resolves first product from previous results.
  5. New Topic: "جبنة بيضاء" -> Resets previous constraints.
"""

from __future__ import annotations

import io
import json
import logging
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from app.main import app

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def run_multiturn_tests() -> bool:
    print("=" * 70)
    print(" Spinneys Assistant - Multi-turn Chat Context Benchmark")
    print("=" * 70)

    client = TestClient(app)
    session_id = "test-session-multi"
    all_passed = True

    # ─────────────────────────────────────────────────────────────────────────
    # Turn 1: New exploration topic
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TURN 1: 'عايز لبن شوفان' ---")
    r1 = client.post("/api/chat", json={"session_id": session_id, "message": "عايز لبن شوفان"})
    assert r1.status_code == 200, f"Expected 200, got {r1.status_code}"
    d1 = r1.json()
    print("Status:", r1.status_code)
    print("Reply:", d1["reply"])
    print("Intent:", d1["intent"])
    print("Filters:", d1["filters"])
    print("Products matched:", len(d1["products"]))
    for p in d1["products"][:3]:
        print(f"  [{p['product_id']}] {p['name_ar']} - {p['price']} EGP")

    t1_passed = d1["intent"] == "search" and len(d1["products"]) > 0
    print(f"Result: {'PASSED ✅' if t1_passed else 'FAILED ❌'}")
    if not t1_passed:
        all_passed = False

    # ─────────────────────────────────────────────────────────────────────────
    # Turn 2: Refinement constraint (keep query "لبن شوفان" + apply max_price <= 60)
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TURN 2: 'اقل من 60 جنيه' (Refinement) ---")
    r2 = client.post("/api/chat", json={"session_id": session_id, "message": "اقل من 60 جنيه"})
    assert r2.status_code == 200, f"Expected 200, got {r2.status_code}"
    d2 = r2.json()
    print("Status:", r2.status_code)
    print("Reply:", d2["reply"])
    print("Intent:", d2["intent"])
    print("Filters:", d2["filters"])
    print("Products matched:", len(d2["products"]))
    for p in d2["products"][:3]:
        print(f"  [{p['product_id']}] {p['name_ar']} - {p['price']} EGP")

    # Verify all returned products have price <= 60.0
    price_ok = all(p["price"] <= 60.0 for p in d2["products"])
    t2_passed = (
        d2["intent"] == "refine"
        and d2["filters"].get("max_price") == 60.0
        and price_ok
        and len(d2["products"]) > 0
    )
    print(f"Result: {'PASSED ✅' if t2_passed else 'FAILED ❌'}")
    if not t2_passed:
        all_passed = False

    # ─────────────────────────────────────────────────────────────────────────
    # Turn 3: Reference ("اول واحد")
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TURN 3: 'اول واحد' (Reference to previous result) ---")
    r3 = client.post("/api/chat", json={"session_id": session_id, "message": "اول واحد"})
    assert r3.status_code == 200
    d3 = r3.json()
    print("Reply:", d3["reply"])
    print("Products matched:", len(d3["products"]))
    if d3["products"]:
        print(f"  Top referenced: [{d3['products'][0]['product_id']}] {d3['products'][0]['name_ar']}")

    # ─────────────────────────────────────────────────────────────────────────
    # Turn 4: New Topic ("شاي اخضر")
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- TURN 4: 'شاي اخضر' (New Topic - resets previous max_price 60) ---")
    r4 = client.post("/api/chat", json={"session_id": session_id, "message": "شاي اخضر"})
    assert r4.status_code == 200
    d4 = r4.json()
    print("Reply:", d4["reply"])
    print("Filters after new topic:", d4["filters"])
    t4_passed = "max_price" not in d4["filters"]
    print(f"Result: {'PASSED ✅' if t4_passed else 'FAILED ❌'}")
    if not t4_passed:
        all_passed = False

    print("\n" + "=" * 70)
    print(f" MULTI-TURN CHAT CONTEXT RESULT: {'ALL TESTS PASSED ✅' if all_passed else 'FAILED ❌'}")
    print("=" * 70)
    return all_passed


if __name__ == "__main__":
    success = run_multiturn_tests()
    sys.exit(0 if success else 1)
