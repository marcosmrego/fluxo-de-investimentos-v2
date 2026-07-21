#!/usr/bin/env python3
"""
Processador de Notas de Corretagem XP.

Fluxo:
  1. Recebe PDF(s) de nota XP (arquivo ou diretório)
  2. Envia para API parser (parserxp.expansao-ai.com.br)
  3. Insere no Postgres: notas_negociacao → operacoes → operacoes_consolidadas_nota → posicoes
  4. Atualiza emails_processados (controle de duplicatas)

Uso:
  python processar_nota_xp.py nota.pdf                          # arquivo único
  python processar_nota_xp.py nota.pdf --senha XP123456         # com senha
  python processar_nota_xp.py ./notas/                          # diretório
  python processar_nota_xp.py nota.pdf --email-id msg123        # vinculando a email
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, date, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values
import requests

# ─── CONFIG ────────────────────────────────────────────────────────────────

API_PARSER_URL = "https://parserxp.expansao-ai.com.br/parse/xp-note"

from db_utils import DB_CONFIG

CRED_FILE = Path("/home/hermes/.hermes/.env")


def _get_db_password() -> str:
    """Extrai a senha do banco do arquivo .env ou do script analise_acoes_diaria.py."""
    import re

    # 1. Tenta do .env
    if CRED_FILE.exists():
        content = CRED_FILE.read_text()
        for key in ("DB_PASSWORD", "POSTGRES_PASSWORD", "PGPASSWORD"):
            pattern = rf"^{key}=(.+)$"
            m = re.search(pattern, content, re.MULTILINE)
            if m:
                return m.group(1).strip().strip('"').strip("'")

    # 2. Fallback: extrai do script analise_acoes_diaria.py
    script_path = Path("/home/hermes/.hermes/workspace/analise_acoes_diaria.py")
    if script_path.exists():
        content = script_path.read_text()
        m = re.search(r'"password":\s*"([^"]+)"', content)
        if m:
            return m.group(1)

    raise ValueError("Senha do banco não encontrada")


# ─── RESOLVEDOR DE TICKERS ─────────────────────────────────────────────────

XP_NOTAS_SENHA = "822"

def _carregar_mapeamento_ativos(conn) -> dict:
    """
    Constrói um mapeamento palavra_chave → ticker a partir da tabela ativos.
    Ex: 'JHSF' → 'JHSF3', 'KLABIN' → 'KLBN3', 'MARCOPOLO' → 'POMO4'
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT ticker, nome FROM investimentos.ativos WHERE monitorar = TRUE"
    )
    rows = cur.fetchall()
    cur.close()

    mapeamento = {}
    for ticker, nome in rows:
        # Adiciona o próprio ticker (sem dígitos finais) como chave
        base = ticker.rstrip('0123456789')  # Remove todos os dígitos do final
        if base and len(base) >= 3:
            mapeamento[base.upper()] = ticker

        # Adiciona o ticker completo também
        mapeamento[ticker.upper()] = ticker

        # Extrai palavras do nome
        if nome:
            palavras = nome.upper().split()
            for p in palavras:
                if len(p) >= 3 and p not in ("S/A", "ON", "NM", "PN", "N1", "N2", "PART", "UNT", "EDJ", "EDR", "DR1", "DR2", "DR3", "CI", "EB", "ATZ", "ATZ"):
                    mapeamento[p] = ticker

    return mapeamento


def resolver_tickers(operacoes: list, conn) -> list:
    """
    Para operações com ticker=None, tenta resolver via tabela ativos.
    Usa a primeira palavra da descrição como chave de busca.
    Retorna a lista de operações com tickers preenchidos.
    """
    mapeamento = _carregar_mapeamento_ativos(conn)
    resolvidos = 0

    for op in operacoes:
        if op.get("ticker"):
            continue

        desc = (op.get("descricao_ativo") or "").upper().strip()
        if not desc:
            continue

        primeira = desc.split()[0] if desc.split() else ""

        # Estratégia 1: match exato da primeira palavra
        if primeira in mapeamento:
            op["ticker"] = mapeamento[primeira]
            resolvidos += 1
            continue

        # Estratégia 2: match parcial (chave está contida na descrição)
        for chave, ticker in mapeamento.items():
            if chave in desc:
                op["ticker"] = ticker
                resolvidos += 1
                break
        else:
            # Estratégia 3: quebrar palavra grudada (ex: "BBSEGURIDADE" → "BB", "SEGURIDADE")
            # e tentar match com cada fragmento
            for chave, ticker in mapeamento.items():
                if len(chave) >= 4 and chave in primeira:
                    op["ticker"] = ticker
                    resolvidos += 1
                    break

    if resolvidos > 0:
        print(f"  [RESOLVE] {resolvidos} ticker(s) resolvidos via tabela ativos")

    return operacoes


