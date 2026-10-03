from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from services.security import get_current_user, login_required
from services.supabase_client import supabase, supabase_admin

main_bp = Blueprint("main", __name__)


@main_bp.route("/healthz")
def healthz():
    return {"status": "ok", "message": "EventHUB is running"}, 200


@main_bp.route("/")
def index():
    search = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    date_f = request.args.get("date", "").strip()

    categories = supabase.table("categories").select("*").execute().data or []

    query = (
        supabase.table("events")
        .select("*, categories(name, slug)")
        .eq("status", "published")
        .order("event_date", desc=False)
    )

    if search:
        query = query.or_(
            f"title.ilike.%{search}%,description.ilike.%{search}%,location.ilike.%{search}%"
        )

    if category:
        cat = supabase.table("categories").select("id").eq("slug", category).execute().data
        if cat:
            query = query.eq("category_id", cat[0]["id"])
        else:
            return render_template("index.html", events=[], categories=categories,
                                   search=search, category_filter=category, date_filter=date_f)

    now = datetime.utcnow()
    if date_f == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        query = query.gte("event_date", start.isoformat()).lt("event_date", end.isoformat())
    elif date_f == "week":
        query = query.gte("event_date", now.isoformat()).lte("event_date", (now + timedelta(days=7)).isoformat())
    elif date_f == "month":
        query = query.gte("event_date", now.isoformat()).lte("event_date", (now + timedelta(days=30)).isoformat())

    events = query.execute().data or []
    return render_template("index.html", events=events, categories=categories,
                           search=search, category_filter=category, date_filter=date_f)


@main_bp.route("/event/<slug>")
def event_detail(slug):
    event = (
        supabase.table("event_details_view")
        .select("*")
        .eq("slug", slug)
        .single()
        .execute()
        .data
    )
    if not event:
        flash("Мероприятие не найдено", "danger")
        return redirect(url_for("main.index"))
    return render_template("detail.html", event=event)


@main_bp.route("/cabinet")
@login_required
def cabinet():
    user = get_current_user()
    regs = (
        supabase.table("registrations")
        .select("*, events(title, slug, event_date, location)")
        .eq("user_id", user["id"])
        .order("registered_at", desc=True)
        .execute()
        .data or []
    )
    active = [r for r in regs if r["status"] in ("created", "confirmed")]
    nearest = active[0] if active else None
    return render_template("cabinet.html", registrations=regs, nearest=nearest)


@main_bp.route("/event/<int:event_id>/register", methods=["POST"])
@login_required
def register_event(event_id):
    user = get_current_user()
    comment = request.form.get("comment", "").strip()

    event = supabase.table("events").select("*").eq("id", event_id).single().execute().data
    if not event:
        flash("Мероприятие не найдено", "danger")
        return redirect(url_for("main.index"))

    if event["available_seats"] <= 0:
        flash("К сожалению, все места на это мероприятие заняты.", "danger")
        return redirect(url_for("main.event_detail", slug=event["slug"]))

    dup = (
        supabase.table("registrations")
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
    supabase_admin.table("registrations").insert({
        "user_id": user["id"],
        "event_id": event_id,
        "status": "confirmed",
        "comment": comment,
        "registered_at": now,
        "confirmed_at": now,
    }).execute()

    supabase_admin.table("events").update({
        "available_seats": event["available_seats"] - 1
    }).eq("id", event_id).execute()

    flash("Вы успешно зарегистрированы, подтверждение отправлено на почту.", "success")
    return redirect(url_for("main.cabinet"))


@main_bp.route("/cancel/<int:reg_id>", methods=["POST"])
@login_required
def cancel_registration(reg_id):
    user = get_current_user()
    reg = supabase.table("registrations").select("*").eq("id", reg_id).single().execute().data

    if not reg or reg["user_id"] != user["id"]:
        flash("Регистрация не найдена.", "danger")
        return redirect(url_for("main.cabinet"))

    if reg["status"] not in ("created", "confirmed"):
        flash("Эту регистрацию нельзя отменить.", "warning")
        return redirect(url_for("main.cabinet"))

    supabase_admin.table("registrations").update({
        "status": "cancelled_by_user",
        "cancelled_at": datetime.utcnow().isoformat(),
    }).eq("id", reg_id).execute()

    ev = supabase.table("events").select("available_seats, total_seats").eq("id", reg["event_id"]).single().execute().data
    if ev:
        supabase_admin.table("events").update({
            "available_seats": min(ev["available_seats"] + 1, ev["total_seats"])
        }).eq("id", ev["id"]).execute()

    flash("Регистрация успешно отменена.", "success")
    return redirect(url_for("main.cabinet"))