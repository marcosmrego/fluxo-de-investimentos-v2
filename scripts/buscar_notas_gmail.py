#!/usr/bin/env python3
"""
Busca notas de negociação XP no Gmail e processa automaticamente.

Fluxo:
  1. Conecta no Gmail (token: google_token_notas.json)
  2. Busca emails de noreply@xpi.com.br com assunto "Nota de Negociação"
  3. Baixa PDFs anexos
  4. Chama processar_nota_xp.py para parse + insert no banco
  5. Marca email como lido após processamento

Uso:
  python buscar_notas_gmail.py               # processa emails não lidos
  python buscar_notas_gmail.py --dias 7      # busca últimos 7 dias
  python buscar_notas_gmail.py --dry-run     # só lista, não processa
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import psycopg2

# ─── CONFIG ────────────────────────────────────────────────────────────────

GMAIL_TOKEN = Path("/home/hermes/.hermes/google_token_notas.json")
GMAIL_SECRET = Path("/home/hermes/.hermes/google_client_secret_notas.json")
DOWNLOAD_DIR = Path("/tmp/notas_xp")
PROCESSOR_SCRIPT = Path("/opt/data/fluxo-de-investimentos-v2/scripts/processar_nota_xp.py")
XP_SENHA = "822"

REMETENTE_XP = "noreply@xpi.com.br"
ASSUNTO_XP = "Nota de Negociação"


def _init_gmail():
    """Inicializa a API do Gmail com o token da conta de notas."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    if not GMAIL_TOKEN.exists():
        raise FileNotFoundError(
            f"Token do Gmail não encontrado: {GMAIL_TOKEN}\n"
            "Execute a autenticação OAuth primeiro."
        )

    with open(GMAIL_TOKEN) as f:
        token_data = json.load(f)

    creds = Credentials.from_authorized_user_info(token_data)
    return build('gmail', 'v1', credentials=creds)


def buscar_emails_xp(service, dias: int = 7) -> list:
    """Busca emails de notas XP nos últimos N dias."""
    query = (
        f"from:{REMETENTE_XP} "
        f"subject:\"{ASSUNTO_XP}\" "
        f"has:attachment filename:pdf "
        f"newer_than:{dias}d"
    )

    results = service.users().messages().list(
        userId='me', q=query, maxResults=20
    ).execute()

    messages = results.get('messages', [])
    print(f"[GMAIL] {len(messages)} email(s) de notas XP encontrados ({dias}d)")

    emails = []
    for msg in messages:
        full = service.users().messages().get(
            userId='me', id=msg['id'], format='metadata',
            metadataHeaders=['From', 'Subject', 'Date']
        ).execute()

        headers = {
            h['name'].lower(): h['value']
            for h in full['payload'].get('headers', [])
        }

        label_ids = full.get('labelIds', [])
        is_unread = 'UNREAD' in label_ids

        # Extrai data do pregão do assunto: "operações realizadas por você no dia 16/07/2026"
        data_pregao = None
        subject = headers.get('subject', '')
        m = re.search(r'dia (\d{2}/\d{2}/\d{4})', subject)
        if m:
            data_pregao = datetime.strptime(m.group(1), '%d/%m/%Y').date()

        emails.append({
            'id': msg['id'],
            'thread_id': full.get('threadId'),
            'from': headers.get('from', ''),
            'subject': subject,
            'date': headers.get('date', ''),
            'is_unread': is_unread,
            'data_pregao': data_pregao,
        })

    return emails


def baixar_anexo_pdf(service, msg_id: str) -> Optional[Path]:
    """Baixa o primeiro anexo PDF do email. Retorna o path ou None."""
    msg = service.users().messages().get(userId='me', id=msg_id).execute()

    for part in msg['payload'].get('parts', []):
        filename = part.get('filename', '')
        if not filename.lower().endswith('.pdf'):
            continue

        attachment_id = part['body'].get('attachmentId')
        if not attachment_id:
            continue

        attachment = service.users().messages().attachments().get(
            userId='me', messageId=msg_id, id=attachment_id
        ).execute()

        data = base64.urlsafe_b64decode(attachment['data'])
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        pdf_path = DOWNLOAD_DIR / filename
        pdf_path.write_bytes(data)
        return pdf_path

    return None


def marcar_como_lido(service, msg_id: str):
    """Remove o label UNREAD do email."""
    service.users().messages().modify(
        userId='me', id=msg_id,
        body={'removeLabelIds': ['UNREAD']}
    ).execute()


