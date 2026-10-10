import os
from datetime import datetime

from services.supabase_client import supabase_admin


def ensure_admin():
    """Создаёт начальную учётную запись администратора из переменных
    окружения при первом запуске (п. 6.2 лабораторной).

    ADMIN_EMAIL и ADMIN_PASSWORD задаются только в .env (п. 6.2.1),
    в коде и логах пароль не выводится (п. 6.2.5). Повторные запуски
    идемпотентны: если профиль с таким email уже есть — ничего не делаем.
    """
    email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD") or ""
    full_name = os.environ.get("ADMIN_NAME", "Главный Администратор")

    if not email or not password:
        return  # переменные не заданы — механизм не активен

    try:
        # Профиль уже есть — админ создан ранее, выходим
        existing = (
            supabase_admin.table("users")
            .select("id, role")
            .eq("email", email)
            .execute()
            .data
        )
        if existing:
            return

        # Создаём пользователя в Supabase Auth (только серверная сторона, п. 6.2.3)
        auth_user = None
        try:
            res = supabase_admin.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"full_name": full_name},
            })
            auth_user = res.user
        except Exception as e:
            # Возможно, пользователь уже есть в Auth (например, создан вручную)
            print(f"[ensure_admin] auth.create_user: пользователь может уже существовать")
            try:
                found = supabase_admin.auth.admin.list_users()
                for u in (getattr(found, "users", None) or []):
                    if getattr(u, "email", "").lower() == email:
                        auth_user = u
                        break
            except Exception:
                auth_user = None

        if not auth_user or not getattr(auth_user, "id", None):
            print("[ensure_admin] не удалось получить пользователя Auth для ADMIN_EMAIL")
            return

        # Профиль с ролью super_admin
        supabase_admin.table("users").insert({
            "id": auth_user.id,
            "email": email,
            "full_name": full_name,
            "role": "super_admin",
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
        }).execute()

        print(f"[ensure_admin] администратор {email} создан")

    except Exception as e:
        # Никаких секретов в вывод — только факт ошибки
        print("[ensure_admin] ошибка инициализации администратора:", type(e).__name__)