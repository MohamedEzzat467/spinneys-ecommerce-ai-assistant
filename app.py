"""
Enterprise Analytics Portal
Integrated Master BI Application for:
1. Maven Market Retail Analytics
2. HR Employee Analytics & Attrition Case Study

Author: Principal BI Architect & Senior Full-Stack Data Applications Developer
"""

import streamlit as st
import pandas as pd
import datetime

# Must be the very first Streamlit command
st.set_page_config(
    page_title="Enterprise Analytics Portal | Maven Market & HR Intelligence",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded"
)

from src.styles import get_custom_css, RETAIL_PRIMARY, HR_PRIMARY
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


def main():
    # --- SIDEBAR TOP HEADER ---
    st.sidebar.markdown(
        """
        <div style="padding: 0.5rem 0.2rem 1rem 0.2rem; border-bottom: 1px solid rgba(255,255,255,0.08); margin-bottom: 1rem;">
            <div style="font-size: 1.25rem; font-weight: 800; color: #FFFFFF; letter-spacing: -0.02em;">
                🌐 ENTERPRISE BI
            </div>
            <div style="font-size: 0.78rem; color: #9CA3AF; margin-top: 2px;">
                Master Analytics & Intelligence Portal
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # --- TOP-LEVEL MODULE SWITCHER ---
    module_choice = st.sidebar.radio(
        "SELECT DOMAIN MODULE",
        [
            "🛒 Retail & Commerce (Maven Market)",
            "👥 People & HR Analytics (Attrition Study)"
        ],
        index=0,
        key="active_module_choice"
    )

    is_retail = "Retail" in module_choice
    active_theme = "retail" if is_retail else "hr"

    # Inject Custom CSS Theme
    st.markdown(get_custom_css(active_theme), unsafe_allow_html=True)

    st.sidebar.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # MODULE 1: RETAIL & COMMERCE (MAVEN MARKET)
    # =========================================================================
    if is_retail:
        # Load Data
        with st.spinner("Initializing Maven Market Data Engine..."):
            retail_data = load_retail_data()
        
        tx_all = retail_data["transactions"]
        ret_all = retail_data["returns"]
        stores_all = retail_data["stores"]
        products_all = retail_data["products"]
        customers_all = retail_data["customers"]

        # Page Navigation
        st.sidebar.markdown(
            """
            <div style="font-size: 0.75rem; font-weight: 700; color: #10B981; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem;">
                Retail Views & Dashboards
            </div>
            """,
            unsafe_allow_html=True
        )
        retail_page = st.sidebar.radio(
            "Navigate to:",
            [
                "📊 Page 1.1: Executive 360° Overview",
                "🏷️ Page 1.2: Products & Category Profitability",
                "👥 Page 1.3: Customer Demographics & VIPs",
                "🏬 Page 1.4: Store Operations & Space Efficiency",
                "🛡️ Page 1.5: Returns & Loss Prevention"
            ],
            index=0,
            key="retail_page_nav"
        )

        st.sidebar.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        st.sidebar.markdown(
            """
            <div style="font-size: 0.75rem; font-weight: 700; color: #9CA3AF; text-transform: uppercase; letter-spacing: 0.05em; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 0.8rem; margin-bottom: 0.4rem;">
                Global Retail Filters
            </div>
            """,
            unsafe_allow_html=True
        )

        # 1. Date Range Filter
        min_date = tx_all["transaction_date"].min().date()
        max_date = tx_all["transaction_date"].max().date()

        date_selection = st.sidebar.date_input(
            "📅 Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            key="retail_date_filter"
        )
        if isinstance(date_selection, (tuple, list)) and len(date_selection) == 2:
            start_date, end_date = date_selection
        else:
            start_date, end_date = min_date, max_date

        # 2. Country & Store Filter
        countries_available = sorted(stores_all["store_country"].unique().tolist())
        selected_countries = st.sidebar.multiselect(
            "🌐 Country",
            options=countries_available,
            default=countries_available,
            key="retail_country_filter"
        )

        filtered_store_names = sorted(stores_all[stores_all["store_country"].isin(selected_countries)]["store_name"].unique().tolist())
        selected_stores = st.sidebar.multiselect(
            "🏬 Stores",
            options=filtered_store_names,
            default=[],
            placeholder="All Stores in selected countries",
            key="retail_store_filter"
        )

        # 3. Product Brand Filter
        brands_available = sorted(products_all["product_brand"].dropna().unique().tolist())
        selected_brands = st.sidebar.multiselect(
            "🏷️ Product Brand",
            options=brands_available,
            default=[],
            placeholder="All Brands (111)",
            key="retail_brand_filter"
        )

        # 4. Customer Demographics Filters
        with st.sidebar.expander("👤 Customer Demographics Filters", expanded=False):
            income_tiers = [
                "$10K - $30K", "$30K - $50K", "$50K - $70K", "$70K - $90K",
                "$90K - $110K", "$110K - $130K", "$130K - $150K", "$150K +"
            ]
            selected_incomes = st.multiselect("Income Bracket", options=income_tiers, default=[], placeholder="All Income Brackets", key="ret_filter_inc")
            
            edu_tiers = ["Partial High School", "High School Degree", "Partial College", "Bachelors Degree", "Graduate Degree"]
            selected_edus = st.multiselect("Education", options=edu_tiers, default=[], placeholder="All Education Levels", key="ret_filter_edu")

            member_tiers = ["Bronze", "Normal", "Silver", "Golden"]
            selected_cards = st.multiselect("Loyalty Tier", options=member_tiers, default=[], placeholder="All Loyalty Tiers", key="ret_filter_card")

            gender_choice = st.selectbox("Customer Gender", ["All", "F", "M"], index=0, key="ret_filter_gender")

        # --- APPLY FILTERS TO TRANSACTIONS & RETURNS ---
        tx_mask = (
            (tx_all["transaction_date"].dt.date >= start_date) &
            (tx_all["transaction_date"].dt.date <= end_date) &
            (tx_all["store_country"].isin(selected_countries))
        )
        if selected_stores:
            tx_mask &= tx_all["store_name"].isin(selected_stores)
        if selected_brands:
            tx_mask &= tx_all["product_brand"].isin(selected_brands)
        if selected_incomes:
            tx_mask &= tx_all["yearly_income"].isin(selected_incomes)
        if selected_edus:
            tx_mask &= tx_all["education"].isin(selected_edus)
        if selected_cards:
            tx_mask &= tx_all["member_card"].isin(selected_cards)
        if gender_choice != "All":
            tx_mask &= (tx_all["gender"] == gender_choice)

        tx_filtered = tx_all[tx_mask]

        # Returns Filter
        ret_mask = (
            (ret_all["return_date"].dt.date >= start_date) &
            (ret_all["return_date"].dt.date <= end_date) &
            (ret_all["store_country"].isin(selected_countries))
        )
        if selected_stores:
            ret_mask &= ret_all["store_name"].isin(selected_stores)
        if selected_brands:
            ret_mask &= ret_all["product_brand"].isin(selected_brands)
        ret_filtered = ret_all[ret_mask]

        # Filter Stats in Sidebar
        st.sidebar.markdown(
            f"""
            <div style="font-size: 0.75rem; color: #9CA3AF; padding: 0.5rem 0.2rem; background: rgba(255,255,255,0.03); border-radius: 6px; margin-top: 1rem;">
                ⚡ <b>Matched Sales Rows:</b> {len(tx_filtered):,} / {len(tx_all):,}<br>
                🔄 <b>Matched Returns:</b> {len(ret_filtered):,} / {len(ret_all):,}
            </div>
            """,
            unsafe_allow_html=True
        )

        # --- PORTAL HEADER BANNER ---
        st.markdown(
            f"""
            <div class="portal-header">
                <div>
                    <div class="portal-title">
                        <span>🛒</span> Maven Market Retail Intelligence Portal
                    </div>
                    <div class="portal-subtitle">
                        Multi-Store Omni-Channel Analytics across USA, Mexico & Canada | Active Range: {start_date} to {end_date}
                    </div>
                </div>
                <div class="portal-badge">
                    COMMERCE ENGINE ACTIVE
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # Route Pages
        if "1.1" in retail_page:
            render_executive_overview(tx_filtered, ret_filtered, stores_all)
        elif "1.2" in retail_page:
            render_products_profitability(tx_filtered, products_all)
        elif "1.3" in retail_page:
            render_customer_demographics(tx_filtered, customers_all, ret_filtered)
        elif "1.4" in retail_page:
            render_store_operations(tx_filtered, stores_all)
        elif "1.5" in retail_page:
            render_returns_loss_prevention(tx_filtered, ret_filtered)

    # =========================================================================
    # MODULE 2: HR ATTRITION & WORKFORCE INTELLIGENCE
    # =========================================================================
    else:
        # Load HR Data
        with st.spinner("Initializing People & HR Analytics Engine..."):
            hr_df = load_hr_data()

        # Page Navigation
        st.sidebar.markdown(
            """
            <div style="font-size: 0.75rem; font-weight: 700; color: #6366F1; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem;">
                People Analytics Views
            </div>
            """,
            unsafe_allow_html=True
        )
        hr_page = st.sidebar.radio(
            "Navigate to:",
            [
                "👥 Page 2.1: Workforce Executive Summary",
                "🔍 Page 2.2: Retention & Risk Factors",
                "🧠 Page 2.3: Employee Experience & Sentiment"
            ],
            index=0,
            key="hr_page_nav"
        )

        st.sidebar.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        st.sidebar.markdown(
            """
            <div style="font-size: 0.75rem; font-weight: 700; color: #9CA3AF; text-transform: uppercase; letter-spacing: 0.05em; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 0.8rem; margin-bottom: 0.4rem;">
                Global HR Workforce Filters
            </div>
            """,
            unsafe_allow_html=True
        )

        # 1. Department Filter
        dept_options = sorted(hr_df["Department"].unique().tolist())
        selected_depts = st.sidebar.multiselect(
            "🏢 Department",
            options=dept_options,
            default=dept_options,
            key="hr_dept_filter"
        )

        # 2. Job Role Filter
        roles_available = sorted(hr_df[hr_df["Department"].isin(selected_depts)]["JobRole"].unique().tolist())
        selected_roles = st.sidebar.multiselect(
            "👔 Job Role",
            options=roles_available,
            default=[],
            placeholder="All Job Roles",
            key="hr_role_filter"
        )

        # 3. Gender Filter
        gender_options = ["All", "Female", "Male"]
        selected_gender = st.sidebar.selectbox("🚻 Gender", gender_options, index=0, key="hr_gender_filter")

        # 4. Education Field Filter
        edu_fields = sorted(hr_df["EducationField"].unique().tolist())
        selected_edu_fields = st.sidebar.multiselect(
            "🎓 Education Field",
            options=edu_fields,
            default=[],
            placeholder="All Education Fields",
            key="hr_edu_filter"
        )

        # 5. OverTime Filter
        overtime_choice = st.sidebar.selectbox("⏰ OverTime", ["All", "Yes", "No"], index=0, key="hr_ot_filter")

        # 6. Age Range Slider
        min_age, max_age = int(hr_df["Age"].min()), int(hr_df["Age"].max())
        selected_age_range = st.sidebar.slider(
            "🎂 Age Range",
            min_value=min_age,
            max_value=max_age,
            value=(min_age, max_age),
            key="hr_age_filter"
        )

        # --- APPLY FILTERS TO HR DATAFRAME ---
        hr_mask = (
            (hr_df["Department"].isin(selected_depts)) &
            (hr_df["Age"] >= selected_age_range[0]) &
            (hr_df["Age"] <= selected_age_range[1])
        )
        if selected_roles:
            hr_mask &= hr_df["JobRole"].isin(selected_roles)
        if selected_gender != "All":
            hr_mask &= (hr_df["Gender"] == selected_gender)
        if selected_edu_fields:
            hr_mask &= hr_df["EducationField"].isin(selected_edu_fields)
        if overtime_choice != "All":
            hr_mask &= (hr_df["OverTime"] == overtime_choice)

        hr_filtered = hr_df[hr_mask]

        # Filter Stats in Sidebar
        st.sidebar.markdown(
            f"""
            <div style="font-size: 0.75rem; color: #9CA3AF; padding: 0.5rem 0.2rem; background: rgba(255,255,255,0.03); border-radius: 6px; margin-top: 1rem;">
                ⚡ <b>Matched Employees:</b> {len(hr_filtered):,} / {len(hr_df):,}<br>
                🚪 <b>Departures in Cohort:</b> {int(hr_filtered['Attrition_Num'].sum()):,}
            </div>
            """,
            unsafe_allow_html=True
        )

        # --- PORTAL HEADER BANNER ---
        st.markdown(
            """
            <div class="portal-header">
                <div>
                    <div class="portal-title">
                        <span>👥</span> People & HR Workforce Analytics Portal
                    </div>
                    <div class="portal-subtitle">
                        Predictive Attrition Modeling, Retention Drivers & Employee Sentiment Diagnostic
                    </div>
                </div>
                <div class="portal-badge" style="background: rgba(99, 102, 241, 0.25); color: #818CF8; border-color: #6366F1;">
                    HR INTELLIGENCE ACTIVE
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # Route Pages
        if "2.1" in hr_page:
            render_workforce_summary(hr_filtered)
        elif "2.2" in hr_page:
            render_retention_risk_factors(hr_filtered)
        elif "2.3" in hr_page:
            render_employee_experience(hr_filtered)

    # --- ENTERPRISE FOOTER ---
    st.markdown(
        """
        <div style="margin-top: 3.5rem; padding-top: 1.5rem; border-top: 1px solid rgba(255,255,255,0.08); text-align: center; color: #6B7280; font-size: 0.78rem;">
            Enterprise BI Analytics Portal | Designed with Streamlit & Plotly | Integrated Maven Market Retail & HR Workforce Modules
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
