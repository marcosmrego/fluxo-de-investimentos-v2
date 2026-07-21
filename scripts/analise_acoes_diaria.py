#!/usr/bin/env python3
import json, urllib.request, datetime, os, sys, time, math

TICKERS = [
    "VALE3.SA",
    "ITUB4.SA",
    "BBDC4.SA",
    "PETR4.SA",
    "VALE5.SA",
    # adicione outros quantos desejar
]

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d"

def fetch_quote(symbol: str) -> dict:
    """Retorna um dicionário com os campos mais úteis da cotação."""
    req = urllib.request.Request(
        YAHOO_URL.format(symbol=symbol),
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            data = json.loads(raw)
            if not data or "quoteResponse" not in data:
                return {}
            result = data["quoteResponse"]["result"][0]
            return {
                "symbol": result.get("symbol"),
                "price": result.get("regularMarketPrice"),
                "prevClose": result.get("previousClose"),
                "changePct": result.get("chartStatistics", {}).get("changePercent", 0.0),
                "currency": result.get("currency")
            }
    except Exception as e:
        print(f"[ERRO] {symbol}: {e}", file=sys.stderr)
        return {}

# Coleta as cotações
quotes = {}
for sym in TICKERS:
    quotes[sym] = fetch_quote(sym)
    time.sleep(1.5)          # delay anti‑rate‑limit

# Filtra movimentos relevantes (> 2 %)
alerts = []
for sym, q in quotes.items():
    if q and q.get("changePct") is not None and abs(q["changePct"]) > 2.0:
        alerts.append((sym, q["changePct"]))

# Monta relatório markdown
lines = [
    "# Análise de Ações – " + datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
    "",
    "## Cotações selecionadas",
]

for sym, q in quotes.items():
    if q:
        pct = q.get("changePct", 0.0)
        lines.append(
            f"- **{sym}** : R${q.get('price', '---')} "
            f"(\\({abs(pct):.2f}% { '' if pct==0 else ('↑' if pct>0 else '↓')})\\)"
        )
    else:
        lines.append(f"- **{sym}** : *dados indisponíveis*")

lines.append("")
if alerts:
    lines.append("## 🚨 Alertas (> 2 % de variação)")
    for sym, pct in alerts:
        lines.append(f"- **{sym}** – variação de **{pct:.2f}%**")
else:
    lines.append("## 🚨 Alertas")
    lines.append("- Nenhum ativo com variação > 2 % hoje.")

report = "\n".join(lines)

# Salva em arquivo (o caminho será usado pelo cron)
OUT_PATH = "/home/hermes/.hermes/cron/output/757d972809fe/$(date +%Y-%m-%d_%H-%M-%S).md"
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
with open(OUT_PATH, "w", encoding="utf-8") as f:
    f.write(report)

# O script termina imprimindo apenas o caminho — o cron cuidará da entrega.
print("REPORT_PATH:", OUT_PATH)