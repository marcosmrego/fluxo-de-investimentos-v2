#!/usr/bin/env python3
"""
gerar_agenda.py — Gera agenda mensal de compras baseada em datas de proventos.

Logica:
- FIIs: pagam mensalmente → prever proximo pagamento → recomendar compra
        ate a data-com estimada (5 dias uteis antes do pgto)
- Acoes: pagam trimestral/semestralmente → prever proxima janela →
         recomendar compra com 2-6 meses de antecedencia
- "Propicio": preco atual < preco medio da carteira (com desconto)

Output: insere em investimentos.agenda_compras + gera mensagem Telegram.
"""

import json
import os
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean

import psycopg2

# ── Config ──────────────────────────────────────────────────────────────
from db_utils import DB_CONFIG

CHAT_ID = "6216425458"
TODAY = date.today()

# ── Helpers ─────────────────────────────────────────────────────────────

def business_days_before(dt: date, days: int) -> date:
    """Retorna 'days' dias uteis antes de dt."""
    result = dt
    skipped = 0
    while skipped < days:
        result = result - timedelta(days=1)
        if result.weekday() < 5:
            skipped += 1
    return result


def next_business_day(dt: date) -> date:
    """Proximo dia util a partir de dt."""
    result = dt
    while result.weekday() >= 5:
        result = result + timedelta(days=1)
    return result


def get_telegram_token() -> str:
    """Extrai o token do bot Telegram do .env."""
    import re
    # Tentar caminhos possiveis
    candidates = [
        "/home/hermes/.hermes/.env",
        os.path.join(os.path.expanduser("~"), ".hermes", ".env"),
    ]
    env_path = None
    for c in candidates:
        if os.path.exists(c):
            env_path = c
            break
    if not env_path:
        print("[aviso] .env nao encontrado")
        return ""
    with open(env_path) as f:
        content = f.read()
    m = re.search(r"^TELEGRAM_BOT_TOKEN=(.+)$", content, re.MULTILINE)
    return m.group(1).strip() if m else ""


def send_telegram(mensagem: str):
    """Envia mensagem via bot Telegram."""
    token = get_telegram_token()
    if not token:
        print("[aviso] TELEGRAM_BOT_TOKEN nao configurado — pulando envio")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": CHAT_ID,
        "text": mensagem,
        "parse_mode": "Markdown",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                print("[telegram] mensagem enviada")
            else:
                print(f"[telegram] erro: {result.get('description')}")
    except Exception as e:
        print(f"[telegram] falha: {e}")


# ── Analise FIIs ────────────────────────────────────────────────────────

def predict_next_fii_payment(ticker: str, cur) -> dict | None:
    """Preve o proximo pagamento de um FII baseado no historico mensal.
    Assume pagamento mensal (~30 dias) pois Yahoo Finance pode retornar
    dados esparsos para FIIs (ex: 10 pontos em 2 anos em vez de 24)."""
    cur.execute("""
        SELECT data_pgto, valor
        FROM investimentos.proventos
        WHERE ticker = %s AND tipo = 'RENDIMENTO'
        ORDER BY data_pgto DESC
        LIMIT 12
    """, (ticker,))
    rows = cur.fetchall()

    if len(rows) < 2:
        return None

    last_payment = rows[0][0]  # mais recente

    # FIIs pagam mensalmente (~30 dias) — ignorar gaps nos dados do Yahoo
    # Calcular o dia medio de pagamento (ex: sempre dia 15)
    payment_days = [r[0].day for r in rows]
    typical_day = int(mean(payment_days))

    # Proximo pagamento: mesmo dia no mes seguinte ao ultimo pagamento
    next_month = last_payment.month + 1
    next_year = last_payment.year
    if next_month > 12:
        next_month = 1
        next_year += 1

    # Ajustar para o dia tipico (respeitando limites do mes)
    import calendar
    max_day = calendar.monthrange(next_year, next_month)[1]
    target_day = min(typical_day, max_day)
    next_payment = date(next_year, next_month, target_day)

    # Se ja passou, avancar mais meses
    while next_payment <= TODAY:
        next_month += 1
        if next_month > 12:
            next_month = 1
            next_year += 1
        max_day = calendar.monthrange(next_year, next_month)[1]
        target_day = min(typical_day, max_day)
        next_payment = date(next_year, next_month, target_day)

    # Data-com estimada: 5 dias uteis antes
    data_com = business_days_before(next_payment, 5)

    # Se data-com ja passou, pular para o mes seguinte
    if data_com <= TODAY:
        next_month += 1
        if next_month > 12:
            next_month = 1
            next_year += 1
        max_day = calendar.monthrange(next_year, next_month)[1]
        target_day = min(typical_day, max_day)
        next_payment = date(next_year, next_month, target_day)
        data_com = business_days_before(next_payment, 5)

    # Valor esperado: media dos ultimos 3 pagamentos (ignorando outliers)
    valores = sorted([float(r[1]) for r in rows[:6]])  # ordena, pega os 6 mais recentes
    if len(valores) >= 4:
        # Remove o maior e menor (outliers)
        valores = valores[1:-1]
    valor_esperado = float(mean(valores))

    return {
        "ticker": ticker,
        "data_pgto_prevista": next_payment,
        "data_com": data_com,
        "valor_esperado": valor_esperado,
        "intervalo_medio_dias": 30,  # FII = mensal
    }


