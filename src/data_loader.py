"""
High-performance cached Data Loader and ETL engine for:
1. Maven Market Retail Analytics
2. HR Employee Workforce & Attrition Case Study
"""

import os
import pandas as pd
import numpy as np
import streamlit as st

# Store Geographic Coordinates (North America Store Network)
STORE_COORDINATES = {
    "Acapulco": {"lat": 16.8531, "lon": -99.8237},
    "Bellingham": {"lat": 48.7519, "lon": -122.4787},
    "Bremerton": {"lat": 47.5653, "lon": -122.6270},
    "Camacho": {"lat": 24.7167, "lon": -102.2833},
    "Guadalajara": {"lat": 20.6597, "lon": -103.3496},
    "Beverly Hills": {"lat": 34.0736, "lon": -118.4004},
    "Los Angeles": {"lat": 34.0522, "lon": -118.2437},
    "Merida": {"lat": 20.9674, "lon": -89.5926},
    "Mexico City": {"lat": 19.4326, "lon": -99.1332},
    "Orizaba": {"lat": 18.8497, "lon": -97.1037},
    "Portland": {"lat": 45.5152, "lon": -122.6784},
    "Hidalgo": {"lat": 22.7709, "lon": -102.5832},
    "Salem": {"lat": 44.9429, "lon": -123.0351},
    "San Francisco": {"lat": 37.7749, "lon": -122.4194},
    "Seattle": {"lat": 47.6062, "lon": -122.3321},
    "Spokane": {"lat": 47.6588, "lon": -117.4260},
    "Tacoma": {"lat": 47.2529, "lon": -122.4443},
    "Vancouver": {"lat": 49.2827, "lon": -123.1207},
    "Victoria": {"lat": 48.4284, "lon": -123.3656},
    "San Andres": {"lat": 19.3333, "lon": -99.1167},
    "Walla Walla": {"lat": 46.0646, "lon": -118.3430},
    "Yakima": {"lat": 46.6021, "lon": -120.5059},
    "San Diego": {"lat": 32.7157, "lon": -117.1611},
}


def _resolve_path(primary: str, fallback: str) -> str:
    """Return primary path if exists, otherwise fallback."""
    if os.path.exists(primary):
        return primary
    if os.path.exists(fallback):
        return fallback
    raise FileNotFoundError(f"File not found in {primary} or {fallback}")


@st.cache_data(show_spinner="Loading Maven Market Data...", ttl=3600)
def load_retail_data():
    """
    Load, concatenate, clean and merge Maven Market retail data:
    Transactions 1997 + 1998, Products, Stores, Customers, Returns, Regions, Calendar.
    """
    local_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "maven_market")
    ext_dir = r"D:\Mohamed\Matirial\POWE PI"

    # Transactions 1997
    tx97_path = _resolve_path(
        os.path.join(local_dir, "MavenMarket_Transactions_1997.csv"),
        os.path.join(ext_dir, "Combine", "MavenMarket_Transactions_1997.csv")
    )
    # Transactions 1998
    tx98_path = _resolve_path(
        os.path.join(local_dir, "MavenMarket_Transactions_1998.csv"),
        os.path.join(ext_dir, "Combine", "MavenMarket_Transactions_1998.csv")
    )
    # Returns
    returns_path = _resolve_path(
        os.path.join(local_dir, "MavenMarket_Returns_1997-1998.csv"),
        os.path.join(ext_dir, "MavenMarket_Returns_1997-1998.csv")
    )
    # Products
    products_path = _resolve_path(
        os.path.join(local_dir, "MavenMarket_Products.csv"),
        os.path.join(ext_dir, "MavenMarket_Products.csv")
    )
    # Stores
    stores_path = _resolve_path(
        os.path.join(local_dir, "MavenMarket_Stores.csv"),
        os.path.join(ext_dir, "MavenMarket_Stores.csv")
    )
    # Customers
    customers_path = _resolve_path(
        os.path.join(local_dir, "MavenMarket_Customers.csv"),
        os.path.join(ext_dir, "MavenMarket_Customers.csv")
    )
    # Regions
    regions_path = _resolve_path(
        os.path.join(local_dir, "MavenMarket_Regions (1).csv"),
        os.path.join(ext_dir, "MavenMarket_Regions (1).csv")
    )

    # 1. Load transactions
    df_97 = pd.read_csv(tx97_path)
    df_98 = pd.read_csv(tx98_path)
    transactions = pd.concat([df_97, df_98], ignore_index=True)
    transactions["transaction_date"] = pd.to_datetime(transactions["transaction_date"], errors="coerce")
    transactions["year"] = transactions["transaction_date"].dt.year
    transactions["year_month"] = transactions["transaction_date"].dt.to_period("M").astype(str)
    transactions["year_quarter"] = transactions["transaction_date"].dt.to_period("Q").astype(str)

    # 2. Load and enrich products
    products = pd.read_csv(products_path)
    products["recyclable_label"] = products["recyclable"].apply(lambda x: "Recyclable" if x == 1.0 else "Non-Recyclable")
    products["low_fat_label"] = products["low_fat"].apply(lambda x: "Low Fat" if x == 1.0 else "Regular")
    
    # 3. Load and enrich stores
    stores = pd.read_csv(stores_path)
    stores["first_opened_date"] = pd.to_datetime(stores["first_opened_date"], errors="coerce")
    stores["last_remodel_date"] = pd.to_datetime(stores["last_remodel_date"], errors="coerce")
    stores["store_age_years"] = (1998 - stores["first_opened_date"].dt.year).clip(lower=0)
    stores["lat"] = stores["store_city"].map(lambda c: STORE_COORDINATES.get(c, {}).get("lat", 38.0))
    stores["lon"] = stores["store_city"].map(lambda c: STORE_COORDINATES.get(c, {}).get("lon", -97.0))

    # 4. Load regions & merge into stores
    regions = pd.read_csv(regions_path)
    stores = stores.merge(regions, on="region_id", how="left")

    # 5. Load and clean customers
    customers = pd.read_csv(customers_path)
    customers["full_name"] = customers["first_name"].fillna("") + " " + customers["last_name"].fillna("")
    customers["full_name"] = customers["full_name"].str.strip()

    # 6. Load returns
    returns = pd.read_csv(returns_path)
    returns["return_date"] = pd.to_datetime(returns["return_date"], errors="coerce")
    returns["year_month"] = returns["return_date"].dt.to_period("M").astype(str)
    returns = returns.merge(products[["product_id", "product_brand", "product_name", "product_retail_price", "product_cost"]], on="product_id", how="left")
    returns = returns.merge(stores[["store_id", "store_name", "store_country", "store_city", "sales_region", "sales_district"]], on="store_id", how="left")
    returns["return_value"] = returns["quantity"] * returns["product_retail_price"]

    # 7. Core Transaction Merges
    merged_tx = transactions.merge(
        products[["product_id", "product_brand", "product_name", "product_retail_price", "product_cost", "recyclable_label", "low_fat_label"]],
        on="product_id",
        how="left"
    )
    merged_tx = merged_tx.merge(
        stores[["store_id", "store_name", "store_type", "store_city", "store_state", "store_country", "sales_region", "sales_district", "total_sqft", "grocery_sqft", "store_age_years", "lat", "lon"]],
        on="store_id",
        how="left"
    )
    merged_tx = merged_tx.merge(
        customers[["customer_id", "full_name", "yearly_income", "gender", "education", "member_card", "occupation", "customer_city", "customer_country"]],
        on="customer_id",
        how="left"
    )

    # 8. Financial KPIs Calculation
    merged_tx["revenue"] = merged_tx["quantity"] * merged_tx["product_retail_price"]
    merged_tx["cost"] = merged_tx["quantity"] * merged_tx["product_cost"]
    merged_tx["profit"] = merged_tx["revenue"] - merged_tx["cost"]
    # Order identification (each unique customer visit to a store on a day)
    merged_tx["order_id"] = merged_tx["customer_id"].astype(str) + "_" + merged_tx["store_id"].astype(str) + "_" + merged_tx["transaction_date"].dt.strftime("%Y%m%d")

    return {
        "transactions": merged_tx,
        "returns": returns,
        "products": products,
        "stores": stores,
        "customers": customers,
        "regions": regions
    }


