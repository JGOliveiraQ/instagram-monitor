"""
Execute este script UMA VEZ para salvar a sessão do Instagram.
Depois o main.py carrega automaticamente.

Uso:
    python login_instagram.py
"""
import instaloader
import getpass

IG_USERNAME = "accountverificarseguidor"

L = instaloader.Instaloader()

print(f"Login do Instagram para: @{IG_USERNAME}")
senha = getpass.getpass("Senha: ")

try:
    L.login(IG_USERNAME, senha)
    L.save_session_to_file(IG_USERNAME)
    print(f"✅ Sessão salva em: session-{IG_USERNAME}")

except instaloader.exceptions.TwoFactorAuthRequiredException:
    codigo = input("🔐 Código de autenticação de 2 fatores: ").strip()
    try:
        L.two_factor_login(codigo)
        L.save_session_to_file(IG_USERNAME)
        print(f"✅ Sessão salva em: session-{IG_USERNAME}")
    except Exception as e:
        print(f"❌ Erro no código 2FA: {e}")

except Exception as e:
    print(f"❌ Erro no login: {e}")
