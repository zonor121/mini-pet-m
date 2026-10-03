"""
seed_users.py — Генератор тестовых пользователей для EventHUB
Запуск: python seed_users.py
"""

import os
from dotenv import load_dotenv
from services.supabase_client import supabase_admin as supabase
from services.supabase_client import create_client

load_dotenv()

# Используем SERVICE_ROLE ключ для админских операций
supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_KEY"]
)

TEST_USERS = [
    {"email": "ivan@example.com", "password": "123456", "full_name": "Иван Иванов"},
    {"email": "maria@example.com", "password": "123456", "full_name": "Мария Петрова"},
    {"email": "alex@example.com", "password": "123456", "full_name": "Алексей Смирнов"},
    {"email": "elena@example.com", "password": "123456", "full_name": "Елена Васильева"},
    {"email": "dmitry@example.com", "password": "123456", "full_name": "Дмитрий Козлов"},
]

def seed_users():
    print("\n=== Создание тестовых пользователей ===\n")
    
    created_count = 0
    skipped_count = 0

    # 1. Получаем список существующих пользователей один раз (оптимизация)
    try:
        response = supabase.auth.admin.list_users()
        
        # Универсальный парсинг ответа (Users list, Data list или просто List)
        existing_users = []
        if hasattr(response, 'users'):
            existing_users = response.users
        elif hasattr(response, 'data'):
            existing_users = response.data
        elif isinstance(response, list):
            existing_users = response
            
        # Преобразуем в словарь {email: id} для быстрого поиска
        users_map = {}
        for u in existing_users:
            email = u.email if hasattr(u, 'email') else u.get('email')
            uid = u.id if hasattr(u, 'id') else u.get('id')
            if email:
                users_map[email] = uid
                
    except Exception as e:
        print(f"⚠️ Не удалось получить список пользователей: {e}")
        users_map = {}

    for user_data in TEST_USERS:
        email = user_data["email"]
        password = user_data["password"]
        full_name = user_data["full_name"]

        try:
            # 2. Проверяем, есть ли пользователь в Auth
            if email in users_map:
                print(f"  = Пользователь уже существует в Auth: {email}")
                user_id = users_map[email]
                
                # Проверяем профиль в public.users
                db_check = supabase.table("users").select("id").eq("id", user_id).execute()
                
                if not db_check.data:
                    print(f"    -> Восстанавливаем профиль в public.users...")
                    supabase.table("users").insert({
                        "id": user_id,
                        "email": email,
                        "full_name": full_name,
                        "role": "user",
                        "is_active": True
                    }).execute()
                
                skipped_count += 1
                continue

            # 3. Создаем пользователя в Supabase Auth
            print(f"  + Создание в Auth: {email}...")
            auth_response = supabase.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"full_name": full_name}
            })

            # Безопасное получение ID созданного пользователя
            new_user = None
            if hasattr(auth_response, 'user'):
                new_user = auth_response.user
            elif isinstance(auth_response, dict) and 'user' in auth_response:
                new_user = auth_response['user']
            
            if new_user:
                user_id = new_user.id if hasattr(new_user, 'id') else new_user.get('id')
                
                # 4. Создаем профиль в public.users
                print(f"    -> Создание профиля в БД...")
                supabase.table("users").insert({
                    "id": user_id,
                    "email": email,
                    "full_name": full_name,
                    "role": "user",
                    "is_active": True
                }).execute()
                
                print(f"    ✅ Успешно создан: {email} / {password}")
                created_count += 1
            else:
                print(f"    ❌ Ошибка: Auth не вернул данные пользователя")

        except Exception as e:
            print(f"  ! Ошибка при обработке {email}: {str(e)}")

    print(f"\n  Итого: создано {created_count}, пропущено {skipped_count}")
    print("\n=== Готово! ===\n")
    print("Данные для входа:")
    for u in TEST_USERS:
        print(f"  Email: {u['email']}  |  Пароль: {u['password']}")

if __name__ == "__main__":
    seed_users()