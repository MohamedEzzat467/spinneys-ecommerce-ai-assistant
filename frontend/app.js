/**
 * Spinneys Egypt — Modern E-Commerce Storefront & AI Assistant Application
 * 
 * Features:
 *   - Fast Catalog Browsing (< 20 ms) with Category, Brand, Price, and Stock Filters.
 *   - Live Debounced Search Bar with Instant Suggestions.
 *   - Slide-Out Shopping Cart Drawer with Real-Time Stock & Free Delivery Progress.
 *   - Mock Checkout Pipeline with Order ID and Receipt Generation.
 *   - Floating Multi-Turn AI Assistant with Filter Chips, Product Cards, and Recipe Smart Cart.
 *   - Bilingual English/Arabic Dynamic Localization.
 */

// ── Configurable Cloud & Local Backend API Endpoint ────────────────────────
const getApiBaseUrl = () => {
  if (typeof window !== "undefined") {
    // 1. Explicit window override (e.g. from config.js)
    if (window.__SPINNEYS_API_BASE__) return window.__SPINNEYS_API_BASE__.replace(/\/+$/, "");
    // 2. Local storage override (set via console or settings)
    const stored = localStorage.getItem("spinneys_api_base");
    if (stored) return stored.replace(/\/+$/, "");
    // 3. Localhost development fallback
    const host = window.location.hostname;
    const isLocal = host === "localhost" || host === "127.0.0.1" || host === "";
    if (isLocal) return "http://localhost:8000";
    // 4. If served from the same host on port 8000 or custom port
    if (window.location.port === "8000") return window.location.origin;
  }
  return "http://localhost:8000";
};

const API_BASE = getApiBaseUrl();

// ── State Management ──────────────────────────────────────────────────────────
const state = {
  lang: localStorage.getItem("spinneys_lang") || "ar",
  cart: JSON.parse(localStorage.getItem("spinneys_cart") || "{}"),
  activeCategory: "all",
  activeBrand: null,
  searchQuery: "",
  priceMin: 0,
  priceMax: 1000,
  inStockOnly: true,
  sort: "popular",
  currentPage: 1,
  pageSize: 24,
  totalPages: 1,
  totalProducts: 0,
  categories: [],
  brands: [],
  aiSessionId: localStorage.getItem("spinneys_ai_session") || ("session-" + Date.now()),
  aiActiveFilters: {},
};

// SVG Placeholder for missing product images
const PLACEHOLDER_SVG = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180' viewBox='0 0 24 24' fill='none' stroke='%2300704A' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'><path d='M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z'/><path d='M3 6h18'/><path d='M16 10a4 4 0 0 1-8 0'/></svg>";

