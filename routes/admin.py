from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from services.security import admin_required, get_current_user
from services.supabase_client import supabase_admin

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin")
@admin_required
def admin_dashboard():
    """Панель аналитики и список регистраций."""
    status_filter = request.args.get("status", "").strip()

    # Значения по умолчанию на случай ошибки БД
    stats = {
        "total_regs": 0, "active_events": 0, "total_users": 0,
        "revenue": 0.0, "cancel_rate": 0.0
    }
    chart_data = {
        "labels": ["Подтверждены", "В ожидании", "Отменены"],
        "values": [0, 0, 0],
        "colors": ["#10B981", "#6366F1", "#EF4444"]
    }
    status_stats = {"confirmed": 0, "created": 0, "cancelled": 0, "total": 0}
    regs = []

    try:
        # Вспомогательная функция для безопасного подсчета строк
        def get_int_count(table_name, filter_dict=None):
            q = supabase_admin.table(table_name).select("id", count="exact")
            if filter_dict:
                for k, v in filter_dict.items():
                    q = q.in_(k, v) if isinstance(v, list) else q.eq(k, v)
            res = q.execute()
            val = getattr(res, "count", None)
            return int(val) if val is not None else len(res.data or [])

        # 1. Считаем показатели
        total_regs = get_int_count("registrations")
        active_events = get_int_count("events", {"status": "published"})
        total_users = get_int_count("users")

        confirmed = get_int_count("registrations", {"status": "confirmed"})
        created = get_int_count("registrations", {"status": "created"})
        cancelled = get_int_count("registrations", {
            "status": ["cancelled_by_user", "cancelled_by_admin", "rejected"]
        })

        cancel_rate = round((cancelled / total_regs) * 100, 1) if total_regs > 0 else 0.0

        # Выручка (сумма цен мероприятий с подтвержденными регистрациями)
        revenue = 0.0
        try:
            conf_regs = supabase_admin.table("registrations").select("event_id").eq("status", "confirmed").execute().data
            if conf_regs:
                event_ids = list(set(r["event_id"] for r in conf_regs))
                prices_res = supabase_admin.table("events").select("price").in_("id", event_ids).execute().data
                revenue = sum(float(p["price"]) for p in prices_res if p.get("price"))
        except Exception as e:
            print(f"Revenue calc error: {e}")

        stats = {
            "total_regs": total_regs,
            "active_events": active_events,
            "total_users": total_users,
            "revenue": revenue,
            "cancel_rate": cancel_rate
        }

        # Данные для графика (CSS Bar Chart)
        chart_data = {
            "labels": ["Подтверждены", "В ожидании", "Отменены"],
            "values": [int(confirmed), int(created), int(cancelled)],
            "colors": ["#10B981", "#6366F1", "#EF4444"]
        }
        status_stats = {
            "confirmed": int(confirmed),
            "created": int(created),
            "cancelled": int(cancelled),
            "total": int(confirmed + created + cancelled)
        }

        # 2. Получаем список регистраций с фильтрацией
        query = (
            supabase_admin.table("registrations")
            .select("*, events(title, event_date)")
            .order("registered_at", desc=True)
            .limit(50)
        )

        if status_filter == "cancelled":
            query = query.in_("status", ["cancelled_by_user", "cancelled_by_admin", "rejected"])
        elif status_filter:
            query = query.eq("status", status_filter)

        regs = query.execute().data or []

    except Exception as e:
        print(f"ADMIN DASHBOARD ERROR: {e}")
        flash("Ошибка загрузки данных панели.", "warning")

    return render_template(
        "admin.html",
        stats=stats,
        registrations=regs,
        status_stats=status_stats,
        chart_data=chart_data,
        current_status_filter=status_filter
    )


