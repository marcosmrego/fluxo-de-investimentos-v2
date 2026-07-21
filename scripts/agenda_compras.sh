#!/bin/bash
# Agenda de Compras V2 — executado toda segunda-feira às 08:00
# 1. Coleta proventos historicos via Yahoo Finance
# 2. Coleta indicadores fundamentalistas via Fundamentus
# 3. Gera agenda de compras com quantidades sugeridas e envia Telegram

set -e
SCRIPT_DIR="/opt/data/fluxo-de-investimentos-v2/scripts"

echo "=== $(date '+%Y-%m-%d %H:%M') — Iniciando Agenda de Compras V2 ==="

echo "[1/3] Coletando proventos (Yahoo Finance)..."
python3 "$SCRIPT_DIR/coletar_proventos.py"

echo "[2/3] Coletando indicadores (Fundamentus)..."
python3 "$SCRIPT_DIR/fundamentus_scraper.py"

echo "[3/3] Gerando agenda com quantidades..."
python3 "$SCRIPT_DIR/gerar_agenda.py"

echo "=== $(date '+%Y-%m-%d %H:%M') — Agenda concluida ==="