// ── Dictionary / Translations ────────────────────────────────────────────────
const i18n = {
  ar: {
    // Top Utility Bar
    promoText: "توصيل مجاني لجميع الطلبات فوق 300 جنيه! | كاش أو بطاقة عند الاستلام",
    customerService: "خدمة العملاء: 16005",
    switchLangText: "English",

    // Header & Search
    searchPlaceholder: "ابحث في أكثر من 25,800 منتج (مثال: حليب المراعي، أرز بسمتي)",
    cartTitle: "سلة التسوق",
    smartAssistantBtn: "المساعد الذكي ✨",

    // Categories
    allProducts: "جميع المنتجات",
    categories: {
      all: "جميع المنتجات",
      Grocery: "البقالة والتموين",
      Dairy: "الألبان والبيض",
      Beverages: "المشروبات",
      "Sweets & Snacks": "الحلويات والتسالي",
      "Beauty & Personal Care": "العناية الشخصية",
      Households: "المنزل والمطبخ",
      "Cleaning Products": "المنظفات",
      "Frozen Food": "المجمدات",
      "Fruits & Vegetables": "الخضار والفاكهة",
    },

    // Filters Sidebar
    filterProducts: "🔍 تصفية المنتجات",
    resetFilters: "إعادة تعيين",
    inStockOnly: "المتوفر في المخزن فقط",
    priceRange: "نطاق السعر (ج.م)",
    priceFrom: "من:",
    priceTo: "إلى:",
    applyPrice: "تطبيق السعر",
    categoriesHeader: "الأقسام",
    topBrands: "الماركات الشهيرة",
    searchBrandPlaceholder: "بحث عن ماركة...",

    // Hero Banner
    heroTag: "🔥 عروض وخصومات حصرية",
    heroTitle: "تسوق كل احتياجات منزلك مع سبينيس",
    heroDesc: "أكثر من 25,800 منتج طازج ومضمون بأسعار الجملة، مع مساعد تسوق ذكي يساعدك في إعداد وجباتك وقوائمك في ثوانٍ.",
    heroExplore: "تصفح العروض الآن",
    heroRecipe: "🍲 اطلب مقادير وصفة بالذكاء الاصطناعي",
    statProductsNum: "+25.8K",
    statProductsLbl: "+25.8K منتج متاح بالكتالوج",
    statDeliveryNum: "< 45 دقيقة",
    statDeliveryLbl: "> 45 دقيقة سرعة التوصيل لباب بيتك",
    statQualityNum: "100%",
    statQualityLbl: "100% جودة وأصالة مضمونة",

    // Toolbar & Products
    sortBy: "الترتيب حسب:",
    sortOptions: {
      popular: "الأكثر شعبية والعروض",
      price_asc: "السعر: من الأقل للأعلى",
      price_desc: "السعر: من الأعلى للأقل",
      discount: "أعلى نسبة خصم",
      name_asc: "الاسم: أبجدياً",
    },
    productsCount: (start, end, total, ms) => `عرض ${start}-${end} من أصل ${total.toLocaleString()} منتج (${ms} ms)`,
    zeroProducts: "0 منتج",
    updatingProducts: "جاري تحديث المنتجات...",
    emptyTitle: "لم نجد أي منتجات تطابق اختياراتك!",
    emptyDesc: "جرب تغيير شروط البحث، أو توسيع نطاق السعر، أو اضغط زر إعادة التعيين.",
    emptyReset: "إعادة تعيين الفلاتر",
    prevPage: "السابق",
    nextPage: "التالي",
    addToCart: "أضف للسلة",
    inStock: "متوفر",
    outOfStock: "غير متوفر",
    unavailable: "غير متوفر",
    currency: "ج.م",

    // Filter tags
    tagCategory: (c) => `القسم: ${c}`,
    tagBrand: (b) => `الماركة: ${b}`,
    tagSearch: (s) => `البحث: "${s}"`,

    // Cart Drawer
    cartDrawerTitle: "سلة المشتريات",
    freeDeliveryProgress: (rem) => `أضف منتجات بقيمة ${rem.toFixed(2)} ج.م للحصول على توصيل مجاني!`,
    freeDeliveryQualified: "🎉 تهانينا! لقد حصلت على توصيل مجاني!",
    subtotal: "المجموع الفرعي:",
    deliveryFee: "رسوم التوصيل:",
    deliveryFree: "مجاناً",
    totalAmount: "الإجمالي الكلي:",
    proceedCheckout: "إتمام الطلب الآن",
    clearCart: "تفريغ السلة",
    cartEmptyTitle: "سلة المشتريات فارغة",
    cartEmptySubtitle: "أضف منتجات من المتجر لتظهر هنا",
    addedToCart: "تمت إضافة المنتج إلى السلة بنجاح",
    confirmClearCart: "هل أنت متأكد من تفريغ سلة المشتريات؟",
    cartEmptyToast: "السلة فارغة حالياً!",

    // Checkout Modal
    checkoutTitle: "إتمام الطلب والتوصيل | Spinneys Checkout",
    nameLabel: "الاسم بالكامل *",
    namePlaceholder: "محمد أحمد",
    phoneLabel: "رقم الهاتف المحمول *",
    phonePlaceholder: "01001234567",
    addressLabel: "عنوان التوصيل بالتفصيل *",
    addressPlaceholder: "المدينة، الحي، اسم الشارع، رقم العمارة والشقة",
    notesLabel: "ملاحظات التوصيل (اختياري)",
    notesPlaceholder: "مثال: يرجى الاتصال عند الوصول، الدور الرابع",
    paymentLabel: "طريقة الدفع *",
    payCash: "الدفع نقداً عند الاستلام (Cash on Delivery)",
    payCard: "بطاقة بنكية / فيزا (Mock Payment)",
    payWallet: "محفظة إلكترونية (فودافون كاش / إنستاباي)",
    itemsCountLabel: "عدد الأصناف:",
    checkoutSubtotalLabel: "المجموع الفرعي:",
    checkoutDeliveryLabel: "خدمة التوصيل:",
    amountDueLabel: "المبلغ المستحق:",
    confirmOrderBtn: "تأكيد الطلب وشحن المنتجات",
    processingOrder: "جاري معالجة الطلب...",

    // Receipt
    receiptTitle: "تم تأكيد طلبك بنجاح!",
    receiptSubtitle: "شكراً لتسوقك من سبينيس. سيصلك مندوب التوصيل في أقرب وقت.",
    orderIdLabel: "رقم مرجع الطلب (Order ID):",
    orderStatusLabel: "حالة الطلب:",
    orderEtaLabel: "وقت التوصيل المتوقع:",
    orderPaymentLabel: "طريقة الدفع:",
    orderAddressLabel: "العنوان:",
    orderTotalLabel: "المبلغ الإجمالي:",
    continueShopping: "متابعة التسوق",
    orderConfirmed: "تم تأكيد طلبك بنجاح!",

    // AI Assistant
    aiBadge: "مساعد سبينيس",
    aiTitle: "مساعد سبينيس الذكي",
    aiStatus: "متصل بـ 25,880 منتج",
    aiInputPlaceholder: "اكتب طلبك... (مثال: لبن جهينة، أو مكونات بيتزا)",
    aiWelcome: "أهلاً بك! 👋 أنا مساعدك الذكي في سبينيس. اطلب أي منتج أو وصفة طبخ وسأبحث لك فوراً:",
    aiSuggestions: [
      { text: "🥛 لبن شوفان", query: "عايز لبن شوفان" },
      { text: "🧀 دومتي تحت 50ج", query: "جبنة دومتي فيتا اقل من 50 جنيه" },
      { text: "🍲 مكرونة بشاميل", query: "عايز اعمل مكرونة بشاميل" },
      { text: "☕ شاي بدون ليبتون", query: "شاي بس مش ليبتون" },
    ],
    aiTyping: "جاري البحث في الكتالوج...",
    aiChipsTitle: "🎯 الفلاتر:",
    aiNewSessionToast: "تم تصفير محادثة المساعد الذكي",
    aiNewSessionMsg: "تم بدء جلسة جديدة! 🔄 كيف يمكنني مساعدتك في التسوق اليوم؟",
    allIngredientsAdded: "تمت إضافة جميع مقادير الوصفة إلى السلة!",
  },

  en: {
    // Top Utility Bar
    promoText: "Free delivery on orders over 300 EGP! | Cash or Card on Delivery",
    customerService: "Customer Service: 16005",
    switchLangText: "العربية",

    // Header & Search
    searchPlaceholder: "Search 25,800+ products (e.g., Juhayna milk, Basmati rice)",
    cartTitle: "Shopping Cart",
    smartAssistantBtn: "Smart AI Assistant ✨",

    // Categories
    allProducts: "All Products",
    categories: {
      all: "All Products",
      Grocery: "Grocery & Pantry",
      Dairy: "Dairy & Eggs",
      Beverages: "Beverages",
      "Sweets & Snacks": "Snacks & Sweets",
      "Beauty & Personal Care": "Personal Care",
      Households: "Home & Kitchen",
      "Cleaning Products": "Cleaning",
      "Frozen Food": "Frozen Food",
      "Fruits & Vegetables": "Fruits & Vegetables",
    },

    // Filters Sidebar
    filterProducts: "🔍 Filter Products",
    resetFilters: "Reset Filters",
    inStockOnly: "In-Stock Only",
    priceRange: "Price Range (EGP)",
    priceFrom: "From:",
    priceTo: "To:",
    applyPrice: "Apply Price",
    categoriesHeader: "Categories",
    topBrands: "Top Brands",
    searchBrandPlaceholder: "Search brand...",

    // Hero Banner
    heroTag: "🔥 Exclusive Offers & Discounts",
    heroTitle: "Shop All Your Daily Groceries With Spinneys",
    heroDesc: "Over 25,800 fresh catalog items guaranteed at best prices, with an AI shopping assistant helping you plan meals and baskets in seconds.",
    heroExplore: "Explore Offers",
    heroRecipe: "🍲 Order Recipe Ingredients with AI",
    statProductsNum: "+25.8K",
    statProductsLbl: "+25.8K Available Catalog Products",
    statDeliveryNum: "< 45 Mins",
    statDeliveryLbl: "< 45 Mins Express Doorstep Delivery",
    statQualityNum: "100%",
    statQualityLbl: "100% Guaranteed Quality",

    // Toolbar & Products
    sortBy: "Sort by:",
    sortOptions: {
      popular: "Most Popular & Offers",
      price_asc: "Price: Low to High",
      price_desc: "Price: High to Low",
      discount: "Highest Discount",
      name_asc: "Name: Alphabetical",
    },
    productsCount: (start, end, total, ms) => `Showing ${start}-${end} of ${total.toLocaleString()} products (${ms} ms)`,
    zeroProducts: "0 products",
    updatingProducts: "Updating products...",
    emptyTitle: "We couldn't find any products matching your selection!",
    emptyDesc: "Try changing search terms, broadening price range, or reset filters.",
    emptyReset: "Reset Filters",
    prevPage: "Previous",
    nextPage: "Next",
    addToCart: "Add to Cart",
    inStock: "In Stock",
    outOfStock: "Out of Stock",
    unavailable: "Unavailable",
    currency: "EGP",

    // Filter tags
    tagCategory: (c) => `Category: ${c}`,
    tagBrand: (b) => `Brand: ${b}`,
    tagSearch: (s) => `Search: "${s}"`,

    // Cart Drawer
    cartDrawerTitle: "Shopping Cart",
    freeDeliveryProgress: (rem) => `Add ${rem.toFixed(2)} EGP more for FREE Delivery!`,
    freeDeliveryQualified: "🎉 Congratulations! You have unlocked FREE Delivery!",
    subtotal: "Subtotal:",
    deliveryFee: "Delivery Fee:",
    deliveryFree: "FREE",
    totalAmount: "Total Amount:",
    proceedCheckout: "Proceed to Checkout",
    clearCart: "Clear Cart",
    cartEmptyTitle: "Your cart is empty",
    cartEmptySubtitle: "Add products to start shopping",
    addedToCart: "Item added to cart successfully",
    confirmClearCart: "Are you sure you want to empty the shopping cart?",
    cartEmptyToast: "Cart is currently empty!",

    // Checkout Modal
    checkoutTitle: "Order Checkout & Delivery | Spinneys",
    nameLabel: "Full Name *",
    namePlaceholder: "Mohamed Ahmed",
    phoneLabel: "Mobile Number *",
    phonePlaceholder: "01001234567",
    addressLabel: "Detailed Delivery Address *",
    addressPlaceholder: "City, district, street name, building & apartment no.",
    notesLabel: "Delivery Notes (Optional)",
    notesPlaceholder: "e.g., Please call upon arrival, 4th floor",
    paymentLabel: "Payment Method *",
    payCash: "Cash on Delivery",
    payCard: "Credit / Debit Card (Mock Payment)",
    payWallet: "Mobile Wallet (Vodafone Cash / InstaPay)",
    itemsCountLabel: "Items Count:",
    checkoutSubtotalLabel: "Subtotal:",
    checkoutDeliveryLabel: "Delivery Fee:",
    amountDueLabel: "Amount Due:",
    confirmOrderBtn: "Confirm Order & Ship Items",
    processingOrder: "Processing Order...",

    // Receipt
    receiptTitle: "Your Order is Confirmed!",
    receiptSubtitle: "Thank you for shopping with Spinneys. Your delivery is on its way.",
    orderIdLabel: "Order Reference ID:",
    orderStatusLabel: "Order Status:",
    orderEtaLabel: "Estimated Delivery Time:",
    orderPaymentLabel: "Payment Method:",
    orderAddressLabel: "Address:",
    orderTotalLabel: "Total Amount:",
    continueShopping: "Continue Shopping",
    orderConfirmed: "Your order has been placed successfully!",

    // AI Assistant
    aiBadge: "Spinneys AI",
    aiTitle: "Spinneys AI Assistant",
    aiStatus: "Connected to 25,880+ Products",
    aiInputPlaceholder: "Type your request... (e.g. Juhayna milk, pizza recipe)",
    aiWelcome: "Welcome! 👋 I am your Spinneys AI Assistant. Ask for any product or recipe to search instantly:",
    aiSuggestions: [
      { text: "🥛 Oat Milk", query: "I want oat milk" },
      { text: "🧀 Domty under 50", query: "Domty feta under 50 EGP" },
      { text: "🍲 Bechamel Pasta", query: "How to make bechamel pasta" },
      { text: "☕ Tea without Lipton", query: "Tea without Lipton" },
    ],
    aiTyping: "Searching catalog...",
    aiChipsTitle: "🎯 Filters:",
    aiNewSessionToast: "AI assistant conversation reset",
    aiNewSessionMsg: "New session started! 🔄 How can I help with your shopping today?",
    allIngredientsAdded: "All recipe ingredients added to cart!",
  }
};