@st.cache_data(show_spinner="Loading HR Workforce Analytics Data...", ttl=3600)
def load_hr_data():
    """
    Load and preprocess the HR Attrition Case Study dataset.
    """
    local_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "hr_workforce", "HR Attrition Case Study.xlsx")
    ext_path = r"D:\Mohamed\Matirial\POWE PI\HR Attrition Case Study.xlsx"
    path = _resolve_path(local_path, ext_path)

    df = pd.read_excel(path, sheet_name="HR-Employee")

    # Clean & Derived Columns
    df["Attrition_Num"] = (df["Attrition"].str.strip().str.lower() == "yes").astype(int)
    
    # Distance Buckets
    bins_dist = [0, 5, 10, 20, 100]
    labels_dist = ["0-5 km", "6-10 km", "11-20 km", "20+ km"]
    df["Distance_Bucket"] = pd.cut(df["DistanceFromHome"], bins=bins_dist, labels=labels_dist, right=True)

    # Age Buckets
    bins_age = [17, 25, 35, 45, 55, 100]
    labels_age = ["<25", "25-34", "35-44", "45-54", "55+"]
    df["Age_Group"] = pd.cut(df["Age"], bins=bins_age, labels=labels_age, right=False)

    # Tenure Buckets
    bins_tenure = [-1, 2, 5, 10, 100]
    labels_tenure = ["0-2 yrs", "3-5 yrs", "6-10 yrs", "10+ yrs"]
    df["Tenure_Group"] = pd.cut(df["YearsAtCompany"], bins=bins_tenure, labels=labels_tenure)

    # Satisfaction Score Descriptors
    sat_map = {1: "1 - Low", 2: "2 - Medium", 3: "3 - High", 4: "4 - Very High"}
    df["JobSat_Label"] = df["JobSatisfaction"].map(sat_map)
    df["EnvSat_Label"] = df["EnvironmentSatisfaction"].map(sat_map)
    df["WLB_Label"] = df["WorkLifeBalance"].map({1: "1 - Bad", 2: "2 - Good", 3: "3 - Better", 4: "4 - Best"})
    df["RelSat_Label"] = df["RelationshipSatisfaction"].map(sat_map)

    # Multi-Factor Attrition Risk Scoring (0 to 100 Index for Intervention)
    # Higher score = higher flight risk
    risk_score = (
        (df["OverTime"] == "Yes").astype(int) * 30 +
        (df["JobSatisfaction"] <= 2).astype(int) * 20 +
        (df["EnvironmentSatisfaction"] <= 2).astype(int) * 15 +
        (df["WorkLifeBalance"] <= 2).astype(int) * 15 +
        (df["DistanceFromHome"] >= 15).astype(int) * 10 +
        (df["YearsSinceLastPromotion"] >= 4).astype(int) * 10
    )
    df["Risk_Score"] = risk_score
    df["Risk_Level"] = pd.cut(
        df["Risk_Score"],
        bins=[-1, 25, 50, 75, 100],
        labels=["Low Risk", "Moderate Risk", "Elevated Risk", "Critical Flight Risk"]
    )

    return df
