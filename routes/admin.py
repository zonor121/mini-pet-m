import csv
import io
from datetime import datetime
import codecs

from flask import Blueprint, Response, flash, redirect, render_template, request, session, url_for

from services.security import admin_required, get_current_user, super_admin_required
from services.supabase_client import supabase_admin

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin")
@admin_required
def admin_dashboard():
    """Панель аналитики и реестр регистраций."""
    status_filter = request.args.get("status", "").strip()
    user_filter = request.args.get("user_id", "").strip()

    # Значения по умолчанию
    stats = {"total_regs": 0, "active_events": 0, "total_users": 0, "revenue": 0.0, "cancel_rate": 0.0}
    status_stats = {"confirmed": 0, "created": 0, "cancelled": 0, "attended": 0, "total": 0}
    regs = []
    all_users = []

    try:
        # --- 1. Статистика (простые запросы count) ---
        def get_count(table, filters=None):
            q = supabase_admin.table(table).select("id", count="exact")
            if filters:
                for k, v in filters.items():
                    q = q.in_(k, v) if isinstance(v, list) else q.eq(k, v)
            res = q.execute()
            return int(res.count) if hasattr(res, "count") else len(res.data or [])

        total_regs = get_count("registrations")
        active_events = get_count("events", {"status": "published"})
        total_users = get_count("users")
        
        confirmed = get_count("registrations", {"status": "confirmed"})
        created = get_count("registrations", {"status": "created"})
        attended = get_count("registrations", {"status": "attended"})
        cancelled = get_count("registrations", {"status": ["cancelled_by_user", "cancelled_by_admin", "rejected"]})

        cancel_rate = round((cancelled / total_regs) * 100, 1) if total_regs > 0 else 0.0

        # Выручка (упрощенно: сумма цен событий с подтвержденными/посещенными регистрациями)
        revenue = 0.0
        try:
            paid_regs = supabase_admin.table("registrations").select("event_id").in_("status", ["confirmed", "attended"]).execute().data
            if paid_regs:
                ids = list(set(r["event_id"] for r in paid_regs))
                prices = supabase_admin.table("events").select("price").in_("id", ids).execute().data
                # Грубая оценка выручки (сумма цен уникальных событий, где есть продажи)
                revenue = sum(float(p["price"]) for p in prices if p.get("price"))
        except Exception:
            pass

        stats = {
            "total_regs": total_regs, "active_events": active_events,
            "total_users": total_users, "revenue": revenue, "cancel_rate": cancel_rate
        }
        status_stats = {
            "confirmed": confirmed, "created": created, "cancelled": cancelled, 
            "attended": attended, "total": confirmed + created + cancelled + attended
        }

        # --- 2. Список пользователей для фильтра ---
        all_users = supabase_admin.table("users").select("id, full_name").order("full_name").execute().data or []

        # --- 3. Реестр регистраций (через VIEW) ---
        query = supabase_admin.table("admin_registrations_view").select("*").order("registered_at", desc=True).limit(100)

        if status_filter == "cancelled":
            query = query.in_("status", ["cancelled_by_user", "cancelled_by_admin", "rejected"])
        elif status_filter:
            query = query.eq("status", status_filter)

        if user_filter:
            query = query.eq("user_id", user_filter)

        regs = query.execute().data or []

    except Exception as e:
        print(f"ADMIN ERROR: {e}")
        flash("Ошибка загрузки данных панели.", "warning")

    return render_template(
        "admin.html",
        stats=stats,
        registrations=regs,
        status_stats=status_stats,
        all_users=all_users,
        current_status_filter=status_filter
    )


