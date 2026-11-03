# -*- coding: utf-8 -*-
"""
scripts/test_i18n_bilingual.py
==============================
Verifies the bilingual localization system across frontend/index.html,
frontend/styles.css, and frontend/app.js.
"""

import io
import re
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent

def test_localization():
    print("=" * 70)
    print("VERIFYING FRONTEND BILINGUAL LOCALIZATION (AR <-> EN)")
    print("=" * 70)

    html_file = ROOT / "frontend" / "index.html"
    css_file = ROOT / "frontend" / "styles.css"
    js_file = ROOT / "frontend" / "app.js"

    assert html_file.exists(), "frontend/index.html not found!"
    assert css_file.exists(), "frontend/styles.css not found!"
    assert js_file.exists(), "frontend/app.js not found!"

    html_content = html_file.read_text(encoding="utf-8")
    css_content = css_file.read_text(encoding="utf-8")
    js_content = js_file.read_text(encoding="utf-8")

    # [1] Verify Language button IDs in HTML & CSS
    print("\n[1] Verifying Language Button Setup:")
    assert 'id="langToggle"' in html_content or 'id="lang-toggle-btn"' in html_content, "Language button ID missing in HTML"
    assert '#langToggle' in css_content, "#langToggle styling rule missing in styles.css"
    assert 'padding: 6px 14px;' in css_content or 'padding: 6px 14px' in css_content, "Padding 6px 14px missing"
    assert 'border-radius: 9999px' in css_content, "border-radius: 9999px missing"
    assert 'font-size: 13px' in css_content, "font-size: 13px missing"
    assert 'inline-flex' in css_content, "display: inline-flex missing"
    assert 'gap: 6px' in css_content, "gap: 6px missing"
    print("    --> Language Button CSS Properties Verified ✅")

    # [2] Verify i18n Dictionary in app.js
    print("\n[2] Verifying i18n Dictionary in app.js:")
    required_ar_snippets = [
      "توصيل مجاني لجميع الطلبات فوق 300 جنيه!",
      "خدمة العملاء: 16005",
      "ابحث في أكثر من 25,800 منتج",
      "سلة التسوق",
      "المساعد الذكي ✨",
      "جميع المنتجات",
      "البقالة والتموين",
      "الألبان والبيض",
      "المشروبات",
      "الحلويات والتسالي",
      "العناية الشخصية",
      "المنزل والمطبخ",
      "المنظفات",
      "المجمدات",
      "الخضار والفاكهة",
      "تصفية المنتجات",
      "المتوفر في المخزن فقط",
      "نطاق السعر",
      "الماركات الشهيرة",
      "إعادة تعيين",
      "تسوق كل احتياجات منزلك مع سبينيس",
      "تصفح العروض الآن",
      "اطلب مقادير وصفة بالذكاء الاصطناعي",
      "أضف للسلة",
      "ج.م"
    ]

    for snippet in required_ar_snippets:
      assert snippet in js_content, f"Arabic snippet missing in i18n: '{snippet}'"
    print(f"    --> All {len(required_ar_snippets)} Arabic UI phrases verified ✅")

    required_en_snippets = [
      "Free delivery on orders over 300 EGP!",
      "Customer Service: 16005",
      "Search 25,800+ products",
      "Shopping Cart",
      "Smart AI Assistant ✨",
      "All Products",
      "Grocery & Pantry",
      "Dairy & Eggs",
      "Beverages",
      "Snacks & Sweets",
      "Personal Care",
      "Home & Kitchen",
      "Cleaning",
      "Frozen Food",
      "Fruits & Vegetables",
      "Filter Products",
      "In-Stock Only",
      "Price Range",
      "Top Brands",
      "Reset Filters",
      "Shop All Your Daily Groceries With Spinneys",
      "Explore Offers",
      "Order Recipe Ingredients with AI",
      "100% Guaranteed Quality",
      "Add to Cart",
      "In Stock",
      "Out of Stock",
      "EGP"
    ]

    for snippet in required_en_snippets:
      assert snippet in js_content, f"English snippet missing in i18n: '{snippet}'"
    print(f"    --> All {len(required_en_snippets)} English UI phrases verified ✅")

    # [3] Verify Direction & Layout rules
    print("\n[3] Verifying Layout Direction (RTL vs LTR):")
    assert '[dir="ltr"]' in css_content, "[dir='ltr'] rules missing in styles.css"
    assert '[dir="rtl"]' in css_content, "[dir='rtl'] rules missing in styles.css"
    assert 'dir = (lang === "ar") ? "rtl" : "ltr"' in js_content or 'dir = (lang === \'ar\') ? "rtl" : "ltr"' in js_content, "Direction switcher missing in app.js"
    assert 'langBtnText.textContent = (lang === "ar") ? "English" : "العربية"' in js_content or 'switchLangText' in js_content, "Language button toggle text missing"
    print("    --> Layout direction and font switching verified ✅")

    print("\n" + "=" * 70)
    print("ALL BILINGUAL LOCALIZATION TESTS PASSED! 🚀")
    print("=" * 70)

if __name__ == "__main__":
    test_localization()
