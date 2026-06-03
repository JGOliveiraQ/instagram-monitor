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
    # Configura Tor na sessão do Instaloader também
    if USE_TOR:
        L.context._session.proxies = {
            "http":  "socks5h://127.0.0.1:9050",
            "https": "socks5h://127.0.0.1:9050",
        }
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

# ── Aba Posts (últimas publicações) ─────────────────────────────────────────
posts_sheet = None
try:
    posts_sheet = gs_client.open("Instagram Monitor").worksheet("Posts")
    print("✅ Aba Posts encontrada")
except Exception:
    try:
        posts_sheet = gs_client.open("Instagram Monitor").add_worksheet("Posts", 2000, 14)
        posts_sheet.insert_row([
            "Data", "Cliente",
            "Thumb1", "Likes1", "Coments1", "Shortcode1",
            "Thumb2", "Likes2", "Coments2", "Shortcode2",
            "Thumb3", "Likes3", "Coments3", "Shortcode3",
        ], 1)
        print("✅ Aba Posts criada")
    except Exception as e_ps:
        print(f"⚠️  Aba Posts: {e_ps}")

headers = sheet.row_values(1)
expected = ["Data", "Cliente", "Seguidores", "Posts", "Curtidas", "Comentarios"]
if not headers:
    sheet.insert_row(expected, 1)
elif headers[:4] == ["Data", "Cliente", "Seguidores", "Posts"]:
    # Planilha já existe — adiciona colunas novas se faltarem
    if len(headers) < 5 or headers[4] != "Curtidas":
        sheet.update_cell(1, 5, "Curtidas")
        print("✅ Coluna 'Curtidas' adicionada ao cabeçalho")
    if len(headers) < 6 or headers[5] != "Comentarios":
        sheet.update_cell(1, 6, "Comentarios")
        print("✅ Coluna 'Comentarios' adicionada ao cabeçalho")
elif headers != expected:
    sheet.insert_row(expected, 1)


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
    from itertools import islice

    # ── Tentativa 1: Instaloader Profile (sessão autenticada, mais confiável) ──
    try:
        profile      = instaloader.Profile.from_username(L.context, username)
        curtidas     = 0
        comentarios  = 0
        recent_posts = []

        for post in islice(profile.get_posts(), 12):
            curtidas    += post.likes
            comentarios += post.comments
            if len(recent_posts) < 3:
                recent_posts.append({
                    "thumb":     post.url,
                    "likes":     post.likes,
                    "comments":  post.comments,
                    "shortcode": post.shortcode,
                })

        amostras = min(12, profile.mediacount)
        print(f"   📸 {len(recent_posts)} posts | {curtidas:,} curtidas | {comentarios:,} coment.")
        return {
            "followers":    profile.followers,
            "posts":        profile.mediacount,
            "curtidas":     curtidas,
            "comentarios":  comentarios,
            "amostras":     amostras,
            "recent_posts": recent_posts,
        }
    except Exception as e_il:
        print(f"   ⚠️  Instaloader Profile: {e_il} — tentando HTTP...")

    # ── Tentativa 2: web_profile_info + /feed/user/ (fallback HTTP) ──────────
    s       = build_session(cookies)
    url     = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
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
    user    = resp.json()["data"]["user"]
    user_id = user.get("id", "")

    edges       = user.get("edge_owner_to_timeline_media", {}).get("edges", [])
    curtidas    = sum(e.get("node", {}).get("edge_liked_by",         {}).get("count", 0) for e in edges)
    comentarios = sum(e.get("node", {}).get("edge_media_to_comment", {}).get("count", 0) for e in edges)
    amostras    = len(edges)
    recent_posts = []
    for e in edges[:3]:
        node = e.get("node", {})
        recent_posts.append({
            "thumb":     node.get("thumbnail_src") or node.get("display_url", ""),
            "likes":     node.get("edge_liked_by",         {}).get("count", 0),
            "comments":  node.get("edge_media_to_comment", {}).get("count", 0),
            "shortcode": node.get("shortcode", ""),
        })

    # Sub-fallback: /feed/user/{id}/
    if amostras == 0 and user_id:
        try:
            feed_resp = s.get(
                f"https://www.instagram.com/api/v1/feed/user/{user_id}/?count=12",
                headers=headers, timeout=30
            )
            if feed_resp.status_code == 200:
                items       = feed_resp.json().get("items", [])
                curtidas    = sum(i.get("like_count",    0) for i in items)
                comentarios = sum(i.get("comment_count", 0) for i in items)
                amostras    = len(items)
                for item in items[:3]:
                    cands = item.get("image_versions2", {}).get("candidates", [])
                    thumb = cands[len(cands) // 2]["url"] if cands else ""
                    recent_posts.append({
                        "thumb":     thumb,
                        "likes":     item.get("like_count",    0),
                        "comments":  item.get("comment_count", 0),
                        "shortcode": item.get("code",          ""),
                    })
                print(f"   📸 Feed HTTP: {amostras} posts")
        except Exception as e_feed:
            print(f"   ⚠️  Feed endpoint: {e_feed}")

    return {
        "followers":    user["edge_followed_by"]["count"],
        "posts":        user["edge_owner_to_timeline_media"]["count"],
        "curtidas":     curtidas,
        "comentarios":  comentarios,
        "amostras":     amostras,
        "recent_posts": recent_posts,
    }


# ============================================
# COLETAR DADOS
# ============================================

hoje = datetime.now().strftime("%d/%m/%Y")

# Carrega registros existentes para evitar duplicatas no mesmo dia
print("Verificando registros existentes...")
registros_existentes = set()
try:
    for row in sheet.get_all_records():
        registros_existentes.add((str(row.get("Data", "")), str(row.get("Cliente", ""))))
except Exception as e:
    print(f"⚠️  Não foi possível verificar duplicatas: {e}")

for usuario in CLIENTES:
    if (hoje, usuario) in registros_existentes:
        print(f"⏭️  @{usuario} — já registrado hoje, pulando...")
        continue

    sucesso = False
    for tentativa in range(1, 21):         # até 20 tentativas por conta
        try:
            print(f"Buscando @{usuario}{'  (tentativa ' + str(tentativa) + ')' if tentativa > 1 else ''}...")
            dados        = get_profile_data(usuario, session_cookies)
            seguidores   = dados["followers"]
            posts        = dados["posts"]
            curtidas     = dados["curtidas"]
            comentarios  = dados["comentarios"]
            amostras     = dados["amostras"]
            recent_posts = dados.get("recent_posts", [])

            sheet.append_row([hoje, usuario, seguidores, posts, curtidas, comentarios])
            registros_existentes.add((hoje, usuario))
            print(f"✅ @{usuario} — {seguidores:,} seg | {posts} posts | "
                  f"{curtidas:,} curtidas | {comentarios:,} comentários ({amostras} amostras)")

            # Salva últimas 3 publicações na aba Posts
            if posts_sheet is not None:
                rp = list(recent_posts) + [{"thumb":"","likes":0,"comments":0,"shortcode":""}] * 3
                row = [hoje, usuario]
                for p in rp[:3]:
                    row.extend([p.get("thumb",""), p.get("likes",0),
                                 p.get("comments",0), p.get("shortcode","")])
                try:
                    posts_sheet.append_row(row)
                except Exception as e_ps:
                    print(f"   ⚠️  Posts sheet: {e_ps}")

            sucesso = True
            break

        except requests.HTTPError as e:
            codigo = e.response.status_code
            if codigo in (429, 400, 403) and USE_TOR and tentativa < 20:
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
