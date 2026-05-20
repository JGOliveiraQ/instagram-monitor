import os
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
import gspread
from oauth2client.service_account import ServiceAccountCredentials

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.secret_key = "gcbs_insta_monitor_s3cr3t_2024"

USERS = {
    "instagram": {"password": "12345",      "display": "Instagram"},
    "nike":      {"password": "12345",      "display": "Nike"},
    "openai":    {"password": "12345",      "display": "OpenAI"},
    "admin":     {"password": "admin12345", "display": "Admin", "is_admin": True},
}

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


def get_sheet():
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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
