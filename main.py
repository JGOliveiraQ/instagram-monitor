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
    for tentativa in range(1, 4):          # até 3 tentativas por conta
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
            if codigo in (429, 400, 403) and USE_TOR and tentativa < 3:
                espera = tentativa * 30
                print(f"   ⚠️  {codigo} — aguardando {espera}s para novo circuito Tor...")
                time.sleep(espera)
            else:
                print(f"❌ Erro em @{usuario}: {e}")
                break
        except Exception as e:
            print(f"❌ Erro em @{usuario}: {e}")
            break

    if sucesso:
        time.sleep(10)   # pausa entre perfis
