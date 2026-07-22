"""Dashboard Carteira — Prof. Marcos."""

import streamlit as st

st.set_page_config(
    page_title="Carteira Prof. Marcos",
    page_icon="📊",
    layout="wide",
)

from components.theme import apply_theme
apply_theme()

# ── Sidebar ───────────────────────────────────────────────────
st.sidebar.markdown("## 📊 Carteira Prof. Marcos")
st.sidebar.markdown("---")
st.sidebar.caption("Dashboard independente — dados reais do seu banco Postgres.")

# ── Página inicial ───────────────────────────────────────────
st.title("Dashboard — Carteira Prof. Marcos")
st.caption("Substituindo o Investidor10 com dados próprios.")

from data.queries import get_patrimonio_total, get_proventos_agregado

pat = get_patrimonio_total()
prov = get_proventos_agregado()

col1, col2, col3, col4 = st.columns(4)

lucro = pat["valor_atual"] - pat["custo_total"]
rentab = (lucro / pat["custo_total"] * 100) if pat["custo_total"] > 0 else 0

col1.metric("💰 Patrimônio", f"R$ {pat['valor_atual']:,.2f}")
col2.metric("📈 Lucro/Prejuízo", f"R$ {lucro:,.2f}", delta=f"{rentab:.2f}%")
col3.metric("💵 Proventos (Ano)", f"R$ {prov['ano_atual']:,.2f}")
col4.metric("📅 Proventos (Mês)", f"R$ {prov['mes_atual']:,.2f}")

st.markdown("---")
st.info("👈 Use o menu lateral para navegar entre **Resumo**, **Posições**, **Proventos**, **Rentabilidade** e **Análise**.")