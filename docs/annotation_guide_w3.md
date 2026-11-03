# Spinneys Conversational Shopping Assistant — Annotation Guide (Week 3)
**Document Version:** 1.0  
**Target:** NLU Intent Classification & Filter Parsing Evaluation  
**Author:** Principal Conversational AI Engineer & NLU Architect  

---

## 1. Overview & Objective
This guide sets the deterministic standards for annotating customer queries for the Spinneys Conversational Shopping Assistant NLU layer. All benchmark datasets (including `data/test_sets/golden_queries_w3.json`) must strictly adhere to these rules to ensure consistent evaluation and reproducibility.

---

## 2. Intent Taxonomy (The 8 Official Intents)

Every customer query must be classified into exactly **one** of the following 8 official intents:

| Intent | Definition | Typical User Goal | Example Queries |
|---|---|---|---|
| `search` | Initial product exploration or new query introducing item keywords. | Find products matching name, brand, or attributes. | *"عايز جبنة بيضا"*, *"show me olive oil"*, *"3ayez laban"* |
| `refine` | Adding or altering constraints on an ongoing search without starting a new query. | Constrain price, brand, stock, or remove a previous filter. | *"تحت 60 جنيه"*, *"only Almarai"*, *"اي براند"*, *"bas al motawafer"* |
| `sort` | Explicitly ordering results by price or popularity without introducing a new search keyword. | Reorder existing result list. | *"رتب من الارخص"*, *"sort by price low to high"*, *"rateb bel se3r"* |
| `recommend` | Seeking advice, meal ideas, or qualitative recommendations. | Get recommendations, suggestions, or inspiration. | *"اقترح عليا فطار صحي"*, *"what do you recommend for dinner"*, *"rashahli zayt"* |
| `compare` | Comparing two distinct items, brands, or variants. | Understand trade-offs between two options. | *"ايه الفرق بين جهينة والمراعي"*, *"compare domty vs president"*, *"2aren ben coke w pepsi"* |
| `alternatives` | Asking for replacements or substitutes for an item. | Find an alternative to an unavailable or undesirable product. | *"بديل لجبنة فيتا"*, *"substitute for whole milk"*, *"badeel le laban"* |
| `cross-sell` | Requesting complementary products that pair with an item. | Complete a recipe or meal combination. | *"ايه ينفع مع الشاي ده"*, *"what goes well with pasta"*, *"eh yemshy ma3 el gebna"* |
| `out-of-scope` | Inquiries unrelated to grocery shopping, products, or store services. | General knowledge, chitchat, weather, outside bookings. | *"الجو عامل ايه النهاردة"*, *"book me a taxi"*, *"el match sa3a kam"* |

### Disambiguation Rules:
- If a query has both a product keyword AND a filter (e.g. *"عايز لبن المراعي تحت 50"*), the intent is **`search`** (with filters extracted), because it introduces an exploration keyword.
- If a query contains ONLY constraint adjustments without a product keyword (e.g. *"تحت 50 جنيه"*, *"only Almarai"*, *"المتوفر بس"*), the intent is **`refine`**.
- If a query says *"رتب من الارخص"* without a product, intent is **`sort`**. If it says *"عايز ارخص لبن"*, intent is **`search`** with `sort="price_asc"`.

---

## 3. Follow-Up Type Taxonomy

Every query is assigned a `follow_up_type` reflecting conversational context:

1. `new_topic`: The user begins a fresh search or autonomous exploration (default for standalone queries and `search`, `recommend`, `compare`, `alternatives`, `out-of-scope`).
2. `refinement`: The user narrows, widens, or sorts an ongoing search session (e.g., adding a price ceiling, specifying a brand, changing sort order).
3. `cancellation`: The user explicitly clears, removes, or relaxes a previous constraint (e.g., *"اي ماركة"*, *"any brand"*, *"all brands"*, *"شيل الفلتر"*).
4. `reference`: The user refers back to a specific item from a previous turn (e.g., *"اول واحد"*, *"الارخص فيهم"*, *"the first one"*, *"what is the price of the second item"*).

---

## 4. Canonical Filter Schema & Field Rules

All extracted filters must strictly map to existing Spinneys database catalog attributes:

### 4.1 `query` (str or null)
- The core product keyword or phrase after stripping conversational fillers (*"عايز"*, *"show me"*, *"please"*), price clauses, brand tokens, and sort directives.
- Null if the query is a pure filter refinement (e.g., *"تحت 50 جنيه"* -> `query: null`).

### 4.2 `brand` (str or null)
- **Strict Rule:** Must ONLY contain an official, normalized clean brand name if explicitly requested by the customer (e.g., *"Almarai"*, *"Juhayna"*, *"Domty"*, *"Spinneys"*).
- If no brand is specified, or if the brand was cancelled (*"any brand"*), it **MUST** be `null`. Never guess or hallucinate a brand.

### 4.3 `category` (str or null)
- Canonical English category name from the Spinneys taxonomy (e.g., *"Cheese, Dairy & Eggs"*, *"Beverages"*). Null if not deterministically mentioned.

### 4.4 `price_min` & `price_max` (float or null)
- Numeric price boundaries in Egyptian Pounds (EGP).
- *"تحت 50 جنيه"* / *"under 50"* -> `price_max: 50.0`, `price_min: null`
- *"اكتر من 100"* / *"over 100"* -> `price_min: 100.0`, `price_max: null`
- *"بين 20 و 50"* / *"between 20 and 50"* -> `price_min: 20.0`, `price_max: 50.0`

### 4.5 `in_stock` (bool or null)
- `true` if user explicitly requests available products (*"متوفر"*, *"in stock"*, *"available"*).
- `false` if explicitly asking for out-of-stock items.
- `null` if stock was not explicitly mentioned.

### 4.6 `sort` (str or null)
- `"price_asc"` for ascending price (*"الارخص"*, *"lowest price"*, *"cheapest"*).
- `"price_desc"` for descending price (*"الاغلى"*, *"highest price"*).
- `null` if no sort requested.

### 4.7 `explicit_fields` (list[str])
- List of field names that were explicitly stated in the user prompt (e.g. `["query", "brand", "price_max"]`).
- When a filter is cancelled (e.g. *"اي براند"*), `"brand"` is included in `explicit_fields` because the user explicitly modified it.

### 4.8 `unsupported_filters` (list[str])
- Identifies customer criteria that **do not exist** as discrete DB columns in the current schema.
- **Strict Policy Rule:** Never hallucinate or force unsupported criteria into `category`, `brand`, or `query`. They must be isolated into `unsupported_filters`.
- Common examples:
  - Dietary: `"sugar-free"`, `"gluten-free"`, `"organic"`, `"vegan"`, `"lactose-free"`, `"diet"`
  - Sourcing/Quality: `"imported"`, `"local"`

---

## 5. Language Tagging Standards
- `EN`: Query written entirely in English.
- `AR`: Query written in standard or Egyptian vernacular Arabic script.
- `MIXED`: Franco-Arabic (Arabizi, e.g. *"3ayez laban"*, *"feen el cheese"*) or English query mixed with Arabic words (e.g. *"olive oil تحت 100"*).
