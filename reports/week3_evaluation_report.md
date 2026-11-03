# Week 3 Evaluation Report: Spinneys NLU & Filter Parsing Engine
**Generated:** 2026-10-19 12:36:01  
**Total Benchmark Queries:** 66 (EN: 22, AR: 22, MIXED: 22)  

---

## 1. Executive Summary & KPI Target Verification

| Metric | Target | Measured Score | Status |
|---|---|---|---|
| **Overall Intent Macro F1** | ≥ 90% | **100.0%** | `PASSED` |
| **Entity (Brand) Accuracy** | ≥ 85% | **100.0%** | `PASSED` |
| **Filter Extraction Accuracy** | ≥ 85% | **100.0%** | `PASSED` |
| **Language Disparity (|AR - EN|)** | ≤ 10.0% | **0.0%** | `PASSED` |
| **Follow-up Type Accuracy** | ≥ 80.0% | **100.0%** | `PASSED` |

---

## 2. Language Breakdown

| Language | Queries Count | Intent Macro F1 | Intent Accuracy | Status |
|---|---|---|---|---|
| **EN** | 22 | 100.0% | 100.0% | `OK` |
| **AR** | 22 | 100.0% | 100.0% | `OK` |
| **MIXED** | 22 | 100.0% | 100.0% | `OK` |

> **Arabic-English Disparity:** Measured disparity is `0.0%` (Threshold: `≤ 10.0%`). Check `PASSED`.

---

## 3. Per-Intent Classification Performance

| Intent Class | Precision | Recall | F1 Score | Support |
|---|---|---|---|---|
| `alternatives` | 100.0% | 100.0% | **100.0%** | 3 |
| `compare` | 100.0% | 100.0% | **100.0%** | 4 |
| `cross-sell` | 100.0% | 100.0% | **100.0%** | 3 |
| `out-of-scope` | 100.0% | 100.0% | **100.0%** | 5 |
| `recommend` | 100.0% | 100.0% | **100.0%** | 5 |
| `refine` | 100.0% | 100.0% | **100.0%** | 18 |
| `search` | 100.0% | 100.0% | **100.0%** | 19 |
| `sort` | 100.0% | 100.0% | **100.0%** | 9 |

---

## 4. Entity & Filter Extraction Performance

| Field / Capability | Precision | Recall | F1 / Accuracy | Notes |
|---|---|---|---|---|
| **Brand Name Extraction** | 100.0% | 100.0% | 100.0% (Acc: 100.0%) | Normalized via `app.core.normalizer` |
| **Structured Filters (Price, Stock, Sort)** | — | — | **100.0%** | Multi-attribute compound accuracy |
| **Unsupported Filters Isolation** | — | — | `100.0%` | Isolated from canonical columns |

---

## 5. System Latency & Resource Consumption

- **Mean Latency:** `2.15 ms` per query
- **P95 Latency:** `2.99 ms`
- **Avg Prompt Tokens:** `0.0` tokens
- **Avg Completion Tokens:** `0.0` tokens

---

## 6. Failure Analysis & Diagnostics

✅ **Zero failures observed across all 66 test queries.** All intents, brands, and filters matched expected canonical ground-truth exactly.