"""
HR Workforce & Employee Attrition Analytics Module:
- Page 2.1: Workforce Executive Summary
- Page 2.2: Retention & Risk Factors
- Page 2.3: Employee Experience & Sentiment
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
from src.styles import HR_PRIMARY, HR_SECONDARY, HR_ACCENT


def render_workforce_summary(hr_df: pd.DataFrame):
    """Page 2.1: Workforce Executive Summary"""
    render_section_header("Workforce Executive Summary & Headcount Dynamics", "Organizational census, turnover benchmarks, and departmental attrition profiles", "👥")

    if hr_df.empty:
        st.warning("⚠️ No employee records match the selected filters.")
        return

    # Key Metrics
    total_employees = len(hr_df)
    former_employees = int(hr_df["Attrition_Num"].sum())
    active_employees = total_employees - former_employees
    attrition_rate = (former_employees / total_employees * 100) if total_employees > 0 else 0.0

    avg_income = hr_df["MonthlyIncome"].mean()
    avg_age = hr_df["Age"].mean()
    avg_tenure = hr_df["YearsAtCompany"].mean()
    avg_job_sat = hr_df["JobSatisfaction"].mean()

    # KPI Row
    kpi_cols = st.columns(6)
    with kpi_cols[0]:
        render_metric_card("Total Headcount", format_number(total_employees), delta=f"{active_employees} Active", delta_type="neutral", subtext=f"{former_employees} Departures", icon="🏢")
    with kpi_cols[1]:
        render_metric_card("Attrition Rate", format_pct(attrition_rate), delta="Threshold: 15%", delta_type="down" if attrition_rate > 15 else "up", subtext="Workforce turnover", icon="🚪")
    with kpi_cols[2]:
        render_metric_card("Avg Monthly Income", f"${avg_income:,.0f}", delta="Median: ${:,.0f}".format(hr_df["MonthlyIncome"].median()), delta_type="neutral", subtext="Base compensation", icon="💵")
    with kpi_cols[3]:
        render_metric_card("Average Age", f"{avg_age:.1f} Yrs", delta="Range: 18-60", delta_type="neutral", subtext="Workforce maturity", icon="🎂")
    with kpi_cols[4]:
        render_metric_card("Average Tenure", f"{avg_tenure:.1f} Yrs", delta="At company", delta_type="neutral", subtext="Organizational loyalty", icon="⏳")
    with kpi_cols[5]:
        render_metric_card("Job Satisfaction", f"{avg_job_sat:.2f} / 4.0", delta="+0.1 vs Bench", delta_type="up" if avg_job_sat >= 2.7 else "down", subtext="Self-reported survey", icon="⭐")

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    # --- ROW 1: DEPARTMENT & JOB ROLE TURNOVER ---
    col_dept, col_role = st.columns([1, 1.2])

    with col_dept:
        st.markdown("#### 🏢 Attrition by Department")
        dept_agg = hr_df.groupby("Department").agg(
            headcount=("EmployeeNumber", "count"),
            attrition_count=("Attrition_Num", "sum")
        ).reset_index()
        dept_agg["attrition_rate"] = (dept_agg["attrition_count"] / dept_agg["headcount"] * 100).round(1)
        dept_agg = dept_agg.sort_values(by="attrition_rate", ascending=False)

        fig_dept = px.bar(
            dept_agg,
            x="Department",
            y="attrition_rate",
            color="attrition_rate",
            color_continuous_scale="Purples",
            text="attrition_rate",
            labels={"attrition_rate": "Attrition Rate (%)", "Department": ""},
            hover_data={"headcount": True, "attrition_count": True}
        )
        fig_dept.add_hline(y=attrition_rate, line_dash="dash", line_color="#F43F5E", annotation_text=f"Org Avg: {attrition_rate:.1f}%", annotation_position="top right")
        fig_dept.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig_dept.update_layout(height=360, yaxis=dict(ticksuffix="%", range=[0, max(dept_agg["attrition_rate"].max() + 8, 30)]))
        apply_plotly_theme(fig_dept, "hr")
        st.plotly_chart(fig_dept, use_container_width=True)

    with col_role:
        st.markdown("#### 👔 Attrition Rate by Job Role")
        role_agg = hr_df.groupby("JobRole").agg(
            headcount=("EmployeeNumber", "count"),
            attrition_count=("Attrition_Num", "sum")
        ).reset_index()
        role_agg["attrition_rate"] = (role_agg["attrition_count"] / role_agg["headcount"] * 100).round(1)
        role_agg = role_agg.sort_values(by="attrition_rate", ascending=True)

        fig_role = px.bar(
            role_agg,
            x="attrition_rate",
            y="JobRole",
            orientation="h",
            color="attrition_rate",
            color_continuous_scale="Reds",
            text="attrition_rate",
            labels={"attrition_rate": "Attrition Rate (%)", "JobRole": ""},
            hover_data={"headcount": True, "attrition_count": True}
        )
        fig_role.add_vline(x=attrition_rate, line_dash="dash", line_color="#F43F5E", annotation_text=f"Org Avg: {attrition_rate:.1f}%", annotation_position="top right")
        fig_role.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig_role.update_layout(height=360, xaxis=dict(ticksuffix="%", range=[0, max(role_agg["attrition_rate"].max() + 8, 45)]))
        apply_plotly_theme(fig_role, "hr")
        st.plotly_chart(fig_role, use_container_width=True)

    # --- ROW 2: DEMOGRAPHIC & TENURE SPREAD ---
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("##### 🚻 Gender Distribution & Attrition Across Departments")
        gender_dept = hr_df.groupby(["Department", "Gender", "Attrition"]).size().reset_index(name="count")
        fig_gd = px.bar(
            gender_dept,
            x="Department",
            y="count",
            color="Attrition",
            facet_col="Gender",
            barmode="group",
            color_discrete_map={"No": "#6366F1", "Yes": "#F43F5E"},
            labels={"count": "Headcount"}
        )
        fig_gd.update_layout(height=300)
        apply_plotly_theme(fig_gd, "hr")
        st.plotly_chart(fig_gd, use_container_width=True)

    with c2:
        st.markdown("##### 🎂 Age Pyramid & Turnover Vulnerability")
        fig_age = px.histogram(
            hr_df,
            x="Age",
            color="Attrition",
            barmode="overlay",
            nbins=25,
            color_discrete_map={"No": "rgba(99, 102, 241, 0.6)", "Yes": "#F43F5E"},
            labels={"Age": "Employee Age (Years)", "count": "Employee Count"}
        )
        fig_age.update_layout(height=300, hovermode="x unified")
        apply_plotly_theme(fig_age, "hr")
        st.plotly_chart(fig_age, use_container_width=True)


def render_retention_risk_factors(hr_df: pd.DataFrame):
    """Page 2.2: Retention & Risk Factors"""
    render_section_header("Turnover Risk Factors & Retention Levers", "OverTime burden, compensation equity, promotion stagnation, and managerial tenure", "🔍")

    if hr_df.empty:
        st.warning("⚠️ No employee records match current filters.")
        return

    # --- ROW 1: OVERTIME IMPACT & DONUT ---
    st.markdown("#### ⏰ OverTime Impact: The Leading Attrition Driver")
    col_ot1, col_ot2 = st.columns([1.2, 0.8])

    with col_ot1:
        ot_agg = hr_df.groupby(["OverTime", "Attrition"]).size().reset_index(name="count")
        ot_totals = hr_df.groupby("OverTime")["Attrition_Num"].agg(["count", "mean"]).reset_index()
        ot_totals["attrition_rate"] = (ot_totals["mean"] * 100).round(1)

        fig_ot = px.bar(
            ot_agg,
            x="OverTime",
            y="count",
            color="Attrition",
            barmode="stack",
            text="count",
            color_discrete_map={"No": "#6366F1", "Yes": "#F43F5E"},
            labels={"count": "Employee Count", "OverTime": "Works OverTime?"}
        )
        fig_ot.update_layout(height=320)
        apply_plotly_theme(fig_ot, "hr")
        st.plotly_chart(fig_ot, use_container_width=True)

    with col_ot2:
        st.markdown("##### 🔄 Turnover Comparison by Overtime")
        ot_yes_rate = ot_totals.loc[ot_totals["OverTime"] == "Yes", "attrition_rate"].values[0] if "Yes" in ot_totals["OverTime"].values else 0
        ot_no_rate = ot_totals.loc[ot_totals["OverTime"] == "No", "attrition_rate"].values[0] if "No" in ot_totals["OverTime"].values else 0
        
        donut_df = pd.DataFrame({
            "Category": [f"OverTime Yes ({ot_yes_rate}%)", f"OverTime No ({ot_no_rate}%)"],
            "Attrition_Rate": [ot_yes_rate, ot_no_rate]
        })
        fig_donut = px.pie(
            donut_df,
            names="Category",
            values="Attrition_Rate",
            hole=0.6,
            color="Category",
            color_discrete_sequence=["#F43F5E", "#38BDF8"]
        )
        fig_donut.update_traces(textinfo="label+value", textfont=dict(color="#FFFFFF", size=12))
        fig_donut.update_layout(height=320, showlegend=False)
        apply_plotly_theme(fig_donut, "hr")
        st.plotly_chart(fig_donut, use_container_width=True)

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    # --- ROW 2: INCOME & COMPENSATION ANALYSIS ---
    st.markdown("#### 💰 Compensation Disparity & Salary Dynamics")
    c_box, c_role_inc = st.columns([1, 1.1])

    with c_box:
        st.markdown("##### 📦 Monthly Income Distribution (Active vs. Departed)")
        fig_box = px.box(
            hr_df,
            x="Attrition",
            y="MonthlyIncome",
            color="Attrition",
            notched=True,
            points="outliers",
            color_discrete_map={"No": "#6366F1", "Yes": "#F43F5E"},
            labels={"MonthlyIncome": "Monthly Income ($)", "Attrition": "Attrition Status"}
        )
        med_no = hr_df[hr_df["Attrition"] == "No"]["MonthlyIncome"].median()
        med_yes = hr_df[hr_df["Attrition"] == "Yes"]["MonthlyIncome"].median()
        diff_pct = ((med_no - med_yes) / med_no * 100) if med_no > 0 else 0
        fig_box.update_layout(
            height=360,
            yaxis=dict(tickprefix="$"),
            title=f"Median Income Gap: Departed employees earn ~{diff_pct:.1f}% less"
        )
        apply_plotly_theme(fig_box, "hr")
        st.plotly_chart(fig_box, use_container_width=True)

    with c_role_inc:
        st.markdown("##### 💼 Median Income & Attrition Rate by Role")
        role_comp = hr_df.groupby("JobRole").agg(
            median_income=("MonthlyIncome", "median"),
            attrition_rate=("Attrition_Num", lambda x: round(x.mean() * 100, 1)),
            count=("EmployeeNumber", "count")
        ).reset_index()

        fig_comp = px.scatter(
            role_comp,
            x="median_income",
            y="attrition_rate",
            size="count",
            color="attrition_rate",
            color_continuous_scale="Reds",
            text="JobRole",
            labels={"median_income": "Median Monthly Income ($)", "attrition_rate": "Attrition Rate (%)", "count": "Headcount"},
            size_max=30
        )
        fig_comp.update_traces(textposition="top center")
        fig_comp.update_layout(height=360, xaxis=dict(tickprefix="$"), yaxis=dict(ticksuffix="%"))
        apply_plotly_theme(fig_comp, "hr")
        st.plotly_chart(fig_comp, use_container_width=True)

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    # --- ROW 3: TENURE & CAREER PROGRESSION ---
    st.markdown("#### ⏳ Tenure & Career Progression vs. Turnover")
    c_mgr, c_promo = st.columns(2)

    with c_mgr:
        st.markdown("##### 🤝 Years with Current Manager vs. Attrition %")
        mgr_agg = hr_df.groupby("YearsWithCurrManager").agg(
            headcount=("EmployeeNumber", "count"),
            attrition_rate=("Attrition_Num", lambda x: round(x.mean() * 100, 1))
        ).reset_index()
        # Filter for statistically relevant cohorts
        mgr_agg = mgr_agg[mgr_agg["headcount"] >= 10]

        fig_mgr = px.line(
            mgr_agg,
            x="YearsWithCurrManager",
            y="attrition_rate",
            markers=True,
            text="attrition_rate",
            labels={"YearsWithCurrManager": "Years with Current Manager", "attrition_rate": "Attrition Rate (%)"}
        )
        fig_mgr.update_traces(
            line=dict(color="#EC4899", width=3),
            marker=dict(size=8, color="#EC4899"),
            texttemplate="%{text:.0f}%",
            textposition="top center"
        )
        fig_mgr.update_layout(height=320, yaxis=dict(ticksuffix="%"))
        apply_plotly_theme(fig_mgr, "hr")
        st.plotly_chart(fig_mgr, use_container_width=True)

    with c_promo:
        st.markdown("##### 🏆 Years Since Last Promotion vs. Turnover")
        promo_agg = hr_df.groupby("YearsSinceLastPromotion").agg(
            headcount=("EmployeeNumber", "count"),
            attrition_rate=("Attrition_Num", lambda x: round(x.mean() * 100, 1))
        ).reset_index()
        promo_agg = promo_agg[promo_agg["headcount"] >= 8]

        fig_promo = px.bar(
            promo_agg,
            x="YearsSinceLastPromotion",
            y="attrition_rate",
            text="attrition_rate",
            color="attrition_rate",
            color_continuous_scale="Purples",
            labels={"YearsSinceLastPromotion": "Years Since Last Promotion", "attrition_rate": "Attrition Rate (%)"}
        )
        fig_promo.update_traces(texttemplate="%{text:.0f}%", textposition="outside")
        fig_promo.update_layout(height=320, yaxis=dict(ticksuffix="%"))
        apply_plotly_theme(fig_promo, "hr")
        st.plotly_chart(fig_promo, use_container_width=True)


def render_employee_experience(hr_df: pd.DataFrame):
    """Page 2.3: Employee Experience & Sentiment"""
    render_section_header("Employee Sentiment & Experience Diagnostic", "Multi-factor satisfaction heatmaps, commute friction, and predictive flight risk watchlist", "🧠")

    if hr_df.empty:
        st.warning("⚠️ No employee records match current filters.")
        return

    # --- ROW 1: SATISFACTION HEATMAP ---
    st.markdown("#### 🔥 Satisfaction Dimensions Cross-Tabulated with Attrition")
    
    col_heat, col_dist = st.columns([1.1, 0.9])

    with col_heat:
        # Cross-tabulate 4 key satisfaction scores by Attrition
        sat_cols = ["JobSatisfaction", "EnvironmentSatisfaction", "WorkLifeBalance", "RelationshipSatisfaction"]
        sat_means = hr_df.groupby("Attrition")[sat_cols].mean().round(2).T
        sat_means.index = ["Job Satisfaction", "Environment Satisfaction", "Work-Life Balance", "Relationship Satisfaction"]
        sat_means["Gap (No - Yes)"] = (sat_means["No"] - sat_means["Yes"]).round(2)

        fig_heat = px.imshow(
            sat_means[["Yes", "No", "Gap (No - Yes)"]],
            text_auto=True,
            color_continuous_scale="RdBu_r",
            aspect="auto",
            labels=dict(x="Cohort", y="Metric", color="Score (1-4)")
        )
        fig_heat.update_layout(height=350)
        apply_plotly_theme(fig_heat, "hr")
        st.plotly_chart(fig_heat, use_container_width=True)

    with col_dist:
        st.markdown("#### 🚗 Commute Friction (Distance vs. Attrition)")
        dist_agg = hr_df.groupby("Distance_Bucket", observed=False).agg(
            headcount=("EmployeeNumber", "count"),
            attrition_rate=("Attrition_Num", lambda x: round(x.mean() * 100, 1))
        ).reset_index()

        fig_dist = px.bar(
            dist_agg,
            x="Distance_Bucket",
            y="attrition_rate",
            color="attrition_rate",
            color_continuous_scale="Reds",
            text="attrition_rate",
            labels={"Distance_Bucket": "Commute Distance", "attrition_rate": "Attrition Rate (%)"}
        )
        fig_dist.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig_dist.update_layout(height=350, yaxis=dict(ticksuffix="%"))
        apply_plotly_theme(fig_dist, "hr")
        st.plotly_chart(fig_dist, use_container_width=True)

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    # --- ROW 2: WORK-LIFE BALANCE & COMMUTE INTERACTION ---
    st.markdown("#### ⚖️ Work-Life Balance vs. Distance Interaction Matrix")
    wlb_dist = hr_df.pivot_table(
        index="WLB_Label",
        columns="Distance_Bucket",
        values="Attrition_Num",
        aggfunc=lambda x: round(x.mean() * 100, 1),
        observed=False
    ).fillna(0)

    fig_wlb_dist = px.imshow(
        wlb_dist,
        text_auto=".1f",
        color_continuous_scale="YlOrRd",
        labels=dict(x="Commute Distance", y="Work-Life Balance Rating", color="Attrition %")
    )
    fig_wlb_dist.update_layout(height=280)
    apply_plotly_theme(fig_wlb_dist, "hr")
    st.plotly_chart(fig_wlb_dist, use_container_width=True)

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    # --- ROW 3: EARLY INTERVENTION FLIGHT RISK WATCHLIST ---
    render_section_header("Early Warning: High Flight-Risk Active Cohort", "Actionable retention watchlist prioritized by multi-factor risk score", "⚠️")

    # Filter active employees with Elevated or Critical Risk
    active_at_risk = hr_df[
        (hr_df["Attrition"] == "No") & 
        (hr_df["Risk_Score"] >= 50)
    ].sort_values(by="Risk_Score", ascending=False)

    total_at_risk = len(active_at_risk)
    critical_count = len(active_at_risk[active_at_risk["Risk_Score"] >= 75])

    r_c1, r_c2, r_c3 = st.columns([1, 1, 2])
    with r_c1:
        render_metric_card("Active Employees at Risk", f"{total_at_risk:,}", delta=f"{total_at_risk/len(hr_df[hr_df['Attrition']=='No'])*100:.1f}% of active staff", delta_type="down", subtext="Score ≥ 50/100", icon="🚨")
    with r_c2:
        render_metric_card("Critical Flight Risks", f"{critical_count:,}", delta="Immediate action needed", delta_type="down", subtext="Score ≥ 75/100", icon="🔥")
    with r_c3:
        st.info("💡 **Recommended HR Retention Playbook**: High-risk profiles exhibit heavy OverTime (>30 hrs/wk), low Job/Environment satisfaction (≤ 2), long commute (>15 km), or stagnant promotion tenure (>3 yrs). Conduct 1-on-1 career check-ins, assess hybrid flexibility, and review compensation adjustments.")

    st.markdown("##### 📋 Active High Flight-Risk Employee Watchlist")
    watchlist_display = active_at_risk[[
        "EmployeeNumber", "Age", "Department", "JobRole", "OverTime", "JobSatisfaction", "WorkLifeBalance", "DistanceFromHome", "MonthlyIncome", "Risk_Score", "Risk_Level"
    ]].head(25).copy()

    watchlist_display["MonthlyIncome"] = watchlist_display["MonthlyIncome"].apply(lambda v: f"${v:,.0f}")
    watchlist_display["DistanceFromHome"] = watchlist_display["DistanceFromHome"].apply(lambda v: f"{v} km")
    watchlist_display.columns = ["Emp ID", "Age", "Department", "Job Role", "OverTime", "Job Sat", "WLB", "Distance", "Monthly Income", "Risk Score", "Risk Tier"]
    st.dataframe(watchlist_display, use_container_width=True, hide_index=True)
