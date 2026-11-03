# -*- coding: utf-8 -*-
"""
scripts/test_healthy_query.py
=============================
Tests the query understanding, sanitization, intent classification,
and retrieval arbitration for descriptive healthy recommendation queries.
"""

import io
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from app.main import app
from app.nlu.parser import parse_query, sanitize_query
from app.retrieval.retriever import ProductRetriever

def run_tests():
    print("=" * 70)
    print("TESTING HEALTHY MEAL & DIET RETRIEVAL ARBITRATION")
    print("=" * 70)

    # 1. Test query sanitization
    raw_query = "اقترح وجبه غذاء صحيه وقليه السعرات الحراريه؟"
    sanitized = sanitize_query(raw_query)
    print(f"\n[1] Raw Query: '{raw_query}'")
    print(f"    Sanitized: '{sanitized}'")
    assert "اقترح" not in sanitized, "Sanitization must strip 'اقترح'"
    assert "وجبه" not in sanitized and "وجبة" not in sanitized, "Sanitization must strip 'وجبه'"
    assert "؟" not in sanitized and "?" not in sanitized, "Sanitization must strip '؟'"
    print("    --> Sanitization Passed ✅")

    # 2. Test NLU Parsing
    nlu = parse_query(raw_query)
    print(f"\n[2] NLU Parsing Result:")
    print(f"    Intent: {nlu.intent}")
    print(f"    Unsupported Filters: {nlu.unsupported_filters}")
    assert nlu.intent == "recommend", f"Expected intent 'recommend', got '{nlu.intent}'"
    assert "diet" in nlu.unsupported_filters, "Expected 'diet' in unsupported filters"
    print("    --> NLU Intent Passed ✅")

    # 3. Test Retriever directly
    retriever = ProductRetriever()
    res = retriever.retrieve(raw_query)
    print(f"\n[3] Retriever Result:")
    print(f"    Is Healthy Meal: {res.get('is_healthy_meal')}")
    print(f"    Dish: {res.get('dish')}")
    print(f"    Total Matched Products: {len(res.get('products', []))}")
    print(f"    Execution Time: {res.get('execution_time_ms')} ms")

    assert res.get("is_healthy_meal") is True, "Expected is_healthy_meal to be True"
    assert len(res.get("products", [])) > 0, "Expected matched products"

    sweetener_count = 0
    print("    Sample Returned Products:")
    for idx, p in enumerate(res.get("products", [])[:6], 1):
        name = p.get("name_ar") or p.get("name_en")
        brand = p.get("brand")
        price = p.get("price")
        print(f"      {idx}. [{brand}] {name} - {price} EGP")
        if any(w in name for w in ["محلى", "محلي", "ستيفيا", "شوجر ماتش", "سويتنر"]):
            sweetener_count += 1

    assert sweetener_count == 0, f"Error: found {sweetener_count} sweetener items in healthy meal!"
    print("    --> Zero Sweeteners in Healthy Meal Passed ✅")

    # 4. Test Chat API via TestClient
    client = TestClient(app)
    chat_resp = client.post("/api/chat", json={
        "session_id": "test-healthy-session",
        "message": raw_query,
    })
    assert chat_resp.status_code == 200, f"Chat API returned {chat_resp.status_code}"
    chat_data = chat_resp.json()

    print(f"\n[4] Chat API Response:")
    print(f"    Session ID: {chat_data.get('session_id')}")
    print(f"    Intent: {chat_data.get('intent')}")
    print(f"    Reply: {chat_data.get('reply')}")
    print(f"    Dish: {chat_data.get('dish')}")
    print(f"    Products Returned: {len(chat_data.get('products', []))}")
    print(f"    Cart Groups: {len(chat_data.get('cart', []))}")

    assert "اقترح" not in chat_data.get("reply", "") or chat_data.get("reply", "").startswith("اقترحت لك"), "Reply must be a natural friendly statement"
    assert len(chat_data.get("products", [])) > 0, "Must return catalog products"
    print("    --> Chat API Endpoint Passed ✅")

    # 5. Verify that explicit sweetener query still returns sweeteners
    sweetener_query = "محلي ستيفيا"
    res_sweet = retriever.retrieve(sweetener_query)
    print(f"\n[5] Explicit Sweetener Query: '{sweetener_query}'")
    print(f"    Total Matched: {len(res_sweet.get('products', []))}")
    has_sweeteners = any(
        any(w in (p.get("name_ar") or "") for w in ["محلى", "محلي", "ستيفيا", "شوجر ماتش", "سويتنر"])
        for p in res_sweet.get("products", [])
    )
    assert has_sweeteners, "Explicit sweetener search must return sweetener products!"
    print("    --> Explicit Sweetener Query Preserved ✅")

    print("\n" + "=" * 70)
    print("ALL HEALTHY MEAL & RETRIEVAL ARBITRATION TESTS PASSED! 🚀")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
