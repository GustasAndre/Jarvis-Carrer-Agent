"""Login no LinkedIn (OAuth 2.0). Rode uma vez e repita quando o token expirar (~60 dias).

    python linkedin_auth.py

Abre o navegador, você autoriza o app e o token fica salvo em
credenciais/linkedin_token.json (pasta ignorada pelo Git).
"""
import json
import os
import secrets
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

import config  # noqa: F401 — import usado pelo efeito colateral (carrega o .env)
from tools.linkedin import TOKEN_PATH

CLIENT_ID = os.environ["LINKEDIN_CLIENT_ID"]
CLIENT_SECRET = os.environ["LINKEDIN_CLIENT_SECRET"]
PORTA = 8765
REDIRECT_URI = f"http://localhost:{PORTA}/callback"
ESCOPOS = "openid profile w_member_social"


class _Callback(BaseHTTPRequestHandler):
    resultado: dict = {}

    def do_GET(self):  # noqa: N802 (nome exigido pela biblioteca)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _Callback.resultado = {k: v[0] for k, v in query.items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<h3>Pronto! Pode fechar esta aba e voltar ao terminal.</h3>".encode())

    def log_message(self, *args):  # silencia o log do servidor
        pass


def main() -> None:
    state = secrets.token_urlsafe(16)  # proteção contra CSRF
    url = "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "scope": ESCOPOS,
    })
    print("Abrindo o navegador para autorizar o Jarvis no LinkedIn...")
    webbrowser.open(url)

    servidor = HTTPServer(("localhost", PORTA), _Callback)
    servidor.handle_request()  # espera exatamente um retorno
    r = _Callback.resultado

    if "error" in r:
        raise SystemExit(f"Autorização negada: {r.get('error_description', r['error'])}")
    if r.get("state") != state:
        raise SystemExit("State inválido: resposta não corresponde a este login. Tente de novo.")

    token = requests.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "authorization_code",
            "code": r["code"],
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        timeout=30,
    )
    token.raise_for_status()
    dados = token.json()

    perfil = requests.get(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {dados['access_token']}"},
        timeout=30,
    )
    perfil.raise_for_status()
    sub = perfil.json()["sub"]

    TOKEN_PATH.parent.mkdir(exist_ok=True)
    TOKEN_PATH.write_text(json.dumps({
        "access_token": dados["access_token"],
        "expira_em": time.time() + int(dados["expires_in"]),
        "autor_urn": f"urn:li:person:{sub}",
        "nome": perfil.json().get("name"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    dias = int(dados["expires_in"]) // 86400
    print(f"Token salvo para {perfil.json().get('name')}. Válido por {dias} dias.")


if __name__ == "__main__":
    main()
