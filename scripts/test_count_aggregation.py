import asyncio
import os
import sys

os.environ["PYTHONPATH"] = "."
os.environ["PYTHONIOENCODING"] = "utf-8"

from app.main import ChatRequest, chat_conversation, lifespan, app
from app.nlu.parser import parse_query
from app.retrieval.retriever import ProductRetriever


async def run_tests():
    print("=== Testing Count Aggregation & Foul Filtering ===")

    # 1. Test NLU parsing
    q1 = "كم نوع فول موجود"
    nlu1 = parse_query(q1)
    print(f"Query: '{q1}'")
    print(f"  action: {nlu1.action}")
    print(f"  intent: {nlu1.intent}")
    print(f"  clean_query: {nlu1.clean_query}")
    print(f"  is_count_query: {nlu1.is_count_query}")

    assert nlu1.is_count_query is True, f"Expected is_count_query=True, got {nlu1.is_count_query}"
    assert nlu1.clean_query == "فول", f"Expected clean_query='فول', got {nlu1.clean_query}"
    assert nlu1.action == "count_inquiry" or nlu1.intent == "count_inquiry", "Expected count_inquiry action/intent"
    print("PASS: NLU Parser test passed.")

    # 2. Test retriever get_entity_aggregation
    retriever = ProductRetriever()
    agg = retriever.get_entity_aggregation("فول")
    print("\nAggregation Results:")
    print(f"  Entity: {agg['entity']}")
    print(f"  Total count: {agg['total_count']}")
    print(f"  Varieties: {agg['varieties']}")
    print(f"  Products count: {len(agg['products'])}")
    for p in agg['products']:
        print(f"    - {p['name_ar']} ({p['price']} EGP)")
        p_text = (p['name_ar'] + " " + p['name_en']).lower()
        assert "سودان" not in p_text and "peanut" not in p_text, f"Peanut found in products: {p['name_ar']}"
        assert "دقيق" not in p_text and "flour" not in p_text, f"Flour found in products: {p['name_ar']}"
        assert "اوتوماتيك" not in p_text and "full hd" not in p_text, f"Non-food item found: {p['name_ar']}"
        assert p['price'] > 0, f"Zero price found: {p['price']}"

    assert agg['total_count'] > 0, "Expected total_count > 0"
    assert "فول مدمس معلب" in agg['varieties'], "Expected canned beans in varieties"
    assert "فول مجروش" in agg['varieties'], "Expected split beans in varieties"
    assert "فول تدميس حب" in agg['varieties'], "Expected whole beans in varieties"
    print("PASS: Retriever get_entity_aggregation test passed.")

    # 3. Test Full Chat Flow
    print("\nTesting Chat Flow for 'كم نوع فول موجود':")
    # Initialize app lifespan dependencies
    async with lifespan(app):
        chat_req = ChatRequest(session_id="test_session_count_1", message="كم نوع فول موجود")
        resp = await chat_conversation(chat_req)
        print(f"Reply:\n{resp.reply}")
        print(f"Products returned: {len(resp.products)}")
        for p in resp.products:
            print(f"  * {p.name_ar} | {p.price} EGP")
            assert "سودان" not in p.name_ar, f"Peanut found: {p.name_ar}"
            assert "دقيق" not in p.name_ar, f"Flour found: {p.name_ar}"

        assert "يوجد في المتجر حوالي" in resp.reply
        assert "فول مدمس معلب" in resp.reply
        assert "فول تدميس حب" in resp.reply
        assert "فول مجروش" in resp.reply
        assert resp.intent == "count_inquiry"
        print("PASS: Chat flow test passed.")

        # 4. Test regular search "افضل 5 انواع فول"
        print("\nTesting Regular Search for 'افضل 5 انواع فول':")
        search_req = ChatRequest(session_id="test_session_count_2", message="افضل 5 انواع فول")
        resp2 = await chat_conversation(search_req)
        print(f"Reply:\n{resp2.reply}")
        print(f"Products returned: {len(resp2.products)}")
        assert len(resp2.products) == 5, f"Expected 5 products, got {len(resp2.products)}"
        for p in resp2.products:
            print(f"  * {p.name_ar} | {p.price} EGP")
            assert "سودان" not in p.name_ar, f"Peanut found: {p.name_ar}"
            assert "دقيق" not in p.name_ar, f"Flour found: {p.name_ar}"
        print("PASS: Regular search test passed.")

    print("\nALL TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(run_tests())
