import instaloader
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from config import CLIENTES
import time

# ============================================
# CONFIGURAÇÃO INSTAGRAM
# ============================================

# Coloque aqui SEU usuário do Instagram (sem @)
IG_USERNAME = "accountverificarseguidor"

# ============================================
# CONECTAR AO GOOGLE SHEETS
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

# Criar cabeçalho se estiver vazio
if sheet.cell(1, 1).value is None:
    sheet.append_row([
        "Data",
        "Cliente",
        "Seguidores",
        "Posts"
    ])

# ============================================
# CARREGAR SESSÃO DO INSTAGRAM
# ============================================

print("Carregando sessão do Instagram...")

L = instaloader.Instaloader()

try:
    L.load_session_from_file(IG_USERNAME)
    print("✅ Sessão carregada com sucesso")
except Exception as e:
    print("❌ Erro ao carregar sessão:", e)
    print("Primeiro rode:")
    print(f'python -m instaloader --login {IG_USERNAME}')
    exit()

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

        # Espera para evitar bloqueio
        time.sleep(8)

    except Exception as e:
        print(f"❌ Erro em {usuario}: {e}")