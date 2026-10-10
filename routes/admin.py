import csv
import io
import codecs
from datetime import datetime
from flask import Blueprint, Response, flash, redirect, render_template, request, session, url_for
from services.security import admin_required, super_admin_required, get_current_user
from services.supabase_client import supabase_admin
from services.log_service import log_status_change

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin")
@admin_required
def admin_dashboard():
    status_filter = request.args.get("status", "").strip()
    user_filter = request.args.get("user_id", "").strip()

    stats = {"total_users": 0, "active_events": 0, "revenue": 0.0, "cancel_rate": 0.0}
    status_stats = {"confirmed": 0, "created": 0, "attended": 0, "cancelled": 0, "total": 0}
    regs = []
    all_users = []
    logs_map = {}

    try:
        # Вспомогательная функция для подсчета
        def count(table, filters=None):
            q = supabase_admin.table(table).select("id", count="exact")
            if filters:
                for k, v in filters.items():
                    q = q.in_(k, v) if isinstance(v, list) else q.eq(k, v)
            res = q.execute()
            return int(res.count) if hasattr(res, "count") else len(res.data or [])

        # --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
        # Считаем именно пользователей из таблицы users
        total_users = count("users") 
        
        # Остальные метрики
        active_events = count("events", {"status": "published"})
        
        confirmed = count("registrations", {"status": "confirmed"})
        created = count("registrations", {"status": "created"})
        attended = count("registrations", {"status": "attended"})
        cancelled = count("registrations", {"status": ["cancelled_by_user", "cancelled_by_admin", "rejected"]})
        
        total_regs = confirmed + created + attended + cancelled
        cancel_rate = round((cancelled / total_regs * 100), 1) if total_regs > 0 else 0.0

        stats = {
            "total_users": total_users,      # Теперь здесь реальное число юзеров
            "active_events": active_events,
            "revenue": 0.0,                  # Упрощено для стабильности
            "cancel_rate": cancel_rate
        }
        # -------------------------

        status_stats = {
            "confirmed": confirmed, "created": created, 
            "attended": attended, "cancelled": cancelled,
            "total": total_regs
        }

        # Список пользователей для фильтра
        all_users = supabase_admin.table("users").select("id, full_name").order("full_name").execute().data or []

        # Реестр через VIEW
        query = supabase_admin.table("admin_registrations_view").select("*").order("registered_at", desc=True).limit(100)
        if status_filter == "cancelled":
            query = query.in_("status", ["cancelled_by_user", "cancelled_by_admin", "rejected"])
        elif status_filter:
            query = query.eq("status", status_filter)
        if user_filter:
            query = query.eq("user_id", user_filter)
            
        regs = query.execute().data or []

        # Загрузка логов для tooltip
        if regs:
            reg_ids = [r["id"] for r in regs]
            logs_res = supabase_admin.table("registration_logs").select("*").in_("registration_id", reg_ids).order("created_at", desc=True).execute()
            for log in logs_res.data:
                rid = log["registration_id"]
                if rid not in logs_map:
                    logs_map[rid] = []
                logs_map[rid].append(log)

    except Exception as e:
        print(f"ADMIN ERROR: {e}")
        flash("Ошибка загрузки данных панели.", "warning")

    return render_template(
        "admin.html", stats=stats, registrations=regs, 
        status_stats=status_stats, all_users=all_users, 
        logs_map=logs_map, current_status_filter=status_filter
    )


@admin_bp.route("/admin/export")
@admin_required
def export_csv():
    """Экспорт с BOM для корректной кириллицы в Excel (п. 6.8, 12.6)."""
    try:
        query = supabase_admin.table("admin_registrations_view").select("*").order("registered_at", desc=True)
        status_filter = request.args.get("status", "").strip()
        if status_filter == "cancelled":
            query = query.in_("status", ["cancelled_by_user", "cancelled_by_admin", "rejected"])
        elif status_filter:
            query = query.eq("status", status_filter)
            
        regs = query.execute().data or []

        output = io.StringIO()
        output.write(codecs.BOM_UTF8.decode("utf-8"))  # Ключ к правильной кодировке
        
        writer = csv.writer(output, delimiter=";")
        writer.writerow(["ID", "Мероприятие", "Дата", "Участник", "Email", "Телефон", "Статус", "Дата рег."])

        for reg in regs:
            writer.writerow([
                reg.get("id"), reg.get("event_title"), 
                reg.get("event_date", "")[:10], reg.get("user_name"),
                reg.get("user_email"), reg.get("reg_phone") or reg.get("user_phone", ""),
                reg.get("status"), reg.get("registered_at", "")[:10]
            ])

        return Response(
            output.getvalue(), mimetype="text/csv; charset=utf-8-sig",
            headers={"Content-Disposition": "attachment;filename=registrations.csv"}
        )
    except Exception as e:
        flash(f"Ошибка экспорта: {e}", "danger")
        return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/admin/cancel/<int:reg_id>", methods=["POST"])