# ─── PARSER (via API) ──────────────────────────────────────────────────────

def parse_pdf(pdf_path: Path, password: Optional[str] = None) -> dict:
    """Envia PDF para API parser e retorna o JSON parseado."""
    print(f"  [PARSER] Enviando {pdf_path.name}...", end=" ")

    with open(pdf_path, "rb") as f:
        files = {"file": (pdf_path.name, f, "application/pdf")}
        data = {}
        if password:
            data["password"] = password

        try:
            resp = requests.post(API_PARSER_URL, files=files, data=data, timeout=60)
            resp.raise_for_status()
            result = resp.json()
        except requests.RequestException as e:
            print(f"ERRO: {e}")
            raise

    if not result.get("success"):
        error = result.get("error", "Erro desconhecido")
        print(f"FALHA: {error}")
        raise ValueError(f"Parser retornou erro: {error}")

    header = result.get("header", {})
    print(f"OK (nota {header.get('numero_nota', '?')}, "
          f"{len(result.get('operacoes_brutas', []))} operações)")
    return result


# ─── BANCO DE DADOS ────────────────────────────────────────────────────────

def _to_numeric(value) -> Optional[Decimal]:
    """Converte valor para Decimal (compatível com NUMERIC do Postgres)."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return None


def _to_int(value) -> Optional[int]:
    if value is None:
        return None
    return int(value)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _consolidate_ops(operacoes: list) -> list:
    """Consolida operações por ticker + tipo + preço unitário."""
    consolidated = {}
    for op in operacoes:
        key = (op.get("ticker"), op.get("tipo_operacao"), op.get("preco_unitario"))
        if key not in consolidated:
            consolidated[key] = {
                "ticker": op.get("ticker"),
                "descricao_ativo": op.get("descricao_ativo"),
                "tipo_operacao": op.get("tipo_operacao"),
                "tipo_mercado": op.get("tipo_mercado"),
                "preco_unitario": _to_numeric(op.get("preco_unitario")),
                "quantidade_total": 0,
                "valor_total": Decimal("0.00"),
            }
        consolidated[key]["quantidade_total"] += (_to_int(op.get("quantidade")) or 0)
        consolidated[key]["valor_total"] += Decimal(str(op.get("valor_operacao") or 0))
    result = []
    for item in consolidated.values():
        item["valor_total"] = float(item["valor_total"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        result.append(item)
    return result


def conectar():
    """Conecta ao banco Postgres."""
    pw = _get_db_password()
    config = {**DB_CONFIG, "password": pw}
    conn = psycopg2.connect(**config)
    conn.autocommit = False
    return conn


def nota_ja_processada(conn, numero_nota: str) -> bool:
    """Verifica se a nota já foi processada (por número da nota)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM investimentos.notas_negociacao WHERE numero_nota = %s LIMIT 1",
        (numero_nota,)
    )
    exists = cur.fetchone() is not None
    cur.close()
    return exists