def get_fii_preco_atual(ticker: str) -> float | None:
    """Busca preco atual de um FII via Yahoo Finance."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.SA?"
           f"range=5d&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        return data["chart"]["result"][0]["meta"].get("regularMarketPrice")
    except Exception:
        return None


# ── Analise Acoes ───────────────────────────────────────────────────────

def predict_next_stock_payment(ticker: str, cur) -> dict | None:
    """Preve a proxima janela de pagamento de uma acao baseado no historico."""
    cur.execute("""
        SELECT data_pgto, valor
        FROM investimentos.proventos
        WHERE ticker = %s AND tipo = 'DIVIDENDO'
        ORDER BY data_pgto DESC
        LIMIT 8
    """, (ticker,))
    rows = cur.fetchall()

    if len(rows) < 2:
        return None

    # Calcular intervalo medio entre pagamentos
    intervals = []
    for i in range(len(rows) - 1):
        gap = (rows[i][0] - rows[i + 1][0]).days
        intervals.append(gap)

    avg_interval = int(mean(intervals))
    last_payment = rows[0][0]

    # Proximo pagamento estimado
    next_payment = last_payment + timedelta(days=avg_interval)
    while next_payment <= TODAY:
        next_payment = next_payment + timedelta(days=avg_interval)

    # Data-com: 10 dias uteis antes
    data_com = business_days_before(next_payment, 10)

    # Valor: media dos ultimos
    valores = [r[1] for r in rows[:3]]
    valor_esperado = float(mean(valores))

    return {
        "ticker": ticker,
        "data_pgto_prevista": next_payment,
        "data_com": data_com,
        "valor_esperado": valor_esperado,
        "intervalo_medio_dias": avg_interval,
    }


# ── Indicadores Fundamentalistas ───────────────────────────────────────

def load_indicadores(cur) -> dict:
    """Carrega P/VP e DY mais recentes do Fundamentus."""
    cur.execute("""
        SELECT DISTINCT ON (ticker) ticker, pvp, dy_percentual
        FROM investimentos.indicadores_fundamentalistas
        ORDER BY ticker, data_referencia DESC
    """)
    return {r[0]: {"pvp": float(r[1]) if r[1] else None,
                    "dy": float(r[2]) if r[2] else None}
            for r in cur.fetchall()}


def calcular_score(r: dict, indicadores: dict) -> float:
    """Calcula score de atratividade (0-100). Maior = melhor."""
    score = 50  # base
    ind = indicadores.get(r["ticker"], {})

    # Abaixo do PM = +25
    if r["abaixo_pm"]:
        score += 25

    # P/VP < 1 = +15
    pvp = ind.get("pvp")
    if pvp and pvp < 1.0:
        score += 15
    elif pvp and pvp < 1.1:
        score += 5

    # Yield maior = mais pontos
    if r["yield_mensal_estimado"]:
        score += min(r["yield_mensal_estimado"] * 3, 15)

    return score


def calcular_quantidades(fiis: list, orcamento: float = 1000.0,
                         max_por_ativo: float = 300.0) -> list:
    """Distribui orcamento entre FIIs recomendados, priorizando score.
    Retorna lista com quantidade sugerida para cada FII."""
    if not fiis:
        return []

    # Ordenar por score decrescente
    ordenados = sorted(fiis, key=lambda r: r.get("score", 0), reverse=True)

    # Filtrar apenas os que tem preco
    candidatos = [r for r in ordenados if r.get("preco_atual") and r["preco_atual"] > 0]
    if not candidatos:
        return ordenados

    restante = orcamento
    resultado = []

    for i, r in enumerate(candidatos):
        restantes = len(candidatos) - i
        teto = min(max_por_ativo, restante / max(restantes, 1))
        qtd = int(teto / r["preco_atual"])
        if qtd < 1:
            qtd = 1 if restante >= r["preco_atual"] else 0

        custo = qtd * r["preco_atual"]
        r["qtd_sugerida"] = qtd
        r["custo_sugerido"] = round(custo, 2)
        restante -= custo
        resultado.append(r)

    # Se sobrou dinheiro, distribuir no de maior yield
    while restante > 0 and candidatos:
        melhor = max(candidatos, key=lambda r: r.get("yield_mensal_estimado", 0))
        if restante >= melhor["preco_atual"]:
            melhor["qtd_sugerida"] += 1
            melhor["custo_sugerido"] = round(melhor["custo_sugerido"] + melhor["preco_atual"], 2)
            restante -= melhor["preco_atual"]
        else:
            break

    return resultado


# ── Main ────────────────────────────────────────────────────────────────

def main():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()

    # Limpar agenda anterior
    cur.execute("DELETE FROM investimentos.agenda_compras WHERE status = 'PENDENTE'")

    # Carregar indicadores fundamentalistas
    indicadores = load_indicadores(cur)

    # Buscar todas as posicoes com preco medio
    cur.execute("""
        SELECT p.ticker, p.preco_medio, p.quantidade_total, a.tipo
        FROM investimentos.posicoes p
        JOIN investimentos.ativos a ON a.ticker = p.ticker
        ORDER BY a.tipo, p.ticker
    """)
    posicoes = {r[0]: {"pm": float(r[1]), "qtd": float(r[2]), "tipo": r[3]}
                for r in cur.fetchall()}

    recomendacoes = []

    for ticker, info in posicoes.items():
        tipo = info["tipo"]
        pm = info["pm"]

        if tipo == "FII":
            pred = predict_next_fii_payment(ticker, cur)
        elif tipo == "ACAO":
            pred = predict_next_stock_payment(ticker, cur)
        else:
            continue

        if not pred:
            continue

        # Buscar preco atual
        preco_atual = get_fii_preco_atual(ticker) if tipo == "FII" else None
        if preco_atual is None and tipo == "ACAO":
            url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.SA?"
                   f"range=5d&interval=1d")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    preco_atual = json.loads(r.read())["chart"]["result"][0]["meta"].get("regularMarketPrice")
            except Exception:
                pass

        # Yield estimado
        if preco_atual and preco_atual > 0:
            yield_estimado = (pred["valor_esperado"] / preco_atual) * 100
        else:
            yield_estimado = None

        # Criterios de atratividade
        abaixo_pm = preco_atual is not None and preco_atual < pm
        dias_ate_data_com = (pred["data_com"] - TODAY).days
        ind = indicadores.get(ticker, {})
        pvp = ind.get("pvp")
        dy_fund = ind.get("dy")

        # Filtrar
        if dias_ate_data_com <= 0:
            continue
        if tipo == "ACAO" and dias_ate_data_com < 60:
            continue

        rec = {
            "ticker": ticker,
            "comprar_ate": pred["data_com"],
            "data_pgto_prevista": pred["data_pgto_prevista"],
            "valor_provento_estimado": round(pred["valor_esperado"], 6),
            "yield_mensal_estimado": round(yield_estimado, 4) if yield_estimado else None,
            "preco_atual": round(preco_atual, 2) if preco_atual else None,
            "abaixo_pm": abaixo_pm,
            "dias_ate_data_com": dias_ate_data_com,
            "tipo": tipo,
            "pvp": round(pvp, 2) if pvp else None,
            "dy_fundamentus": round(dy_fund, 2) if dy_fund else None,
            "pm": round(pm, 2),
            "qtd_sugerida": 0,
            "custo_sugerido": 0.0,
        }
        rec["score"] = calcular_score(rec, indicadores)
        recomendacoes.append(rec)

    # Ordenar por score decrescente
    recomendacoes.sort(key=lambda r: r.get("score", 0), reverse=True)

    # Calcular quantidades sugeridas para FIIs do mes
    fiis_mes = [r for r in recomendacoes if r["tipo"] == "FII" and r["dias_ate_data_com"] <= 35]
    fiis_mes = calcular_quantidades(fiis_mes, orcamento=1000.0)

    # Atualizar recomendacoes com quantidades
    for r in recomendacoes:
        for f in fiis_mes:
            if r["ticker"] == f["ticker"]:
                r["qtd_sugerida"] = f.get("qtd_sugerida", 0)
                r["custo_sugerido"] = f.get("custo_sugerido", 0)

    # Separar para exibicao
    all_fiis = [r for r in recomendacoes if r["tipo"] == "FII" and r["dias_ate_data_com"] <= 35]
    acoes = [r for r in recomendacoes if r["tipo"] == "ACAO"]

    # Inserir no banco
    inserted = 0
    for r in recomendacoes:
        cur.execute("""
            INSERT INTO investimentos.agenda_compras
            (ticker, comprar_ate, data_pgto_prevista, valor_provento_estimado,
             yield_mensal_estimado, preco_atual, status, observacao)
            VALUES (%s, %s, %s, %s, %s, %s, 'PENDENTE', %s)
        """, (
            r["ticker"], r["comprar_ate"], r["data_pgto_prevista"],
            r["valor_provento_estimado"], r["yield_mensal_estimado"],
            r["preco_atual"],
            f'{"ABAIXO_DO_PM" if r["abaixo_pm"] else "ACIMA_DO_PM"}'
            f' | P/VP={r["pvp"]} | score={r["score"]:.0f}'
            f' | qtd_sug={r["qtd_sugerida"]} | data-com em {r["dias_ate_data_com"]}d',
        ))
        inserted += 1

    cur.close()
    conn.close()

    # ── Montar mensagem Telegram ────────────────────────────────────────
    if not recomendacoes:
        msg = (
            f"*📅 Agenda de Compras — {TODAY.strftime('%d/%m/%Y')}*\n\n"
            "Nenhuma recomendacao de compra nesta semana.\n"
            "Proximas datas-com ainda distantes ou dados insuficientes."
        )
        send_telegram(msg)
        print(msg)
        return

    lines = [f"*📅 Agenda de Compras — {TODAY.strftime('%d/%m/%Y')}*\n"]

    # Secao FIIs com sugestao de quantidade
    if all_fiis:
        total_fii = sum(r["custo_sugerido"] for r in all_fiis)
        lines.append(f"*🏢 FIIs — Aporte sugerido: ~R$ {total_fii:.0f} (orcamento: R$ 1.000)*\n")
        for r in all_fiis:
            emoji = "🟢" if r["abaixo_pm"] else "🟡"
            pvp_str = f"P/VP={r['pvp']:.2f}" if r["pvp"] else ""
            dy_str = f"DY fund={r['dy_fundamentus']:.1f}%" if r["dy_fundamentus"] else ""

            line = (
                f"{emoji} *{r['ticker']}* — comprar ate *{r['comprar_ate'].strftime('%d/%m')}* "
                f"(pgto ~{r['data_pgto_prevista'].strftime('%d/%m')})\n"
                f"  R$ {r['preco_atual']:.2f} (PM: R$ {r['pm']:.2f}) | {pvp_str} {dy_str}\n"
            )
            if r["qtd_sugerida"] > 0:
                line += f"  ➤ *Comprar {r['qtd_sugerida']} cota{'s' if r['qtd_sugerida'] > 1 else ''}* "
                line += f"= R$ {r['custo_sugerido']:.2f} "
                line += f"| provento est: R$ {r['valor_provento_estimado']:.4f} "
                line += f"| yield mes: {r['yield_mensal_estimado']:.2f}%"
            else:
                line += f"  provento est: R$ {r['valor_provento_estimado']:.4f} "
                line += f"| yield mes: {r['yield_mensal_estimado']:.2f}%"
            lines.append(line)

    # Secao Acoes
    if acoes:
        if all_fiis:
            lines.append("")
        lines.append("*📈 Acoes — programar compra com 2-6 meses de antecedencia:*\n")
        for r in acoes:
            emoji = "🟢" if r["abaixo_pm"] else "🟡"
            pvp_str = f"P/VP={r['pvp']:.2f}" if r["pvp"] else ""
            dy_str = f"DY={r['dy_fundamentus']:.1f}%" if r["dy_fundamentus"] else ""

            lines.append(
                f"{emoji} *{r['ticker']}* — data-com: *{r['comprar_ate'].strftime('%d/%m/%Y')}* "
                f"({r['dias_ate_data_com']} dias)\n"
                f"  R$ {r['preco_atual']:.2f} (PM: R$ {r['pm']:.2f}) | {pvp_str} {dy_str}\n"
                f"  provento est: R$ {r['valor_provento_estimado']:.4f} "
                f"| yield: {r['yield_mensal_estimado']:.2f}% | score: {r['score']:.0f}"
            )

    lines.append(f"\n_🟢 = abaixo do PM (oportunidade) | 🟡 = acima do PM_")
    lines.append(f"_Score: PM abaixo + P/VP<1 + yield | Orcamento referencia: R$ 1.000/mes_")
    lines.append(f"_Proxima atualizacao: proxima segunda-feira_")

    msg = "\n".join(lines)
    send_telegram(msg)
    print(f"\n=== {inserted} recomendacoes geradas ===")
    print(msg)


if __name__ == "__main__":
    main()