import os
from functools import wraps
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from supabase import create_client, Client

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

# ── Supabase client ──────────────────────────────────────────
supabase: Client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_KEY"],
)


# ── Helpers ──────────────────────────────────────────────────
def get_current_user():
    """Возвращает dict пользователя из сессии или None."""
    return session.get("user")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not get_current_user():
            flash("Войдите в систему", "warning")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        user = get_current_user()
        if user.get("role") not in ("admin", "super_admin"):
            flash("Доступ запрещён", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated


def fmt_date(iso_str: str) -> str:
    """'2024-11-15T10:00:00+03:00' → '15 Ноября, 10:00'"""
    try:
        dt = datetime.fromisoformat(iso_str)
        months = ["Января","Февраля","Марта","Апреля","Мая","Июня",
                  "Июля","Августа","Сентября","Октября","Ноября","Декабря"]
        return f"{dt.day} {months[dt.month - 1]}, {dt.strftime('%H:%M')}"
    except Exception:
        return iso_str or ""


def fmt_short_date(iso_str: str) -> str:
    """'2024-11-15T...' → '15 Ноя 2024'"""
    try:
        dt = datetime.fromisoformat(iso_str)
        months = ["Янв","Фев","Мар","Апр","Мая","Июн",
                  "Июл","Авг","Сен","Окт","Ноя","Дек"]
        return f"{dt.day} {months[dt.month - 1]} {dt.year}"
    except Exception:
        return iso_str or ""


# Передаём хелперы во все шаблоны
app.jinja_env.globals.update(
    fmt_date=fmt_date,
    fmt_short_date=fmt_short_date,
    get_current_user=get_current_user,
)


# ── Routes ───────────────────────────────────────────────────

@app.route("/")
def index():
    search   = request.args.get("q", "")
    category = request.args.get("category", "")
    date_f   = request.args.get("date", "")

    query = (
        supabase.table("events")
        .select("*, categories(name, slug)")
        .eq("status", "published")
        .order("event_date", desc=False)
    )
    if search:
        query = query.ilike("title", f"%{search}%")
    if category:
        query = query.eq("categories.slug", category)

    events = query.execute().data or []

    # Ближайшее событие для баннера (если есть пользователь — показываем в кабинете)
    upcoming = (
        supabase.table("events")
        .select("*")
        .eq("status", "published")
        .gte("event_date", datetime.utcnow().isoformat())
        .order("event_date", desc=False)
        .limit(1)
        .execute()
        .data
    )
    next_event = upcoming[0] if upcoming else None

    return render_template("index.html",
                           events=events,
                           next_event=next_event,
                           search=search)


@app.route("/event/<slug>")
def event_detail(slug):
    result = (
        supabase.table("events")
        .select("*, categories(name), users!organizer_id(full_name)")
        .eq("slug", slug)
        .single()
        .execute()
    )
    event = result.data
    if not event:
        flash("Мероприятие не найдено", "danger")
        return redirect(url_for("index"))

    return render_template("detail.html", event=event)


@app.route("/register/<int:event_id>", methods=["POST"])
@login_required
def register(event_id):
    user = get_current_user()
    comment = request.form.get("comment", "")

    try:
        supabase.table("registrations").insert({
            "user_id":   user["id"],
            "event_id":  event_id,
            "status":    "confirmed",
            "comment":   comment,
        }).execute()
        flash("Вы успешно зарегистрированы!", "success")
    except Exception as e:
        flash(f"Ошибка регистрации: {e}", "danger")

    return redirect(url_for("event_detail",
                            slug=request.form.get("slug", "")))


@app.route("/cabinet")
@login_required
def cabinet():
    user = get_current_user()

    regs = (
        supabase.table("registrations")
        .select("*, events(title, slug, event_date, location, status)")
        .eq("user_id", user["id"])
        .order("registered_at", desc=True)
        .execute()
        .data or []
    )

    upcoming = (
        supabase.table("events")
        .select("*")
        .eq("status", "published")
        .gte("event_date", datetime.utcnow().isoformat())
        .order("event_date", desc=False)
        .limit(1)
        .execute()
        .data
    )
    next_event = upcoming[0] if upcoming else None

    return render_template("cabinet.html",
                           registrations=regs,
                           next_event=next_event)


@app.route("/cancel/<int:reg_id>", methods=["POST"])
@login_required
def cancel_registration(reg_id):
    user = get_current_user()
    supabase.table("registrations").update({
        "status":       "cancelled_by_user",
        "cancelled_at": datetime.utcnow().isoformat(),
    }).eq("id", reg_id).eq("user_id", user["id"]).execute()
    flash("Регистрация отменена", "info")
    return redirect(url_for("cabinet"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    # Метрики
    total_regs   = supabase.table("registrations").select("id", count="exact").execute().count or 0
    active_events = (supabase.table("events").select("id", count="exact")
                     .eq("status", "published").execute().count or 0)
    cancelled     = (supabase.table("registrations").select("id", count="exact")
                     .in_("status", ["cancelled_by_user", "cancelled_by_admin", "rejected"])
                     .execute().count or 0)
    cancel_rate   = round(cancelled / total_regs * 100, 1) if total_regs else 0

    # Регистрации
    regs = (
        supabase.table("registrations")
        .select("*, events(title, event_date, status)")
        .order("registered_at", desc=True)
        .limit(50)
        .execute()
        .data or []
    )

    # Уведомления
    notifs = (
        supabase.table("notifications")
        .select("*")
        .order("created_at", desc=True)
        .limit(10)
        .execute()
        .data or []
    )

    # Статистика статусов
    confirmed_count = (supabase.table("registrations").select("id", count="exact")
                       .eq("status", "confirmed").execute().count or 0)
    created_count   = (supabase.table("registrations").select("id", count="exact")
                       .eq("status", "created").execute().count or 0)
    cancelled_count = cancelled

    stats = {
        "total":    total_regs,
        "active":   active_events,
        "cancel_rate": cancel_rate,
        "confirmed": confirmed_count,
        "created":   created_count,
        "cancelled": cancelled_count,
    }

    return render_template("admin.html",
                           stats=stats,
                           registrations=regs,
                           notifications=notifs)


# ── Простая авторизация через email (демо) ──────────────────
@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email", "").strip()
    result = supabase.table("users").select("*").eq("email", email).execute()
    if result.data:
        session["user"] = result.data[0]
        flash(f"Добро пожаловать, {result.data[0]['full_name']}!", "success")
    else:
        flash("Пользователь не найден", "danger")
    return redirect(request.referrer or url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    flash("Вы вышли из системы", "info")
    return redirect(url_for("index"))


# ── API для таймера (JSON) ───────────────────────────────────
@app.route("/api/next-event")
def api_next_event():
    upcoming = (
        supabase.table("events")
        .select("event_date")
        .eq("status", "published")
        .gte("event_date", datetime.utcnow().isoformat())
        .order("event_date", desc=False)
        .limit(1)
        .execute()
        .data
    )
    if upcoming:
        return jsonify({"event_date": upcoming[0]["event_date"]})
    return jsonify({"event_date": None})


if __name__ == "__main__":
    app.run(debug=True, port=5000)