def inserir_nota(conn, parsed: dict, email_id: Optional[str] = None,
                 arquivo_nome: Optional[str] = None) -> uuid.UUID:
    """Insere registro em notas_negociacao e retorna o ID."""
    header = parsed["header"]
    fin = parsed["financeiro"]

    nota_id = uuid.uuid4()
    agora = _now()

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO investimentos.notas_negociacao (
            id, email_id, corretora, numero_nota, data_pregao,
            cliente_nome, codigo_cliente, arquivo_nome,
            valor_liquido_operacoes, valor_liquido_operacoes_dc,
            total_cblc, total_cblc_dc,
            total_bovespa_soma, total_bovespa_soma_dc,
            total_custos_despesas, total_custos_despesas_dc,
            liquido_para_data, liquido_para_valor, liquido_para_dc,
            raw_text_preview, criado_em, atualizado_em
        ) VALUES (
            %(id)s, %(email_id)s, %(corretora)s, %(numero_nota)s, %(data_pregao)s,
            %(cliente)s, %(codigo_cliente)s, %(arquivo_nome)s,
            %(vl_ops)s, %(vl_ops_dc)s,
            %(cblc)s, %(cblc_dc)s,
            %(bovespa)s, %(bovespa_dc)s,
            %(custos)s, %(custos_dc)s,
            %(liq_data)s, %(liq_valor)s, %(liq_dc)s,
            %(raw)s, %(criado_em)s, %(atualizado_em)s
        )
    """, {
        "id": str(nota_id),
        "email_id": email_id,
        "corretora": header.get("corretora", "XP INVESTIMENTOS"),
        "numero_nota": header.get("numero_nota"),
        "data_pregao": header.get("data_pregao"),
        "cliente": header.get("cliente"),
        "codigo_cliente": header.get("codigo_cliente"),
        "arquivo_nome": arquivo_nome,
        "vl_ops": _to_numeric(_get_fin_valor(fin, "valor_liquido_operacoes")),
        "vl_ops_dc": _get_fin_dc(fin, "valor_liquido_operacoes"),
        "cblc": _to_numeric(_get_fin_valor(fin, "total_cblc")),
        "cblc_dc": _get_fin_dc(fin, "total_cblc"),
        "bovespa": _to_numeric(_get_fin_valor(fin, "total_bovespa_soma")),
        "bovespa_dc": _get_fin_dc(fin, "total_bovespa_soma"),
        "custos": _to_numeric(_get_fin_valor(fin, "total_custos_despesas")),
        "custos_dc": _get_fin_dc(fin, "total_custos_despesas"),
        "liq_data": fin.get("liquido_para_data"),
        "liq_valor": _to_numeric(fin.get("liquido_para_valor")),
        "liq_dc": fin.get("liquido_para_dc"),
        "raw": parsed.get("raw_text_preview", "")[:2000],
        "criado_em": agora,
        "atualizado_em": agora,
    })
    cur.close()
    print(f"  [DB] Nota {header.get('numero_nota')} inserida (id={nota_id})")
    return nota_id


def _get_fin_valor(fin: dict, key: str):
    """Extrai valor numérico do dict financeiro (formato {'valor': X, 'dc': 'D'})."""
    item = fin.get(key)
    if item is None:
        return None
    if isinstance(item, dict):
        return item.get("valor")
    return item


def _get_fin_dc(fin: dict, key: str) -> Optional[str]:
    item = fin.get(key)
    if isinstance(item, dict):
        return item.get("dc")
    return None


def inserir_operacoes(conn, nota_id: uuid.UUID, operacoes: list):
    """Insere operações brutas em operacoes."""
    if not operacoes:
        print("  [DB] Nenhuma operação para inserir")
        return

    agora = _now()
    rows = []
    for i, op in enumerate(operacoes, start=1):
        rows.append((
            str(uuid.uuid4()),
            str(nota_id),
            i,  # linha_seq
            op.get("negociacao"),
            op.get("tipo_operacao"),
            op.get("tipo_mercado"),
            op.get("descricao_ativo"),
            op.get("ticker"),
            op.get("observacoes"),
            _to_int(op.get("quantidade")),
            _to_numeric(op.get("preco_unitario")),
            _to_numeric(op.get("valor_operacao")),
            op.get("debito_credito"),
            agora,
        ))

    cur = conn.cursor()
    execute_values(cur, """
        INSERT INTO investimentos.operacoes (
            id, nota_id, linha_seq, negociacao, tipo_operacao,
            tipo_mercado, descricao_ativo, ticker, observacoes,
            quantidade, preco_unitario, valor_operacao, debito_credito,
            criado_em
        ) VALUES %s
    """, rows)
    cur.close()
    print(f"  [DB] {len(rows)} operações inseridas")


def inserir_consolidadas(conn, nota_id: uuid.UUID, consolidadas: list):
    """Insere operações consolidadas em operacoes_consolidadas_nota."""
    if not consolidadas:
        print("  [DB] Nenhuma consolidação para inserir")
        return

    agora = _now()
    rows = []
    for c in consolidadas:
        rows.append((
            str(uuid.uuid4()),
            str(nota_id),
            c.get("ticker"),
            c.get("descricao_ativo"),
            c.get("tipo_operacao"),
            c.get("tipo_mercado"),
            _to_numeric(c.get("preco_unitario")),
            _to_int(c.get("quantidade_total")),
            _to_numeric(c.get("valor_total")),
            agora,
        ))

    cur = conn.cursor()
    execute_values(cur, """
        INSERT INTO investimentos.operacoes_consolidadas_nota (
            id, nota_id, ticker, descricao_ativo, tipo_operacao,
            tipo_mercado, preco_unitario, quantidade_total, valor_total,
            criado_em
        ) VALUES %s
    """, rows)
    cur.close()
    print(f"  [DB] {len(rows)} consolidações inseridas")


def atualizar_posicoes(conn, operacoes: list):
    """
    Atualiza a tabela de posicoes com base nas operações processadas.
    - COMPRA: aumenta quantidade e recalcula preço médio
    - VENDA: reduz quantidade (preço médio se mantém)
    """
    if not operacoes:
        return

    cur = conn.cursor()
    atualizadas = 0

    for op in operacoes:
        ticker = op.get("ticker")
        if not ticker:
            continue

        quantidade = _to_int(op.get("quantidade", 0)) or 0
        preco_unitario = _to_numeric(op.get("preco_unitario", 0)) or Decimal("0")
        valor_operacao = _to_numeric(op.get("valor_operacao", 0)) or Decimal("0")
        tipo = op.get("tipo_operacao", "")

        # Busca posição atual (se existir)
        cur.execute(
            "SELECT id, quantidade_total, preco_medio, custo_total "
            "FROM investimentos.posicoes WHERE ticker = %s",
            (ticker,)
        )
        row = cur.fetchone()

        if tipo == "COMPRA":
            if row:
                pos_id, qtd_antiga, pm_antigo, custo_antigo = row
                qtd_antiga = int(qtd_antiga or 0)
                pm_antigo = Decimal(str(pm_antigo or 0))
                custo_antigo = Decimal(str(custo_antigo or 0))

                nova_qtd = qtd_antiga + quantidade
                novo_custo = custo_antigo + valor_operacao
                novo_pm = (novo_custo / nova_qtd).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )

                cur.execute("""
                    UPDATE investimentos.posicoes
                    SET quantidade_total = %s, preco_medio = %s,
                        custo_total = %s, atualizado_em = %s
                    WHERE id = %s
                """, (nova_qtd, novo_pm, novo_custo, _now(), pos_id))
            else:
                # Nova posição
                cur.execute("""
                    INSERT INTO investimentos.posicoes (
                        id, ticker, quantidade_total, preco_medio,
                        custo_total, atualizado_em
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    str(uuid.uuid4()),
                    ticker,
                    quantidade,
                    preco_unitario,
                    valor_operacao,
                    _now(),
                ))

            atualizadas += 1

        elif tipo == "VENDA":
            if row:
                pos_id, qtd_antiga, pm_antigo, custo_antigo = row
                qtd_antiga = int(qtd_antiga or 0)
                pm_antigo = Decimal(str(pm_antigo or 0))
                custo_antigo = Decimal(str(custo_antigo or 0))

                nova_qtd = qtd_antiga - quantidade
                if nova_qtd <= 0:
                    # Remove posição se zerou
                    cur.execute(
                        "DELETE FROM investimentos.posicoes WHERE id = %s",
                        (pos_id,)
                    )
                else:
                    # Custo reduz proporcionalmente
                    custo_removido = pm_antigo * Decimal(str(quantidade))
                    novo_custo = custo_antigo - custo_removido
                    cur.execute("""
                        UPDATE investimentos.posicoes
                        SET quantidade_total = %s, custo_total = %s,
                            atualizado_em = %s
                        WHERE id = %s
                    """, (nova_qtd, novo_custo, _now(), pos_id))

                atualizadas += 1

    cur.close()
    if atualizadas > 0:
        print(f"  [DB] {atualizadas} posições atualizadas")


