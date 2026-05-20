import sys
import os
import time
import instaloader
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from config import CLIENTES

# ============================================
# CONFIGURAÇÃO
# ============================================

IG_USERNAME = "accountverificarseguidor"
IG_APP_ID   = "936619743392459"

# USE_TOR=true no GitHub Actions para rotacionar IP via Tor
USE_TOR = os.getenv("USE_TOR", "false").lower() == "true"

if USE_TOR:
    print("🧅 Modo Tor ativado — tráfego roteado via proxy Tor")

# ============================================
# INSTAGRAM (sessão salva)
# ============================================

L = instaloader.Instaloader()
session_cookies = None

print("Carregando sessão do Instagram...")
try:
    L.load_session_from_file(
        IG_USERNAME,
        filename="session-accountverificarseguidor"
    )
    session_cookies = dict(L.context._session.cookies)
    print("✅ Sessão carregada com sucesso")
except Exception as e:
    if USE_TOR:
        print(f"⚠️  Sessão não disponível ({e}) — continuando via Tor sem auth")
    else:
        print(f"❌ Erro ao carregar sessão: {e}")
        sys.exit(1)

# ============================================
# GOOGLE SHEETS
# ============================================

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

try:
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)
    gs_client = gspread.authorize(creds)
    sheet = gs_client.open("Instagram Monitor").sheet1
except Exception as e:
    print(f"❌ Erro ao conectar ao Google Sheets: {e}")
    sys.exit(1)

headers = sheet.row_values(1)
if headers != ["Data", "Cliente", "Seguidores", "Posts"]:
    sheet.insert_row(["Data", "Cliente", "Seguidores", "Posts"], 1)


# ============================================
# BUSCAR DADOS DO INSTAGRAM
# ============================================

def rotate_tor_circuit():
    """Solicita novo circuito Tor via socket (cookie auth ou null auth)."""
    if not USE_TOR:
        return
    try:
        import socket, binascii

        # Tenta ler o cookie de autenticação do Tor
        cookie = b""
        for cookie_path in [
            "/run/tor/control.authcookie",
            "/var/run/tor/control.authcookie",
        ]:
            try:
                with open(cookie_path, "rb") as f:
                    cookie = f.read()
                break
            except OSError:
                pass

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(10)
            s.connect(("127.0.0.1", 9051))
            if cookie:
                # Cookie auth: envia os bytes do cookie em hexadecimal
                auth_cmd = b"AUTHENTICATE " + binascii.hexlify(cookie) + b"\r\n"
            else:
                # Null auth (fallback quando cookie não está disponível)
                auth_cmd = b'AUTHENTICATE ""\r\n'
            s.sendall(auth_cmd + b"SIGNAL NEWNYM\r\nQUIT\r\n")
            resp = s.recv(256).decode("utf-8", errors="replace")

        if "250" in resp:
            print("🔄 Novo circuito Tor solicitado — aguardando 15s...")
            time.sleep(15)
        else:
            raise Exception(f"Resposta: {resp!r}")
    except Exception as e:
        print(f"⚠️  Rotação de circuito indisponível ({e}) — aguardando 20s...")
        time.sleep(20)


def build_session(cookies=None) -> requests.Session:
    """Cria sessão requests, com Tor e/ou cookies do Instagram."""
    s = requests.Session()
    if USE_TOR:
        s.proxies = {
            "http":  "socks5h://127.0.0.1:9050",
            "https": "socks5h://127.0.0.1:9050",
        }
    if cookies:
        s.cookies.update(cookies)
    return s


def get_profile_data(username: str, cookies=None) -> dict:
    s = build_session(cookies)
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
    headers = {
        "x-ig-app-id":      IG_APP_ID,
        "User-Agent":       (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept":           "application/json",
        "Accept-Language":  "pt-BR,pt;q=0.9",
        "Referer":          f"https://www.instagram.com/{username}/",
        "X-Requested-With": "XMLHttpRequest",
    }
    resp = s.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    user = resp.json()["data"]["user"]
    return {
        "followers": user["edge_followed_by"]["count"],
        "posts":     user["edge_owner_to_timeline_media"]["count"],
    }


# ============================================
# COLETAR DADOS
# ============================================

hoje = datetime.now().strftime("%d/%m/%Y")

for usuario in CLIENTES:
    sucesso = False
    for tentativa in range(1, 7):          # até 6 tentativas por conta
        try:
            print(f"Buscando @{usuario}{'  (tentativa ' + str(tentativa) + ')' if tentativa > 1 else ''}...")
            dados     = get_profile_data(usuario, session_cookies)
            seguidores = dados["followers"]
            posts      = dados["posts"]

            sheet.append_row([hoje, usuario, seguidores, posts])
            print(f"✅ @{usuario} — {seguidores:,} seguidores, {posts} posts")
            sucesso = True
            break

        except requests.HTTPError as e:
            codigo = e.response.status_code
            if codigo in (429, 400, 403) and USE_TOR and tentativa < 6:
                print(f"   ⚠️  {codigo} — rotacionando circuito Tor...")
                rotate_tor_circuit()
            else:
                print(f"❌ Erro em @{usuario}: {e}")
                break
        except Exception as e:
            print(f"❌ Erro em @{usuario}: {e}")
            break

    if sucesso:
        rotate_tor_circuit()  # novo IP antes do próximo perfil
    else:
        time.sleep(5)
