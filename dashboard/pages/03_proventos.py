"""Página Proventos — Histórico de dividendos."""

import streamlit as st
import plotly.express as px
import pandas as pd

from data.queries import get_proventos, get_proventos_agregado
from components.theme import CLIMATE, PLOTLY_TEMPLATE

st.title("💵 Proventos")

prov = get_proventos_agregado()
c1, c2, c3 = st.columns(3)
c1.metric("12 Meses", f"R$ {prov['doze_meses']:,.2f}")
c2.metric("Ano Atual", f"R$ {prov['ano_atual']:,.2f}")
c3.metric("Mês Atual", f"R$ {prov['mes_atual']:,.2f}")

# ── Dados ────────────────────────────────────────────────────
df = get_proventos(24)  # últimos 24 meses

if df.empty:
    st.info("Nenhum provento registrado.")
    st.stop()

# ── Gráfico: proventos mensais ───────────────────────────────
st.markdown("---")
st.subheader("📊 Proventos Mensais (últimos 24 meses)")

df["ano_mes"] = pd.to_datetime(df["data_pgto"]).dt.to_period("M").astype(str)
mensal = df.groupby("ano_mes")["valor"].sum().reset_index()
mensal = mensal.sort_values("ano_mes")

fig = px.bar(
    mensal, x="ano_mes", y="valor",
    template=None, height=350,
    color_discrete_sequence=[CLIMATE["positive"]]
)
fig.update_layout(**PLOTLY_TEMPLATE["layout"])
fig.update_yaxes(tickprefix="R$ ")
fig.update_xaxes(title="")
st.plotly_chart(fig, width='stretch')

# ── Tabela de proventos ──────────────────────────────────────
st.markdown("---")
st.subheader("📋 Últimos Proventos")

st.dataframe(
    df.sort_values("data_pgto", ascending=False).head(50),
    column_config={
        "ticker": "Ativo",
        "data_pgto": st.column_config.DateColumn("Data Pgto", format="DD/MM/YYYY"),
        "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
        "tipo": "Tipo",
    },
    hide_index=True,
    width='stretch',
)