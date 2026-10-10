import re
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from services.supabase_client import supabase, supabase_admin

auth_bp = Blueprint("auth", __name__)

# П. 6.1.2–6.1.3: требования к email и паролю на стороне СЕРВЕРА
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 6  # минимум Supabase Auth; можно поднять до 8


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")
    full_name = request.form.get("full_name", "").strip()
    phone = request.form.get("phone", "").strip()

    # --- Серверная валидация (п. 6.1, 5.3) ---
    if not email or not password or not full_name or not phone:
        flash("Заполните все обязательные поля.", "danger")
        return render_template("register.html")

    if not EMAIL_RE.match(email):
        flash("Введите корректный email-адрес.", "danger")
        return render_template("register.html")

    if len(password) < MIN_PASSWORD_LEN:
        flash(f"Пароль должен содержать не менее {MIN_PASSWORD_LEN} символов.", "danger")
        return render_template("register.html")

    if password != confirm_password:
        flash("Пароль и подтверждение пароля не совпадают.", "danger")
        return render_template("register.html")

    try:
        # 1. Регистрация в Supabase Auth
        res = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"full_name": full_name, "phone": phone}}
        })

        if res.user is None:
            flash("Не удалось создать аккаунт. Возможно, email уже занят.", "danger")
            return render_template("register.html")

        # 2. Профиль в public.users. Роль всегда "user" — публично
        #    назначить администратора нельзя (п. 6.1.6).
        try:
            supabase_admin.table("users").insert({
                "id": res.user.id,
                "email": email,
                "full_name": full_name,
                "phone": phone,
                "role": "user",
                "is_active": True,
            }).execute()
        except Exception:
            # Профиль уже существует (повторная регистрация) — не критично,
            # но в интерфейс детали не выводим (п. 2.9)
            pass

        # 3. Сессия
        session["user"] = {
            "id": res.user.id,
            "email": email,
            "full_name": full_name,
            "phone": phone,
            "role": "user",
        }

        flash(f"Добро пожаловать, {full_name}! Регистрация успешна.", "success")
        return redirect(url_for("main.index"))

    except Exception as e:
        # Детали ошибки — только в лог сервера, пользователю — нейтральный текст
        print(f"Register error: {e}")
        flash("Не удалось завершить регистрацию. Попробуйте позже.", "danger")
        return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
    except Exception:
        flash("Неверный email или пароль.", "danger")
        return render_template("login.html")

    profile = (
        supabase_admin.table("users")
        .select("*")
        .eq("id", res.user.id)
        .single()
        .execute()
        .data
    )

    # Заблокированные пользователи не допускаются (п. 9.2.3)
    if profile and not profile.get("is_active", True):
        supabase.auth.sign_out()
        flash("Учетная запись заблокирована администратором.", "danger")
        return render_template("login.html")

    session["user"] = {
        "id": res.user.id,
        "email": profile.get("email", email) if profile else email,
        "full_name": profile.get("full_name", "Пользователь") if profile else "Пользователь",
        "phone": profile.get("phone", "") if profile else "",
        "role": profile.get("role", "user") if profile else "user",
    }
    flash(f"Добро пожаловать, {session['user']['full_name']}!", "success")

    if session["user"]["role"] in ("admin", "super_admin"):
        return redirect(url_for("admin.admin_dashboard"))
    return redirect(url_for("main.index"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("main.index"))