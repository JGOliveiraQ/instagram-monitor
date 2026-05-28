import os
import json
import secrets
import requests as http_requests
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
import gspread
from oauth2client.service_account import ServiceAccountCredentials

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DATA_FILE = os.path.join(BASE_DIR, "user_data.json")

app = Flask(__name__)
app.secret_key = "gcbs_insta_monitor_s3cr3t_2024"

USERS = {
    "ddtiza":           {"password": "1527034814", "display": "DDtiza",             "email": "ddtiza.praga@terra.com.br",      "instagram": "ddtizapragas"},
    "previct":          {"password": "5762384988", "display": "Previct",            "email": "previct@previct.com.br",         "instagram": "previctchurras"},
    "viadasflores":     {"password": "3787202186", "display": "Via das Flores",     "email": "glaubergustavobh@gmail.com",     "instagram": "viadasfloresbh"},
    "preall":           {"password": "2740280667", "display": "Preall",             "email": "rogerio@preall.com.br",          "instagram": "prealldesigncimenticio"},
    "drdiego":          {"password": "8536332321", "display": "Dr. Diego",          "email": "diegomedufrj@hotmail.com",       "instagram": "dr.diegomartins"},
    "drgilgalvao":      {"password": "4815602081", "display": "Dr. Gil Galvão",     "email": "gilggbs@gmail.com",              "instagram": "drgilgalvao"},
    "drigorpedrinha":   {"password": "6271456446", "display": "Dr. Igor Pedrinha",  "email": "igorsmpedrinha@yahoo.com.br",    "instagram": "drigorpedrinha"},
    "drothaviolopes":   {"password": "1570474158", "display": "Dr. Othavio Lopes",  "email": "othavio.lopes@gmail.com",        "instagram": "dr.othaviolopes"},
    "drraphaelfonseca": {"password": "4391284491", "display": "Dr. Raphael Fonseca","email": "raphael_s_f@hotmail.com",        "instagram": "raphu_fonseca"},
    "drpedrofrade":     {"password": "2512135217", "display": "Dr. Pedro Frade",    "email": "drpedrofrade@gmail.com",         "instagram": "dr.pedrofradeurologista"},
    "drwagnervieira":   {"password": "3316708980", "display": "Dr. Wagner Vieira",  "email": "wagnervieirabh@gmail.com",       "instagram": "drwagnervieira"},
    "drjacques":        {"password": "2034907622", "display": "Dr. Jacques",        "email": "",                               "instagram": "drjacqueshouly"},
    "drairacemafonseca":{"password": "8429768667", "display": "Dra. Iracema Fonseca","email": "",                              "instagram": "iracemafonsecadra"},
    "fvascular":        {"password": "4700459790", "display": "FVascular",          "email": "",                               "instagram": "mannarinomatheus"},
    "fginecologia":     {"password": "9205105363", "display": "FGinecologia",       "email": "",                               "instagram": "dr.marciolamblet"},
    "joaoteste":        {"password": "8397123992", "display": "João Teste",          "email": "jgoliveiraqm@gmail.com",         "instagram": "jgoliveiraq"},
    "admin":            {"password": "admin12345", "display": "Admin",              "email": "suportegcbs@gmail.com",          "is_admin": True},
}

# tokens de redefinição de senha: {token: {"username": str, "expires": datetime}}
RESET_TOKENS: dict = {}


# ── Persistência de senhas e e-mails ────────────────────────────────────────

def load_user_data():
    """Aplica senhas e e-mails salvos em disco sobre o dict USERS."""
    if not os.path.exists(USER_DATA_FILE):
        return
    try:
        with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for uname, fields in data.items():
            if uname in USERS:
                if "password" in fields:
                    USERS[uname]["password"] = fields["password"]
                if "email" in fields:
                    USERS[uname]["email"] = fields["email"]
    except Exception as e:
        print(f"Aviso: não foi possível carregar user_data.json: {e}")


def save_user_data(username: str, field: str, value: str):
    """Salva alteração de senha ou e-mail no arquivo persistente em disco."""
    data = {}
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    data.setdefault(username, {})[field] = value
    with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


load_user_data()  # aplica ao iniciar o servidor

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


def _send_reset_email(to_email: str, display: str, reset_link: str):
    api_key = os.getenv("BREVO_API_KEY", "")
    if not api_key:
        raise RuntimeError("Variável BREVO_API_KEY não configurada no servidor.")
    body = (
        f"Olá, {display}!\n\n"
        "Você solicitou a redefinição de senha na plataforma GCBS Instagram Monitor.\n\n"
        f"Clique no link abaixo para criar uma nova senha:\n{reset_link}\n\n"
        "O link expira em 1 hora.\n\n"
        "Se você não solicitou isso, ignore este e-mail.\n\n— GCBS Monitor"
    )
    resp = http_requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": api_key, "Content-Type": "application/json"},
        json={
            "sender":      {"name": "GCBS Monitor", "email": "redefinirsenha.gcbs@gmail.com"},
            "to":          [{"email": to_email}],
            "subject":     "Redefinição de senha — GCBS Monitor",
            "textContent": body,
        },
        timeout=10,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Brevo retornou {resp.status_code}: {resp.text}")


