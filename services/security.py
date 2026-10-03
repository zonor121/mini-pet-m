from functools import wraps
from flask import flash, redirect, session, url_for


def get_current_user():
    return session.get("user")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            flash("Пожалуйста, войдите в систему.", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Доступ для Организатора и Супер-админа."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        # Проверяем наличие прав организатора или админа
        if not user or user.get("role") not in ("organizer", "admin", "super_admin"):
            flash("Доступ запрещен. Требуются права организатора.", "danger")
            return redirect(url_for("main.index"))
        return f(*args, **kwargs)
    return decorated


def super_admin_required(f):
    """Доступ только для Супер-админа (управление пользователями)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or user.get("role") != "super_admin":
            flash("Доступ запрещен. Только для супер-администратора.", "danger")
            return redirect(url_for("main.index"))
        return f(*args, **kwargs)
    return decorated