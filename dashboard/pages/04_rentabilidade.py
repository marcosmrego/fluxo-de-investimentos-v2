"""Pagina Rentabilidade — Evolucao do patrimonio e rentabilidade."""

import streamlit as st
import plotly.express as px
import pandas as pd

from data.queries import get_rentabilidade_historica
from data.metrics import twr
from components.theme import CLEAN, PLOTLY_TEMPLATE

st.title("Rentabilidade")

dias = st.selectbox("Periodo", [30, 90, 180, 365], index=1,
                    format_func=lambda d: f"Ultimos {d} dias")

df = get_rentabilidade_historica(dias)

if df.empty:
    st.warning("Sem dados de rentabilidade historica.")
    st.stop()

twr_val = twr(df)
lucro_total = df.iloc[-1]["lucro_prejuizo"] if len(df) > 0 else 0
rentab_dia = df.iloc[-1]["rentabilidade"] if len(df) > 0 else 0

c1, c2, c3 = st.columns(3)
c1.metric("Rentabilidade (TWR)", f"{twr_val:+.2f}%")
c2.metric("Ultimo dia", f"{rentab_dia:+.2f}%")
c3.metric("Lucro/Prejuizo", f"R$ {lucro_total:,.2f}")

st.markdown("---")
st.subheader("Evolucao do Patrimonio")

fig1 = px.line(df, x="data", y="valor_total", template=None, height=350)
fig1.update_layout(**PLOTLY_TEMPLATE["layout"])
fig1.update_traces(line_color=CLEAN["accent"], line_width=2)
fig1.update_yaxes(tickprefix="R$ ")
st.plotly_chart(fig1, use_container_width=True)

st.markdown("---")
st.subheader("Rentabilidade Diaria (%)")

df["positive"] = df["rentabilidade"] >= 0
fig2 = px.bar(df, x="data", y="rentabilidade", template=None, height=300,
              color="positive",
              color_discrete_map={True: CLEAN["green"], False: CLEAN["red"]})
fig2.update_layout(**PLOTLY_TEMPLATE["layout"], showlegend=False)
fig2.update_yaxes(ticksuffix="%")
st.plotly_chart(fig2, use_container_width=True)