@admin_bp.route("/admin/cancel/<int:reg_id>", methods=["POST"])
@admin_required
def admin_cancel_registration(reg_id):
    """Отмена регистрации администратором."""
    try:
        reg_res = supabase_admin.table("registrations").select("*").eq("id", reg_id).single().execute()
        reg = reg_res.data

        if not reg:
            flash("Регистрация не найдена.", "danger")
            return redirect(url_for("admin.admin_dashboard"))

        if reg["status"] in ["cancelled_by_user", "cancelled_by_admin", "rejected", "attended"]:
            flash("Эту регистрацию нельзя отменить (она уже закрыта).", "warning")
            return redirect(url_for("admin.admin_dashboard", status=request.args.get("status")))

        # Обновляем статус
        supabase_admin.table("registrations").update({
            "status": "cancelled_by_admin",
            "cancelled_at": datetime.utcnow().isoformat()
        }).eq("id", reg_id).execute()

        # Возвращаем место
        event_id = reg["event_id"]
        event_res = supabase_admin.table("events").select("available_seats, total_seats").eq("id", event_id).single().execute()
        event = event_res.data

        if event:
            new_available = min(event["available_seats"] + 1, event["total_seats"])
            supabase_admin.table("events").update({"available_seats": new_available}).eq("id", event_id).execute()

        flash(f"Регистрация #{reg_id} успешно отменена.", "success")

    except Exception as e:
        print(f"Cancel error: {e}")
        flash(f"Ошибка при отмене: {str(e)}", "danger")

    status_filter = request.args.get("status", "")
    return redirect(url_for("admin.admin_dashboard", status=status_filter))


@admin_bp.route("/admin/users")
@admin_required
def admin_users():
    """Страница управления пользователями."""
    try:
        users_res = supabase_admin.table("users").select("*").order("created_at", desc=True).execute()
        users = users_res.data or []
        return render_template("admin_users.html", users=users)
    except Exception as e:
        print(f"Error loading users: {e}")
        flash("Ошибка загрузки списка пользователей", "danger")
        return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/admin/users/<user_id>/toggle_role", methods=["POST"])
@admin_required
def toggle_user_role(user_id):
    """Быстрое переключение роли пользователя."""
    try:
        user_res = supabase_admin.table("users").select("role").eq("id", user_id).single().execute()
        current_role = user_res.data.get("role")

        if user_id == session['user']['id']:
            flash("Нельзя изменить роль самому себе.", "warning")
            return redirect(url_for("admin.admin_users"))

        new_role = "user" if current_role in ["admin", "super_admin"] else "admin"

        supabase_admin.table("users").update({"role": new_role}).eq("id", user_id).execute()
        flash(f"Роль пользователя изменена на {new_role}", "success")

    except Exception as e:
        flash(f"Ошибка: {str(e)}", "danger")

    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/admin/users/<user_id>/edit", methods=["POST"])
@admin_required
def edit_user(user_id):
    """Редактирование данных пользователя (имя, роль, статус)."""
    try:
        full_name = request.form.get("full_name", "").strip()
        role = request.form.get("role", "user")
        is_active = request.form.get("is_active") == "on"

        if not full_name:
            flash("Имя не может быть пустым", "danger")
            return redirect(url_for("admin.admin_users"))

        # Защита от блокировки/понижения самого себя
        if user_id == session['user']['id']:
            if role != session['user']['role']:
                flash("Нельзя изменить собственную роль.", "warning")
                return redirect(url_for("admin.admin_users"))
            if not is_active:
                flash("Нельзя заблокировать самого себя.", "warning")
                return redirect(url_for("admin.admin_users"))

        update_data = {
            "full_name": full_name,
            "role": role,
            "is_active": is_active,
            "updated_at": datetime.utcnow().isoformat()
        }

        supabase_admin.table("users").update(update_data).eq("id", user_id).execute()

        # Если редактировали себя, обновляем сессию
        if user_id == session['user']['id']:
            session['user']['role'] = role
            session['user']['full_name'] = full_name

        flash("Данные пользователя успешно обновлены", "success")

    except Exception as e:
        print(f"Edit user error: {e}")
        flash(f"Ошибка сохранения: {str(e)}", "danger")

    return redirect(url_for("admin.admin_users"))