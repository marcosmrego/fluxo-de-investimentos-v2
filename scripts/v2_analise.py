#!/usr/bin/env python3
import datetime, os, sys, json, urllib.request, time

# Config V2
TICKERS = [
    "VALE3.SA","BBDC4.SA","PETR4.SA","ITSA3.SA","BBAS3.SA",  # ações
    "HGLG11.SA","KNRI11.SA","MXRF11.SA","ALZR11.SA","CPTS11.SA",
    "GARE11.SA","HGRU11.SA","KNCR11.SA","VGHF11.SA"  # FIIs
]

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d"
THRESHOLD = 0.5  # percent

def fetch(symbol):
    try:
        req = urllib.request.Request(YAHOO_URL.format(symbol=symbol),
                                   headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if not data or "chart" not in data: return {}
            result = data["chart"]["result"][0]
            meta = result.get("meta", {})
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            pct = ((price - prev) / prev * 100) if price and prev else 0.0
            return {"symbol": meta.get("symbol") or symbol,
                    "price": price,
                    "changePct": round(pct, 2)}
    except Exception as e:
        print(f"[ERRO] {symbol}: {e}", file=sys.stderr)
        return {}

def main():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] V2 analysis start")
    quotes = {}
    for i, sym in enumerate(TICKERS):
        q = fetch(sym)
        quotes[sym] = q
        if i < len(TICKERS) - 1:
            time.sleep(1.5)  # rate-limiting protection
    lines = ["# Análise V2 – " + now, ""]
    lines.append("## Cotações")
    alerts = []
    for sym,q in quotes.items():
        if not q: continue
        pct = q.get("changePct",0.0)
        if abs(pct) >= THRESHOLD:
            alerts.append((sym,pct))
        lines.append(f"- **{sym}** : R${q.get('price','---')} (Δ {pct:.2f}%)")
    if alerts:
        lines.append("\n## 🚨 Alertas")
        for sym,pct in alerts:
            lines.append(f"- **{sym}** – variação **{pct:.2f}%**")
    out_dir = "/opt/data/fluxo-de-investimentos-v2/reports"
    os.makedirs(out_dir,exist_ok=True)
    path = os.path.join(out_dir, f"report_{int(time.time())}.md")
    with open(path,"w",encoding="utf-8") as f: f.write("\n".join(lines))
    print(f"[INFO] Report saved to {path}")

if __name__=="__main__":
    main()