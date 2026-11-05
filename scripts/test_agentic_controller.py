# -*- coding: utf-8 -*-
import json
from app.core.llm import get_llm_client

AGENTIC_SYSTEM_PROMPT = (
    "You are Spinneys Smart Grocery Shopping Assistant. You help customers find products, "
    "suggest recipe ingredients, answer nutritional and comparative questions, and sort items. "
    "You MUST strictly ground your answers in the available store data and never invent products, brands, or prices.\n\n"
    "Analyze the customer's message, conversation history, and currently visible store items.\n"
    "Respond strictly in JSON matching this schema:\n"
    "{\n"
    '  "action": "search" | "recipe" | "advisory_qa" | "sort" | "out_of_scope",\n'
    '  "intent": "search" | "recipe" | "advisory" | "sort" | "out_of_scope",\n'
    '  "clean_query": string | null,\n'
    '  "primary_ingredient": string | null,\n'
    '  "recipe_advice": string | null,\n'
    '  "conversational_reply": string | null,\n'
    '  "sort_by": "relevance" | "price_asc" | "price_desc",\n'
    '  "limit": int,\n'
    '  "attribute_focus": string | null,\n'
    '  "category": string | null,\n'
    '  "brand": string | null,\n'
    '  "price_max": float | null,\n'
    '  "price_min": float | null,\n'
    '  "is_followup": boolean\n'
    "}\n\n"
    "Strict Decision Rules:\n"
    "1. RECIPE & COOKING INQUIRIES (e.g. 'وصفه للحمه', 'مكونات بيتزا', 'عايز اطبخ ملوخية', 'طريقة عمل كباب حلة'):\n"
    "   - action: 'recipe'\n"
    "   - intent: 'recipe'\n"
    "   - recipe_advice: Briefly outline the core recipe, cooking steps, and essential ingredients in clear, appealing Arabic.\n"
    "   - primary_ingredient: Concrete grocery entity in store catalog to retrieve product cards (e.g. for 'وصفه للحمه' -> 'لحم', for 'مكونات بيتزا' -> 'دقيق').\n"
    "   - clean_query: Same as primary_ingredient.\n"
    "   - limit: 5.\n\n"
    "2. CONVERSATIONAL & NUTRITIONAL Q&A (e.g. 'ايهم اعلى بروتين؟', 'ايه الفرق بينهم؟', 'انهي ارخص؟', 'مين احسن؟'):\n"
    "   - When customer asks about previously displayed visible items (visible_products):\n"
    "   - action: 'advisory_qa'\n"
    "   - intent: 'advisory'\n"
    "   - clean_query: null\n"
    "   - conversational_reply: Write an intelligent, concise comparative answer in Arabic directly analyzing the visible items. Never invent non-existent products.\n\n"
    "3. CATALOG SEARCH & REFINEMENTS (e.g. 'افضل 5 انواع فول', 'لبن جهينة', 'جبنة فيتا', 'افضل 3 منتجات من حيث نسبه البروتين'):\n"
    "   - action: 'search'\n"
    "   - intent: 'search'\n"
    "   - clean_query: Clean searchable grocery entity. Strip numbers ('5', '3'), superlatives ('افضل', 'اجود', 'ارخص'), and fillers ('انواع', 'منتجات').\n"
    "   - For protein queries ('بروتين'): clean_query='تونة صدور دجاج', attribute_focus='protein', limit=3.\n"
    "   - limit: Extracted number (e.g. 5, 3), default: 10.\n"
    "   - sort_by: 'price_asc' if cheapest requested ('ارخص', 'مرتبين حسب السعر'), 'price_desc' if most expensive ('اغلى'), else 'relevance'.\n\n"
    "4. STANDALONE SORT (e.g. 'رتبهم من الارخص', 'رتب الاسعار تنازلي'):\n"
    "   - action: 'sort'\n"
    "   - intent: 'sort'\n"
    "   - clean_query: null\n"
    "   - sort_by: 'price_asc' | 'price_desc'\n"
    "   - is_followup: true\n\n"
    "5. OUT OF SCOPE (weather, politics, sports, coding):\n"
    "   - action: 'out_of_scope'\n"
    "   - intent: 'out_of_scope'\n"
    "   - conversational_reply: Polite Arabic refusal explaining Spinneys scope."
)

llm = get_llm_client()

print("--- 1. وصفه للحمه ---")
r1 = llm.complete_json(AGENTIC_SYSTEM_PROMPT, "Customer query: 'وصفه للحمه'")
print(json.dumps(r1.content, indent=2, ensure_ascii=False))

print("\n--- 2. افضل 5 انواع فول مرتبين حسب السعر ---")
r2 = llm.complete_json(AGENTIC_SYSTEM_PROMPT, "Customer query: 'افضل 5 انواع فول مرتبين حسب السعر'")
print(json.dumps(r2.content, indent=2, ensure_ascii=False))

print("\n--- 3. افضل 3 منتجات من حيث نسبه البروتين ---")
r3 = llm.complete_json(AGENTIC_SYSTEM_PROMPT, "Customer query: 'افضل 3 منتجات من حيث نسبه البروتين'")
print(json.dumps(r3.content, indent=2, ensure_ascii=False))

print("\n--- 4. ايهم اعلى بروتين؟ (with visible products) ---")
q4 = """Currently visible store items:
1. لحم سن بقري بلدي (Brand: Spinneys, Price: 439.95 EGP)
2. حواوشى لحم بلدى (Brand: Spinneys, Price: 49.95 EGP)
3. انتركوت بقرى بلدى (Brand: Spinneys, Price: 394.95 EGP)

Conversation history:
user: وصفه للحمه
assistant: وصفة كباب حلة باللحمة شهية...

Customer query: 'ايهم اعلى بروتين؟'"""
r4 = llm.complete_json(AGENTIC_SYSTEM_PROMPT, q4)
print(json.dumps(r4.content, indent=2, ensure_ascii=False))
