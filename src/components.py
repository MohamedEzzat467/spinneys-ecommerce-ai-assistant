"""
Reusable executive UI components and Plotly visual theming helpers.
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from src.styles import (
    RETAIL_PRIMARY, RETAIL_ACCENT,
    HR_PRIMARY, HR_SECONDARY
)


def format_currency(val: float) -> str:
    """Format numeric value as compact currency."""
    if val is None or np_isnan(val):
        return "$0.00"
    abs_val = abs(val)
    sign = "-" if val < 0 else ""
    if abs_val >= 1_000_000:
        return f"{sign}${abs_val / 1_000_000:.2f}M"
    elif abs_val >= 1_000:
        return f"{sign}${abs_val / 1_000:.1f}K"
    else:
        return f"{sign}${abs_val:,.2f}"


def format_number(val: float) -> str:
    """Format numeric value compactly."""
    if val is None or np_isnan(val):
        return "0"
    abs_val = abs(val)
    sign = "-" if val < 0 else ""
    if abs_val >= 1_000_000:
        return f"{sign}{abs_val / 1_000_000:.2f}M"
    elif abs_val >= 1_000:
        return f"{sign}{abs_val / 1_000:.1f}K"
    else:
        return f"{sign}{abs_val:,.0f}"


def format_pct(val: float) -> str:
    """Format percentage value."""
    if val is None or np_isnan(val):
        return "0.0%"
    return f"{val:.1f}%"


def np_isnan(val):
    try:
        import numpy as np
        return np.isnan(val)
    except:
        return False


def render_metric_card(
    label: str,
    value: str,
    delta: str = None,
    delta_type: str = "up",  # "up", "down", "neutral"
    subtext: str = None,
    icon: str = None
):
    """Render a modern glassmorphic executive metric KPI card."""
    pill_html = ""
    if delta:
        css_class = {
            "up": "metric-pill-up",
            "down": "metric-pill-down",
            "neutral": "metric-pill-neutral"
        }.get(delta_type, "metric-pill-neutral")
        pill_html = f'<span class="{css_class}">{delta}</span>'

    icon_html = f'<span style="font-size:1.1rem; opacity:0.85;">{icon}</span>' if icon else ""
    subtext_html = f'<span>{subtext}</span>' if subtext else ""

    card_html = f"""
    <div class="metric-card">
        <div class="metric-label">
            <span>{label}</span>
            {icon_html}
        </div>
        <div class="metric-value">{value}</div>
        <div class="metric-footer">
            {pill_html}
            {subtext_html}
        </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)


def render_section_header(title: str, subtitle: str = None, icon: str = None):
    """Render a styled section header with accent bar."""
    icon_str = f"{icon} " if icon else ""
    st.markdown(f'<div class="section-title">{icon_str}{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<p style="color:#9CA3AF; font-size:0.85rem; margin-top:-0.3rem; margin-bottom:0.8rem;">{subtitle}</p>', unsafe_allow_html=True)


def apply_plotly_theme(fig, module="retail"):
    """Apply unified enterprise dark theme to any Plotly figure."""
    primary = RETAIL_PRIMARY if module == "retail" else HR_PRIMARY
    
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(17, 24, 39, 0)",
        plot_bgcolor="rgba(17, 24, 39, 0.4)",
        font=dict(family="Inter, sans-serif", color="#E5E7EB", size=12),
        margin=dict(l=40, r=30, t=50, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(17, 24, 39, 0.6)",
            bordercolor="rgba(255, 255, 255, 0.1)",
            borderwidth=1,
            font=dict(size=11)
        ),
        hoverlabel=dict(
            bgcolor="#1F2937",
            bordercolor=primary,
            font=dict(color="#F9FAFB", family="Inter, sans-serif", size=12)
        )
    )
    fig.update_xaxes(
        gridcolor="rgba(255, 255, 255, 0.06)",
        zerolinecolor="rgba(255, 255, 255, 0.12)",
        tickfont=dict(color="#9CA3AF")
    )
    fig.update_yaxes(
        gridcolor="rgba(255, 255, 255, 0.06)",
        zerolinecolor="rgba(255, 255, 255, 0.12)",
        tickfont=dict(color="#9CA3AF")
    )
    return fig
