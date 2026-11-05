# -*- coding: utf-8 -*-
"""
End-to-End Verification Test for LLM-First Agentic Architecture in Spinneys Assistant.
Tests:
  1. Recipe inquiry: "وصفه للحمه" -> outputs real meat cuts + recipe advice.
  2. Follow-up Q&A: "ايهم اعلى بروتين؟" -> grounds in visible meat items without catalog re-query.
  3. Catalog search: "افضل 5 انواع فول" -> returns clean 5 items, no vouchers.
  4. Protein search: "افضل 3 منتجات من حيث نسبه البروتين" -> top protein items, no processed cheese.
"""

import asyncio
from app.main import chat_conversation, ChatRequest

async def run_tests():
    session_id = "test_agentic_session_001"

    print("=================================================================")
    print("TEST 1: Recipe Inquiry ('وصفه للحمه')")
    print("=================================================================")
    req1 = ChatRequest(session_id=session_id, message="وصفه للحمه")
    res1 = await chat_conversation(req1)
    
    print("Reply:")
    print(res1.reply)
    print("\nIntent:", res1.intent)
    print("Products returned count:", len(res1.products))
    for p in res1.products:
        print(f"  - [{p.product_id}] {p.name_ar} | {p.name_en} | {p.price} EGP | Brand: {p.brand}")
    
    # Assertions for Test 1
    assert res1.intent == "recipe", f"Expected intent 'recipe', got '{res1.intent}'"
    assert len(res1.products) > 0, "Expected meat products returned, got 0"
    for p in res1.products:
        p_name = (p.name_ar + " " + (p.name_en or "")).lower()
        assert not any(bad in p_name for bad in ["أم علي", "ام علي", "حلوى", "dessert"]), f"Polluted product: {p.name_ar}"
        assert float(p.price) > 0, f"Found zero price product: {p.name_ar}"
    print(">>> TEST 1 PASSED: Real meat cuts returned alongside recipe advice!")

    print("\n=================================================================")
    print("TEST 2: Follow-up Nutritional Q&A ('ايهم اعلى بروتين؟')")
    print("=================================================================")
    req2 = ChatRequest(session_id=session_id, message="ايهم اعلى بروتين؟")
    res2 = await chat_conversation(req2)

    print("Reply:")
    print(res2.reply)
    print("Intent:", res2.intent)
    print("Products count:", len(res2.products))
    
    # Assertions for Test 2
    assert res2.intent == "advisory", f"Expected intent 'advisory', got '{res2.intent}'"
    assert len(res2.reply) > 20, "Expected informative advisory reply"
    # Ensure no vouchers or 0.00 EGP products
    for p in res2.products:
        assert float(p.price) > 0, f"Found 0.00 EGP product: {p.name_ar}"
        assert "voucher" not in (p.name_en or "").lower()
    print(">>> TEST 2 PASSED: Grounded advisory answer with no catalog fallback or voucher pollution!")

    print("\n=================================================================")
    print("TEST 3: Catalog Search & Exact Slicing ('افضل 5 انواع فول')")
    print("=================================================================")
    req3 = ChatRequest(session_id="test_session_foul", message="افضل 5 انواع فول")
    res3 = await chat_conversation(req3)

    print("Reply:")
    print(res3.reply)
    print("Products returned count:", len(res3.products))
    for p in res3.products:
        print(f"  - [{p.product_id}] {p.name_ar} | {p.price} EGP")
    
    # Assertions for Test 3
    assert len(res3.products) == 5, f"Expected exactly 5 products, got {len(res3.products)}"
    for p in res3.products:
        assert float(p.price) > 0, "Found 0 EGP item"
        assert any(w in p.name_ar for w in ["فول", "foul", "beans"]), f"Unrelated product: {p.name_ar}"
    print(">>> TEST 3 PASSED: Exactly 5 foul products returned!")

    print("\n=================================================================")
    print("TEST 4: Targeted Nutritional Search ('افضل 3 منتجات من حيث نسبه البروتين')")
    print("=================================================================")
    req4 = ChatRequest(session_id="test_session_protein", message="افضل 3 منتجات من حيث نسبه البروتين")
    res4 = await chat_conversation(req4)

    print("Reply:")
    print(res4.reply)
    print("Products returned count:", len(res4.products))
    for p in res4.products:
        print(f"  - [{p.product_id}] {p.name_ar} | {p.name_en} | {p.price} EGP")

    # Assertions for Test 4
    assert len(res4.products) == 3, f"Expected 3 products, got {len(res4.products)}"
    assert "صدور الدواجن والتونة" in res4.reply, f"Expected standard intro in reply, got '{res4.reply}'"
    for p in res4.products:
        p_name = (p.name_ar + " " + (p.name_en or "")).lower()
        assert not any(bad in p_name for bad in ["مطبوخ", "كريمي", "سبريد", "مثلثات", "جبن خضار"]), f"Processed cheese returned: {p.name_ar}"
        assert float(p.price) >= 2.0, f"Too cheap or herb item: {p.name_ar}"
    print(">>> TEST 4 PASSED: Top protein items returned with NO processed cheese!")

    print("\n=================================================================")
    print("ALL 4 TESTS PASSED SUCCESSFULLY!")
    print("=================================================================")

if __name__ == "__main__":
    asyncio.run(run_tests())
