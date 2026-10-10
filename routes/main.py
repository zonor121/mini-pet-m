from datetime import datetime, timedelta
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from services.security import get_current_user, login_required
from services.supabase_client import supabase_admin
from services.log_service import log_status_change

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    search = request.args.get("q", "").strip()
    date_filter = request.args.get("date", "").strip()
    category_filter = request.args.get("category", "").strip()

    # Категории для фильтра (серверный доступ через service_role)
    categories = supabase_admin.table("categories").select("*").order("name").execute().data or []
    slug_to_id = {c.get("slug"): c.get("id") for c in categories}

    now_iso = datetime.utcnow().isoformat()

    # Берём ВСЕ опубликованные события: актуальные и прошедшие
    all_events = (
        supabase_admin.table("events")
        .select("*, categories(*)")
        .eq("status", "published")
        .order("event_date")
        .execute()
        .data or []
    )

    # Актуальные — по возрастанию даты, прошедшие — после них, по убыванию
    upcoming = [e for e in all_events if (e.get("event_date") or "") >= now_iso]
    past = [e for e in all_events if (e.get("event_date") or "") < now_iso]
    events = upcoming + list(reversed(past))

    # Поиск: название, описание, место
    if search:
        q = search.lower()
        events = [
            e for e in events
            if q in e.get("title", "").lower()
            or q in (e.get("description") or "").lower()
            or q in (e.get("location") or "").lower()
        ]

    # Фильтр по категории (slug -> id)
    if category_filter and category_filter in slug_to_id:
        cat_id = slug_to_id[category_filter]
        events = [e for e in events if e.get("category_id") == cat_id]

    # Фильтр по дате
    if date_filter:
        now = datetime.utcnow()
        today_str = now.date().isoformat()
        if date_filter == "today":
            events = [e for e in events if (e.get("event_date") or "")[:10] == today_str]
        elif date_filter == "week":
            week_later = (now + timedelta(days=7)).isoformat()
            now_iso2 = now.isoformat()
            events = [e for e in events if now_iso2 <= (e.get("event_date") or "") <= week_later]
        elif date_filter == "month":
            month_prefix = today_str[:7]
            events = [e for e in events if (e.get("event_date") or "")[:7] == month_prefix]

    return render_template(
        "index.html",
        events=events,
        search=search,
        date_filter=date_filter,
        category_filter=category_filter,
        categories=categories,
        now_iso=now_iso,
    )


@main_bp.route("/event/<slug>")
def event_detail(slug):
    event = (
        supabase_admin.table("events")
        .select("*")
        .eq("slug", slug)
        .single()
        .execute()
        .data
    )
    if not event:
        flash("Мероприятие не найдено.", "danger")
        return redirect(url_for("main.index"))
    return render_template("detail.html", event=event, now_iso=datetime.utcnow().isoformat())


@main_bp.route("/event/<int:event_id>/register", methods=["POST"])
@login_required
def register_event(event_id):
    user = get_current_user()
    phone = request.form.get("phone", "").strip()
    comment = request.form.get("comment", "").strip()

    # Валидация телефона (п. 6.2, 8)
    if not phone or len(phone) < 10:
        flash("Укажите корректный номер телефона.", "danger")
        return redirect(url_for("main.event_detail", slug=request.form.get("slug", "")))

    # Проверка события и мест (п. 6.6)
    event = supabase_admin.table("events").select("*").eq("id", event_id).single().execute().data
    if not event:
        flash("Мероприятие не найдено.", "danger")
        return redirect(url_for("main.index"))

    # Бизнес-правило: запрет регистрации на прошедшее событие (п. 7.3)
    if (event.get("event_date") or "") < datetime.utcnow().isoformat():
        flash("Это мероприятие уже завершилось.", "warning")
        return redirect(url_for("main.event_detail", slug=event["slug"]))

    if event["available_seats"] <= 0:
        flash("К сожалению, все места на это мероприятие заняты.", "danger")
        return redirect(url_for("main.event_detail", slug=event["slug"]))

    # Бизнес-правило: запрет дубля регистрации (п. 6.7)
    dup = (
        supabase_admin.table("registrations")
        .select("id")
        .eq("event_id", event_id)
        .eq("user_id", user["id"])
        .not_.in_("status", ["cancelled_by_user", "cancelled_by_admin", "rejected"])
        .execute()
        .data
    )
    if dup:
        flash("Вы уже зарегистрированы на это мероприятие.", "warning")
        return redirect(url_for("main.event_detail", slug=event["slug"]))

    now = datetime.utcnow().isoformat()

    # Создание регистрации (сразу confirmed)
    reg_res = supabase_admin.table("registrations").insert({
        "user_id": user["id"],
        "event_id": event_id,
        "status": "confirmed",
        "phone": phone,
        "comment": comment,
        "registered_at": now,
        "confirmed_at": now,
    }).execute()

    new_reg_id = reg_res.data[0]["id"] if reg_res.data else None

    # Логирование создания (п. 6.9)
    if new_reg_id:
        log_status_change(new_reg_id, None, "confirmed", user["id"])

    # Уменьшение мест
    supabase_admin.table("events").update({
        "available_seats": event["available_seats"] - 1
    }).eq("id", event_id).execute()

    flash("Вы успешно зарегистрированы! Подтверждение отправлено на почту.", "success")
    return redirect(url_for("main.cabinet"))


