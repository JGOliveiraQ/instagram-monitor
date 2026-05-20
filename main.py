import sys
import time
import instaloader
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from config import CLIENTES

# ============================================
# INSTAGRAM (sessão salva)
# ============================================

IG_USERNAME = "accountverificarseguidor"

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
# COLETAR DADOS
# ============================================

hoje = datetime.now().strftime("%d/%m/%Y")

for usuario in CLIENTES:
    try:
        print(f"Buscando @{usuario}...")

        profile = instaloader.Profile.from_username(L.context, usuario)

        seguidores = profile.followers
        posts = profile.mediacount

        sheet.append_row([hoje, usuario, seguidores, posts])

        print(f"✅ @{usuario} — {seguidores:,} seguidores, {posts} posts")
        time.sleep(8)

    except Exception as e:
        print(f"❌ Erro em @{usuario}: {e}")
