#!/usr/bin/env python3
"""
Reautenticacao Google OAuth — gera novo token apos migracao Testing -> Production.
Usa o mesmo client_id do token existente. Executar LOCALMENTE (precisa de navegador).
"""
import json, secrets, hashlib, base64, urllib.parse, urllib.request, http.server, sys

TOKEN_PATH = "/home/hermes/.hermes/google_token.json"

with open(TOKEN_PATH) as f:
    old = json.load(f)

CLIENT_ID = old.get("client_id", "")
CLIENT_SECRET = old.get("client_secret", "")
SCOPES = old.get("scopes", ["https://www.googleapis.com/auth/drive"])
REDIRECT_PORT = 8099
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"

if not CLIENT_ID:
    print("ERRO: client_id nao encontrado no token atual")
    sys.exit(1)

# PKCE
code_verifier = secrets.token_urlsafe(64)
code_challenge = base64.urlsafe_b64encode(
    hashlib.sha256(code_verifier.encode()).digest()
).rstrip(b"=").decode()

# URL de autorizacao
params = {
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT_URI,
    "response_type": "code",
    "scope": " ".join(SCOPES),
    "access_type": "offline",
    "prompt": "consent",
    "code_challenge": code_challenge,
    "code_challenge_method": "S256",
}
auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)

print("=" * 60)
print("REAUTENTICACAO GOOGLE DRIVE")
print("=" * 60)
print(f"\nAbra este link no navegador:\n\n{auth_url}\n")

# Servidor HTTP local para receber o callback
auth_code = None

class OAuthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if "code" in qs:
            auth_code = qs["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h2>Autorizado!</h2><p>Pode fechar esta janela.</p>")
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, *args):
        pass

server = http.server.HTTPServer(("localhost", REDIRECT_PORT), OAuthHandler)
server.timeout = 120

print(f"Aguardando autorizacao na porta {REDIRECT_PORT} (timeout: 120s)...")
try:
    server.handle_request()
except KeyboardInterrupt:
    pass

if not auth_code:
    print("Timeout ou cancelado.")
    sys.exit(1)

print("Codigo recebido. Trocando por token...")

token_data = urllib.parse.urlencode({
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "code": auth_code,
    "code_verifier": code_verifier,
    "grant_type": "authorization_code",
    "redirect_uri": REDIRECT_URI,
}).encode()

req = urllib.request.Request(
    "https://oauth2.googleapis.com/token",
    data=token_data,
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        new_token = json.loads(resp.read())
except urllib.error.HTTPError as e:
    print(f"ERRO HTTP {e.code}: {e.read().decode()}")
    sys.exit(1)

old["token"] = new_token["access_token"]
old["refresh_token"] = new_token.get("refresh_token", old.get("refresh_token"))

with open(TOKEN_PATH, "w") as f:
    json.dump(old, f, indent=2)

print(f"\nToken salvo em {TOKEN_PATH}")
print(f"Scopes: {len(SCOPES)} permissoes")
print("Pronto para usar!")