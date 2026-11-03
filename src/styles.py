"""
Styling and theme injection for the Enterprise Analytics Portal.
Provides responsive CSS, glassmorphic metric cards, color palettes,
and executive UI aesthetics.
"""

# Theme Palettes
RETAIL_PRIMARY = "#10B981"      # Emerald
RETAIL_SECONDARY = "#059669"
RETAIL_ACCENT = "#34D399"
RETAIL_BG_DARK = "#0F172A"       # Slate 900
RETAIL_CARD_BG = "rgba(30, 41, 59, 0.7)"

HR_PRIMARY = "#6366F1"          # Indigo
HR_SECONDARY = "#EC4899"        # Rose
HR_ACCENT = "#818CF8"
HR_BG_DARK = "#0F172A"
HR_CARD_BG = "rgba(30, 41, 59, 0.7)"

def get_custom_css(module="retail"):
    """Generate dynamic CSS based on the active module theme."""
    primary_color = RETAIL_PRIMARY if module == "retail" else HR_PRIMARY
    accent_color = RETAIL_ACCENT if module == "retail" else HR_SECONDARY
    glow_color = "rgba(16, 185, 129, 0.25)" if module == "retail" else "rgba(99, 102, 241, 0.25)"
    
    return f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    /* Global Typography & Background */
    html, body, [class*="css"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }}
    
    .stApp {{
        background: linear-gradient(180deg, #0B0F19 0%, #111827 100%);
        color: #F3F4F6;
    }}

    /* Main Container Padding */
    .block-container {{
        padding-top: 1.5rem;
        padding-bottom: 2.5rem;
        padding-left: 2rem;
        padding-right: 2rem;
        max-width: 98% !important;
    }}

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {{
        background: #0D131F !important;
        border-right: 1px solid rgba(255, 255, 255, 0.08);
    }}
    section[data-testid="stSidebar"] .block-container {{
        padding-top: 1.5rem;
        padding-left: 1rem;
        padding-right: 1rem;
    }}

    /* Top Header Banner */
    .portal-header {{
        background: linear-gradient(135deg, rgba(17, 24, 39, 0.85) 0%, rgba(31, 41, 55, 0.75) 100%);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 14px;
        padding: 1.25rem 1.75rem;
        margin-bottom: 1.5rem;
        backdrop-filter: blur(12px);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        display: flex;
        justify-content: space-between;
        align-items: center;
    }}
    .portal-title {{
        font-size: 1.5rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        margin: 0;
        color: #FFFFFF;
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }}
    .portal-subtitle {{
        font-size: 0.85rem;
        color: #9CA3AF;
        margin-top: 0.25rem;
    }}
    .portal-badge {{
        font-size: 0.75rem;
        font-weight: 600;
        padding: 0.35rem 0.85rem;
        border-radius: 9999px;
        background: {glow_color};
        color: {primary_color};
        border: 1px solid {primary_color};
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}

    /* Glassmorphic Metric Cards */
    .metric-card {{
        background: linear-gradient(145deg, rgba(26, 34, 52, 0.75) 0%, rgba(17, 24, 39, 0.85) 100%);
        border: 1px solid rgba(255, 255, 255, 0.09);
        border-radius: 12px;
        padding: 1.2rem 1.2rem;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
        backdrop-filter: blur(8px);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        position: relative;
        overflow: hidden;
    }}
    .metric-card:hover {{
        transform: translateY(-2px);
        box-shadow: 0 8px 28px rgba(0, 0, 0, 0.4), 0 0 15px {glow_color};
        border-color: rgba(255, 255, 255, 0.2);
    }}
    .metric-card::before {{
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, {primary_color}, {accent_color});
    }}
    .metric-label {{
        font-size: 0.78rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #9CA3AF;
        margin-bottom: 0.4rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }}
    .metric-value {{
        font-size: 1.7rem;
        font-weight: 700;
        color: #F9FAFB;
        letter-spacing: -0.02em;
        line-height: 1.2;
    }}
    .metric-footer {{
        font-size: 0.75rem;
        color: #6B7280;
        margin-top: 0.45rem;
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }}
    .metric-pill-up {{
        background: rgba(16, 185, 129, 0.15);
        color: #10B981;
        padding: 0.15rem 0.45rem;
        border-radius: 6px;
        font-weight: 600;
    }}
    .metric-pill-down {{
        background: rgba(239, 68, 68, 0.15);
        color: #EF4444;
        padding: 0.15rem 0.45rem;
        border-radius: 6px;
        font-weight: 600;
    }}
    .metric-pill-neutral {{
        background: rgba(107, 114, 128, 0.2);
        color: #D1D5DB;
        padding: 0.15rem 0.45rem;
        border-radius: 6px;
        font-weight: 500;
    }}

    /* Section Subheadings */
    .section-title {{
        font-size: 1.15rem;
        font-weight: 700;
        color: #F3F4F6;
        margin-top: 1.25rem;
        margin-bottom: 0.75rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        border-left: 4px solid {primary_color};
        padding-left: 0.6rem;
    }}

    /* Custom Streamlit Tabs */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 8px;
        background: rgba(17, 24, 39, 0.6);
        padding: 6px;
        border-radius: 10px;
        border: 1px solid rgba(255, 255, 255, 0.08);
    }}
    .stTabs [data-baseweb="tab"] {{
        height: 42px;
        white-space: pre-wrap;
        background-color: transparent;
        border-radius: 7px;
        color: #9CA3AF;
        font-size: 0.9rem;
        font-weight: 600;
        padding: 0 16px;
        border: none;
    }}
    .stTabs [aria-selected="true"] {{
        background: {primary_color} !important;
        color: #FFFFFF !important;
        box-shadow: 0 4px 12px {glow_color};
    }}

    /* Dataframe Table styling */
    .stDataFrame {{
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.08);
    }}

    /* Custom Alert/Warning callout */
    .custom-alert {{
        background: rgba(30, 41, 59, 0.85);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-left: 4px solid {primary_color};
        border-radius: 8px;
        padding: 0.85rem 1.2rem;
        margin: 1rem 0;
        font-size: 0.88rem;
        color: #E2E8F0;
    }}
    </style>
    """
