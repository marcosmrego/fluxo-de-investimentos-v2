"""Design tokens — Tema FUTURISTA (Climate-style)."""

import streamlit as st

# ── Paleta Climate ────────────────────────────────────────────
CLIMATE = {
    "bg":           "#07111D",
    "bg2":          "#0C1628",
    "surface":      "#0E1E30",
    "surface2":     "#132436",
    "border":       "rgba(255,255,255,0.07)",
    "border_accent": "rgba(255,255,255,0.14)",
    "text":         "#E8EEF5",
    "text2":        "#8EA2BE",
    "text3":        "#546A84",
    "accent":       "#5EC8F8",
    "accent_dim":   "rgba(94,200,248,0.12)",
    "accent_glow":  "rgba(94,200,248,0.22)",
    "info":         "#5EC8F8",
    "warning":      "#FFA726",
    "critical":     "#EF5350",
    "positive":     "#4ADE80",
    "negative":     "#EF5350",
    "radius":       "16px",
    "radius_sm":    "10px",
}

# ── Plotly template ──────────────────────────────────────────
PLOTLY_TEMPLATE = {
    "layout": {
        "plot_bgcolor": CLIMATE["surface"],
        "paper_bgcolor": CLIMATE["bg"],
        "font": {"color": CLIMATE["text2"], "family": "Inter, system-ui, sans-serif", "size": 12},
        "xaxis": {"gridcolor": CLIMATE["border"], "linecolor": CLIMATE["border_accent"], "zerolinecolor": CLIMATE["border_accent"]},
        "yaxis": {"gridcolor": CLIMATE["border"], "linecolor": CLIMATE["border_accent"], "zerolinecolor": CLIMATE["border_accent"]},
        "margin": {"l": 40, "r": 20, "t": 50, "b": 30},
        "title": {"font": {"color": CLIMATE["text"], "size": 16, "family": "Space Grotesk, sans-serif"}},
    }
}


def apply_theme():
    """Inject CSS futurista."""
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');

    /* ── Base ── */
    .stApp {{
        background: {CLIMATE["bg"]};
    }}

    html, body, .stApp, .stMarkdown, p, span, div {{
        color: {CLIMATE["text"]};
    }}

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {{
        background: {CLIMATE["surface"]};
        border-right: 1px solid {CLIMATE["border"]};
    }}
    section[data-testid="stSidebar"] * {{
        color: {CLIMATE["text2"]} !important;
    }}
    section[data-testid="stSidebar"] h2, 
    section[data-testid="stSidebar"] h3 {{
        color: {CLIMATE["text"]} !important;
    }}

    /* ── Headers ── */
    h1, h2, h3 {{
        font-family: 'Space Grotesk', sans-serif !important;
        color: {CLIMATE["text"]} !important;
        letter-spacing: -0.3px;
    }}
    h1 {{ font-size: 26px !important; font-weight: 700 !important; }}
    h2 {{ font-size: 20px !important; font-weight: 600 !important; }}
    h3 {{ font-size: 16px !important; font-weight: 600 !important; }}

    /* ── Cards KPIs ── */
    [data-testid="stMetric"] {{
        background: {CLIMATE["surface"]};
        border: 1px solid {CLIMATE["border"]};
        border-radius: {CLIMATE["radius"]};
        padding: 16px !important;
        transition: border .22s ease;
    }}
    [data-testid="stMetric"]:hover {{
        border-color: {CLIMATE["border_accent"]};
    }}
    [data-testid="stMetric"] label {{
        color: {CLIMATE["text3"]} !important;
        font-size: 12px !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    [data-testid="stMetric"] [data-testid="stMetricValue"] {{
        color: {CLIMATE["text"]} !important;
        font-family: 'Space Grotesk', sans-serif !important;
        font-size: 24px !important;
        font-weight: 700 !important;
    }}

    /* ── DataFrames ── */
    .stDataFrame {{
        background: {CLIMATE["surface"]} !important;
        border: 1px solid {CLIMATE["border"]} !important;
        border-radius: {CLIMATE["radius"]} !important;
    }}
    .stDataFrame th {{
        background: {CLIMATE["surface2"]} !important;
        color: {CLIMATE["text3"]} !important;
        font-size: 11px !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        border-bottom: 1px solid {CLIMATE["border"]} !important;
    }}
    .stDataFrame td {{
        color: {CLIMATE["text"]} !important;
        border-bottom: 1px solid {CLIMATE["border"]} !important;
    }}

    /* ── Selectbox / Inputs ── */
    .stSelectbox > div > div {{
        background: {CLIMATE["surface"]} !important;
        border: 1px solid {CLIMATE["border"]} !important;
        border-radius: {CLIMATE["radius_sm"]} !important;
        color: {CLIMATE["text"]} !important;
    }}

    /* ── Captions ── */
    .stCaption, .stCaption p {{
        color: {CLIMATE["text3"]} !important;
        font-size: 12px;
    }}

    /* ── Info / Warning / Error boxes ── */
    .stAlert {{
        background: {CLIMATE["surface"]} !important;
        border: 1px solid {CLIMATE["border_accent"]} !important;
        border-radius: {CLIMATE["radius_sm"]} !important;
        color: {CLIMATE["text"]} !important;
    }}

    /* ── Scrollbar ── */
    ::-webkit-scrollbar {{ width: 6px; }}
    ::-webkit-scrollbar-track {{ background: {CLIMATE["bg"]}; }}
    ::-webkit-scrollbar-thumb {{ background: {CLIMATE["text3"]}; border-radius: 3px; }}

    /* ── Separator ── */
    hr {{
        border-color: {CLIMATE["border"]} !important;
        margin: 24px 0 !important;
    }}
    </style>
    """, unsafe_allow_html=True)