def get_sheet():
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        import json
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            json.loads(creds_json), SCOPE
        )
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            os.path.join(BASE_DIR, "credentials.json"), SCOPE
        )
    gc = gspread.authorize(creds)
    return gc.open("Instagram Monitor").sheet1


# Cache de registros da planilha (evita múltiplas conexões simultâneas)
_records_cache: dict = {"data": None, "ts": None}
_CACHE_TTL = timedelta(minutes=5)


def get_cached_records():
    """Retorna todos os registros da planilha, usando cache de 5 min."""
    now = datetime.now()
    if _records_cache["data"] is not None and _records_cache["ts"] and \
            (now - _records_cache["ts"]) < _CACHE_TTL:
        return _records_cache["data"]
    records = get_sheet().get_all_records()
    _records_cache["data"] = records
    _records_cache["ts"] = now
    return records


def _build_stats(username, records):
    """Monta o dict de stats para um username a partir dos records já carregados."""
    rows = [
        r for r in records
        if str(r.get("Cliente", "")).strip().lower() == username.lower()
    ]
    if not rows:
        return {"has_data": False}

    dates     = [str(r.get("Data", ""))      for r in rows]
    followers = [int(r.get("Seguidores", 0)) for r in rows]
    posts     = [int(r.get("Posts", 0))      for r in rows]
    curtidas  = [int(r.get("Curtidas", 0))   for r in rows]

    first       = followers[0]
    current_val = followers[-1]
    growth_abs  = current_val - first
    growth_pct  = round(growth_abs / first * 100, 2) if first else 0.0

    weekly_f  = _calendar_period_growth(dates, followers, 'week')
    monthly_f = _calendar_period_growth(dates, followers, 'month')
    weekly_p  = _calendar_period_growth(dates, posts,     'week')
    monthly_p = _calendar_period_growth(dates, posts,     'month')
    weekly_l  = _calendar_period_growth(dates, curtidas,  'week')
    monthly_l = _calendar_period_growth(dates, curtidas,  'month')

    cur_curtidas = curtidas[-1] if curtidas else 0
    cur_posts    = posts[-1] if posts else 0
    # Média de curtidas por post (últimas amostras — até 12 posts)
    amostras_ref = min(12, cur_posts) if cur_posts else 1
    avg_curtidas = round(cur_curtidas / amostras_ref, 1) if amostras_ref else 0

    return {
        "has_data":          True,
        "dates":             dates,
        "followers":         followers,
        "posts":             posts,
        "curtidas":          curtidas,
        "current_followers": current_val,
        "growth_absolute":   growth_abs,
        "growth_pct":        growth_pct,
        "current_posts":     cur_posts,
        "current_likes":     cur_curtidas,
        "avg_likes":         avg_curtidas,
        "weekly_followers":  weekly_f,
        "monthly_followers": monthly_f,
        "weekly_posts":      weekly_p,
        "monthly_posts":     monthly_p,
        "weekly_likes":      weekly_l,
        "monthly_likes":     monthly_l,
    }


def _first_monday_on_or_after(d):
    """Retorna a primeira segunda-feira a partir da data d (inclusive)."""
    days_ahead = (0 - d.weekday()) % 7  # 0 = segunda-feira
    return d + timedelta(days=days_ahead)


def _calendar_period_growth(dates, values, period='week'):
    """
    Crescimento do período ATUAL em andamento, zerado a cada:
      week  → toda segunda-feira
      month → primeira segunda-feira do mês atual

    Compara com o período imediatamente anterior para o trend.
    Retorna: growth, pct, prev_growth, trend, label.
    """
    if not dates or not values:
        return {"growth": 0, "pct": 0.0, "prev_growth": 0, "trend": "stable", "label": "—"}

    today = datetime.now().date()

    parsed = []
    for d, v in zip(dates, values):
        try:
            parsed.append((datetime.strptime(d, "%d/%m/%Y").date(), int(v)))
        except Exception:
            pass
    if not parsed:
        return {"growth": 0, "pct": 0.0, "prev_growth": 0, "trend": "stable", "label": "—"}

    def val_at_or_before(target):
        result = None
        for dt, v in parsed:
            if dt <= target:
                result = v
        return result

    meses = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez']

    if period == 'week':
        # Início do período atual = esta segunda-feira
        period_start = today - timedelta(days=today.weekday())
        # Período anterior = semana passada (segunda→domingo)
        prev_start = period_start - timedelta(days=7)
        prev_end   = period_start - timedelta(days=1)
        label = f"{period_start.strftime('%d/%m')} – {today.strftime('%d/%m')}"

    else:  # month
        # Início do período atual = 1ª segunda do mês corrente
        first_of_month = today.replace(day=1)
        period_start   = _first_monday_on_or_after(first_of_month)
        # Período anterior = do início do mês passado (1ª segunda) até véspera do período atual
        if today.month == 1:
            prev_year, prev_month = today.year - 1, 12
        else:
            prev_year, prev_month = today.year, today.month - 1
        prev_first = today.replace(year=prev_year, month=prev_month, day=1)
        prev_start = _first_monday_on_or_after(prev_first)
        prev_end   = period_start - timedelta(days=1)
        label = f"{meses[today.month - 1]}/{today.year}"

    # Crescimento atual = valor mais recente − valor na véspera do início do período
    val_now   = val_at_or_before(today)
    val_base  = val_at_or_before(period_start - timedelta(days=1))

    # Crescimento do período anterior (para o comparativo de trend)
    val_prev_end   = val_at_or_before(prev_end)
    val_prev_start = val_at_or_before(prev_start - timedelta(days=1))

    if val_now  is None: val_now  = parsed[-1][1]
    if val_base is None: val_base = parsed[0][1]

    growth      = val_now - val_base
    pct         = round(growth / val_base * 100, 2) if val_base else 0.0
    prev_growth = (val_prev_end - val_prev_start) \
                  if (val_prev_end is not None and val_prev_start is not None) else 0
    trend = "up" if growth > prev_growth else ("down" if growth < prev_growth else "stable")

    return {"growth": growth, "pct": pct, "prev_growth": prev_growth, "trend": trend, "label": label}