def registrar_email_processado(conn, email_id: str, arquivo_nome: str,
                               status: str, erro: Optional[str] = None,
                               registro_id: Optional[str] = None):
    """Registra ou atualiza entrada em emails_processados."""
    cur = conn.cursor()
    agora = _now()
    rid = registro_id or str(uuid.uuid4())
    cur.execute("""
        INSERT INTO investimentos.emails_processados (
            id, message_id, arquivo_nome, status_processamento,
            erro_processamento, criado_em, atualizado_em
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE
        SET status_processamento = EXCLUDED.status_processamento,
            erro_processamento = EXCLUDED.erro_processamento,
            atualizado_em = EXCLUDED.atualizado_em
    """, (
        rid,
        email_id,
        arquivo_nome,
        status,
        erro,
        agora,
        agora,
    ))
    cur.close()


# ─── FLUXO PRINCIPAL ───────────────────────────────────────────────────────

def processar_pdf(pdf_path: Path, conn, password: Optional[str] = None,
                  email_id: Optional[str] = None) -> bool:
    """
    Processa um único PDF de nota XP:
      1. Parse via API
      2. Resolve tickers ausentes
      3. Verifica duplicata
      4. Insere no banco (nota + operações + consolidadas + posições)
    Retorna True se sucesso, False se pulado (duplicata).
    """
    # Converte message_id do Gmail em UUID determinístico
    email_uuid = None
    if email_id:
        email_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"gmail:{email_id}"))

    print(f"\n{'='*60}")
    print(f"Processando: {pdf_path.name}")

    # 1. Parse
    parsed = parse_pdf(pdf_path, password)
    header = parsed.get("header", {})
    numero_nota = header.get("numero_nota")

    if not numero_nota:
        print("  [ERRO] Número da nota não encontrado no PDF")
        return False

    # 2. Resolve tickers ausentes
    operacoes_brutas = parsed.get("operacoes_brutas", [])
    operacoes_brutas = resolver_tickers(operacoes_brutas, conn)
    parsed["operacoes_brutas"] = operacoes_brutas

    # Re-consolida com tickers resolvidos
    parsed["operacoes_consolidadas"] = _consolidate_ops(operacoes_brutas)

    # 3. Verifica duplicata
    if nota_ja_processada(conn, numero_nota):
        print(f"  [PULAR] Nota {numero_nota} já existe no banco")
        return False

    # 3. Insere no banco (transação única)
    nota_id = None
    try:
        # Registra email processado primeiro (FK constraint)
        if email_id:
            registrar_email_processado(conn, email_id, pdf_path.name,
                                       "processando", registro_id=email_uuid)

        nota_id = inserir_nota(conn, parsed, email_id=email_uuid,
                               arquivo_nome=pdf_path.name)
        inserir_operacoes(conn, nota_id, parsed.get("operacoes_brutas", []))
        inserir_consolidadas(conn, nota_id, parsed.get("operacoes_consolidadas", []))
        atualizar_posicoes(conn, parsed.get("operacoes_brutas", []))
        conn.commit()

        if email_id:
            registrar_email_processado(conn, email_id, pdf_path.name,
                                       "sucesso", registro_id=email_uuid)

        print(f"  [OK] Nota {numero_nota} processada com sucesso")
        return True

    except Exception:
        conn.rollback()
        print(f"  [ERRO] Falha ao processar nota {numero_nota} — rollback executado")
        if email_id:
            try:
                registrar_email_processado(conn, email_id, pdf_path.name,
                                           "erro", str(sys.exc_info()[1]),
                                           registro_id=email_uuid)
            except Exception:
                pass
        raise


