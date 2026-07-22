"""Página Resumo — Visão geral da carteira."""

import streamlit as st
import plotly.express as px
import pandas as pd

from data.queries import (
    get_patrimonio_total, get_proventos_agregado,
    get_rentabilidade_historica, get_distribuicao_tipo, get_posicoes
)
from data.metrics import twr
from components.theme import CLIMATE, PLOTLY_TEMPLATE

st.title("📋 Resumo da Carteira")

# ── KPIs ─────────────────────────────────────────────────────
pat = get_patrimonio_total()
prov = get_proventos_agregado()
posicoes = get_posicoes()

lucro = pat["valor_atual"] - pat["custo_total"]
rentab = (lucro / pat["custo_total"] * 100) if pat["custo_total"] > 0 else 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Patrimônio", f"R$ {pat['valor_atual']:,.0f}")
c2.metric("Lucro", f"R$ {lucro:,.0f}", delta=f"{rentab:.1f}%")
c3.metric("Proventos 12M", f"R$ {prov['doze_meses']:,.0f}")
c4.metric("Ativos", len(posicoes))
c5.metric("Proventos Mês", f"R$ {prov['mes_atual']:,.0f}")

# ── Rentabilidade calculada ──────────────────────────────────
st.markdown("---")
rent_hist = get_rentabilidade_historica(90)
twr_val = twr(rent_hist) if not rent_hist.empty else 0
st.caption(f"Rentabilidade ponderada (TWR) nos últimos 90 dias: **{twr_val:+.2f}%**")

# ── Gráficos ─────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.subheader("📈 Evolução do Patrimônio")
    if not rent_hist.empty:
        fig = px.line(
            rent_hist, x="data", y="valor_total",
            template=None, height=350
        )
        fig.update_layout(**PLOTLY_TEMPLATE["layout"])
        fig.update_traces(line_color=CLIMATE["accent"], line_width=2)
        fig.update_yaxes(tickprefix="R$ ")
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("Sem dados de rentabilidade histórica.")

with col2:
    st.subheader("🎯 Diversificação por Tipo")
    dist = get_distribuicao_tipo()
    if not dist.empty:
        fig = px.pie(
            dist, values="valor", names="tipo",
            color_discrete_sequence=["#5EC8F8", "#FFA726", "#EF5350", "#4ADE80", "#A78BFA"],
            height=350
        )
        fig.update_layout(**PLOTLY_TEMPLATE["layout"])
        fig.update_traces(textinfo="label+percent")
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("Sem dados de distribuição.")

# ── Top posições ─────────────────────────────────────────────
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