# ── Decorators ───────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        if not USERS.get(session["user"], {}).get("is_admin"):
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated


# ── Rotas ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "user" not in session:
        return redirect(url_for("login"))
    if USERS.get(session["user"], {}).get("is_admin"):
        return redirect(url_for("admin"))
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = USERS.get(username)
        if user and user["password"] == password:
            session["user"] = username
            return redirect(url_for("index"))
        error = "Usuário ou senha incorretos."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    username = session["user"]
    if USERS.get(username, {}).get("is_admin"):
        return redirect(url_for("admin"))
    return render_template(
        "dashboard.html",
        username=username,
        display=USERS[username]["display"],
    )


@app.route("/admin")
@admin_required
def admin():
    clients = [
        {"id": k, "display": v["display"]}
        for k, v in USERS.items()
        if not v.get("is_admin")
    ]
    return render_template("admin.html", clients=clients)


# ── API ──────────────────────────────────────────────────────────────────────

@app.route("/api/stats/<username>")
@login_required
def get_stats(username):
    current_user = session["user"]
    if not USERS.get(current_user, {}).get("is_admin") and current_user != username:
        return jsonify({"error": "Acesso negado"}), 403
    try:
        records = get_cached_records()
        # Usa o @ do Instagram real do usuário para buscar no Sheets
        insta = USERS.get(username, {}).get("instagram", username)
        return jsonify(_build_stats(insta, records))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/all_stats")
@admin_required
def get_all_stats():
    """Retorna stats de todos os clientes em uma única chamada ao Sheets."""
    try:
        records = get_cached_records()
        result = {}
        for uid, udata in USERS.items():
            if udata.get("is_admin"):
                continue
            insta = udata.get("instagram", uid)
            result[uid] = _build_stats(insta, records)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if "user" in session:
        return redirect(url_for("index"))
    msg = error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        user = USERS.get(username)
        # Remove tokens expirados
        now = datetime.now()
        for t in list(RESET_TOKENS):
            if now > RESET_TOKENS[t]["expires"]:
                del RESET_TOKENS[t]
        if user and user.get("email"):
            token = secrets.token_urlsafe(32)
            RESET_TOKENS[token] = {"username": username, "expires": now + timedelta(hours=1)}
            link = url_for("reset_password", token=token, _external=True)
            try:
                _send_reset_email(user["email"], user["display"], link)
                msg = f"Link enviado para {user['email']}. Verifique sua caixa de entrada."
            except Exception as exc:
                error = f"Erro ao enviar e-mail: {exc}"
        else:
            msg = "Se o usuário existir e tiver e-mail cadastrado, você receberá o link."
    return render_template("forgot_password.html", msg=msg, error=error)


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    data = RESET_TOKENS.get(token)
    if not data or datetime.now() > data["expires"]:
        return render_template("reset_password.html", invalid=True)
    error = None
    if request.method == "POST":
        pw  = request.form.get("password", "")
        pw2 = request.form.get("confirm_password", "")
        if len(pw) < 6:
            error = "A senha deve ter pelo menos 6 caracteres."
        elif pw != pw2:
            error = "As senhas não coincidem."
        else:
            USERS[data["username"]]["password"] = pw
            save_user_data(data["username"], "password", pw)
            del RESET_TOKENS[token]
            return render_template("reset_password.html", success=True)
    return render_template("reset_password.html", token=token, error=error)


@app.route("/register-email", methods=["GET", "POST"])
def register_email():
    if "user" in session:
        return redirect(url_for("index"))
    msg = error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        email    = request.form.get("email", "").strip()
        user = USERS.get(username)
        if not user or user.get("is_admin") or user["password"] != password:
            error = "Usuário ou senha incorretos."
        elif not email or "@" not in email or "." not in email:
            error = "Digite um e-mail válido."
        else:
            USERS[username]["email"] = email
            save_user_data(username, "email", email)
            msg = True
    return render_template("register_email.html", msg=msg, error=error)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
