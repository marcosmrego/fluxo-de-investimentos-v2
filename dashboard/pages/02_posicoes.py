"""Página Posições — Tabela completa de ativos."""

import streamlit as st
import pandas as pd

from data.queries import get_posicoes, get_patrimonio_total
from data.metrics import percentual_carteira
from components.theme import CLEAN

st.title("📑 Posições")

posicoes = get_posicoes()
pat = get_patrimonio_total()
total = pat["valor_atual"]

if posicoes.empty:
    st.warning("Nenhuma posição encontrada.")
    st.stop()

# ── Filtros ──────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    tipos = ["Todos"] + sorted(posicoes["tipo"].dropna().unique().tolist())
    tipo_filtro = st.selectbox("Tipo de ativo", tipos)
with col2:
    setores = ["Todos"] + sorted(posicoes["setor"].dropna().unique().tolist())
    setor_filtro = st.selectbox("Setor", setores)

# ── Filtrar dados ────────────────────────────────────────────
df = posicoes.copy()
if tipo_filtro != "Todos":
    df = df[df["tipo"] == tipo_filtro]
if setor_filtro != "Todos":
    df = df[df["setor"] == setor_filtro]

# ── Calcular % carteira ──────────────────────────────────────
df["pct_carteira"] = df["saldo_atual"].apply(lambda x: percentual_carteira(x, total))

# ── Tabela ───────────────────────────────────────────────────
st.dataframe(
    df[[
        "ticker", "nome", "tipo", "setor",
        "quantidade_total", "preco_medio", "preco_atual",
        "var_dia_pct", "lucro_prejuizo", "rentabilidade_pct",
        "saldo_atual", "pct_carteira"
    ]],
    column_config={
        "ticker": "Ativo",
        "nome": "Nome",
        "tipo": "Tipo",
        "setor": "Setor",
        "quantidade_total": st.column_config.NumberColumn("Qtd", format="%.0f"),
        "preco_medio": st.column_config.NumberColumn("Preço Médio", format="R$ %.2f"),
        "preco_atual": st.column_config.NumberColumn("Preço Atual", format="R$ %.2f"),
        "var_dia_pct": st.column_config.NumberColumn("Var. Dia", format="%.2f%%"),
        "lucro_prejuizo": st.column_config.NumberColumn("Lucro", format="R$ %,.2f"),
        "rentabilidade_pct": st.column_config.NumberColumn("Rent. %", format="%.2f%%"),
        "saldo_atual": st.column_config.NumberColumn("Saldo", format="R$ %,.2f"),
        "pct_carteira": st.column_config.NumberColumn("% Carteira", format="%.1f%%"),
    },
    hide_index=True,
    use_container_width=True,
)

# ── Totais ───────────────────────────────────────────────────
st.caption(
    f"**{len(df)} ativos** | "
    f"Saldo total: **R$ {df['saldo_atual'].sum():,.2f}** | "
    f"Lucro total: **R$ {df['lucro_prejuizo'].sum():,.2f}**"
)