@admin_bp.route("/admin/export")
@admin_required
def export_csv():
    """Экспорт регистраций в CSV с правильной кодировкой для Excel."""
    status_filter = request.args.get("status", "").strip()
    user_filter = request.args.get("user_id", "").strip()

    try:
        query = supabase_admin.table("admin_registrations_view").select("*").order("registered_at", desc=True)

        if status_filter == "cancelled":
            query = query.in_("status", ["cancelled_by_user", "cancelled_by_admin", "rejected"])
        elif status_filter:
            query = query.eq("status", status_filter)
        if user_filter:
            query = query.eq("user_id", user_filter)

        regs = query.execute().data or []

        # Создаем строковый буфер
        output = io.StringIO()
        
        # ЗАПИСЫВАЕМ BOM (маркер кодировки UTF-8) в самое начало
        # Это заставляет Excel понимать, что файл в UTF-8
        output.write(codecs.BOM_UTF8.decode('utf-8')) 
        
        writer = csv.writer(output, delimiter=';') # Используем точку с запятой, так Excel лучше понимает колонки в РФ
        
        # Заголовки
        writer.writerow(["ID", "Мероприятие", "Дата события", "Участник", "Email", "Статус", "Дата регистрации"])

        for reg in regs:
            writer.writerow([
                reg.get("id"),
                reg.get("event_title", "N/A"),
                reg.get("event_date", "")[:10] if reg.get("event_date") else "",
                reg.get("user_name", "Unknown"),
                reg.get("user_email", ""),
                reg.get("status"),
                reg.get("registered_at", "")[:10] if reg.get("registered_at") else ""
            ])

        # Получаем содержимое
        csv_content = output.getvalue()
        
        # Возвращаем файл
        # Важно: mimetype должен быть text/csv, но кодировку мы уже внедрили через BOM
        return Response(
            csv_content,
            mimetype="text/csv; charset=utf-8-sig", # charset=utf-8-sig тоже помогает браузерам
            headers={"Content-Disposition": "attachment;filename=registrations.csv"}
        )
        
    except Exception as e:
        print(f"Export error: {e}")
        flash(f"Ошибка экспорта: {e}", "danger")
        return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/admin/cancel/<int:reg_id>", methods=["POST"])
@admin_required
def admin_cancel_registration(reg_id):
    """Отмена регистрации организатором."""
    try:
        # 1. Получаем данные регистрации
        # Используем .maybe_single() или проверяем .data явно
        res = supabase_admin.table("registrations").select("*").eq("id", reg_id).execute()
        
        # В зависимости от версии библиотеки, данные могут быть в res.data (список) или res.data (объект)
        if not res.data:
            flash("Регистрация не найдена.", "warning")
            return redirect(url_for("admin.admin_dashboard"))
            
        # Если вернулся список, берем первый элемент
        reg = res.data[0] if isinstance(res.data, list) else res.data

        # 2. Проверяем статус (нельзя отменить уже отмененное или посещенное)
        if reg.get("status") in ["cancelled_by_user", "cancelled_by_admin", "rejected", "attended"]:
            flash("Эту заявку нельзя отменить (она уже закрыта).", "warning")
            return redirect(url_for("admin.admin_dashboard"))

        # 3. Обновляем статус
        supabase_admin.table("registrations").update({
            "status": "cancelled_by_admin",
            "cancelled_at": datetime.utcnow().isoformat()
        }).eq("id", reg_id).execute()

        # 4. Возвращаем место
        # Получаем ID события из найденной регистрации
        event_id = reg.get("event_id")
        if event_id:
            ev_res = supabase_admin.table("events").select("available_seats, total_seats").eq("id", event_id).execute()
            if ev_res.data:
                ev = ev_res.data[0] if isinstance(ev_res.data, list) else ev_res.data
                new_avail = min(ev.get("available_seats", 0) + 1, ev.get("total_seats", 0))
                supabase_admin.table("events").update({"available_seats": new_avail}).eq("id", event_id).execute()

        flash("Регистрация успешно отменена.", "success")

    except Exception as e:
        print(f"Cancel error: {e}")
        flash(f"Ошибка при отмене: {str(e)}", "danger")

    # Сохраняем фильтр при возврате
    status_filter = request.args.get("status", "")
    return redirect(url_for("admin.admin_dashboard", status=status_filter))


@admin_bp.route("/admin/attend/<int:reg_id>", methods=["POST"])
@admin_required
def mark_attended(reg_id):
    """Отметка о посещении (финальный статус)."""
    try:
        reg = supabase_admin.table("registrations").select("status").eq("id", reg_id).single().execute().data
        if not reg or reg["status"] != "confirmed":
            flash("Нельзя отметить посещение для этой заявки.", "warning")
            return redirect(url_for("admin.admin_dashboard"))

        supabase_admin.table("registrations").update({"status": "attended"}).eq("id", reg_id).execute()
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
        if user_id == session['user']['id']:
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

        if user_id == session['user']['id'] and (role != session['user']['role'] or not is_active):
            flash("Нельзя заблокировать себя или сменить свою роль.", "warning")
            return redirect(url_for("admin.admin_users"))

        supabase_admin.table("users").update({
            "full_name": full_name, "role": role, "is_active": is_active, "updated_at": datetime.utcnow().isoformat()
        }).eq("id", user_id).execute()

        if user_id == session['user']['id']:
            session['user'].update({"role": role, "full_name": full_name})

        flash("Данные обновлены.", "success")
    except Exception as e:
        flash(f"Ошибка: {e}", "danger")
    return redirect(url_for("admin.admin_users"))