// ── Initialization ───────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  setupLanguage(state.lang);
  setupEventListeners();
  loadTaxonomy();
  loadProducts(1);
  renderCart();
});

// ── Language Setup & DOM Localization ─────────────────────────────────────────
function setupLanguage(lang) {
  state.lang = lang;
  localStorage.setItem("spinneys_lang", lang);
  document.documentElement.lang = lang;
  document.documentElement.dir = (lang === "ar") ? "rtl" : "ltr";
  document.title = (lang === "ar") 
    ? "سبينيس هايبرماركت | Spinneys Egypt Online Store & AI Assistant" 
    : "Spinneys Egypt | Online Store & AI Shopping Assistant";

  applyTranslations(lang);
  renderAiWelcomeMessage();
}

function applyTranslations(lang) {
  const t = i18n[lang];
  if (!t) return;

  // 1. Top Announcement Bar
  const promoEl = document.getElementById("promo-text");
  if (promoEl) promoEl.textContent = t.promoText;
  const supportEl = document.getElementById("support-text");
  if (supportEl) supportEl.textContent = t.customerService;
  const langBtnText = document.getElementById("lang-btn-text");
  if (langBtnText) langBtnText.textContent = t.switchLangText;

  // 2. Header & Search
  const searchInput = document.getElementById("store-search-input");
  if (searchInput) searchInput.placeholder = t.searchPlaceholder;
  const headerAiLabel = document.getElementById("header-ai-label");
  if (headerAiLabel) headerAiLabel.textContent = t.smartAssistantBtn;
  const cartTitleLabel = document.getElementById("cart-title-label");
  if (cartTitleLabel) cartTitleLabel.textContent = t.cartTitle;

  // 3. Category Tabs Ribbon
  document.querySelectorAll(".cat-tab").forEach(tab => {
    const catKey = tab.dataset.category;
    const catNameSpan = tab.querySelector(".cat-name");
    if (catNameSpan && catKey && t.categories[catKey]) {
      catNameSpan.textContent = t.categories[catKey];
    }
  });

  // 4. Hero Banner
  const heroTag = document.getElementById("hero-tag");
  if (heroTag) heroTag.textContent = t.heroTag;
  const heroTitle = document.getElementById("hero-title");
  if (heroTitle) heroTitle.textContent = t.heroTitle;
  const heroDesc = document.getElementById("hero-desc");
  if (heroDesc) heroDesc.textContent = t.heroDesc;
  const heroExploreBtn = document.getElementById("hero-explore-btn");
  if (heroExploreBtn) heroExploreBtn.textContent = t.heroExplore;
  const heroRecipeBtn = document.getElementById("hero-recipe-btn");
  if (heroRecipeBtn) heroRecipeBtn.textContent = t.heroRecipe;

  const statNumProducts = document.getElementById("stat-num-products");
  if (statNumProducts) statNumProducts.textContent = t.statProductsNum;
  const statLblProducts = document.getElementById("stat-lbl-products");
  if (statLblProducts) statLblProducts.textContent = t.statProductsLbl;

  const statNumDelivery = document.getElementById("stat-num-delivery");
  if (statNumDelivery) statNumDelivery.textContent = t.statDeliveryNum;
  const statLblDelivery = document.getElementById("stat-lbl-delivery");
  if (statLblDelivery) statLblDelivery.textContent = t.statDeliveryLbl;

  const statNumQuality = document.getElementById("stat-num-quality");
  if (statNumQuality) statNumQuality.textContent = t.statQualityNum;
  const statLblQuality = document.getElementById("stat-lbl-quality");
  if (statLblQuality) statLblQuality.textContent = t.statQualityLbl;

  // 5. Sidebar Filters
  const sidebarTitle = document.getElementById("sidebar-title");
  if (sidebarTitle) sidebarTitle.textContent = t.filterProducts;
  const resetFiltersBtn = document.getElementById("btn-reset-filters");
  if (resetFiltersBtn) resetFiltersBtn.textContent = t.resetFilters;
  const lblInstock = document.getElementById("lbl-instock");
  if (lblInstock) lblInstock.textContent = t.inStockOnly;
  const lblPricerange = document.getElementById("lbl-pricerange");
  if (lblPricerange) lblPricerange.textContent = t.priceRange;
  const lblPriceFrom = document.getElementById("lbl-price-from");
  if (lblPriceFrom) lblPriceFrom.textContent = t.priceFrom;
  const lblPriceTo = document.getElementById("lbl-price-to");
  if (lblPriceTo) lblPriceTo.textContent = t.priceTo;
  const btnApplyPrice = document.getElementById("btn-apply-price");
  if (btnApplyPrice) btnApplyPrice.textContent = t.applyPrice;
  const lblCategories = document.getElementById("lbl-categories");
  if (lblCategories) lblCategories.textContent = t.categoriesHeader;
  const lblBrands = document.getElementById("lbl-brands");
  if (lblBrands) lblBrands.textContent = t.topBrands;
  const brandSearchInput = document.getElementById("brand-search-input");
  if (brandSearchInput) brandSearchInput.placeholder = t.searchBrandPlaceholder;

  // 6. Toolbar & Pagination
  const lblSort = document.getElementById("lbl-sort");
  if (lblSort) lblSort.textContent = t.sortBy;
  const sortSelect = document.getElementById("store-sort-select");
  if (sortSelect) {
    Array.from(sortSelect.options).forEach(opt => {
      if (t.sortOptions[opt.value]) opt.textContent = t.sortOptions[opt.value];
    });
  }
  const emptyTitle = document.getElementById("empty-title");
  if (emptyTitle) emptyTitle.textContent = t.emptyTitle;
  const emptyDesc = document.getElementById("empty-desc");
  if (emptyDesc) emptyDesc.textContent = t.emptyDesc;
  const btnEmptyReset = document.getElementById("btn-empty-reset");
  if (btnEmptyReset) btnEmptyReset.textContent = t.emptyReset;
  const btnPrevPage = document.getElementById("btn-prev-page");
  if (btnPrevPage) btnPrevPage.textContent = t.prevPage;
  const btnNextPage = document.getElementById("btn-next-page");
  if (btnNextPage) btnNextPage.textContent = t.nextPage;

  // 7. Cart Drawer
  const drawerTitleText = document.getElementById("drawer-title-text");
  if (drawerTitleText) drawerTitleText.textContent = t.cartDrawerTitle;
  const lblSubtotal = document.getElementById("lbl-subtotal");
  if (lblSubtotal) lblSubtotal.textContent = t.subtotal;
  const lblDelivery = document.getElementById("lbl-delivery");
  if (lblDelivery) lblDelivery.textContent = t.deliveryFee;
  const lblTotal = document.getElementById("lbl-total");
  if (lblTotal) lblTotal.textContent = t.totalAmount;
  const btnCheckoutText = document.getElementById("btn-checkout-text");
  if (btnCheckoutText) btnCheckoutText.textContent = t.proceedCheckout;
  const checkoutArrow = document.querySelector(".checkout-arrow");
  if (checkoutArrow) checkoutArrow.textContent = (lang === "ar") ? "←" : "→";
  const btnClearCart = document.getElementById("btn-clear-cart");
  if (btnClearCart) btnClearCart.textContent = t.clearCart;

  // 8. Checkout Modal
  const checkoutModalTitle = document.getElementById("checkout-modal-title");
  if (checkoutModalTitle) checkoutModalTitle.textContent = t.checkoutTitle;
  const lblCustName = document.getElementById("lbl-cust-name");
  if (lblCustName) lblCustName.textContent = t.nameLabel;
  const custNameInput = document.getElementById("cust-name");
  if (custNameInput) custNameInput.placeholder = t.namePlaceholder;
  const lblCustPhone = document.getElementById("lbl-cust-phone");
  if (lblCustPhone) lblCustPhone.textContent = t.phoneLabel;
  const custPhoneInput = document.getElementById("cust-phone");
  if (custPhoneInput) custPhoneInput.placeholder = t.phonePlaceholder;
  const lblCustAddress = document.getElementById("lbl-cust-address");
  if (lblCustAddress) lblCustAddress.textContent = t.addressLabel;
  const custAddressInput = document.getElementById("cust-address");
  if (custAddressInput) custAddressInput.placeholder = t.addressPlaceholder;
  const lblCustNotes = document.getElementById("lbl-cust-notes");
  if (lblCustNotes) lblCustNotes.textContent = t.notesLabel;
  const custNotesInput = document.getElementById("cust-notes");
  if (custNotesInput) custNotesInput.placeholder = t.notesPlaceholder;
  const lblPaymentMethod = document.getElementById("lbl-payment-method");
  if (lblPaymentMethod) lblPaymentMethod.textContent = t.paymentLabel;
  const lblPayCash = document.getElementById("lbl-pay-cash");
  if (lblPayCash) lblPayCash.textContent = t.payCash;
  const lblPayCard = document.getElementById("lbl-pay-card");
  if (lblPayCard) lblPayCard.textContent = t.payCard;
  const lblPayWallet = document.getElementById("lbl-pay-wallet");
  if (lblPayWallet) lblPayWallet.textContent = t.payWallet;

  const lblChkItems = document.getElementById("lbl-chk-items");
  if (lblChkItems) lblChkItems.textContent = t.itemsCountLabel;
  const lblChkSubtotal = document.getElementById("lbl-chk-subtotal");
  if (lblChkSubtotal) lblChkSubtotal.textContent = t.checkoutSubtotalLabel;
  const lblChkDelivery = document.getElementById("lbl-chk-delivery");
  if (lblChkDelivery) lblChkDelivery.textContent = t.checkoutDeliveryLabel;
  const lblChkTotal = document.getElementById("lbl-chk-total");
  if (lblChkTotal) lblChkTotal.textContent = t.amountDueLabel;
  const btnSubmitOrderText = document.getElementById("btn-submit-order-text");
  if (btnSubmitOrderText) btnSubmitOrderText.textContent = t.confirmOrderBtn;

  // 9. Receipt View
  const rcptH2 = document.getElementById("rcpt-h2");
  if (rcptH2) rcptH2.textContent = t.receiptTitle;
  const rcptPSubtitle = document.getElementById("rcpt-p-subtitle");
  if (rcptPSubtitle) rcptPSubtitle.textContent = t.receiptSubtitle;
  const lblRcptId = document.getElementById("lbl-rcpt-id");
  if (lblRcptId) lblRcptId.textContent = t.orderIdLabel;
  const lblRcptStatus = document.getElementById("lbl-rcpt-status");
  if (lblRcptStatus) lblRcptStatus.textContent = t.orderStatusLabel;
  const lblRcptEta = document.getElementById("lbl-rcpt-eta");
  if (lblRcptEta) lblRcptEta.textContent = t.orderEtaLabel;
  const lblRcptPayment = document.getElementById("lbl-rcpt-payment");
  if (lblRcptPayment) lblRcptPayment.textContent = t.orderPaymentLabel;
  const lblRcptAddress = document.getElementById("lbl-rcpt-address");
  if (lblRcptAddress) lblRcptAddress.textContent = t.orderAddressLabel;
  const lblRcptTotal = document.getElementById("lbl-rcpt-total");
  if (lblRcptTotal) lblRcptTotal.textContent = t.orderTotalLabel;
  const btnContinueShopping = document.getElementById("btn-continue-shopping");
  if (btnContinueShopping) btnContinueShopping.textContent = t.continueShopping;

  // 10. AI Assistant Widget
  const aiBadge = document.getElementById("ai-badge");
  if (aiBadge) aiBadge.textContent = t.aiBadge;
  const aiOverlayTitle = document.getElementById("ai-overlay-title");
  if (aiOverlayTitle) aiOverlayTitle.textContent = t.aiTitle;
  const aiOverlayStatus = document.getElementById("ai-overlay-status");
  if (aiOverlayStatus) aiOverlayStatus.innerHTML = `<span class="dot"></span> ${t.aiStatus}`;
  const aiMessageInput = document.getElementById("ai-message-input");
  if (aiMessageInput) aiMessageInput.placeholder = t.aiInputPlaceholder;
  const aiChipsTitle = document.getElementById("ai-chips-title");
  if (aiChipsTitle) aiChipsTitle.textContent = t.aiChipsTitle;
  const aiTypingText = document.getElementById("ai-typing-text");
  if (aiTypingText) aiTypingText.textContent = t.aiTyping;

  // Re-render sidebar categories
  if (state.categories && state.categories.length > 0) {
    renderSidebarCategories(state.categories);
  }
}

