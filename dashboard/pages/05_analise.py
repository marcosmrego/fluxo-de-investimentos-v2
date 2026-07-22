"""Página Análise — Indicadores fundamentalistas, Bazin, Graham."""

import streamlit as st
import plotly.express as px
import pandas as pd

from data.queries import get_indicadores
from data.metrics import bazin_preco_teto, graham_preco_justo
from components.theme import CLEAN, PLOTLY_TEMPLATE

st.title("🔬 Análise Fundamentalista")

df = get_indicadores()

if df.empty:
    st.warning("Sem indicadores fundamentalistas. Execute o Fundamentus scraper.")
    st.stop()

st.caption(f"Dados mais recentes: {df['data_coleta'].max().strftime('%d/%m/%Y')}")

# ── Tabela de indicadores ────────────────────────────────────
st.subheader("📋 Indicadores")

st.dataframe(
    df[[
        "ticker", "p_l", "p_vp", "roe", "roic",
        "marg_liquida", "marg_bruta", "dividend_yield",
        "cres_rec_5a", "div_liq_patrim", "osc_12m"
    ]],
    column_config={
        "ticker": "Ativo",
        "p_l": st.column_config.NumberColumn("P/L", format="%.2f"),
        "p_vp": st.column_config.NumberColumn("P/VP", format="%.2f"),
        "roe": st.column_config.NumberColumn("ROE", format="%.1f%%"),
        "roic": st.column_config.NumberColumn("ROIC", format="%.1f%%"),
        "marg_liquida": st.column_config.NumberColumn("Marg. Líq.", format="%.1f%%"),
        "marg_bruta": st.column_config.NumberColumn("Marg. Bruta", format="%.1f%%"),
        "dividend_yield": st.column_config.NumberColumn("DY", format="%.2f%%"),
        "cres_rec_5a": st.column_config.NumberColumn("CAGR Rec 5a", format="%.1f%%"),
        "div_liq_patrim": st.column_config.NumberColumn("Dív/PL", format="%.2f"),
        "osc_12m": st.column_config.NumberColumn("Osc. 12M", format="%.1f%%"),
    },
    hide_index=True,
    use_container_width=True,
)

# ── Gráfico: ROE vs P/VP ─────────────────────────────────────
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader("ROE vs P/VP")
    fig = px.scatter(
        df.dropna(subset=["roe", "p_vp"]),
        x="p_vp", y="roe", text="ticker",
        template=None, height=350,
        color_discrete_sequence=[CLEAN["accent"]]
    )
    fig.update_layout(**PLOTLY_TEMPLATE["layout"])
    fig.update_traces(textposition="top center", marker=dict(size=12))
    fig.update_xaxes(title="P/VP")
    fig.update_yaxes(title="ROE (%)", ticksuffix="%")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Ranking: Dividend Yield")
    dy_rank = df.dropna(subset=["dividend_yield"]).nlargest(10, "dividend_yield")
    fig = px.bar(
        dy_rank, x="dividend_yield", y="ticker",
        template=None, height=350, orientation="h",
        color_discrete_sequence=[CLEAN["green"]]
    )
    fig.update_layout(**PLOTLY_TEMPLATE["layout"])
    fig.update_xaxes(ticksuffix="%", title="DY")
    fig.update_yaxes(title="")
    st.plotly_chart(fig, use_container_width=True)

# ── Bazin & Graham ───────────────────────────────────────────
st.markdown("---")
st.subheader("💎 Preço-Teto (Bazin) & Preço Justo (Graham)")

# Calcular para cada ativo que tem dados
calculos = []
for _, row in df.iterrows():
    dy = row.get("dividend_yield") or 0
    lpa = row.get("p_l") or 0
    vpa = row.get("p_vp") or 0

    # Graham precisa de LPA = Preço / (P/L). Simplificamos usando DY e P/VP como proxy
    lpa_val = (100 / lpa) if lpa and lpa > 0 else 0
    vpa_val = (100 / vpa) if vpa and vpa > 0 else 0

    calculos.append({
        "ticker": row["ticker"],
        "Bazin (R$)": bazin_preco_teto(dy),
        "Graham (R$)": graham_preco_justo(lpa_val, vpa_val),
    })

if calculos:
    calc_df = pd.DataFrame(calculos)
    st.dataframe(calc_df, hide_index=True, use_container_width=True)
    st.caption(
        "**Bazin:** Preço máximo baseado no DY médio (yield desejado = 6%). "
        "**Graham:** √(22.5 × LPA × VPA). Valores são estimativas simplificadas."
    )