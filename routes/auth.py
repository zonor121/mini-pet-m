from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from services.supabase_client import supabase, supabase_admin

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    full_name = request.form.get("full_name", "").strip()

    if not email or not password or not full_name:
        flash("Заполните все обязательные поля.", "danger")
        return render_template("register.html")

    try:
        res = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"full_name": full_name}},
        })
        if res.user is None:
            flash("Не удалось создать аккаунт.", "danger")
            return render_template("register.html")

        supabase_admin.table("users").insert({
            "id": res.user.id,
            "email": email,
            "full_name": full_name,
            "role": "user",
            "is_active": True,
        }).execute()

        session["user"] = {
            "id": res.user.id,
            "email": email,
            "full_name": full_name,
            "role": "user",
        }
        flash(f"Добро пожаловать, {full_name}!", "success")
        return redirect(url_for("main.index"))
    except Exception as e:
        flash(f"Ошибка регистрации: {e}", "danger")
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

    if profile and not profile.get("is_active", True):
        supabase.auth.sign_out()
        flash("Учетная запись заблокирована администратором.", "danger")
        return render_template("login.html")

    session["user"] = {
        "id": res.user.id,
        "email": profile.get("email", email) if profile else email,
        "full_name": profile.get("full_name", "Пользователь") if profile else "Пользователь",
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