function renderAiWelcomeMessage() {
  const stream = document.getElementById("ai-messages-stream");
  if (!stream) return;
  const userMsgs = stream.querySelectorAll(".user-msg");
  if (userMsgs.length === 0) {
    const t = i18n[state.lang];
    stream.innerHTML = `
      <div class="chat-msg assistant-msg">
        <div class="msg-avatar">🤖</div>
        <div class="msg-bubble">
          <p>${t.aiWelcome}</p>
          <div class="chat-quick-suggestions">
            ${t.aiSuggestions.map(s => `
              <button class="chat-chip-prompt" data-query="${s.query}">${s.text}</button>
            `).join("")}
          </div>
        </div>
      </div>
    `;
  }
}

// ── Event Listeners ──────────────────────────────────────────────────────────
function setupEventListeners() {
  // Language Switcher
  const langToggleBtn = document.getElementById("langToggle") || document.getElementById("lang-toggle-btn");
  langToggleBtn?.addEventListener("click", () => {
    const nextLang = (state.lang === "ar") ? "en" : "ar";
    setupLanguage(nextLang);
    loadProducts(state.currentPage);
    renderCart();
  });

  // Search Input with Debounce
  const searchInput = document.getElementById("store-search-input");
  const clearSearchBtn = document.getElementById("search-clear-btn");
  let searchDebounceTimer;

  searchInput?.addEventListener("input", (e) => {
    const val = e.target.value.trim();
    if (clearSearchBtn) clearSearchBtn.style.display = val ? "block" : "none";
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
      state.searchQuery = val;
      loadProducts(1);
    }, 350);
  });

  clearSearchBtn?.addEventListener("click", () => {
    if (searchInput) searchInput.value = "";
    clearSearchBtn.style.display = "none";
    state.searchQuery = "";
    loadProducts(1);
  });

  // Category Tabs Click
  const catTabs = document.getElementById("category-tabs-list");
  catTabs?.addEventListener("click", (e) => {
    const tab = e.target.closest(".cat-tab");
    if (!tab) return;
    document.querySelectorAll(".cat-tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    state.activeCategory = tab.dataset.category || "all";
    loadProducts(1);
  });

  // Sorting Dropdown
  document.getElementById("store-sort-select")?.addEventListener("change", (e) => {
    state.sort = e.target.value;
    loadProducts(1);
  });

  // In-Stock Toggle
  document.getElementById("filter-instock")?.addEventListener("change", (e) => {
    state.inStockOnly = e.target.checked;
    loadProducts(1);
  });

  // Price Filter Apply
  document.getElementById("btn-apply-price")?.addEventListener("click", () => {
    const minVal = parseFloat(document.getElementById("price-min-input")?.value || 0);
    const maxVal = parseFloat(document.getElementById("price-max-input")?.value || 1000);
    state.priceMin = minVal;
    state.priceMax = maxVal;
    loadProducts(1);
  });

  // Reset Filters
  document.getElementById("btn-reset-filters")?.addEventListener("click", resetFilters);
  document.getElementById("btn-empty-reset")?.addEventListener("click", resetFilters);

  // Brand Search in Sidebar
  document.getElementById("brand-search-input")?.addEventListener("input", (e) => {
    const filterText = e.target.value.toLowerCase();
    document.querySelectorAll(".filter-item-row[data-brand]").forEach(row => {
      const bName = row.dataset.brand.toLowerCase();
      row.style.display = bName.includes(filterText) ? "flex" : "none";
    });
  });

  // Pagination Buttons
  document.getElementById("btn-prev-page")?.addEventListener("click", () => {
    if (state.currentPage > 1) loadProducts(state.currentPage - 1);
  });
  document.getElementById("btn-next-page")?.addEventListener("click", () => {
    if (state.currentPage < state.totalPages) loadProducts(state.currentPage + 1);
  });

  // Cart Drawer Open / Close
  const cartDrawer = document.getElementById("cart-drawer");
  const cartOverlay = document.getElementById("cart-drawer-overlay");
  
  const openCart = () => {
    cartDrawer?.classList.add("active");
    cartOverlay?.classList.add("active");
  };
  const closeCart = () => {
    cartDrawer?.classList.remove("active");
    cartOverlay?.classList.remove("active");
  };

  document.getElementById("cart-drawer-btn")?.addEventListener("click", openCart);
  document.getElementById("drawer-close-btn")?.addEventListener("click", closeCart);
  cartOverlay?.addEventListener("click", closeCart);

  // Clear Cart
  document.getElementById("btn-clear-cart")?.addEventListener("click", () => {
    if (confirm(state.lang === "ar" ? "هل أنت متأكد من تفريغ سلة المشتريات؟" : "Are you sure you want to empty the cart?")) {
      state.cart = {};
      saveCart();
    }
  });

  // Checkout Modal Open / Close
  const checkoutModalOverlay = document.getElementById("checkout-modal-overlay");
  document.getElementById("btn-checkout-drawer")?.addEventListener("click", () => {
    if (Object.keys(state.cart).length === 0) {
      showToast(state.lang === "ar" ? "السلة فارغة حالياً!" : "Cart is currently empty!");
      return;
    }
    closeCart();
    openCheckoutModal();
  });

  document.getElementById("checkout-modal-close")?.addEventListener("click", () => {
    if (checkoutModalOverlay) checkoutModalOverlay.style.display = "none";
  });

  // Payment Options Radio Selection Style
  document.querySelectorAll(".payment-radio").forEach(radio => {
    radio.addEventListener("click", () => {
      document.querySelectorAll(".payment-radio").forEach(r => r.classList.remove("selected"));
      radio.classList.add("selected");
    });
  });

  // Checkout Form Submission
  document.getElementById("checkout-form")?.addEventListener("submit", handleCheckoutSubmit);
  document.getElementById("btn-continue-shopping")?.addEventListener("click", () => {
    if (checkoutModalOverlay) checkoutModalOverlay.style.display = "none";
    document.getElementById("checkout-form").style.display = "block";
    document.getElementById("order-receipt-view").style.display = "none";
  });

  // Floating AI Assistant Widget
  const aiOverlay = document.getElementById("ai-chat-overlay");
  const toggleAiWidget = () => {
    if (!aiOverlay) return;
    const isHidden = aiOverlay.style.display === "none" || !aiOverlay.style.display;
    aiOverlay.style.display = isHidden ? "flex" : "none";
    if (isHidden) {
      document.getElementById("ai-message-input")?.focus();
    }
  };

  document.getElementById("ai-launcher-btn")?.addEventListener("click", toggleAiWidget);
  document.getElementById("header-ai-btn")?.addEventListener("click", toggleAiWidget);
  document.getElementById("btn-ai-minimize")?.addEventListener("click", () => {
    if (aiOverlay) aiOverlay.style.display = "none";
  });

  // Reset AI Chat
  document.getElementById("btn-ai-new-chat")?.addEventListener("click", () => {
    state.aiSessionId = "session-" + Date.now();
    localStorage.setItem("spinneys_ai_session", state.aiSessionId);
    state.aiActiveFilters = {};
    updateAiFilterChips();
    const stream = document.getElementById("ai-messages-stream");
    if (stream) {
      stream.innerHTML = `
        <div class="chat-msg assistant-msg">
          <div class="msg-avatar">🤖</div>
          <div class="msg-bubble">
            <p>تم بدء جلسة جديدة! 🔄 كيف يمكنني مساعدتك في التسوق اليوم؟</p>
          </div>
        </div>
      `;
    }
    showToast("تم تصفير محادثة المساعد الذكي");
  });

  // AI Chat Form
  document.getElementById("ai-chat-form")?.addEventListener("submit", handleAiChatSubmit);

  // AI Chat Quick Suggestion Chips
  document.addEventListener("click", (e) => {
    const promptBtn = e.target.closest(".chat-chip-prompt");
    if (promptBtn && promptBtn.dataset.query) {
      const q = promptBtn.dataset.query;
      const input = document.getElementById("ai-message-input");
      if (input) {
        input.value = q;
        document.getElementById("ai-chat-form")?.dispatchEvent(new Event("submit"));
      }
    }
  });

  // Hero Actions
  document.getElementById("hero-explore-btn")?.addEventListener("click", () => {
    document.querySelector(".store-main")?.scrollIntoView({ behavior: "smooth" });
  });
  document.getElementById("hero-recipe-btn")?.addEventListener("click", () => {
    if (aiOverlay) aiOverlay.style.display = "flex";
    const input = document.getElementById("ai-message-input");
    if (input) {
      input.value = "عايز اعمل مكرونة بشاميل";
      document.getElementById("ai-chat-form")?.dispatchEvent(new Event("submit"));
    }
  });
}

