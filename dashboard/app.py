"""Dashboard Carteira — Prof. Marcos."""

import streamlit as st
import plotly.express as px

st.set_page_config(
    page_title="Carteira Prof. Marcos",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from components.theme import CLIMATE, PLOTLY_TEMPLATE, apply_theme
apply_theme()

from data.queries import (
    get_patrimonio_total, get_proventos_agregado,
    get_rentabilidade_historica, get_distribuicao_tipo, get_posicoes
)
from data.metrics import twr

# ── Sidebar ───────────────────────────────────────────────────
st.sidebar.markdown("""
<div style="text-align:center; padding: 12px 0;">
    <span style="font-size:32px;">📊</span>
</div>
""", unsafe_allow_html=True)
st.sidebar.markdown("## Carteira")
st.sidebar.markdown("Prof. Marcos")
st.sidebar.markdown("---")
st.sidebar.caption("Dashboard independente — dados reais Postgres.")

# ── Header ────────────────────────────────────────────────────
st.markdown("""
<div style="padding: 8px 0 4px;">
    <h1 style="margin:0;font-size:26px;">Dashboard de Investimentos</h1>
    <p style="color:#546A84;font-size:13px;margin:4px 0 0;">Acompanhamento em tempo real da sua carteira</p>
</div>
""", unsafe_allow_html=True)

# ── Dados ─────────────────────────────────────────────────────
pat = get_patrimonio_total()
prov = get_proventos_agregado()
posicoes = get_posicoes()
rent_hist = get_rentabilidade_historica(90)

lucro = pat["valor_atual"] - pat["custo_total"]
rentab = (lucro / pat["custo_total"] * 100) if pat["custo_total"] > 0 else 0
twr_val = twr(rent_hist) if not rent_hist.empty else 0

# ── KPIs ──────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("💰 Patrimônio", f"R$ {pat['valor_atual']:,.0f}")
c2.metric("📈 Lucro", f"R$ {lucro:,.0f}", delta=f"{rentab:.1f}%")
c3.metric("🔄 TWR 90d", f"{twr_val:+.1f}%")
c4.metric("💵 Prov. Ano", f"R$ {prov['ano_atual']:,.0f}")
c5.metric("📅 Prov. Mês", f"R$ {prov['mes_atual']:,.0f}")

# ── Gráfico 1: Evolução do Patrimônio ─────────────────────────
st.markdown("---")
st.subheader("📈 Evolução do Patrimônio")
if not rent_hist.empty:
    fig = px.line(
        rent_hist, x="data", y="valor_total",
        template=None, height=400
    )
    fig.update_layout(**PLOTLY_TEMPLATE["layout"])
    fig.update_traces(line_color=CLIMATE["accent"], line_width=2)
    fig.update_yaxes(tickprefix="R$ ")
    st.plotly_chart(fig, width='stretch')
else:
    st.info("Sem dados de rentabilidade histórica.")

# ── Gráfico 2: Diversificação por Tipo ────────────────────────
st.markdown("---")
st.subheader("🎯 Diversificação por Tipo")
dist = get_distribuicao_tipo()
if not dist.empty:
    fig = px.pie(
        dist, values="valor", names="tipo",
        color_discrete_sequence=["#5EC8F8", "#FFA726", "#EF5350", "#4ADE80", "#A78BFA"],
        height=400
    )
    fig.update_layout(**PLOTLY_TEMPLATE["layout"])
    fig.update_traces(textinfo="label+percent")
    st.plotly_chart(fig, width='stretch')
else:
    st.info("Sem dados de distribuição.")

# ── Top 5 Posições ────────────────────────────────────────────
st.markdown("---")
st.subheader("🏆 Top 5 Posições")
if not posicoes.empty:
    top5 = posicoes.nlargest(5, "saldo_atual")
    st.dataframe(
        top5[["ticker", "nome", "preco_atual", "saldo_atual", "rentabilidade_pct"]],
        column_config={
            "ticker": "Ativo",
            "nome": "Nome",
            "preco_atual": st.column_config.NumberColumn("Preço", format="R$ %.2f"),
            "saldo_atual": st.column_config.NumberColumn("Saldo", format="R$ %,.2f"),
            "rentabilidade_pct": st.column_config.NumberColumn("Rent. %", format="%.2f%%"),
        },
        hide_index=True,
        width='stretch',
    )
else:
    st.info("Nenhuma posição encontrada.")
