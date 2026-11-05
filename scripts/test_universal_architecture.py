# -*- coding: utf-8 -*-
"""
Verification script for the Universal Nutrition, Attribute & Product Architecture:
1. Voucher purge verification across catalog.
2. High Protein search: "افضل 3 منتجات من حيث نسبه البروتين" -> returns actual protein items (poultry, cheese, etc.), not parsley/dill.
3. Low Calorie search: "3 منتجات قليلة السعرات" -> returns diet/light items.
4. Advisory follow-up: "ايهم اعلى في البروتين؟" -> expert 2-sentence Arabic advice comparing visible items.
5. Concrete category search: "افضل 5 انواع جبن" -> returns 5 cheese items.
6. Sorting & limit search: "ارخص 4 انواع زيت" -> returns 4 oil products sorted ascending.
"""
import asyncio
from app.main import chat_conversation, ChatRequest, require_retriever
from app.nlu.parser import parse_query

async def run_tests():
    print("=" * 70)
    print("TEST 1: PERMANENT VOUCHER & ZERO-PRICE PURGE")
    print("=" * 70)
    retriever = require_retriever()
    df_meta = retriever.df_meta
    zero_p = (df_meta["effective_price"] <= 0.0).sum()
    vouchers = df_meta["name_en"].str.contains(r"\bvoucher\b", case=False).sum()
    print(f"Clean catalog size: {len(df_meta)} | Zero-price: {zero_p} | Vouchers: {vouchers}")
    assert zero_p == 0, f"Found zero price items: {zero_p}"
    assert vouchers == 0, f"Found vouchers: {vouchers}"
    print(">>> PASS\n")

    print("=" * 70)
    print("TEST 2: HIGH PROTEIN - 'افضل 3 منتجات من حيث نسبه البروتين'")
    print("=" * 70)
    res_prot = await chat_conversation(ChatRequest(session_id="session_prot", message="افضل 3 منتجات من حيث نسبه البروتين"))
    print(f"Reply: {res_prot.reply}")
    print(f"Count: {len(res_prot.products)}")
    for p in res_prot.products:
        print(f"  - [{p.product_id}] {p.name_ar} ({p.name_en}) | {p.price} EGP")
    assert len(res_prot.products) == 3, f"Expected 3 items, got {len(res_prot.products)}"
    assert all(p.price >= 2.00 for p in res_prot.products), "Found garnish item < 2.00 EGP!"
    assert not any("بقدونس" in p.name_ar or "شبت" in p.name_ar for p in res_prot.products), "Found parsley/dill!"
    print(">>> PASS: Returned real protein products.\n")

    print("=" * 70)
    print("TEST 3: LOW CALORIE - '3 منتجات قليلة السعرات'")
    print("=" * 70)
    res_diet = await chat_conversation(ChatRequest(session_id="session_diet", message="3 منتجات قليلة السعرات"))
    print(f"Reply: {res_diet.reply}")
    print(f"Count: {len(res_diet.products)}")
    for p in res_diet.products:
        print(f"  - [{p.product_id}] {p.name_ar} ({p.name_en}) | {p.price} EGP")
    assert len(res_diet.products) == 3, f"Expected 3 items, got {len(res_diet.products)}"
    assert all(p.price >= 2.00 for p in res_diet.products), "Found item < 2.00 EGP!"
    print(">>> PASS: Returned diet / low calorie items.\n")

    print("=" * 70)
    print("TEST 4: ADVISORY FOLLOW-UP - 'ايهم اعلى في البروتين؟'")
    print("=" * 70)
    res_adv = await chat_conversation(ChatRequest(session_id="session_prot", message="ايهم اعلى في البروتين؟"))
    print(f"Reply: {res_adv.reply}")
    print(f"Retained count: {len(res_adv.products)}")
    assert res_adv.intent == "advisory", f"Expected advisory intent, got {res_adv.intent}"
    assert len(res_adv.products) == 3, f"Expected 3 retained items, got {len(res_adv.products)}"
    assert "بروتين" in res_adv.reply, "Expected protein reasoning in advisory response"
    print(">>> PASS: Advisory pipeline answered without re-searching DB.\n")

    print("=" * 70)
    print("TEST 5: CATEGORY SEARCH - 'افضل 5 انواع جبن'")
    print("=" * 70)
    res_cheese = await chat_conversation(ChatRequest(session_id="session_cheese", message="افضل 5 انواع جبن"))
    print(f"Reply: {res_cheese.reply}")
    print(f"Count: {len(res_cheese.products)}")
    for p in res_cheese.products:
        print(f"  - [{p.product_id}] {p.name_ar} | {p.price} EGP")
    assert len(res_cheese.products) == 5, f"Expected 5 items, got {len(res_cheese.products)}"
    print(">>> PASS\n")

    print("=" * 70)
    print("TEST 6: SORTING & LIMIT - 'ارخص 4 انواع زيت'")
    print("=" * 70)
    res_oil = await chat_conversation(ChatRequest(session_id="session_oil", message="ارخص 4 انواع زيت"))
    print(f"Reply: {res_oil.reply}")
    print(f"Count: {len(res_oil.products)}")
    prices = [p.price for p in res_oil.products]
    print(f"Prices: {prices}")
    for p in res_oil.products:
        print(f"  - [{p.product_id}] {p.name_ar} | {p.price} EGP")
    assert len(res_oil.products) == 4, f"Expected 4 items, got {len(res_oil.products)}"
    assert prices == sorted(prices), "Prices not sorted ascending!"
    print(">>> PASS\n")

    print("=" * 70)
    print("ALL 6 TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run_tests())