function resetFilters() {
  state.activeCategory = "all";
  state.activeBrand = null;
  state.searchQuery = "";
  state.priceMin = 0;
  state.priceMax = 1000;
  state.inStockOnly = true;
  state.sort = "popular";

  // Reset inputs
  const sInput = document.getElementById("store-search-input");
  if (sInput) sInput.value = "";
  const clrBtn = document.getElementById("search-clear-btn");
  if (clrBtn) clrBtn.style.display = "none";
  const pMin = document.getElementById("price-min-input");
  if (pMin) pMin.value = 0;
  const pMax = document.getElementById("price-max-input");
  if (pMax) pMax.value = 1000;
  const stockToggle = document.getElementById("filter-instock");
  if (stockToggle) stockToggle.checked = true;

  // Reset tabs
  document.querySelectorAll(".cat-tab").forEach(t => {
    t.classList.toggle("active", t.dataset.category === "all");
  });

  loadProducts(1);
}

// ── Taxonomy Loading (Categories & Brands) ───────────────────────────────────
async function loadTaxonomy() {
  try {
    const res = await fetch(`${API_BASE}/api/store/categories`);
    if (!res.ok) throw new Error("Failed to load taxonomy");
    const data = await res.json();
    state.categories = data.categories || [];
    state.brands = data.brands || [];

    renderSidebarCategories(state.categories);
    renderSidebarBrands(state.brands);
  } catch (err) {
    console.error("Error loading taxonomy:", err);
  }
}

function renderSidebarCategories(categories) {
  const container = document.getElementById("sidebar-categories-list");
  if (!container) return;

  container.innerHTML = categories.slice(0, 20).map(cat => {
    const locName = (i18n[state.lang].categories && i18n[state.lang].categories[cat.name])
      ? i18n[state.lang].categories[cat.name]
      : cat.name;
    return `
      <div class="filter-item-row" data-cat="${cat.name}">
        <label>
          <input type="radio" name="side-cat" ${state.activeCategory === cat.name ? "checked" : ""} />
          <span>${cat.icon || "🏷️"} ${locName}</span>
        </label>
        <span class="filter-item-count">${cat.count.toLocaleString()}</span>
      </div>
    `;
  }).join("");

  container.querySelectorAll(".filter-item-row").forEach(row => {
    row.addEventListener("click", () => {
      const catName = row.dataset.cat;
      state.activeCategory = catName;
      // Sync with top ribbon
      document.querySelectorAll(".cat-tab").forEach(tab => {
        tab.classList.toggle("active", tab.dataset.category === catName);
      });
      loadProducts(1);
    });
  });
}

function renderSidebarBrands(brands) {
  const container = document.getElementById("sidebar-brands-list");
  if (!container) return;

  container.innerHTML = brands.slice(0, 30).map(b => `
    <div class="filter-item-row" data-brand="${b.name}">
      <label>
        <input type="radio" name="side-brand" ${state.activeBrand === b.name ? "checked" : ""} />
        <span>${b.name}</span>
      </label>
      <span class="filter-item-count">${b.count.toLocaleString()}</span>
    </div>
  `).join("");

  container.querySelectorAll(".filter-item-row").forEach(row => {
    row.addEventListener("click", () => {
      const bName = row.dataset.brand;
      state.activeBrand = (state.activeBrand === bName) ? null : bName;
      loadProducts(1);
    });
  });
}

