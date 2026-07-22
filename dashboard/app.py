"""Dashboard Carteira — Prof. Marcos."""

import streamlit as st

st.set_page_config(
    page_title="Carteira Prof. Marcos",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from components.theme import CLIMATE, apply_theme
apply_theme()

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

# ── Página inicial ───────────────────────────────────────────
st.markdown("""
<div style="padding: 8px 0 4px;">
    <h1 style="margin:0;font-size:26px;">Dashboard de Investimentos</h1>
    <p style="color:#546A84;font-size:13px;margin:4px 0 0;">Acompanhamento em tempo real da sua carteira</p>
</div>
""", unsafe_allow_html=True)

from data.queries import get_patrimonio_total, get_proventos_agregado, get_rentabilidade_historica
from data.metrics import twr

pat = get_patrimonio_total()
prov = get_proventos_agregado()
rent_hist = get_rentabilidade_historica(90)

lucro = pat["valor_atual"] - pat["custo_total"]
rentab = (lucro / pat["custo_total"] * 100) if pat["custo_total"] > 0 else 0
twr_val = twr(rent_hist) if not rent_hist.empty else 0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("💰 Patrimônio", f"R$ {pat['valor_atual']:,.0f}")
col2.metric("📈 Lucro", f"R$ {lucro:,.0f}", delta=f"{rentab:.1f}%")
col3.metric("🔄 TWR 90d", f"{twr_val:+.1f}%")
col4.metric("💵 Prov. Ano", f"R$ {prov['ano_atual']:,.0f}")
col5.metric("📅 Prov. Mês", f"R$ {prov['mes_atual']:,.0f}")

st.markdown("---")
st.info("👈 Use o menu lateral para navegar entre **Resumo**, **Posições**, **Proventos**, **Rentabilidade** e **Análise**.")