def processar_pdf(pdf_path: Path, email_id: str) -> bool:
    """Chama o script processar_nota_xp.py para o PDF."""
    cmd = [
        sys.executable, str(PROCESSOR_SCRIPT),
        str(pdf_path),
        "--senha", XP_SENHA,
        "--email-id", email_id,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    print(result.stdout)
    if result.returncode != 0:
        print(f"[ERRO] {result.stderr}")
        return False
    return "processada com sucesso" in result.stdout


def main():
    parser = argparse.ArgumentParser(
        description="Busca notas XP no Gmail e processa automaticamente."
    )
    parser.add_argument("--dias", type=int, default=7,
                        help="Buscar emails dos últimos N dias (default: 7)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Apenas lista emails, não processa")
    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"Busca de Notas XP — Gmail → Parser → Postgres")
    print(f"{'='*60}")

    service = _init_gmail()
    emails = buscar_emails_xp(service, args.dias)

    if not emails:
        print("Nenhum email de nota XP encontrado.")
        return

    processados = 0
    for email in emails:
        print(f"\n---")
        print(f"Email: {email['subject']}")
        print(f"Data:  {email['date']}")
        print(f"Lido:  {'Não' if email['is_unread'] else 'Sim'}")
        if email['data_pregao']:
            print(f"Pregão:{email['data_pregao']}")

        if args.dry_run:
            continue

        # Baixar PDF
        print("Baixando PDF...", end=" ")
        pdf_path = baixar_anexo_pdf(service, email['id'])
        if not pdf_path:
            print("Nenhum PDF encontrado!")
            continue
        print(f"OK ({pdf_path.stat().st_size} bytes)")

        # Processar
        if processar_pdf(pdf_path, email['id']):
            processados += 1
            # Marcar como lido (ignora erro se token não tem permissão modify)
            if email['is_unread']:
                try:
                    marcar_como_lido(service, email['id'])
                    print("  [GMAIL] Marcado como lido")
                except Exception:
                    pass  # Token readonly — sem permissão modify

        # Limpar PDF temporário
        pdf_path.unlink(missing_ok=True)

    # Gerar resumo para Telegram
    print(f"\n{'='*60}")
    if args.dry_run:
        print(f"Dry-run: {len(emails)} email(s) encontrados (nada foi processado)")
    elif processados > 0:
        print(f"{processados} nota(s) processada(s). Gerando resumo...")
        try:
            conn_db = _conectar_banco()
            resumo = gerar_resumo(conn_db)
            conn_db.close()
            if resumo:
                print(resumo)
        except Exception as e:
            print(f"[ERRO ao gerar resumo]: {e}")
    else:
        print("Nenhuma nota nova processada.")


def gerar_resumo(conn) -> str:
    """Gera resumo das operações processadas nas últimas 24h."""
    cur = conn.cursor()

    # Notas processadas hoje
    cur.execute("""
        SELECT n.numero_nota, n.data_pregao,
               COUNT(o.id) as num_ops
        FROM investimentos.notas_negociacao n
        JOIN investimentos.operacoes o ON o.nota_id = n.id
        WHERE n.criado_em >= NOW() - INTERVAL '24 hours'
        GROUP BY n.numero_nota, n.data_pregao, n.criado_em
        ORDER BY n.criado_em DESC
    """)
    notas = cur.fetchall()

    if not notas:
        cur.close()
        return None

    # Operações das notas recentes
    cur.execute("""
        SELECT o.ticker, o.tipo_operacao, o.quantidade, o.preco_unitario,
               o.valor_operacao, n.data_pregao
        FROM investimentos.operacoes o
        JOIN investimentos.notas_negociacao n ON n.id = o.nota_id
        WHERE n.criado_em >= NOW() - INTERVAL '24 hours'
        ORDER BY n.data_pregao DESC, o.linha_seq
    """)
    ops = cur.fetchall()
    cur.close()

    linhas = []
    linhas.append("*📊 Notas XP Processadas*")
    linhas.append("")

    for nota_num, data_pregao, num_ops in notas:
        linhas.append(f"📝 *Nota {nota_num}* — Pregão {data_pregao.strftime('%d/%m')}")
        for op in ops:
            if data_pregao != op[5]:
                continue
            ticker = op[0] or "???"
            tipo = "🟢" if op[1] == "COMPRA" else "🔴"
            linhas.append(f"  {tipo} {ticker}: {int(op[2])} un × R$ {float(op[3]):.2f} = R$ {float(op[4]):.2f}")
        linhas.append("")

    # Posições atualizadas
    cur2 = conn.cursor()
    cur2.execute("""
        SELECT ticker, quantidade_total, preco_medio, custo_total
        FROM investimentos.posicoes
        WHERE ticker IS NOT NULL AND ticker != 'null' AND quantidade_total > 0
        ORDER BY custo_total DESC
    """)
    posicoes = cur2.fetchall()
    cur2.close()

    if posicoes:
        linhas.append("*💼 Carteira Atualizada*")
        total = 0
        for ticker, qtd, pm, custo in posicoes:
            total += float(custo or 0)
            linhas.append(f"  {ticker}: {int(qtd)} un | PM R$ {float(pm):.2f} | Total R$ {float(custo):.2f}")
        linhas.append(f"  ─────────────────────")
        linhas.append(f"  *Custo total: R$ {total:,.2f}*")

    return "\n".join(linhas)


def _conectar_banco():
    """Conecta ao Postgres para consulta (read-only)."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from db_utils import DB_CONFIG
    return psycopg2.connect(**DB_CONFIG)


if __name__ == "__main__":
    main()