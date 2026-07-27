"""Configuração do banco de dados — fonte canônica: vault de credenciais."""
import os
from pathlib import Path

# 1. Tenta carregar .env do projeto (espelho do vault)
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass

# 2. Fallback: se senha vazia, busca direto no vault
_password = os.environ.get("DB_PASSWORD", "")
if not _password:
    _vault_pg = Path("/opt/data/vault/credentials/postgres.env")
    if _vault_pg.exists():
        for line in _vault_pg.read_text().split("\n"):
            if line.startswith("DB_PASSWORD="):
                _password = line.split("=", 1)[1].strip()
                break

DB_CONFIG = {
    "host": os.environ.get("DB_HOST") or "212.85.22.227",
    "port": int(os.environ.get("DB_PORT") or "5432"),
    "user": os.environ.get("DB_USER") or "postgres",
    "password": _password,
    "dbname": os.environ.get("DB_NAME") or "carteira_investimentos",
}