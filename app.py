import os
import secrets
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
import gspread
from oauth2client.service_account import ServiceAccountCredentials

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.secret_key = "gcbs_insta_monitor_s3cr3t_2024"

USERS = {
    "instagram": {"password": "12345",      "display": "Instagram", "email": ""},
    "nike":      {"password": "12345",      "display": "Nike",      "email": ""},
    "openai":    {"password": "12345",      "display": "OpenAI",    "email": ""},
    "ddtiza":    {"password": "1527034814", "display": "DDTiza",    "email": "ddtiza.praga@terra.com.br"},
    "admin":     {"password": "admin12345", "display": "Admin",     "email": "suportegcbs@gmail.com", "is_admin": True},
}

# tokens de redefinição de senha: {token: {"username": str, "expires": datetime}}
RESET_TOKENS: dict = {}

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


def _send_reset_email(to_email: str, display: str, reset_link: str):
    mail_user = os.getenv("MAIL_USER", "suportegcbs@gmail.com")
    mail_pass = os.getenv("MAIL_PASS", "")
    if not mail_pass:
        raise RuntimeError("Variável MAIL_PASS não configurada no servidor.")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Redefinição de senha — GCBS Monitor"
    msg["From"]    = f"GCBS Monitor <{mail_user}>"
    msg["To"]      = to_email
    body = (
        f"Olá, {display}!\n\n"
        "Você solicitou a redefinição de senha na plataforma GCBS Instagram Monitor.\n\n"
        f"Clique no link abaixo para criar uma nova senha:\n{reset_link}\n\n"
        "O link expira em 1 hora.\n\n"
        "Se você não solicitou isso, ignore este e-mail.\n\n— GCBS Monitor"
    )
    msg.attach(MIMEText(body, "plain", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as srv:
        srv.login(mail_user, mail_pass)
        srv.sendmail(mail_user, to_email, msg.as_string())


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


def _period_growth(dates, values, days):
    """
    Growth over the last `days` days compared to the previous `days` days.
    Returns dict with growth, pct, prev_growth, trend.
    """
    if not dates or not values:
        return {"growth": 0, "pct": 0.0, "prev_growth": 0, "trend": "stable"}

    now = datetime.now()
    cutoff      = now - timedelta(days=days)
    cutoff_prev = now - timedelta(days=days * 2)

    parsed = []
    for d, v in zip(dates, values):
        try:
            parsed.append((datetime.strptime(d, "%d/%m/%Y"), int(v)))
        except Exception:
            pass

    if not parsed:
        return {"growth": 0, "pct": 0.0, "prev_growth": 0, "trend": "stable"}

    latest = parsed[-1][1]

    # Value closest to (but not after) cutoff
    val_cutoff = None
    val_prev   = None
    for dt, v in parsed:
        if dt <= cutoff:
            val_cutoff = v
        if dt <= cutoff_prev:
            val_prev = v

    if val_cutoff is None:
        val_cutoff = parsed[0][1]

    growth     = latest - val_cutoff
    pct        = round(growth / val_cutoff * 100, 2) if val_cutoff else 0.0
    prev_growth = (val_cutoff - val_prev) if val_prev is not None else 0
    trend = "up" if growth > prev_growth else ("down" if growth < prev_growth else "stable")

    return {"growth": growth, "pct": pct, "prev_growth": prev_growth, "trend": trend}


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
        sheet   = get_sheet()
        records = sheet.get_all_records()
        rows    = [
            r for r in records
            if str(r.get("Cliente", "")).strip().lower() == username.lower()
        ]

        if not rows:
            return jsonify({"has_data": False})

        dates     = [str(r.get("Data", ""))      for r in rows]
        followers = [int(r.get("Seguidores", 0)) for r in rows]
        posts     = [int(r.get("Posts", 0))      for r in rows]

        first       = followers[0]
        current_val = followers[-1]
        growth_abs  = current_val - first
        growth_pct  = round(growth_abs / first * 100, 2) if first else 0.0

        weekly_f  = _period_growth(dates, followers, 7)
        monthly_f = _period_growth(dates, followers, 30)
        weekly_p  = _period_growth(dates, posts, 7)
        monthly_p = _period_growth(dates, posts, 30)

        return jsonify({
            "has_data":          True,
            "dates":             dates,
            "followers":         followers,
            "posts":             posts,
            "current_followers": current_val,
            "growth_absolute":   growth_abs,
            "growth_pct":        growth_pct,
            "current_posts":     posts[-1] if posts else 0,
            "weekly_followers":  weekly_f,
            "monthly_followers": monthly_f,
            "weekly_posts":      weekly_p,
            "monthly_posts":     monthly_p,
        })

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
            del RESET_TOKENS[token]
            return render_template("reset_password.html", success=True)
    return render_template("reset_password.html", token=token, error=error)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
