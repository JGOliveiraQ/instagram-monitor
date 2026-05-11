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
    exit()
# ============================================
# GOOGLE SHEETS
# ============================================

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name(
    "credentials.json",
    scope
)

client = gspread.authorize(creds)
sheet = client.open("Instagram Monitor").sheet1

if sheet.cell(1, 1).value is None:
    sheet.append_row([
        "Data",
        "Cliente",
        "Seguidores",
        "Posts"
    ])

# ============================================
# COLETAR DADOS
# ============================================

hoje = datetime.now().strftime("%d/%m/%Y")

for usuario in CLIENTES:
    try:
        print(f"Buscando @{usuario}...")

        profile = instaloader.Profile.from_username(
            L.context,
            usuario
        )

        seguidores = profile.followers
        posts = profile.mediacount

        sheet.append_row([
            hoje,
            usuario,
            seguidores,
            posts
        ])

        print("✅ Salvo com sucesso")
        time.sleep(8)

    except Exception as e:
        print(f"❌ Erro em {usuario}: {e}")
