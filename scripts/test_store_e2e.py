# -*- coding: utf-8 -*-
import io
import sys

# Ensure UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from app.main import app

def run_tests():
    client = TestClient(app)

    print("=== 1. Health check ===")
    r = client.get("/health")
    print("Health:", r.status_code, r.json()["status"])
    assert r.status_code == 200

    print("\n=== 2. Store Categories ===")
    r = client.get("/api/store/categories")
    cats = r.json()
    print("Categories:", len(cats["categories"]), "Brands:", len(cats["brands"]), "Price range:", cats["price_range"])
    assert len(cats["categories"]) > 0

    print("\n=== 3. Store Products Filter ===")
    r = client.get("/api/store/products?category=Dairy&page=1&page_size=4&sort=price_asc")
    prods = r.json()
    print("Dairy Products:", prods["total_products"], "Page items:", len(prods["products"]))
    assert prods["total_products"] > 0
    for p in prods["products"]:
        print(f"  - [{p['product_id']}] {p['name_ar']} ({p['price']} EGP, stock: {p['availability']})")

    print("\n=== 4. AI Recipe Search ===")
    r = client.post("/api/chat", json={"session_id": "test-e2e", "message": "عايز اعمل مكرونة بشاميل"})
    chat_res = r.json()
    print("Chat Intent:", chat_res["intent"], "Dish:", chat_res.get("dish"))
    recipe_items = chat_res.get("cart") or []
    print("Recipe cart items count:", len(recipe_items))
    assert len(recipe_items) > 0

    print("\n=== 5. Validate Cart with Recipe Items ===")
    cart_payload = []
    for item in recipe_items:
        if "products" in item and len(item["products"]) > 0:
            cart_payload.append({"product_id": item["products"][0]["product_id"], "quantity": 1})
        elif "product_id" in item:
            cart_payload.append({"product_id": item["product_id"], "quantity": 1})
    r = client.post("/api/store/cart/validate", json={"items": cart_payload})
    val_res = r.json()
    print("Cart valid:", val_res["is_valid"], "Subtotal:", val_res["subtotal"], "Delivery:", val_res["delivery_fee"], "Total:", val_res["total"])
    assert val_res["total"] > 0

    print("\n=== 6. Checkout Pipeline ===")
    order_payload = {
        "customer_name": "Hossam Hassan",
        "customer_phone": "01122334455",
        "delivery_address": "45 Al-Ahram St, Heliopolis, Cairo",
        "delivery_notes": "Apartment 5, 2nd floor",
        "payment_method": "Cash on Delivery",
        "items": cart_payload
    }
    r = client.post("/api/store/checkout", json=order_payload)
    order_res = r.json()
    print("Checkout Success:", order_res["success"], "Order ID:", order_res["order_reference"])
    print("ETA:", order_res["estimated_delivery"], "Total Paid:", order_res["total_amount"])
    assert order_res["success"] is True
    assert "SPN-" in order_res["order_reference"]

    print("\n✅ ALL STOREFRONT & ASSISTANT E2E TESTS PASSED!")

if __name__ == "__main__":
    run_tests()