// ── Catalog Products Loading ─────────────────────────────────────────────────
async function loadProducts(page = 1) {
  const loader = document.getElementById("grid-loader");
  const grid = document.getElementById("products-grid-container");
  const emptyState = document.getElementById("empty-state");
  const resultsCountText = document.getElementById("results-count-text");

  if (loader) loader.style.display = "flex";
  if (grid) grid.style.display = "none";
  if (emptyState) emptyState.style.display = "none";

  state.currentPage = page;

  // Build Query URL
  const params = new URLSearchParams({
    page: page.toString(),
    page_size: state.pageSize.toString(),
    sort: state.sort,
  });

  if (state.activeCategory && state.activeCategory !== "all") {
    params.set("category", state.activeCategory);
  }
  if (state.activeBrand) {
    params.set("brand", state.activeBrand);
  }
  if (state.searchQuery) {
    params.set("search", state.searchQuery);
  }
  if (state.inStockOnly) {
    params.set("in_stock", "true");
  }
  if (state.priceMin > 0) {
    params.set("price_min", state.priceMin.toString());
  }
  if (state.priceMax > 0 && state.priceMax < 10000) {
    params.set("price_max", state.priceMax.toString());
  }

  try {
    const res = await fetch(`${API_BASE}/api/store/products?${params.toString()}`);
    if (!res.ok) throw new Error("HTTP error " + res.status);
    const data = await res.json();

    state.totalPages = data.total_pages || 1;
    state.totalProducts = data.total_products || 0;

    if (loader) loader.style.display = "none";

    if (!data.products || data.products.length === 0) {
      if (emptyState) emptyState.style.display = "block";
      if (resultsCountText) {
        resultsCountText.textContent = (state.lang === "ar") ? "0 منتج" : "0 products found";
      }
      renderPagination(0, 0);
      return;
    }

    if (grid) {
      grid.style.display = "grid";
      grid.innerHTML = data.products.map(p => renderProductCard(p)).join("");
    }

    if (resultsCountText) {
      const start = (data.page - 1) * data.page_size + 1;
      const end = Math.min(data.page * data.page_size, data.total_products);
      resultsCountText.textContent = (state.lang === "ar")
        ? `عرض ${start}-${end} من أصل ${data.total_products.toLocaleString()} منتج (${data.execution_ms} ms)`
        : `Showing ${start}-${end} of ${data.total_products.toLocaleString()} products (${data.execution_ms} ms)`;
    }

    renderActiveFilterTags();
    renderPagination(data.page, data.total_pages);
  } catch (err) {
    console.error("Failed to load products:", err);
    if (loader) loader.style.display = "none";
    if (emptyState) emptyState.style.display = "block";
  }
}

// ── Product Card Component ───────────────────────────────────────────────────
function renderProductCard(p) {
  const inCartQty = state.cart[p.product_id]?.quantity || 0;
  const isArabic = (state.lang === "ar");
  const title = isArabic ? (p.name_ar || p.name_en) : (p.name_en || p.name_ar);
  const subTitle = isArabic ? p.name_en : p.name_ar;
  const curr = i18n[state.lang].currency;
  const localizedCat = (i18n[state.lang].categories && i18n[state.lang].categories[p.category])
    ? i18n[state.lang].categories[p.category]
    : p.category;

  const discountPercent = (p.has_discount && p.regular_price > p.price)
    ? Math.round(((p.regular_price - p.price) / p.regular_price) * 100)
    : 0;

  return `
    <div class="product-card" data-product-id="${p.product_id}">
      <div class="card-top-badges">
        ${discountPercent > 0 ? `<span class="discount-badge">-${discountPercent}%</span>` : `<span></span>`}
        <span class="stock-badge ${p.availability ? 'in-stock' : 'out-stock'}">
          ${p.availability ? (isArabic ? 'متوفر' : 'In Stock') : (isArabic ? 'غير متوفر' : 'Out of Stock')}
        </span>
      </div>

      <div class="product-img-box">
        <img 
          src="${p.image_url || PLACEHOLDER_SVG}" 
          alt="${p.name_en}"
          loading="lazy"
          onerror="this.onerror=null; this.src='${PLACEHOLDER_SVG}';"
        />
      </div>

      <div class="card-meta">
        <span class="brand-badge">${p.brand || 'Generic'}</span>
        <span class="category-tag">${localizedCat}</span>
      </div>

      <h3 class="product-title-ar" title="${title}">${title}</h3>
      <div class="product-title-en">${subTitle || ''}</div>

      <div class="product-price-row">
        <span class="current-price">${p.price.toFixed(2)} ${curr}</span>
        ${p.has_discount && p.regular_price > p.price ? `<span class="regular-price">${p.regular_price.toFixed(2)} ${curr}</span>` : ''}
      </div>

      <div class="card-action-box" id="card-action-${p.product_id}">
        ${inCartQty > 0 ? `
          <div class="card-qty-control">
            <button class="btn-qty" onclick="changeQuantity(${p.product_id}, -1)">−</button>
            <span class="qty-val">${inCartQty}</span>
            <button class="btn-qty" onclick="changeQuantity(${p.product_id}, 1)">+</button>
          </div>
        ` : `
          <button 
            class="btn-add-cart" 
            onclick="addProductToCart(${p.product_id})"
            ${!p.availability ? 'disabled' : ''}
          >
            <span>+</span>
            <span>${p.availability ? i18n[state.lang].addToCart : (isArabic ? 'غير متوفر' : 'Unavailable')}</span>
          </button>
        `}
      </div>
    </div>
  `;
}

// ── Active Filters Bar (Storefront) ──────────────────────────────────────────
function renderActiveFilterTags() {
  const container = document.getElementById("active-store-tags");
  if (!container) return;
  const t = i18n[state.lang];

  const tags = [];
  if (state.activeCategory && state.activeCategory !== "all") {
    const catName = t.categories[state.activeCategory] || state.activeCategory;
    tags.push({ label: t.tagCategory(catName), onRemove: () => { state.activeCategory = "all"; loadProducts(1); } });
  }
  if (state.activeBrand) {
    tags.push({ label: t.tagBrand(state.activeBrand), onRemove: () => { state.activeBrand = null; loadProducts(1); } });
  }
  if (state.searchQuery) {
    tags.push({ label: t.tagSearch(state.searchQuery), onRemove: () => { state.searchQuery = ""; const i = document.getElementById("store-search-input"); if (i) i.value = ""; loadProducts(1); } });
  }

  container.innerHTML = tags.map((tg, idx) => `
    <span class="store-tag-chip">
      ${tg.label}
      <span class="store-tag-remove" onclick="removeActiveFilter(${idx})">✕</span>
    </span>
  `).join("");

  window._activeFiltersCallbacks = tags.map(tg => tg.onRemove);
}

window.removeActiveFilter = function(index) {
  if (window._activeFiltersCallbacks && window._activeFiltersCallbacks[index]) {
    window._activeFiltersCallbacks[index]();
  }
};

// ── Pagination Rendering ─────────────────────────────────────────────────────
function renderPagination(page, totalPages) {
  const container = document.getElementById("page-numbers-container");
  const prevBtn = document.getElementById("btn-prev-page");
  const nextBtn = document.getElementById("btn-next-page");

  if (prevBtn) prevBtn.disabled = (page <= 1);
  if (nextBtn) nextBtn.disabled = (page >= totalPages || totalPages === 0);

  if (!container) return;
  if (totalPages <= 1) {
    container.innerHTML = "";
    return;
  }

  const pages = [];
  const start = Math.max(1, page - 2);
  const end = Math.min(totalPages, page + 2);

  for (let i = start; i <= end; i++) {
    pages.push(`
      <button 
        class="page-num-btn ${i === page ? 'active' : ''}" 
        onclick="loadProducts(${i})"
      >${i}</button>
    `);
  }
  container.innerHTML = pages.join("");
}

// ── Cart Operations & Persistence ────────────────────────────────────────────
window.addProductToCart = async function(productId, qty = 1) {
  // If product details not loaded, find from current cards or fetch
  const card = document.querySelector(`.product-card[data-product-id="${productId}"]`);
  let item = state.cart[productId];

  if (!item && card) {
    const titleAr = card.querySelector(".product-title-ar")?.textContent.trim() || "";
    const titleEn = card.querySelector(".product-title-en")?.textContent.trim() || "";
    const brand = card.querySelector(".brand-badge")?.textContent.trim() || "Generic";
    const priceText = card.querySelector(".current-price")?.textContent || "0";
    const price = parseFloat(priceText.replace(/[^0-9.]/g, "")) || 0;
    const img = card.querySelector("img")?.src || PLACEHOLDER_SVG;

    item = {
      product_id: productId,
      name_ar: titleAr,
      name_en: titleEn,
      brand: brand,
      price: price,
      quantity: 0,
      image_url: img,
    };
  } else if (!item) {
    item = {
      product_id: productId,
      name_ar: "منتج سبينيس",
      name_en: "Spinneys Product",
      brand: "Spinneys",
      price: 50.0,
      quantity: 0,
      image_url: PLACEHOLDER_SVG,
    };
  }

  item.quantity += qty;
  state.cart[productId] = item;
  saveCart();
  showToast(i18n[state.lang].addedToCart);
};

