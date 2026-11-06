import asyncio
import os
import sys

os.environ["PYTHONPATH"] = "."
os.environ["PYTHONIOENCODING"] = "utf-8"

from app.main import ChatRequest, chat_conversation, lifespan, app
from app.nlu.parser import parse_query, sanitize_query, strip_brand_from_query
from app.retrieval.retriever import ProductRetriever


async def run_tests():
    print("=== Testing Search & Production Retrieval Fixes ===")

    # 1. Test Brand Extraction & Query Normalization
    print("\n--- 1. Testing Brand Extraction & Query Normalization ---")
    q_brand = "عايز حليب جهينة"
    nlu_brand = parse_query(q_brand)
    print(f"Query: '{q_brand}'")
    print(f"  clean_query: '{nlu_brand.clean_query}'")
    print(f"  brand: '{nlu_brand.brand}'")
    
    assert nlu_brand.brand == "Juhayna", f"Expected brand Juhayna, got {nlu_brand.brand}"
    assert "جهين" not in (nlu_brand.clean_query or ""), f"Brand name not stripped from clean_query: {nlu_brand.clean_query}"
    assert "حليب" in (nlu_brand.clean_query or ""), f"Expected 'حليب' in clean_query, got {nlu_brand.clean_query}"
    print("PASS: Brand extracted and stripped from clean_query.")

    # Test retriever with brand filter (Arabic and canonical)
    retriever = ProductRetriever()
    res_b1 = retriever.retrieve("حليب", filter_overrides={"brand": "Juhayna"}, limit=5)
    print(f"Retrieved with brand='Juhayna': {len(res_b1['products'])} products")
    assert len(res_b1["products"]) > 0, "Expected > 0 products for Juhayna milk"
    for p in res_b1["products"]:
        print(f"  - {p['name_ar']} | Brand: {p['brand']} | {p['price']} EGP")
        assert p["brand"].lower() == "juhayna", f"Non-Juhayna product found: {p['brand']}"

    res_b2 = retriever.retrieve("حليب", filter_overrides={"brand": "جهينة"}, limit=5)
    print(f"Retrieved with brand='جهينة': {len(res_b2['products'])} products")
    assert len(res_b2["products"]) > 0, "Expected > 0 products for Arabic brand 'جهينة'"
    print("PASS: Bilingual brand filtering verified.")

    # 2. Test Category Ambiguity (فين الزيت؟)
    print("\n--- 2. Testing Category Ambiguity (فين الزيت؟) ---")
    q_oil = "فين الزيت؟"
    res_oil = retriever.retrieve(q_oil, limit=5)
    print(f"Results for '{q_oil}': {len(res_oil['products'])} products")
    for p in res_oil["products"]:
        print(f"  - {p['name_ar']} | {p['price']} EGP")
        name = p["name_ar"].lower()
        assert "شعر" not in name, f"Cosmetic hair oil found: {p['name_ar']}"
        assert "مساج" not in name, f"Massage oil found: {p['name_ar']}"
        assert "كوبرا" not in name, f"Cosmetic oil found: {p['name_ar']}"
        assert "بديل الزيت" not in name, f"Hair conditioner found: {p['name_ar']}"
    print("PASS: Cooking oils prioritized over cosmetics.")

    # 3. Test Multi-term Token Leaks (قصدى زيت طعام)
    print("\n--- 3. Testing Multi-term Token Leaks (قصدى زيت طعام) ---")
    q_oil_food = "قصدى زيت طعام"
    res_food_oil = retriever.retrieve(q_oil_food, limit=5)
    print(f"Results for '{q_oil_food}': {len(res_food_oil['products'])} products")
    for p in res_food_oil["products"]:
        print(f"  - {p['name_ar']} | {p['price']} EGP")
        name = p["name_ar"].lower()
        assert "ملح" not in name, f"Salt leaked into oil results: {p['name_ar']}"
        assert "علب" not in name and "بوكس" not in name and "حافظة" not in name, f"Plastic box leaked: {p['name_ar']}"
        assert "زيت" in name or "oil" in p["name_en"].lower(), f"Item missing anchor noun زيت: {p['name_ar']}"
    print("PASS: Anchor noun enforced, token leaks prevented.")

    # 4. Test Chat End-to-End
    print("\n--- 4. Testing Chat Conversation End-to-End ---")
    async with lifespan(app):
        # 4a. Juhayna milk chat
        chat_req1 = ChatRequest(session_id="test_sess_brand_1", message="عايز حليب جهينة")
        chat_resp1 = await chat_conversation(chat_req1)
        print(f"Chat Reply 1: {chat_resp1.reply}")
        print(f"Products returned: {len(chat_resp1.products)}")
        assert len(chat_resp1.products) > 0, "Expected > 0 products for عايز حليب جهينة"
        for p in chat_resp1.products[:3]:
            print(f"  * {p.name_ar} | {p.brand} | {p.price} EGP")
            assert p.brand.lower() == "juhayna"

        # 4b. Oil location chat
        chat_req2 = ChatRequest(session_id="test_sess_oil_1", message="فين الزيت؟")
        chat_resp2 = await chat_conversation(chat_req2)
        print(f"\nChat Reply 2: {chat_resp2.reply}")
        print(f"Products returned: {len(chat_resp2.products)}")
        assert len(chat_resp2.products) > 0, "Expected > 0 products for فين الزيت؟"
        for p in chat_resp2.products[:3]:
            print(f"  * {p.name_ar} | {p.price} EGP")
            assert "شعر" not in p.name_ar

        # 4c. Food oil clarification chat
        chat_req3 = ChatRequest(session_id="test_sess_oil_food_1", message="قصدى زيت طعام")
        chat_resp3 = await chat_conversation(chat_req3)
        print(f"\nChat Reply 3: {chat_resp3.reply}")
        print(f"Products returned: {len(chat_resp3.products)}")
        assert len(chat_resp3.products) > 0, "Expected > 0 products for قصدى زيت طعام"
        for p in chat_resp3.products[:3]:
            print(f"  * {p.name_ar} | {p.price} EGP")
            assert "ملح" not in p.name_ar
            assert "علب" not in p.name_ar

    print("\nALL PRODUCTION SEARCH FIXES VERIFIED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(run_tests())