@main_bp.route("/cabinet")
@login_required
def cabinet():
    user = get_current_user()
    regs = (
        supabase_admin.table("registrations")
        .select("*, events(title, slug, event_date)")
        .eq("user_id", user["id"])
        .order("registered_at", desc=True)
        .execute()
        .data or []
    )
    # Актуальный профиль из БД (на случай изменений из админки)
    profile = (
        supabase_admin.table("users")
        .select("full_name, email, phone, role")
        .eq("id", user["id"])
        .single()
        .execute()
        .data
    )
    return render_template("cabinet.html", registrations=regs, profile=profile, active_tab=request.args.get("tab", "registrations"))


@main_bp.route("/cabinet/profile", methods=["POST"])
@login_required
def update_profile():
    user = get_current_user()
    full_name = request.form.get("full_name", "").strip()
    phone = request.form.get("phone", "").strip()

    if not full_name:
        flash("ФИО не может быть пустым.", "danger")
        return redirect(url_for("main.cabinet", tab="profile"))
    if phone and len(phone) < 10:
        flash("Укажите корректный номер телефона.", "danger")
        return redirect(url_for("main.cabinet", tab="profile"))

    try:
        supabase_admin.table("users").update({
            "full_name": full_name,
            "phone": phone,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", user["id"]).execute()

        # Синхронизируем сессию
        session["user"]["full_name"] = full_name
        session["user"]["phone"] = phone
        session.modified = True

        flash("Профиль обновлён.", "success")
    except Exception:
        flash("Не удалось сохранить профиль. Попробуйте позже.", "danger")

    return redirect(url_for("main.cabinet", tab="profile"))


@main_bp.route("/cancel/<int:reg_id>", methods=["POST"])
@login_required
def cancel_registration(reg_id):
    user = get_current_user()
    reg = supabase_admin.table("registrations").select("*").eq("id", reg_id).single().execute().data

    if not reg or reg["user_id"] != user["id"]:
        flash("Регистрация не найдена.", "danger")
        return redirect(url_for("main.cabinet"))

    # Бизнес-правило: отмена возможна только из Created или Confirmed (п. 5)
    if reg["status"] not in ("created", "confirmed"):
        flash("Эту регистрацию нельзя отменить.", "warning")
        return redirect(url_for("main.cabinet"))

    supabase_admin.table("registrations").update({
        "status": "cancelled_by_user",
        "cancelled_at": datetime.utcnow().isoformat()
    }).eq("id", reg_id).execute()

    # Логирование отмены пользователем (п. 6.9)
    log_status_change(reg_id, reg["status"], "cancelled_by_user", user["id"])

    # Возврат места
    ev = supabase_admin.table("events").select("id, available_seats, total_seats").eq("id", reg["event_id"]).single().execute().data
    if ev:
        supabase_admin.table("events").update({
            "available_seats": min(ev["available_seats"] + 1, ev["total_seats"])
        }).eq("id", ev["id"]).execute()

    flash("Регистрация успешно отменена.", "success")
    return redirect(url_for("main.cabinet"))


@main_bp.route("/healthz")
def health_check():
    return "OK", 200