@admin_required
def admin_cancel_registration(reg_id):
    try:
        res = supabase_admin.table("registrations").select("*").eq("id", reg_id).execute()
        if not res.data:
            flash("Регистрация не найдена.", "warning")
            return redirect(url_for("admin.admin_dashboard"))
            
        reg = res.data[0] if isinstance(res.data, list) else res.data
        old_status = reg.get("status")

        if old_status in ["cancelled_by_user", "cancelled_by_admin", "rejected", "attended"]:
            flash("Эту заявку нельзя отменить.", "warning")
            return redirect(url_for("admin.admin_dashboard"))

        supabase_admin.table("registrations").update({
            "status": "cancelled_by_admin", "cancelled_at": datetime.utcnow().isoformat()
        }).eq("id", reg_id).execute()

        # Лог отмены организатором (п. 6.9)
        log_status_change(reg_id, old_status, "cancelled_by_admin", session["user"]["id"])

        # Возврат места
        ev = supabase_admin.table("events").select("available_seats, total_seats").eq("id", reg["event_id"]).single().execute()
        if ev.data:
            ev_data = ev.data[0] if isinstance(ev.data, list) else ev.data
            supabase_admin.table("events").update({
                "available_seats": min(ev_data["available_seats"] + 1, ev_data["total_seats"])
            }).eq("id", reg["event_id"]).execute()

        flash("Регистрация отменена.", "success")
    except Exception as e:
        flash(f"Ошибка: {e}", "danger")
        
    return redirect(url_for("admin.admin_dashboard", status=request.args.get("status")))


@admin_bp.route("/admin/attend/<int:reg_id>", methods=["POST"])
@admin_required
def mark_attended(reg_id):
    """Отметка посещения (п. 5, 6.5, 12.3)."""
    try:
        reg = supabase_admin.table("registrations").select("status").eq("id", reg_id).single().execute().data
        if not reg or reg["status"] != "confirmed":
            flash("Нельзя отметить посещение для этой заявки.", "warning")
            return redirect(url_for("admin.admin_dashboard"))

        supabase_admin.table("registrations").update({"status": "attended"}).eq("id", reg_id).execute()
        
        # Лог посещения (п. 6.9)
        log_status_change(reg_id, "confirmed", "attended", session["user"]["id"])
        
        flash("Посещение отмечено.", "success")
    except Exception as e:
        flash(f"Ошибка: {e}", "danger")
        
    return redirect(url_for("admin.admin_dashboard"))


# --- Управление пользователями (Только Super Admin) ---

@admin_bp.route("/admin/users")
@super_admin_required
def admin_users():
    try:
        users = supabase_admin.table("users").select("*").order("created_at", desc=True).execute().data or []
        return render_template("admin_users.html", users=users)
    except Exception as e:
        flash("Ошибка загрузки пользователей", "danger")
        return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/admin/users/<user_id>/toggle_role", methods=["POST"])
@super_admin_required
def toggle_user_role(user_id):
    try:
        user = supabase_admin.table("users").select("role").eq("id", user_id).single().execute().data
        if user_id == session["user"]["id"]:
            flash("Нельзя изменить свою роль.", "warning")
            return redirect(url_for("admin.admin_users"))

        new_role = "user" if user.get("role") in ["organizer", "admin", "super_admin"] else "organizer"
        supabase_admin.table("users").update({"role": new_role}).eq("id", user_id).execute()
        flash(f"Роль изменена на {new_role}", "success")
    except Exception as e:
        flash(f"Ошибка: {e}", "danger")
    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/admin/users/<user_id>/edit", methods=["POST"])
@super_admin_required
def edit_user(user_id):
    try:
        full_name = request.form.get("full_name", "").strip()
        role = request.form.get("role", "user")
        is_active = request.form.get("is_active") == "on"

        if user_id == session["user"]["id"] and (role != session["user"]["role"] or not is_active):
            flash("Нельзя заблокировать себя или сменить свою роль.", "warning")
            return redirect(url_for("admin.admin_users"))

        supabase_admin.table("users").update({
            "full_name": full_name, "role": role, "is_active": is_active, 
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", user_id).execute()

        if user_id == session["user"]["id"]:
            session["user"].update({"role": role, "full_name": full_name})
        flash("Данные обновлены.", "success")
    except Exception as e:
        flash(f"Ошибка: {e}", "danger")
    return redirect(url_for("admin.admin_users"))