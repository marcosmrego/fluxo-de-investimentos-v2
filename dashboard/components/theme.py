"""Design tokens — Tema CLEAN (claro)."""

import streamlit as st

# ── Palette ──────────────────────────────────────────────────
CLEAN = {
    "bg":          "#FAFBFC",
    "card":        "#FFFFFF",
    "border":      "#D0D7DE",
    "text":        "#1F2328",
    "muted":       "#656D76",
    "accent":      "#0969DA",
    "green":       "#1A7F37",
    "red":         "#CF222E",
    "yellow":      "#9A6700",
    "orange":      "#BC4C00",
    "purple":      "#8250DF",
}

# ── Plotly template ──────────────────────────────────────────
PLOTLY_TEMPLATE = {
    "layout": {
        "plot_bgcolor": CLEAN["card"],
        "paper_bgcolor": CLEAN["bg"],
        "font": {"color": CLEAN["text"], "family": "Inter, system-ui, sans-serif"},
        "xaxis": {"gridcolor": CLEAN["border"], "linecolor": CLEAN["border"]},
        "yaxis": {"gridcolor": CLEAN["border"], "linecolor": CLEAN["border"]},
        "margin": {"l": 40, "r": 20, "t": 40, "b": 30},
    }
}

def apply_theme():
    """Inject CSS for CLEAN theme."""
    st.markdown(f"""
    <style>
    .stApp {{
        background-color: {CLEAN["bg"]};
    }}
    .stMetric {{
        background-color: {CLEAN["card"]};
        border: 1px solid {CLEAN["border"]};
        border-radius: 8px;
        padding: 12px;
    }}
    .stDataFrame {{
        background-color: {CLEAN["card"]};
    }}
    section[data-testid="stSidebar"] {{
        background-color: {CLEAN["card"]};
        border-right: 1px solid {CLEAN["border"]};
    }}
    h1, h2, h3 {{
        color: {CLEAN["text"]};
    }}
    </style>
    """, unsafe_allow_html=True)