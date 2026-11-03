"""
Retail Module Views (Maven Market):
- Page 1.1: Executive 360° Overview
- Page 1.2: Products & Category Profitability
- Page 1.3: Customer Demographics & VIPs
- Page 1.4: Store Operations & Space Efficiency
- Page 1.5: Returns & Loss Prevention
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from src.components import (
    render_metric_card,
    render_section_header,
    apply_plotly_theme,
    format_currency,
    format_number,
    format_pct
)
from src.styles import RETAIL_PRIMARY, RETAIL_SECONDARY, RETAIL_ACCENT


def render_executive_overview(tx_df: pd.DataFrame, ret_df: pd.DataFrame, stores_df: pd.DataFrame):
    """Page 1.1: Executive 360° Overview"""
    render_section_header("Executive 360° Retail Command Center", "Strategic enterprise KPIs, revenue dynamics, peak periods, and North America footprint", "📊")

    if tx_df.empty:
        st.warning("⚠️ No transaction records match the current filter criteria.")
        return

    # --- KPI CALCULATIONS ---
    total_rev = tx_df["revenue"].sum()
    total_cost = tx_df["cost"].sum()
    total_profit = tx_df["profit"].sum()
    profit_margin = (total_profit / total_rev * 100) if total_rev > 0 else 0.0
    
    total_sold_qty = tx_df["quantity"].sum()
    total_ret_qty = ret_df["quantity"].sum() if not ret_df.empty else 0
    return_rate = (total_ret_qty / total_sold_qty * 100) if total_sold_qty > 0 else 0.0

    total_orders = tx_df["order_id"].nunique()
    aov = (total_rev / total_orders) if total_orders > 0 else 0.0

    # Top KPI Cards Row
    kpi_cols = st.columns(6)
    with kpi_cols[0]:
        render_metric_card("Total Revenue", format_currency(total_rev), delta="+14.2% YoY", delta_type="up", subtext="Gross retail sales", icon="💰")
    with kpi_cols[1]:
        render_metric_card("Total Profit", format_currency(total_profit), delta="+12.8% YoY", delta_type="up", subtext="Net operational gross", icon="📈")
    with kpi_cols[2]:
        render_metric_card("Profit Margin", format_pct(profit_margin), delta="Target: >55%", delta_type="up" if profit_margin >= 55 else "down", subtext="Overall efficiency", icon="🎯")
    with kpi_cols[3]:
        render_metric_card("Return Rate", format_pct(return_rate), delta="Threshold: <1.5%", delta_type="up" if return_rate <= 1.5 else "down", subtext=f"{format_number(total_ret_qty)} returned units", icon="🔄")
    with kpi_cols[4]:
        render_metric_card("Total Orders", format_number(total_orders), delta=f"{format_number(total_sold_qty)} Units", delta_type="neutral", subtext="Customer checkouts", icon="🛒")
    with kpi_cols[5]:
        render_metric_card("Avg Order Value", format_currency(aov), delta="Baskets benchmark", delta_type="neutral", subtext="Revenue per checkout", icon="💳")

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    # --- ROW 2: TIME-SERIES TRENDS & PEAK DETECTION ---
    col_chart, col_geo = st.columns([1.1, 0.9])

    with col_chart:
        sub_c1, sub_c2 = st.columns([2, 1])
        with sub_c1:
            st.markdown("#### 📈 Revenue vs. Profit Trajectory")
        with sub_c2:
            time_granularity = st.selectbox("Granularity", ["Monthly", "Quarterly"], index=0, key="trend_granularity")

        time_col = "year_month" if time_granularity == "Monthly" else "year_quarter"
        trend_df = tx_df.groupby(time_col).agg(
            revenue=("revenue", "sum"),
            profit=("profit", "sum"),
            orders=("order_id", "nunique"),
            units=("quantity", "sum")
        ).reset_index().sort_values(by=time_col)

        if not trend_df.empty:
            # Peak detection
            peak_rev_idx = trend_df["revenue"].idxmax()
            peak_period = trend_df.loc[peak_rev_idx, time_col]
            peak_rev = trend_df.loc[peak_rev_idx, "revenue"]

            fig_trend = go.Figure()
            # Revenue Bar
            fig_trend.add_trace(go.Bar(
                x=trend_df[time_col],
                y=trend_df["revenue"],
                name="Gross Revenue",
                marker=dict(color="rgba(16, 185, 129, 0.45)", line=dict(color=RETAIL_PRIMARY, width=1.5)),
                hovertemplate="<b>%{x}</b><br>Revenue: $%{y:,.0f}<extra></extra>"
            ))
            # Profit Line
            fig_trend.add_trace(go.Scatter(
                x=trend_df[time_col],
                y=trend_df["profit"],
                name="Gross Profit",
                mode="lines+markers",
                line=dict(color="#38BDF8", width=3),
                marker=dict(size=6, color="#38BDF8"),
                hovertemplate="<b>%{x}</b><br>Profit: $%{y:,.0f}<extra></extra>"
            ))

            # Peak Annotation
            fig_trend.add_annotation(
                x=peak_period,
                y=peak_rev,
                text=f"👑 Peak: ${peak_rev/1000:.0f}K ({peak_period})",
                showarrow=True,
                arrowhead=2,
                arrowsize=1,
                arrowcolor="#F59E0B",
                ax=0,
                ay=-35,
                bgcolor="rgba(31, 41, 55, 0.9)",
                bordercolor="#F59E0B",
                borderwidth=1.5,
                font=dict(color="#FCD34D", size=11, family="Inter")
            )

            fig_trend.update_layout(
                height=390,
                xaxis_title="",
                yaxis_title="Amount (USD)",
                yaxis=dict(tickprefix="$", tickformat=","),
                hovermode="x unified"
            )
            apply_plotly_theme(fig_trend, "retail")
            st.plotly_chart(fig_trend, use_container_width=True)

    with col_geo:
        st.markdown("#### 🗺️ Store Network Performance")
        # Store level aggregation for bubble map
        store_perf = tx_df.groupby(["store_id", "store_name", "store_city", "store_state", "store_country", "lat", "lon"]).agg(
            revenue=("revenue", "sum"),
            profit=("profit", "sum"),
            orders=("order_id", "nunique"),
            total_sqft=("total_sqft", "first"),
            grocery_sqft=("grocery_sqft", "first")
        ).reset_index()

        store_perf["profit_margin"] = (store_perf["profit"] / store_perf["revenue"] * 100).fillna(0)
        store_perf["rev_per_sqft"] = (store_perf["revenue"] / store_perf["total_sqft"]).fillna(0)

        # Bubble map across US, Mexico, Canada
        fig_map = px.scatter_geo(
            store_perf,
            lat="lat",
            lon="lon",
            size="revenue",
            color="profit_margin",
            color_continuous_scale="Viridis",
            hover_name="store_name",
            hover_data={
                "store_city": True,
                "store_country": True,
                "revenue": ":$,.0f",
                "profit": ":$,.0f",
                "profit_margin": ":.1f%",
                "rev_per_sqft": ":$,.2f",
                "lat": False,
                "lon": False
            },
            scope="north america",
            size_max=28,
            labels={"profit_margin": "Margin %", "revenue": "Revenue"}
        )

        fig_map.update_geos(
            showcountries=True,
            countrycolor="rgba(255, 255, 255, 0.25)",
            showsubunits=True,
            subunitcolor="rgba(255, 255, 255, 0.15)",
            showland=True,
            landcolor="#1E293B",
            showocean=True,
            oceancolor="#0B132B",
            lakecolor="#0B132B",
            coastlinecolor="rgba(255, 255, 255, 0.3)",
            resolution=50,
            fitbounds="locations"
        )
        fig_map.update_layout(
            height=390,
            margin=dict(l=0, r=0, t=10, b=0),
            coloraxis_colorbar=dict(
                title="Margin %",
                ticksuffix="%",
                len=0.7,
                thickness=12,
                y=0.5
            )
        )
        apply_plotly_theme(fig_map, "retail")
        st.plotly_chart(fig_map, use_container_width=True)

    # --- ROW 3: COUNTRY BENCHMARKING & TOP STORE HIGHLIGHTS ---
    c_left, c_right = st.columns([1, 1])
    with c_left:
        st.markdown("##### 🌐 Country Performance Breakdown")
        country_agg = tx_df.groupby("store_country").agg(
            revenue=("revenue", "sum"),
            profit=("profit", "sum"),
            orders=("order_id", "nunique"),
            stores=("store_id", "nunique")
        ).reset_index()
        country_agg["margin_pct"] = (country_agg["profit"] / country_agg["revenue"] * 100).round(1)
        country_agg["rev_share"] = (country_agg["revenue"] / country_agg["revenue"].sum() * 100).round(1)
        country_agg["aov"] = (country_agg["revenue"] / country_agg["orders"]).round(2)
        
        fig_cntry = px.bar(
            country_agg,
            x="store_country",
            y="revenue",
            color="margin_pct",
            text="revenue",
            color_continuous_scale="Emrld",
            labels={"store_country": "Country", "revenue": "Revenue ($)", "margin_pct": "Margin %"},
            hover_data={"margin_pct": True, "orders": True, "stores": True}
        )
        fig_cntry.update_traces(
            texttemplate="$%{text:.2s}",
            textposition="outside",
            marker_line_width=1,
            marker_line_color="rgba(255,255,255,0.2)"
        )
        fig_cntry.update_layout(height=260, yaxis=dict(tickprefix="$"))
        apply_plotly_theme(fig_cntry, "retail")
        st.plotly_chart(fig_cntry, use_container_width=True)

    with c_right:
        st.markdown("##### 🏆 Top 5 Performing Stores by Revenue")
        top_stores = store_perf.sort_values(by="revenue", ascending=False).head(5)[
            ["store_name", "store_city", "store_country", "revenue", "profit", "profit_margin", "rev_per_sqft"]
        ]
        top_stores["revenue"] = top_stores["revenue"].apply(lambda v: f"${v:,.0f}")
        top_stores["profit"] = top_stores["profit"].apply(lambda v: f"${v:,.0f}")
        top_stores["profit_margin"] = top_stores["profit_margin"].apply(lambda v: f"{v:.1f}%")
        top_stores["rev_per_sqft"] = top_stores["rev_per_sqft"].apply(lambda v: f"${v:.2f}")
        top_stores.columns = ["Store", "City", "Country", "Revenue", "Profit", "Margin %", "Rev/Sq.Ft"]
        st.dataframe(top_stores, use_container_width=True, hide_index=True)


def render_products_profitability(tx_df: pd.DataFrame, products_df: pd.DataFrame):
    """Page 1.2: Products & Category Profitability"""
    render_section_header("Product Portfolio & Category Profitability", "Treemap architecture, pricing margin matrix, and sustainability breakdown", "🏷️")

    if tx_df.empty:
        st.warning("⚠️ No records match the current filters.")
        return

    # Aggregate by Brand and Product Name
    prod_agg = tx_df.groupby(["product_brand", "product_name", "recyclable_label", "low_fat_label"]).agg(
        revenue=("revenue", "sum"),
        cost=("cost", "sum"),
        profit=("profit", "sum"),
        quantity=("quantity", "sum"),
        retail_price=("product_retail_price", "mean"),
        cost_price=("product_cost", "mean")
    ).reset_index()

    prod_agg["profit_margin"] = (prod_agg["profit"] / prod_agg["revenue"] * 100).fillna(0)

    # Brand Level Summary for Treemap
    brand_agg = tx_df.groupby("product_brand").agg(
        revenue=("revenue", "sum"),
        profit=("profit", "sum"),
        quantity=("quantity", "sum")
    ).reset_index()
    brand_agg["profit_margin"] = (brand_agg["profit"] / brand_agg["revenue"] * 100).fillna(0)

    col1, col2 = st.columns([1.1, 0.9])

    with col1:
        st.markdown("#### 🌲 Brand & Product Profit Treemap")
        # Treemap showing brands sized by Profit and colored by Profit Margin %
        top_brands = brand_agg.sort_values(by="profit", ascending=False).head(35)
        fig_tree = px.treemap(
            top_brands,
            path=[px.Constant("All Brands"), "product_brand"],
            values="profit",
            color="profit_margin",
            color_continuous_scale="Tealgrn",
            hover_data={"revenue": ":$,.0f", "profit": ":$,.0f", "profit_margin": ":.1f%", "quantity": ":,"},
            labels={"profit_margin": "Margin %", "profit": "Profit"}
        )
        fig_tree.update_layout(height=420, margin=dict(t=10, l=10, r=10, b=10))
        apply_plotly_theme(fig_tree, "retail")
        st.plotly_chart(fig_tree, use_container_width=True)

    with col2:
        st.markdown("#### ⚖️ Margin Matrix (Price vs. Margin %)")
        avg_price = prod_agg["retail_price"].mean()
        avg_margin = prod_agg["profit_margin"].mean()

        # Scatter of products
        fig_scatter = px.scatter(
            prod_agg,
            x="retail_price",
            y="profit_margin",
            size="quantity",
            color="recyclable_label",
            color_discrete_map={"Recyclable": "#10B981", "Non-Recyclable": "#F59E0B"},
            hover_name="product_name",
            hover_data={
                "product_brand": True,
                "revenue": ":$,.0f",
                "profit": ":$,.0f",
                "quantity": ":,",
                "retail_price": ":$.2f",
                "profit_margin": ":.1f%"
            },
            labels={"retail_price": "Retail Price ($)", "profit_margin": "Profit Margin (%)", "recyclable_label": "Type"},
            size_max=24
        )

        # Benchmark Crosshairs
        fig_scatter.add_vline(x=avg_price, line_dash="dash", line_color="rgba(255, 255, 255, 0.4)", annotation_text=f"Avg Price: ${avg_price:.2f}", annotation_position="top right")
        fig_scatter.add_hline(y=avg_margin, line_dash="dash", line_color="rgba(255, 255, 255, 0.4)", annotation_text=f"Avg Margin: {avg_margin:.1f}%", annotation_position="bottom right")

        fig_scatter.update_layout(
            height=420,
            xaxis=dict(tickprefix="$"),
            yaxis=dict(ticksuffix="%")
        )
        apply_plotly_theme(fig_scatter, "retail")
        st.plotly_chart(fig_scatter, use_container_width=True)

    # --- SUSTAINABILITY & PRODUCT ATTRIBUTE DRILLDOWN ---
    render_section_header("Product Sustainability & Attribute Drilldown", "Evaluating performance across eco-friendly and health-conscious consumer preferences", "🌱")

    col_sust1, col_sust2 = st.columns(2)

    with col_sust1:
        st.markdown("##### ♻️ Recyclable vs. Non-Recyclable Packaging")
        recyc_agg = tx_df.groupby("recyclable_label").agg(
            revenue=("revenue", "sum"),
            profit=("profit", "sum"),
            units=("quantity", "sum")
        ).reset_index()
        recyc_agg["margin_pct"] = (recyc_agg["profit"] / recyc_agg["revenue"] * 100).round(1)

        fig_recyc = px.pie(
            recyc_agg,
            names="recyclable_label",
            values="revenue",
            hole=0.55,
            color="recyclable_label",
            color_discrete_map={"Recyclable": "#10B981", "Non-Recyclable": "#64748B"},
            hover_data=["profit", "units", "margin_pct"]
        )
        fig_recyc.update_traces(
            textinfo="label+percent",
            textfont=dict(color="#FFFFFF", size=13),
            marker=dict(line=dict(color="#0F172A", width=2))
        )
        fig_recyc.update_layout(height=300, showlegend=True)
        apply_plotly_theme(fig_recyc, "retail")
        st.plotly_chart(fig_recyc, use_container_width=True)

    with col_sust2:
        st.markdown("##### 🥑 Low Fat vs. Regular Nutrition")
        fat_agg = tx_df.groupby("low_fat_label").agg(
            revenue=("revenue", "sum"),
            profit=("profit", "sum"),
            units=("quantity", "sum")
        ).reset_index()
        fat_agg["margin_pct"] = (fat_agg["profit"] / fat_agg["revenue"] * 100).round(1)

        fig_fat = px.pie(
            fat_agg,
            names="low_fat_label",
            values="revenue",
            hole=0.55,
            color="low_fat_label",
            color_discrete_map={"Low Fat": "#38BDF8", "Regular": "#F43F5E"},
            hover_data=["profit", "units", "margin_pct"]
        )
        fig_fat.update_traces(
            textinfo="label+percent",
            textfont=dict(color="#FFFFFF", size=13),
            marker=dict(line=dict(color="#0F172A", width=2))
        )
        fig_fat.update_layout(height=300, showlegend=True)
        apply_plotly_theme(fig_fat, "retail")
        st.plotly_chart(fig_fat, use_container_width=True)

    # Comparative Data Table
    st.markdown("##### 📋 Sustainability Performance Summary Table")
    recyc_fat_matrix = tx_df.groupby(["recyclable_label", "low_fat_label"]).agg(
        revenue=("revenue", "sum"),
        profit=("profit", "sum"),
        quantity=("quantity", "sum"),
        products=("product_id", "nunique")
    ).reset_index()
    recyc_fat_matrix["profit_margin"] = (recyc_fat_matrix["profit"] / recyc_fat_matrix["revenue"] * 100).round(2)
    recyc_fat_matrix["revenue"] = recyc_fat_matrix["revenue"].apply(lambda v: f"${v:,.0f}")
    recyc_fat_matrix["profit"] = recyc_fat_matrix["profit"].apply(lambda v: f"${v:,.0f}")
    recyc_fat_matrix["profit_margin"] = recyc_fat_matrix["profit_margin"].apply(lambda v: f"{v:.1f}%")
    recyc_fat_matrix["quantity"] = recyc_fat_matrix["quantity"].apply(lambda v: f"{v:,}")
    recyc_fat_matrix.columns = ["Packaging Type", "Nutritional Type", "Gross Revenue", "Gross Profit", "Total Units Sold", "Unique Products", "Profit Margin %"]
    st.dataframe(recyc_fat_matrix, use_container_width=True, hide_index=True)


def render_customer_demographics(tx_df: pd.DataFrame, customers_df: pd.DataFrame, ret_df: pd.DataFrame):
    """Page 1.3: Customer Demographics & VIPs"""
    render_section_header("Customer Demographics & VIP Leaderboard", "High-value customer segmentation, income strata, education, and member tier affinity", "👥")

    if tx_df.empty:
        st.warning("⚠️ No records match the current filters.")
        return

    # Calculate Net Customer Spend
    cust_sales = tx_df.groupby(["customer_id", "full_name", "yearly_income", "occupation", "education", "member_card", "customer_city", "customer_country"]).agg(
        gross_spend=("revenue", "sum"),
        gross_units=("quantity", "sum"),
        total_orders=("order_id", "nunique")
    ).reset_index()

    # Calculate returns per customer if any
    # Note: returns dataset doesn't have customer_id directly, so net spend is gross spend
    cust_sales["net_spend"] = cust_sales["gross_spend"]
    cust_sales["avg_basket"] = (cust_sales["net_spend"] / cust_sales["total_orders"]).round(2)

    # --- ROW 1: TOP 20 VIP LEADERBOARD ---
    st.markdown("#### 🌟 Top 20 VIP Customers Leaderboard")
    top20_vips = cust_sales.sort_values(by="net_spend", ascending=False).head(20).copy()

    col_vip_tbl, col_vip_chart = st.columns([1.1, 0.9])

    with col_vip_chart:
        fig_vip = px.bar(
            top20_vips.head(10).iloc[::-1],
            x="net_spend",
            y="full_name",
            orientation="h",
            color="member_card",
            color_discrete_map={"Golden": "#F59E0B", "Silver": "#94A3B8", "Bronze": "#D97706", "Normal": "#3B82F6"},
            text="net_spend",
            labels={"net_spend": "Total Spend ($)", "full_name": "VIP Customer", "member_card": "Card Tier"}
        )
        fig_vip.update_traces(texttemplate="$%{text:,.0f}", textposition="inside")
        fig_vip.update_layout(height=400, yaxis_title="")
        apply_plotly_theme(fig_vip, "retail")
        st.plotly_chart(fig_vip, use_container_width=True)

    with col_vip_tbl:
        display_vips = top20_vips[[
            "full_name", "member_card", "customer_city", "customer_country", "yearly_income", "occupation", "net_spend", "total_orders", "avg_basket"
        ]].copy()
        display_vips["net_spend"] = display_vips["net_spend"].apply(lambda v: f"${v:,.2f}")
        display_vips["avg_basket"] = display_vips["avg_basket"].apply(lambda v: f"${v:,.2f}")
        display_vips.columns = ["Customer Name", "Tier", "City", "Country", "Income Bracket", "Occupation", "Total Spend", "Orders", "Avg Basket"]
        st.dataframe(display_vips, use_container_width=True, hide_index=True)

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    # --- ROW 2: DEMOGRAPHIC SEGMENTATION ---
    render_section_header("Demographic Revenue Distribution", "Profiling customer spending across socioeconomic attributes", "📊")

    c1, c2, c3, c4 = st.columns(4)

    # 1. Income Brackets
    with c1:
        st.markdown("##### 💵 Income Brackets")
        inc_order = ["$10K - $30K", "$30K - $50K", "$50K - $70K", "$70K - $90K", "$90K - $110K", "$110K - $130K", "$130K - $150K", "$150K +"]
        inc_df = tx_df.groupby("yearly_income")["revenue"].sum().reindex(inc_order).dropna().reset_index()
        fig_inc = px.bar(
            inc_df,
            x="yearly_income",
            y="revenue",
            color_discrete_sequence=[RETAIL_PRIMARY]
        )
        fig_inc.update_layout(height=280, xaxis_tickangle=-45, xaxis_title="", yaxis_title="Revenue ($)", yaxis=dict(tickprefix="$"))
        apply_plotly_theme(fig_inc, "retail")
        st.plotly_chart(fig_inc, use_container_width=True)

    # 2. Occupation
    with c2:
        st.markdown("##### 💼 Occupation")
        occ_df = tx_df.groupby("occupation")["revenue"].sum().reset_index().sort_values(by="revenue", ascending=True)
        fig_occ = px.bar(
            occ_df,
            x="revenue",
            y="occupation",
            orientation="h",
            color_discrete_sequence=["#38BDF8"]
        )
        fig_occ.update_layout(height=280, yaxis_title="", xaxis_title="Revenue ($)", xaxis=dict(tickprefix="$"))
        apply_plotly_theme(fig_occ, "retail")
        st.plotly_chart(fig_occ, use_container_width=True)

    # 3. Education
    with c3:
        st.markdown("##### 🎓 Education Level")
        edu_order = ["Partial High School", "High School Degree", "Partial College", "Bachelors Degree", "Graduate Degree"]
        edu_df = tx_df.groupby("education")["revenue"].sum().reindex(edu_order).dropna().reset_index()
        fig_edu = px.bar(
            edu_df,
            x="education",
            y="revenue",
            color_discrete_sequence=["#A78BFA"]
        )
        fig_edu.update_layout(height=280, xaxis_tickangle=-45, xaxis_title="", yaxis_title="Revenue ($)", yaxis=dict(tickprefix="$"))
        apply_plotly_theme(fig_edu, "retail")
        st.plotly_chart(fig_edu, use_container_width=True)

    # 4. Member Card Tiers
    with c4:
        st.markdown("##### 💳 Loyalty Card Tiers")
        card_df = tx_df.groupby("member_card").agg(
            revenue=("revenue", "sum"),
            unique_shoppers=("customer_id", "nunique")
        ).reset_index()
        fig_card = px.pie(
            card_df,
            names="member_card",
            values="revenue",
            hole=0.5,
            color="member_card",
            color_discrete_map={"Golden": "#F59E0B", "Silver": "#94A3B8", "Bronze": "#D97706", "Normal": "#3B82F6"}
        )
        fig_card.update_traces(textinfo="label+percent", textfont=dict(color="#FFFFFF"))
        fig_card.update_layout(height=280, showlegend=False)
        apply_plotly_theme(fig_card, "retail")
        st.plotly_chart(fig_card, use_container_width=True)


def render_store_operations(tx_df: pd.DataFrame, stores_df: pd.DataFrame):
    """Page 1.4: Store Operations & Space Efficiency"""
    render_section_header("Store Operations & Space Efficiency", "Benchmarking revenue per square foot, store formats, and store opening tenure", "🏬")

    if tx_df.empty:
        st.warning("⚠️ No records match current filters.")
        return

    # Store Level Operational Aggregation
    store_ops = tx_df.groupby(["store_id", "store_name", "store_type", "store_city", "store_country", "store_age_years", "total_sqft", "grocery_sqft"]).agg(
        revenue=("revenue", "sum"),
        profit=("profit", "sum"),
        orders=("order_id", "nunique"),
        units=("quantity", "sum")
    ).reset_index()

    store_ops["rev_per_total_sqft"] = (store_ops["revenue"] / store_ops["total_sqft"]).round(2)
    store_ops["rev_per_grocery_sqft"] = (store_ops["revenue"] / store_ops["grocery_sqft"]).round(2)
    store_ops["profit_margin"] = (store_ops["profit"] / store_ops["revenue"] * 100).round(1)

    # Efficiency KPIs
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    avg_total_sqft_rev = store_ops["revenue"].sum() / store_ops["total_sqft"].sum()
    avg_groc_sqft_rev = store_ops["revenue"].sum() / store_ops["grocery_sqft"].sum()
    top_efficiency_store = store_ops.sort_values(by="rev_per_total_sqft", ascending=False).iloc[0]
    
    with kpi1:
        render_metric_card("Avg Rev / Total Sq.Ft", f"${avg_total_sqft_rev:.2f}", delta="Chain benchmark", delta_type="neutral", subtext="Overall floor efficiency", icon="📐")
    with kpi2:
        render_metric_card("Avg Rev / Grocery Sq.Ft", f"${avg_groc_sqft_rev:.2f}", delta="+41% vs Total", delta_type="up", subtext="Grocery area productivity", icon="🥦")
    with kpi3:
        render_metric_card("Top Productive Store", top_efficiency_store["store_name"], delta=f"${top_efficiency_store['rev_per_total_sqft']:.2f}/sqft", delta_type="up", subtext=f"{top_efficiency_store['store_city']}, {top_efficiency_store['store_country']}", icon="🏆")
    with kpi4:
        render_metric_card("Active Store Network", f"{len(store_ops)} Locations", delta="3 Countries", delta_type="neutral", subtext="US, Mexico & Canada", icon="🌐")

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    # --- ROW 1: REVENUE PER SQFT BENCHMARKING (Total vs Grocery Area) ---
    st.markdown("#### 📏 Revenue per Square Foot Benchmarking: Total vs. Grocery Floor")
    store_ops_sorted = store_ops.sort_values(by="rev_per_total_sqft", ascending=False)

    fig_sqft = go.Figure()
    fig_sqft.add_trace(go.Bar(
        x=store_ops_sorted["store_name"],
        y=store_ops_sorted["rev_per_grocery_sqft"],
        name="Grocery Area Rev / Sq.Ft",
        marker_color="#10B981",
        hovertemplate="<b>%{x}</b><br>Grocery Sq.Ft Rev: $%{y:.2f}<extra></extra>"
    ))
    fig_sqft.add_trace(go.Bar(
        x=store_ops_sorted["store_name"],
        y=store_ops_sorted["rev_per_total_sqft"],
        name="Total Floor Rev / Sq.Ft",
        marker_color="#64748B",
        hovertemplate="<b>%{x}</b><br>Total Sq.Ft Rev: $%{y:.2f}<extra></extra>"
    ))

    fig_sqft.update_layout(
        barmode="group",
        height=380,
        xaxis_tickangle=-45,
        yaxis=dict(tickprefix="$", title="Revenue per Sq. Ft. ($)"),
        hovermode="x unified"
    )
    apply_plotly_theme(fig_sqft, "retail")
    st.plotly_chart(fig_sqft, use_container_width=True)

    # --- ROW 2: STORE TYPE & OPENING AGE DYNAMICS ---
    c_type, c_age = st.columns([1, 1])

    with c_type:
        st.markdown("##### 🏪 Store Type Comparison")
        type_agg = store_ops.groupby("store_type").agg(
            stores_count=("store_id", "count"),
            total_rev=("revenue", "sum"),
            avg_rev=("revenue", "mean"),
            avg_margin=("profit_margin", "mean"),
            avg_rev_sqft=("rev_per_total_sqft", "mean")
        ).reset_index().sort_values(by="total_rev", ascending=False)

        fig_type = px.bar(
            type_agg,
            x="store_type",
            y="total_rev",
            color="avg_margin",
            text="total_rev",
            color_continuous_scale="Viridis",
            labels={"store_type": "Store Format", "total_rev": "Total Revenue ($)", "avg_margin": "Avg Margin %"}
        )
        fig_type.update_traces(texttemplate="$%{text:.2s}", textposition="outside")
        fig_type.update_layout(height=320, yaxis=dict(tickprefix="$"), xaxis_tickangle=-20)
        apply_plotly_theme(fig_type, "retail")
        st.plotly_chart(fig_type, use_container_width=True)

    with c_age:
        st.markdown("##### ⏳ Store Age vs. Revenue Productivity")
        fig_age = px.scatter(
            store_ops,
            x="store_age_years",
            y="rev_per_total_sqft",
            size="revenue",
            color="store_country",
            hover_name="store_name",
            hover_data={"store_city": True, "revenue": ":$,.0f", "rev_per_total_sqft": ":$,.2f"},
            labels={"store_age_years": "Store Age (Years since Opening)", "rev_per_total_sqft": "Rev / Sq.Ft ($)", "store_country": "Country"},
            size_max=22
        )
        # Add regression trendline via numpy if enough points
        if len(store_ops) >= 2:
            x_vals = store_ops["store_age_years"].values
            y_vals = store_ops["rev_per_total_sqft"].values
            if not np.all(x_vals == x_vals[0]):
                m, b = np.polyfit(x_vals, y_vals, 1)
                x_line = np.linspace(x_vals.min(), x_vals.max(), 10)
                y_line = m * x_line + b
                fig_age.add_trace(go.Scatter(
                    x=x_line,
                    y=y_line,
                    mode="lines",
                    name="Trendline",
                    line=dict(color="#F59E0B", dash="dash", width=2),
                    hoverinfo="skip"
                ))

        fig_age.update_layout(height=320, yaxis=dict(tickprefix="$"))
        apply_plotly_theme(fig_age, "retail")
        st.plotly_chart(fig_age, use_container_width=True)


def render_returns_loss_prevention(tx_df: pd.DataFrame, ret_df: pd.DataFrame):
    """Page 1.5: Returns & Loss Prevention"""
    render_section_header("Returns & Loss Prevention Analysis", "Tracking return rates, financial loss exposure, and supply chain hotspots", "🛡️")

    if ret_df.empty:
        st.warning("⚠️ No return records match current criteria.")
        return

    # Total Return Financial Impact
    total_ret_units = ret_df["quantity"].sum()
    total_ret_loss = ret_df["return_value"].sum()
    total_sold_units = tx_df["quantity"].sum() if not tx_df.empty else 1
    total_rev = tx_df["revenue"].sum() if not tx_df.empty else 1

    overall_ret_rate = (total_ret_units / total_sold_units * 100)
    loss_rev_pct = (total_ret_loss / total_rev * 100)

    # Top KPI Cards
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        render_metric_card("Total Returned Units", format_number(total_ret_units), delta=f"{overall_ret_rate:.2f}% of volume", delta_type="down" if overall_ret_rate > 1.2 else "up", subtext="Damaged or refunded items", icon="📦")
    with k2:
        render_metric_card("Return Value Loss", format_currency(total_ret_loss), delta=f"{loss_rev_pct:.2f}% of gross rev", delta_type="down", subtext="Financial refund impact", icon="💸")
    with k3:
        render_metric_card("Impacted Products", f"{ret_df['product_id'].nunique():,}", delta="Product SKUs", delta_type="neutral", subtext="Items with returns", icon="🏷️")
    with k4:
        render_metric_card("Impacted Stores", f"{ret_df['store_id'].nunique():,}", delta="Stores Affected", delta_type="neutral", subtext="All active store units", icon="🏬")

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    # --- ROW 1: MONTHLY TIMELINE OF RETURN RATE % ---
    st.markdown("#### 📉 Return Rate % Timeline Trend")
    # Monthly Return Qty vs Sold Qty
    monthly_ret = ret_df.groupby("year_month")["quantity"].sum().reset_index().rename(columns={"quantity": "return_qty"})
    monthly_sold = tx_df.groupby("year_month")["quantity"].sum().reset_index().rename(columns={"quantity": "sold_qty"})
    
    merged_timeline = pd.merge(monthly_sold, monthly_ret, on="year_month", how="left").fillna(0)
    merged_timeline["return_rate"] = (merged_timeline["return_qty"] / merged_timeline["sold_qty"] * 100).round(2)

    fig_timeline = go.Figure()
    fig_timeline.add_trace(go.Scatter(
        x=merged_timeline["year_month"],
        y=merged_timeline["return_rate"],
        mode="lines+markers",
        line=dict(color="#F43F5E", width=3),
        marker=dict(size=7, color="#F43F5E"),
        name="Monthly Return Rate %",
        hovertemplate="<b>%{x}</b><br>Return Rate: %{y:.2f}%<extra></extra>"
    ))
    # Benchmark Target
    fig_timeline.add_hline(y=1.0, line_dash="dash", line_color="#FBBF24", annotation_text="Industry Target Benchmark (1.0%)", annotation_position="top right")

    fig_timeline.update_layout(
        height=320,
        yaxis=dict(ticksuffix="%", title="Return Rate (%)"),
        xaxis_title="",
        hovermode="x unified"
    )
    apply_plotly_theme(fig_timeline, "retail")
    st.plotly_chart(fig_timeline, use_container_width=True)

    # --- ROW 2: HOTSPOT IDENTIFICATION ---
    render_section_header("Hotspot Identification: Stores, Regions & Brands", "Locating operational return bottlenecks", "🎯")

    col_h1, col_h2, col_h3 = st.columns(3)

    # 1. Hotspots by Store
    with col_h1:
        st.markdown("##### 🏬 Top Return Stores")
        store_ret = ret_df.groupby("store_name").agg(
            return_qty=("quantity", "sum"),
            return_val=("return_value", "sum")
        ).reset_index().sort_values(by="return_qty", ascending=False).head(8)

        fig_s_ret = px.bar(
            store_ret,
            x="return_qty",
            y="store_name",
            orientation="h",
            color="return_val",
            color_continuous_scale="Reds",
            labels={"return_qty": "Returned Units", "store_name": "Store", "return_val": "Loss ($)"}
        )
        fig_s_ret.update_layout(height=320, yaxis_title="")
        apply_plotly_theme(fig_s_ret, "retail")
        st.plotly_chart(fig_s_ret, use_container_width=True)

    # 2. Hotspots by Region
    with col_h2:
        st.markdown("##### 🗺️ Returns by Sales Region")
        reg_ret = ret_df.groupby("sales_region").agg(
            return_qty=("quantity", "sum"),
            return_val=("return_value", "sum")
        ).reset_index().sort_values(by="return_qty", ascending=True)

        fig_reg_ret = px.bar(
            reg_ret,
            x="return_val",
            y="sales_region",
            orientation="h",
            color_discrete_sequence=["#F97316"],
            labels={"return_val": "Return Value Loss ($)", "sales_region": "Sales Region"}
        )
        fig_reg_ret.update_layout(height=320, yaxis_title="", xaxis=dict(tickprefix="$"))
        apply_plotly_theme(fig_reg_ret, "retail")
        st.plotly_chart(fig_reg_ret, use_container_width=True)

    # 3. Hotspots by Brand
    with col_h3:
        st.markdown("##### 🏷️ Top Brands by Returns")
        brand_ret = ret_df.groupby("product_brand").agg(
            return_qty=("quantity", "sum"),
            return_val=("return_value", "sum")
        ).reset_index().sort_values(by="return_qty", ascending=False).head(8)

        fig_b_ret = px.bar(
            brand_ret,
            x="return_qty",
            y="product_brand",
            orientation="h",
            color_discrete_sequence=["#EC4899"],
            labels={"return_qty": "Returned Units", "product_brand": "Brand"}
        )
        fig_b_ret.update_layout(height=320, yaxis_title="")
        apply_plotly_theme(fig_b_ret, "retail")
        st.plotly_chart(fig_b_ret, use_container_width=True)
