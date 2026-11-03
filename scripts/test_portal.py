"""
Unit testing script to execute each view function in head-less mode.
"""
import sys
import os
import pandas as pd

# Mock streamlit functions that render charts or HTML
import streamlit as st

sys.path.append(".")
from src.data_loader import load_retail_data, load_hr_data
from src.retail_views import (
    render_executive_overview,
    render_products_profitability,
    render_customer_demographics,
    render_store_operations,
    render_returns_loss_prevention
)
from src.hr_views import (
    render_workforce_summary,
    render_retention_risk_factors,
    render_employee_experience
)

print("--- Testing Retail Data Loading ---")
retail = load_retail_data()
tx = retail["transactions"]
ret = retail["returns"]
stores = retail["stores"]
products = retail["products"]
customers = retail["customers"]

print(f"Loaded {len(tx)} tx rows, {len(ret)} return rows.")

print("--- Testing Retail Page 1.1 ---")
render_executive_overview(tx.head(1000), ret.head(100), stores)

print("--- Testing Retail Page 1.2 ---")
render_products_profitability(tx.head(1000), products)

print("--- Testing Retail Page 1.3 ---")
render_customer_demographics(tx.head(1000), customers, ret.head(100))

print("--- Testing Retail Page 1.4 ---")
render_store_operations(tx.head(1000), stores)

print("--- Testing Retail Page 1.5 ---")
render_returns_loss_prevention(tx.head(1000), ret.head(100))

print("--- Testing HR Data Loading ---")
hr = load_hr_data()
print(f"Loaded {len(hr)} HR rows.")

print("--- Testing HR Page 2.1 ---")
render_workforce_summary(hr)

print("--- Testing HR Page 2.2 ---")
render_retention_risk_factors(hr)

print("--- Testing HR Page 2.3 ---")
render_employee_experience(hr)

print("ALL VIEWS EXECUTED WITHOUT ANY ERRORS! SUCCESS!")
