import sys
import time
import instaloader
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from config import CLIENTES

# ============================================
# INSTAGRAM (sessão salva)
# ============================================

IG_USERNAME = "accountverificarseguidor"
# App ID público do Instagram Web (não muda)
IG_APP_ID   = "936619743392459"

print("Carregando sessão do Instagram...")

L = instaloader.Instaloader()

try:
    L.load_session_from_file(
        IG_USERNAME,
        filename="session-accountverificarseguidor"
    )
    print("✅ Sessão carregada com sucesso")
except Exception as e:
    print("❌ Erro ao carregar sessão:", e)
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
    print("❌ Erro ao conectar ao Google Sheets:", e)
    sys.exit(1)

headers = sheet.row_values(1)
if headers != ["Data", "Cliente", "Seguidores", "Posts"]:
    sheet.insert_row(["Data", "Cliente", "Seguidores", "Posts"], 1)


# ============================================
# BUSCAR DADOS VIA API WEB DO INSTAGRAM
# ============================================

def get_profile_data(username: str, session: requests.Session) -> dict:
    """
    Usa o endpoint web do Instagram (diferente do GraphQL que está bloqueado).
    Retorna dict com 'followers' e 'posts', ou lança exceção.
    """
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
    headers = {
        "x-ig-app-id": IG_APP_ID,
        "User-Agent":  (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept":          "application/json",
        "Accept-Language": "pt-BR,pt;q=0.9",
        "Referer":         f"https://www.instagram.com/{username}/",
        "X-Requested-With": "XMLHttpRequest",
    }
    resp = session.get(url, headers=headers, timeout=20)
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

# Reutiliza a sessão autenticada do instaloader
ig_session = L.context._session

for usuario in CLIENTES:
    try:
        print(f"Buscando @{usuario}...")

        dados = get_profile_data(usuario, ig_session)
        seguidores = dados["followers"]
        posts      = dados["posts"]

        sheet.append_row([hoje, usuario, seguidores, posts])
        print(f"✅ @{usuario} — {seguidores:,} seguidores, {posts} posts")
        time.sleep(8)

    except Exception as e:
        print(f"❌ Erro em @{usuario}: {e}")
