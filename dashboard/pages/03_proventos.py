"""Página Proventos — Histórico de dividendos."""

import streamlit as st
import plotly.express as px
import pandas as pd

from data.queries import get_proventos, get_proventos_agregado
from components.theme import CLIMATE, PLOTLY_TEMPLATE

st.title("💵 Proventos")

# ── KPIs ──────────────────────────────────────────────────────
prov = get_proventos_agregado()
c1, c2, c3 = st.columns(3)
c1.metric("12 Meses", f"R$ {prov['doze_meses']:,.2f}")
c2.metric("Ano Atual", f"R$ {prov['ano_atual']:,.2f}")
c3.metric("Mês Atual", f"R$ {prov['mes_atual']:,.2f}")

# ── Filtro de período ─────────────────────────────────────────
st.markdown("---")
periodo = st.segmented_control(
    "Período de análise",
    options=["24 meses", "12 meses", "6 meses", "1 mês"],
    default="12 meses",
)

meses = int(periodo.split()[0])

# ── Dados ────────────────────────────────────────────────────
df = get_proventos(meses)

if df.empty:
    st.info("Nenhum provento registrado no período.")
    st.stop()

# ── Gráfico ───────────────────────────────────────────────────
st.markdown("---")

if meses == 1:
    st.subheader(f"📊 Proventos por Ativo (último mês)")
    # Agrupa por ticker — mostra quais ativos pagaram no mês
    por_ticker = df.groupby("ticker")["valor"].sum().reset_index()
    por_ticker = por_ticker.sort_values("valor", ascending=True)

    fig = px.bar(
        por_ticker, x="valor", y="ticker",
        orientation="h",
        template=None, height=max(300, len(por_ticker) * 35),
        color_discrete_sequence=[CLIMATE["positive"]],
        text=por_ticker["valor"].apply(lambda v: f"R$ {v:,.2f}"),
    )
    fig.update_traces(textposition="outside", textfont_color=CLIMATE["text2"])
else:
    st.subheader(f"📊 Proventos Mensais (últimos {meses} meses)")
    df["ano_mes"] = pd.to_datetime(df["data_pgto"]).dt.to_period("M").astype(str)
    mensal = df.groupby("ano_mes")["valor"].sum().reset_index()
    mensal = mensal.sort_values("ano_mes")

    fig = px.bar(
        mensal, x="ano_mes", y="valor",
        template=None, height=400,
        color_discrete_sequence=[CLIMATE["positive"]],
    )

fig.update_layout(**PLOTLY_TEMPLATE["layout"])
fig.update_yaxes(tickprefix="R$ ")
fig.update_xaxes(title="")
st.plotly_chart(fig, width='stretch')

# ── Tabela ────────────────────────────────────────────────────
st.markdown("---")
st.subheader(f"📋 Proventos (últimos {meses} meses)")

st.dataframe(
    df.sort_values("data_pgto", ascending=False),
    column_config={
        "ticker": "Ativo",
        "data_pgto": st.column_config.DateColumn("Data Pgto", format="DD/MM/YYYY"),
        "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
        "tipo": "Tipo",
    },
    hide_index=True,
    width='stretch',
)