window.changeQuantity = function(productId, delta) {
  if (!state.cart[productId]) return;
  state.cart[productId].quantity += delta;
  if (state.cart[productId].quantity <= 0) {
    delete state.cart[productId];
  }
  saveCart();
};

window.removeFromCart = function(productId) {
  delete state.cart[productId];
  saveCart();
};

function saveCart() {
  localStorage.setItem("spinneys_cart", JSON.stringify(state.cart));
  renderCart();
  syncAllProductCardButtons();
}

function renderCart() {
  const badgeCount = document.getElementById("cart-badge-count");
  const drawerCount = document.getElementById("drawer-items-count");
  const headerTotal = document.getElementById("header-cart-total");
  const stream = document.getElementById("cart-items-stream");
  const subtotalEl = document.getElementById("summary-subtotal");
  const deliveryEl = document.getElementById("summary-delivery");
  const totalEl = document.getElementById("summary-total");
  const progressText = document.getElementById("delivery-progress-text");
  const progressFill = document.getElementById("delivery-progress-fill");

  const items = Object.values(state.cart);
  const totalItems = items.reduce((sum, itm) => sum + itm.quantity, 0);
  const subtotal = items.reduce((sum, itm) => sum + (itm.price * itm.quantity), 0);
  const deliveryFee = (subtotal >= 300 || subtotal === 0) ? 0 : 20.0;
  const total = subtotal + deliveryFee;
  const curr = i18n[state.lang].currency;

  if (badgeCount) badgeCount.textContent = totalItems;
  if (drawerCount) drawerCount.textContent = totalItems;
  if (headerTotal) headerTotal.textContent = `${subtotal.toFixed(2)} ${curr}`;

  // Progress Bar for Free Delivery
  if (progressText && progressFill) {
    if (subtotal >= 300) {
      progressText.textContent = i18n[state.lang].freeDeliveryQualified;
      progressFill.style.width = "100%";
    } else {
      const remaining = 300 - subtotal;
      progressText.textContent = i18n[state.lang].freeDeliveryProgress(remaining);
      progressFill.style.width = `${Math.min(100, (subtotal / 300) * 100)}%`;
    }
  }

  // Items stream
  if (stream) {
    if (items.length === 0) {
      stream.innerHTML = `
        <div style="text-align: center; padding: 3rem 1rem; color: #94A3B8;">
          <span style="font-size: 3rem; display: block; margin-bottom: 0.5rem;">🛍️</span>
          <p style="font-weight: 700;">${state.lang === 'ar' ? 'سلة المشتريات فارغة' : 'Your cart is empty'}</p>
          <span style="font-size: 0.8rem;">${state.lang === 'ar' ? 'أضف منتجات من المتجر لتظهر هنا' : 'Add products to start shopping'}</span>
        </div>
      `;
    } else {
      stream.innerHTML = items.map(itm => `
        <div class="cart-item-row">
          <img 
            src="${itm.image_url || PLACEHOLDER_SVG}" 
            class="cart-item-img"
            onerror="this.onerror=null; this.src='${PLACEHOLDER_SVG}';"
          />
          <div class="cart-item-info">
            <h4 class="cart-item-title">${state.lang === 'ar' ? (itm.name_ar || itm.name_en) : (itm.name_en || itm.name_ar)}</h4>
            <div class="cart-item-price">${itm.price.toFixed(2)} ${curr}</div>
            <div class="cart-item-controls">
              <button class="cart-qty-btn" onclick="changeQuantity(${itm.product_id}, -1)">−</button>
              <span class="cart-qty-display">${itm.quantity}</span>
              <button class="cart-qty-btn" onclick="changeQuantity(${itm.product_id}, 1)">+</button>
              <button class="cart-item-remove-btn" onclick="removeFromCart(${itm.product_id})" title="حذف">🗑️</button>
            </div>
          </div>
        </div>
      `).join("");
    }
  }

  if (subtotalEl) subtotalEl.textContent = `${subtotal.toFixed(2)} ${curr}`;
  if (deliveryEl) deliveryEl.textContent = (deliveryFee === 0) ? (state.lang === 'ar' ? 'مجاناً' : 'FREE') : `${deliveryFee.toFixed(2)} ${curr}`;
  if (totalEl) totalEl.textContent = `${total.toFixed(2)} ${curr}`;
}

function syncAllProductCardButtons() {
  document.querySelectorAll(".product-card").forEach(card => {
    const pId = parseInt(card.dataset.productId);
    const actionBox = card.querySelector(".card-action-box");
    if (!actionBox || !pId) return;

    const inCartQty = state.cart[pId]?.quantity || 0;
    if (inCartQty > 0) {
      actionBox.innerHTML = `
        <div class="card-qty-control">
          <button class="btn-qty" onclick="changeQuantity(${pId}, -1)">−</button>
          <span class="qty-val">${inCartQty}</span>
          <button class="btn-qty" onclick="changeQuantity(${pId}, 1)">+</button>
        </div>
      `;
    } else {
      actionBox.innerHTML = `
        <button class="btn-add-cart" onclick="addProductToCart(${pId})">
          <span>+</span>
          <span>${i18n[state.lang].addToCart}</span>
        </button>
      `;
    }
  });
}

// ── Checkout Modal & Pipeline ────────────────────────────────────────────────
function openCheckoutModal() {
  const overlay = document.getElementById("checkout-modal-overlay");
  const form = document.getElementById("checkout-form");
  const receipt = document.getElementById("order-receipt-view");

  if (overlay) overlay.style.display = "flex";
  if (form) form.style.display = "block";
  if (receipt) receipt.style.display = "none";

  const items = Object.values(state.cart);
  const totalItems = items.reduce((sum, itm) => sum + itm.quantity, 0);
  const subtotal = items.reduce((sum, itm) => sum + (itm.price * itm.quantity), 0);
  const deliveryFee = (subtotal >= 300 || subtotal === 0) ? 0 : 20.0;
  const total = subtotal + deliveryFee;
  const curr = i18n[state.lang].currency;

  document.getElementById("chk-items-count").textContent = totalItems;
  document.getElementById("chk-subtotal").textContent = `${subtotal.toFixed(2)} ${curr}`;
  document.getElementById("chk-delivery").textContent = (deliveryFee === 0) ? "0.00 (مجاناً)" : `${deliveryFee.toFixed(2)} ${curr}`;
  document.getElementById("chk-total").textContent = `${total.toFixed(2)} ${curr}`;
}

