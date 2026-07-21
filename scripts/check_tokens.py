#!/usr/bin/env python3
"""Watchdog de tokens Google OAuth — verifica validade e alerta via Telegram."""
import json, os, sys, re
from datetime import datetime, timezone

BASE = "/home/hermes/.hermes"
TOKS = {
    "google_token.json": BASE + "/google_token.json",
    "google_token_notas.json": BASE + "/google_token_notas.json",
}
ENV_FILE = BASE + "/.env"
CHAT = "6216425458"

def get_token():
    with open(ENV_FILE) as f:
        content = f.read()
    # Extrai TELEGRAM_BOT_TOKEN do .env
    lines = content.split("\n")
    for line in lines:
        if line.startswith("TELEGRAM_BOT_TOKEN"):
            val = line.split("=", 1)[1].strip()
            return val
    return ""

def send_telegram(msg):
    import urllib.request
    token = get_token()
    if not token:
        print("ERRO: sem bot token")
        return False
    url = "https://api.telegram.org/bot" + token + "/sendMessage"
    d = json.dumps({"chat_id": CHAT, "text": msg}).encode()
    req = urllib.request.Request(url, data=d, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:
        print("Erro Telegram:", e)
        return False

def check():
    alertas = []
    for nome, path in TOKS.items():
        try:
            with open(path) as f:
                t = json.load(f)
        except Exception as e:
            alertas.append(nome + ": arquivo invalido")
            continue
        expiry = t.get("expiry", "")
        has_refresh = bool(t.get("refresh_token"))
        has_access = len(t.get("token", "")) > 10
        if not has_access and not has_refresh:
            alertas.append(nome + ": sem token - reautenticar")
            continue
        if not expiry:
            continue
        try:
            exp_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            agora = datetime.now(timezone.utc)
            horas = (exp_dt - agora).total_seconds() / 3600
            if horas < 0:
                alertas.append("EXPIRADO: " + nome + " (" + str(abs(int(horas))) + "h)")
            # Access token expira em ~1h — normal. So alertar se expirado.
        except:
            pass
    if alertas:
        msg = "Token Alert\n\n" + "\n".join(alertas)
        msg += "\n\nRodar: reauth_google.py"
        print(msg)
        send_telegram(msg)
        return 1
    else:
        print("Tokens OK")
        return 0

if __name__ == "__main__":
    sys.exit(check())