def find_pdfs(path: Path) -> list[Path]:
    """Encontra todos os PDFs em um caminho (arquivo ou diretório)."""
    if path.is_file():
        if path.suffix.lower() == ".pdf":
            return [path]
        else:
            raise ValueError(f"Arquivo não é PDF: {path}")

    if path.is_dir():
        pdfs = sorted(path.glob("*.pdf")) + sorted(path.glob("*.PDF"))
        return pdfs

    raise FileNotFoundError(f"Caminho não encontrado: {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Processa notas de corretagem XP e insere no banco Postgres.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  %(prog)s nota.pdf
  %(prog)s nota.pdf --senha XP123456
  %(prog)s ./notas/
  %(prog)s nota.pdf --email-id msg_abc123
  %(prog)s ./notas/ --dry-run          (só faz parse, não insere)
        """
    )
    parser.add_argument("pdf", help="Arquivo PDF ou diretório com PDFs de notas XP")
    parser.add_argument("--senha", "--password", default=None,
                        help="Senha do PDF (se protegido)")
    parser.add_argument("--email-id", default=None,
                        help="ID do email de origem (para rastreamento)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Apenas faz o parse, sem inserir no banco")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    pdfs = find_pdfs(pdf_path)

    if not pdfs:
        print(f"Nenhum PDF encontrado em: {pdf_path}")
        sys.exit(1)

    print(f"Encontrados {len(pdfs)} PDF(s) para processar")

    if args.dry_run:
        for p in pdfs:
            try:
                parsed = parse_pdf(p, args.senha)
                print(f"  Header: {json.dumps(parsed.get('header', {}), indent=2)}")
                print(f"  Operações: {len(parsed.get('operacoes_brutas', []))}")
                for op in parsed.get("operacoes_brutas", []):
                    print(f"    - {op.get('ticker', '?')} {op.get('tipo_operacao')} "
                          f"Qtd={op.get('quantidade')} Preço={op.get('preco_unitario')}")
            except Exception as e:
                print(f"  ERRO: {e}")
        return

    conn = conectar()
    try:
        processados = 0
        for p in pdfs:
            try:
                if processar_pdf(p, conn, args.senha, args.email_id):
                    processados += 1
            except Exception as e:
                print(f"  [ERRO FATAL] {p.name}: {e}")
                # Continua com próximos PDFs

        print(f"\n{'='*60}")
        print(f"Concluído: {processados}/{len(pdfs)} PDF(s) processados com sucesso")
    finally:
        conn.close()


if __name__ == "__main__":
    main()