async function handleCheckoutSubmit(e) {
  e.preventDefault();
  const submitBtn = document.getElementById("btn-submit-order");
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = `<span>${i18n[state.lang].processingOrder}</span>`;
  }

  const custName = document.getElementById("cust-name")?.value || "Customer";
  const custPhone = document.getElementById("cust-phone")?.value || "";
  const custAddress = document.getElementById("cust-address")?.value || "";
  const custNotes = document.getElementById("cust-notes")?.value || "";
  const payMethod = document.querySelector('input[name="payment_method"]:checked')?.value || "Cash on Delivery";

  const itemsPayload = Object.values(state.cart).map(itm => ({
    product_id: itm.product_id,
    quantity: itm.quantity,
  }));

  try {
    const res = await fetch(`${API_BASE}/api/store/checkout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        customer_name: custName,
        customer_phone: custPhone,
        delivery_address: custAddress,
        delivery_notes: custNotes,
        payment_method: payMethod,
        items: itemsPayload,
      }),
    });

    if (!res.ok) throw new Error("Checkout error " + res.status);
    const receiptData = await res.json();

    // Show Confirmation Receipt View
    document.getElementById("checkout-form").style.display = "none";
    const receiptView = document.getElementById("order-receipt-view");
    receiptView.style.display = "block";

    document.getElementById("rcpt-order-id").textContent = receiptData.order_reference;
    document.getElementById("rcpt-status").textContent = receiptData.status;
    document.getElementById("rcpt-eta").textContent = receiptData.estimated_delivery;
    document.getElementById("rcpt-payment").textContent = receiptData.payment_method;
    document.getElementById("rcpt-address").textContent = receiptData.delivery_address;
    document.getElementById("rcpt-total").textContent = `${receiptData.total_amount.toFixed(2)} ${i18n[state.lang].currency}`;

    // Clear user cart
    state.cart = {};
    saveCart();
    showToast(i18n[state.lang].orderConfirmed);
  } catch (err) {
    console.error("Checkout failed:", err);
    alert(state.lang === "ar" ? "حدث خطأ أثناء تأكيد الطلب، يرجى المحاولة مرة أخرى." : "Checkout failed. Please retry.");
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = `<span id="btn-submit-order-text">${i18n[state.lang].confirmOrderBtn}</span>`;
    }
  }
}

// ── Floating AI Assistant Multiturn Chat ──────────────────────────────────────
async function handleAiChatSubmit(e) {
  e.preventDefault();
  const input = document.getElementById("ai-message-input");
  const msg = input?.value.trim();
  if (!msg) return;

  // Append User Message Bubble
  appendChatMessage("user", msg);
  input.value = "";

  const typingIndicator = document.getElementById("chat-typing-indicator");
  if (typingIndicator) typingIndicator.style.display = "flex";
  scrollAiChatToBottom();

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.aiSessionId,
        message: msg,
      }),
    });

    if (!res.ok) throw new Error("HTTP error " + res.status);
    const data = await res.json();

    if (typingIndicator) typingIndicator.style.display = "none";

    // Update active filter chips
    state.aiActiveFilters = data.filters || {};
    updateAiFilterChips();

    // Check if Recipe Smart Cart
    if (data.intent === "recipe" && data.cart && data.cart.length > 0) {
      appendRecipeSmartCartMessage(data.dish, data.reply, data.cart);
    } else {
      appendChatMessage("assistant", data.reply, data.products);
    }

  } catch (err) {
    console.error("AI Chat failed:", err);
    if (typingIndicator) typingIndicator.style.display = "none";
    appendChatMessage("assistant", state.lang === "ar" ? "عذراً، حدث خطأ أثناء الاتصال بالنظام. يرجى المحاولة مجدداً." : "Sorry, an error occurred. Please try again.");
  }

  scrollAiChatToBottom();
}

function appendChatMessage(sender, text, products = []) {
  const stream = document.getElementById("ai-messages-stream");
  if (!stream) return;

  const msgDiv = document.createElement("div");
  msgDiv.className = `chat-msg ${sender}-msg`;

  let productsHtml = "";
  if (products && products.length > 0) {
    productsHtml = `
      <div class="chat-products-carousel">
        ${products.map(p => `
          <div class="chat-product-mini-card">
            <img 
              src="${p.image_url || PLACEHOLDER_SVG}" 
              class="chat-product-img"
              onerror="this.onerror=null; this.src='${PLACEHOLDER_SVG}';"
            />
            <div class="chat-product-title">${state.lang === 'ar' ? (p.name_ar || p.name_en) : (p.name_en || p.name_ar)}</div>
            <div class="chat-product-price">${p.price.toFixed(2)} ${i18n[state.lang].currency}</div>
            <button class="btn-chat-add-cart" onclick="addProductToCart(${p.product_id})">
              <span>+</span>
              <span>${i18n[state.lang].addToCart}</span>
            </button>
          </div>
        `).join("")}
      </div>
    `;
  }

  msgDiv.innerHTML = `
    <div class="msg-avatar">${sender === 'assistant' ? '🤖' : '👤'}</div>
    <div class="msg-bubble">
      <p>${text}</p>
      ${productsHtml}
    </div>
  `;

  stream.appendChild(msgDiv);
  scrollAiChatToBottom();
}

function appendRecipeSmartCartMessage(dishName, replyText, ingredientsCart) {
  const stream = document.getElementById("ai-messages-stream");
  if (!stream) return;

  // Flatten ingredients cart so that each item has product details
  const flattenedProducts = (ingredientsCart || []).map(item => {
    const prod = (item.products && item.products.length > 0) ? item.products[0] : item;
    return {
      ingredient: item.ingredient || prod.name_ar || prod.name_en,
      product_id: prod.product_id,
      name_ar: prod.name_ar,
      name_en: prod.name_en,
      brand: prod.brand || "Spinneys",
      price: prod.price || 0,
      image_url: prod.image_url || PLACEHOLDER_SVG,
    };
  }).filter(p => p.product_id);

  window._lastRecipeCart = flattenedProducts;

  const msgDiv = document.createElement("div");
  msgDiv.className = "chat-msg assistant-msg";

  const ingredientsListHtml = flattenedProducts.map(item => `
    <li>
      <strong>${item.ingredient}:</strong> 
      ${item.name_ar || item.name_en} (${item.price.toFixed(2)} ${i18n[state.lang].currency})
    </li>
  `).join("");

  const isAr = (state.lang === "ar");
  const bundleHeader = isAr ? `🍲 مقادير ${dishName} المتوفرة في سبينيس` : `🍲 Spinneys ingredients for ${dishName}`;
  const addAllText = isAr ? `إضافة جميع مقادير ${dishName} إلى السلة فوراً` : `Add all ${dishName} ingredients to cart`;

  msgDiv.innerHTML = `
    <div class="msg-avatar">🤖</div>
    <div class="msg-bubble">
      <p>${replyText}</p>
      <div class="recipe-bundle-box">
        <div class="recipe-bundle-header">${bundleHeader}</div>
        <ul class="recipe-ingredients-list">
          ${ingredientsListHtml}
        </ul>
        <button class="btn-add-recipe-all" onclick="addAllRecipeIngredients()">
          <span>🛒</span>
          <span>${addAllText}</span>
        </button>
      </div>
    </div>
  `;

  stream.appendChild(msgDiv);
  scrollAiChatToBottom();
}

window.addAllRecipeIngredients = function() {
  if (!window._lastRecipeCart || window._lastRecipeCart.length === 0) return;
  window._lastRecipeCart.forEach(p => {
    state.cart[p.product_id] = {
      product_id: p.product_id,
      name_ar: p.name_ar,
      name_en: p.name_en,
      brand: p.brand || "Spinneys",
      price: p.price,
      quantity: (state.cart[p.product_id]?.quantity || 0) + 1,
      image_url: p.image_url || PLACEHOLDER_SVG,
    };
  });
  saveCart();
  showToast(i18n[state.lang].allIngredientsAdded);
  // Open cart drawer
  document.getElementById("cart-drawer")?.classList.add("active");
  document.getElementById("cart-drawer-overlay")?.classList.add("active");
};

function updateAiFilterChips() {
  const bar = document.getElementById("ai-filters-bar");
  const container = document.getElementById("ai-chips-container");
  if (!bar || !container) return;

  const f = state.aiActiveFilters;
  const chips = [];
  const isAr = (state.lang === "ar");

  if (f.brand) chips.push({ label: isAr ? `الماركة: ${f.brand}` : `Brand: ${f.brand}`, action: isAr ? "الغاء الماركة" : "remove brand" });
  if (f.max_price) chips.push({ label: isAr ? `أقل من ${f.max_price} ج.م` : `Under ${f.max_price} EGP`, action: isAr ? "الغاء حد السعر" : "remove max price" });
  if (f.in_stock) chips.push({ label: isAr ? `المتوفر فقط` : `In-Stock Only`, action: isAr ? "كل المنتجات" : "all products" });
  if (f.sort) chips.push({ label: isAr ? `الترتيب: ${f.sort}` : `Sort: ${f.sort}`, action: isAr ? "ترتيب افتراضي" : "default sort" });

  if (chips.length === 0) {
    bar.style.display = "none";
    container.innerHTML = "";
  } else {
    bar.style.display = "flex";
    container.innerHTML = chips.map((c, i) => `
      <span class="ai-chip">
        ${c.label}
        <span class="ai-chip-remove" onclick="removeAiFilter('${c.action}')">✕</span>
      </span>
    `).join("");
  }
}

window.removeAiFilter = function(actionCommand) {
  const input = document.getElementById("ai-message-input");
  if (input) {
    input.value = actionCommand;
    document.getElementById("ai-chat-form")?.dispatchEvent(new Event("submit"));
  }
};

function scrollAiChatToBottom() {
  const stream = document.getElementById("ai-messages-stream");
  if (stream) {
    stream.scrollTop = stream.scrollHeight;
  }
}

// ── Toast Notification System ────────────────────────────────────────────────
function showToast(message) {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = "toast";
  toast.innerHTML = `<span>✓</span> <span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.transition = "opacity 0.3s ease";
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 300);
  }, 2600);
}
