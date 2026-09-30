import os
from functools import wraps
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from supabase import create_client, Client

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-me")

# ── Supabase Clients ─────────────────────────────────────────
# Anon key для публичных операций (если нужны)
supabase_anon = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_KEY"] # Это anon key
)

# Service role для админских операций (обход RLS, создание юзеров)
supabase_admin = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_KEY"]
)

# ── Инициализация Администратора  ────────────────────
def init_admin():
    """Создает админа из .env, если его нет."""
    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_pass = os.environ.get("ADMIN_PASSWORD")
    
    if not admin_email or not admin_pass:
        print("⚠️ ADMIN_EMAIL или ADMIN_PASSWORD не заданы в .env")
        return

    try:
        # Получаем список пользователей
        response = supabase_admin.auth.admin.list_users()
        
        # В разных версиях библиотеки ответ может быть в .users, .data или быть списком
        users_list = []
        if hasattr(response, 'users'):
            users_list = response.users
        elif hasattr(response, 'data'):
            users_list = response.data
        elif isinstance(response, list):
            users_list = response
            
        # Проверяем, есть ли админ
        admin_exists = False
        admin_id = None
        
        for u in users_list:
            # u может быть объектом User или словарем
            email = u.email if hasattr(u, 'email') else u.get('email')
            uid = u.id if hasattr(u, 'id') else u.get('id')
            
            if email == admin_email:
                admin_exists = True
                admin_id = uid
                break
        
        if not admin_exists:
            print(f"👤 Создание администратора: {admin_email}...")
            new_user = supabase_admin.auth.admin.create_user({
                "email": admin_email,
                "password": admin_pass,
                "email_confirm": True
            })
            
            # Получаем ID созданного пользователя
            created_user = new_user.user if hasattr(new_user, 'user') else new_user.get('user')
            
            if created_user:
                user_id = created_user.id if hasattr(created_user, 'id') else created_user.get('id')
                
                # Создаем профиль в public.users
                try:
                    supabase_admin.table("users").insert({
                        "id": user_id,
                        "email": admin_email,
                        "full_name": "Главный Администратор",
                        "role": "super_admin",
                        "is_active": True
                    }).execute()
                    print("✅ Администратор успешно создан.")
                except Exception as db_err:
                    print(f"⚠️ Ошибка при создании профиля в БД (возможно, уже существует): {db_err}")
            else:
                print("❌ Ошибка создания админа в Auth.")
        else:
            print(f"✅ Администратор {admin_email} уже существует в Auth.")
            # Проверим профиль в БД
            db_user = supabase_admin.table("users").select("*").eq("email", admin_email).execute()
            if not db_user.data:
                print("   -> Восстанавливаем профиль в таблице users...")
                try:
                    supabase_admin.table("users").insert({
                        "id": admin_id,
                        "email": admin_email,
                        "full_name": "Главный Администратор",
                        "role": "super_admin",
                        "is_active": True
                    }).execute()
                except Exception as e:
                    print(f"   -> Ошибка восстановления профиля: {e}")
                 
    except Exception as e:
        print(f"❌ Критическая ошибка инициализации админа: {e}")

# Запускаем при старте
with app.app_context():
    init_admin()

# ── Helpers ─────────────────────────────────────────────────
def get_current_user():
    """Получает данные пользователя из сессии."""
    if 'user' in session:
        return session['user']
    return None

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not get_current_user():
            flash("Пожалуйста, войдите в систему.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        user = get_current_user()
        # Проверяем роль в БД каждый раз (на всякий случай), или берем из сессии
        # Для скорости берем из сессии, но лучше сверять с БД при важных операциях
        if user.get('role') not in ['admin', 'super_admin']:
            flash("Доступ запрещен. Требуются права администратора.", "danger")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

def fmt_date(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        months = ["Января","Февраля","Марта","Апреля","Мая","Июня",
                  "Июля","Августа","Сентября","Октября","Ноября","Декабря"]
        return f"{dt.day} {months[dt.month - 1]}, {dt.strftime('%H:%M')}"
    except: return iso_str or ""

def fmt_short_date(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        months = ["Янв","Фев","Мар","Апр","Мая","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"]
        return f"{dt.day} {months[dt.month - 1]} {dt.year}"
    except: return iso_str or ""

app.jinja_env.globals.update(
    fmt_date=fmt_date, 
    fmt_short_date=fmt_short_date, 
    get_current_user=get_current_user
)

# ── Auth Routes ──────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        full_name = request.form.get('full_name', '').strip()

        # Валидация (п. 6.1)
        if not email or not password or not full_name:
            flash("Все поля обязательны для заполнения.", "danger")
            return render_template('register.html')
        
        if len(password) < 6:
            flash("Пароль должен быть не менее 6 символов.", "danger")
            return render_template('register.html')
            
        if password != confirm_password:
            flash("Пароли не совпадают.", "danger")
            return render_template('register.html')

        try:
            # 1. Регистрация в Supabase Auth
            auth_response = supabase_anon.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": { "full_name": full_name } # Метаданные
                }
            })
            
            if auth_response.user:
                # 2. Создание профиля в public.users
                # Обычно это делается триггером в БД, но сделаем явно для надежности
                try:
                    supabase_admin.table("users").insert({
                        "id": auth_response.user.id,
                        "email": email,
                        "full_name": full_name,
                        "role": "user", # Жестко задаем роль (п. 6.1.6)
                        "is_active": True
                    }).execute()
                except Exception as db_err:
                    # Если юзер уже есть в таблице (например, триггер сработал), игнорируем ошибку дубликата
                    print(f"DB Profile Info: {db_err}") 

                flash("Регистрация успешна! Теперь вы можете войти.", "success")
                return redirect(url_for('login'))
            else:
                flash("Ошибка регистрации. Возможно, пользователь уже существует.", "danger")
                
        except Exception as e:
            flash(f"Ошибка: {str(e)}", "danger")

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        try:
            # Вход через Supabase Auth
            response = supabase_anon.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            if response.user:
                # Получаем профиль из нашей таблицы, чтобы знать роль и имя
                profile = supabase_anon.table("users").select("*").eq("id", response.user.id).single().execute()
                
                if profile.data:
                    # Сохраняем в сессию
                    session['user'] = {
                        "id": profile.data['id'],
                        "email": profile.data['email'],
                        "full_name": profile.data['full_name'],
                        "role": profile.data['role'],
                        "access_token": response.session.access_token
                    }
                    flash(f"Добро пожаловать, {profile.data['full_name']}!", "success")
                    
                    # Редирект в зависимости от роли
                    if profile.data['role'] in ['admin', 'super_admin']:
                        return redirect(url_for('admin_dashboard'))
                    return redirect(url_for('index'))
                else:
                    flash("Профиль пользователя не найден в системе.", "danger")
                    supabase_anon.auth.sign_out()
            else:
                flash("Неверный email или пароль.", "danger")
                
        except Exception as e:
            flash("Ошибка входа. Проверьте данные.", "danger")
            print(e)

    return render_template('login.html')

@app.route('/logout')
def logout():
    try:
        if 'user' in session and 'access_token' in session['user']:
            supabase_anon.auth.sign_out(session['user']['access_token'])
    except: pass
    
    session.clear()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for('index'))

# ── Main Routes ──────────────────────────────────────────────

@app.route("/")
def index():
    search   = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    date_f   = request.args.get("date", "").strip()

    categories = supabase_anon.table("categories").select("*").execute().data or []

    query = (
        supabase_anon.table("events")
        .select("*, categories(name, slug)")
        .eq("status", "published")
        .order("event_date", desc=False)
    )

    # --- УЛУЧШЕННЫЙ ПОИСК ---
    if search:
        # Ищем по названию ИЛИ описанию ИЛИ локации (регистронезависимо)
        # Supabase PostgREST поддерживает .or_ для множественных условий
        query = query.or_(
            f"title.ilike.%{search}%,description.ilike.%{search}%,location.ilike.%{search}%"
        )
    # ------------------------

    if category:
        cat_res = supabase_anon.table("categories").select("id").eq("slug", category).execute()
        if cat_res.data:
            query = query.eq("category_id", cat_res.data[0]['id'])
        else:
            events = []
            return render_template("index.html", events=events, categories=categories, search=search, category_filter=category, date_filter=date_f)

    now = datetime.utcnow()
    if date_f == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end   = start + timedelta(days=1)
        query = query.gte("event_date", start.isoformat()).lt("event_date", end.isoformat())
    elif date_f == "week":
        end = now + timedelta(days=7)
        query = query.gte("event_date", now.isoformat()).lte("event_date", end.isoformat())
    elif date_f == "month":
        end = now + timedelta(days=30)
        query = query.gte("event_date", now.isoformat()).lte("event_date", end.isoformat())

    events = query.execute().data or []

    return render_template("index.html", events=events, categories=categories, search=search, category_filter=category, date_filter=date_f)

@app.route("/event/<slug>")
def event_detail(slug):
    # Запрашиваем VIEW вместо таблицы events
    result = (
        supabase_anon.table("event_details_view")
        .select("*")
        .eq("slug", slug)
        .single()
        .execute()
    )
    event = result.data
    if not event:
        flash("Мероприятие не найдено", "danger")
        return redirect(url_for("index"))
        
    return render_template("detail.html", event=event)

@app.route("/register_event/<int:event_id>", methods=["POST"])
@login_required
def register_event(event_id):
    user = get_current_user()
    comment = request.form.get("comment", "")
    
    # Бизнес-правило: проверка мест (п. 7.3)
    event_data = supabase_anon.table("events").select("available_seats, slug").eq("id", event_id).single().execute().data
    
    if not event_data or event_data['available_seats'] <= 0:
        flash("Извините, все места заняты.", "danger")
        return redirect(url_for("event_detail", slug=event_data['slug'] if event_data else 'index'))

    try:
        supabase_anon.table("registrations").insert({
            "user_id":   user["id"],
            "event_id":  event_id,
            "status":    "confirmed", # Или 'created', если нужна модерация
            "comment":   comment,
        }).execute()
        flash("Вы успешно зарегистрированы!", "success")
    except Exception as e:
        # Обработка дубликатов (UNIQUE constraint)
        if "duplicate" in str(e).lower():
             flash("Вы уже зарегистрированы на это событие.", "warning")
        else:
             flash(f"Ошибка регистрации: {e}", "danger")

    return redirect(url_for("event_detail", slug=event_data['slug']))

@app.route("/cabinet")
@login_required
def cabinet():
    user = get_current_user()
    regs = (
        supabase_anon.table("registrations")
        .select("*, events(title, slug, event_date, location, status)")
        .eq("user_id", user["id"])
        .order("registered_at", desc=True)
        .execute()
        .data or []
    )
    
    upcoming = (
        supabase_anon.table("events")
        .select("*")
        .eq("status", "published")
        .gte("event_date", datetime.utcnow().isoformat())
        .order("event_date", desc=False)
        .limit(1)
        .execute()
        .data
    )
    next_event = upcoming[0] if upcoming else None

    return render_template("cabinet.html", registrations=regs, next_event=next_event)

@app.route("/cancel/<int:reg_id>", methods=["POST"])
@login_required
def cancel_registration(reg_id):
    user = get_current_user()
    # Обновляем статус только если это запись текущего пользователя
    res = supabase_anon.table("registrations").update({
        "status": "cancelled_by_user",
        "cancelled_at": datetime.utcnow().isoformat()
    }).eq("id", reg_id).eq("user_id", user["id"]).in_("status", ["confirmed", "created"]).execute()
    
    if res.data:
        flash("Регистрация отменена.", "info")
    else:
        flash("Не удалось отменить регистрацию.", "danger")
        
    return redirect(url_for("cabinet"))

# ... импорты и создание app ...

@app.route('/healthz')
def health_check():
    """
    Эндпоинт для проверки работоспособности сервера (Render Health Check).
    Не обращается к БД, отвечает мгновенно.
    """
    return jsonify({"status": "ok", "message": "EventHUB is running"}), 200

# ... остальные роуты ...

@app.route("/admin")
@admin_required
def admin_dashboard():
    status_filter = request.args.get("status", "").strip()
    
    # Значения по умолчанию
    stats = {"total_regs": 0, "active_events": 0, "total_users": 0, "revenue": 0, "cancel_rate": 0}
    status_stats = {"confirmed": 0, "created": 0, "cancelled": 0}
    regs = []

    try:
        # Простая функция подсчета
        def count_rows(table, filters=None):
            q = supabase_admin.table(table).select("id", count="exact")
            if filters:
                for k, v in filters.items():
                    if isinstance(v, list): q = q.in_(k, v)
                    else: q = q.eq(k, v)
            res = q.execute()
            return int(res.count) if hasattr(res, 'count') else len(res.data)

        # Считаем
        total_regs = count_rows("registrations")
        active_events = count_rows("events", {"status": "published"})
        total_users = count_rows("users")
        
        confirmed = count_rows("registrations", {"status": "confirmed"})
        created = count_rows("registrations", {"status": "created"})
        cancelled = count_rows("registrations", {"status": ["cancelled_by_user", "cancelled_by_admin", "rejected"]})
        
        cancel_rate = round((cancelled / total_regs * 100), 1) if total_regs > 0 else 0
        
        # Выручка (простая)
        revenue = 0
        try:
            conf_regs = supabase_admin.table("registrations").select("event_id").eq("status", "confirmed").execute().data
            if conf_regs:
                ids = list(set(r['event_id'] for r in conf_regs))
                prices = supabase_admin.table("events").select("price").in_("id", ids).execute().data
                revenue = sum(float(p['price']) for p in prices)
        except: pass

        stats = {
            "total_regs": total_regs, "active_events": active_events, 
            "total_users": total_users, "revenue": revenue, "cancel_rate": cancel_rate
        }
        
        # Передаем просто числа для CSS-графика
        status_stats = {
            "confirmed": confirmed,
            "created": created,
            "cancelled": cancelled,
            "total": confirmed + created + cancelled # Для расчета процентов ширины
        }

        # Список регистраций
        q = supabase_admin.table("registrations").select("*, events(title, event_date)").order("registered_at", desc=True).limit(50)
        if status_filter:
            if status_filter == 'cancelled': q = q.in_("status", ["cancelled_by_user", "cancelled_by_admin", "rejected"])
            else: q = q.eq("status", status_filter)
        regs = q.execute().data or []

    except Exception as e:
        print(f"Error: {e}")
        flash("Ошибка загрузки данных", "warning")

    return render_template(
        "admin.html", 
        stats=stats, 
        registrations=regs, 
        status_stats=status_stats, # Передаем словарь с числами
        current_status_filter=status_filter
    )

@app.route("/admin/cancel/<int:reg_id>", methods=["POST"])
@admin_required
def admin_cancel_registration(reg_id):
    """Отмена регистрации администратором."""
    try:
        # 1. Получаем данные регистрации
        reg_res = supabase_admin.table("registrations").select("*").eq("id", reg_id).single().execute()
        reg = reg_res.data
        
        if not reg:
            flash("Регистрация не найдена.", "danger")
            return redirect(url_for("admin_dashboard"))
        
        # 2. Проверяем статус (бизнес-правило: нельзя отменить уже отмененное)
        if reg["status"] in ["cancelled_by_user", "cancelled_by_admin", "rejected", "attended"]:
            flash("Эту регистрацию нельзя отменить (она уже отменена или завершена).", "warning")
            return redirect(url_for("admin_dashboard", status=request.args.get("status")))

        # 3. Обновляем статус регистрации
        supabase_admin.table("registrations").update({
            "status": "cancelled_by_admin",
            "cancelled_at": datetime.utcnow().isoformat()
        }).eq("id", reg_id).execute()
        
        # 4. Возвращаем место (обычный UPDATE, без RPC)
        event_id = reg["event_id"]
        
        # Получаем текущее количество мест
        event_res = supabase_admin.table("events").select("available_seats, total_seats").eq("id", event_id).single().execute()
        event = event_res.data
        
        if event:
            new_available = event["available_seats"] + 1
            # Защита от переполнения (нельзя больше чем total_seats)
            if new_available > event["total_seats"]:
                new_available = event["total_seats"]
                
            supabase_admin.table("events").update({
                "available_seats": new_available
            }).eq("id", event_id).execute()
        
        flash(f"Регистрация #{reg_id} успешно отменена.", "success")
        
    except Exception as e:
        print(f"Error cancelling registration: {e}")
        flash(f"Ошибка при отмене: {str(e)}", "danger")
    
    # Возвращаемся с сохранением фильтра
    status_filter = request.args.get("status", "")
    return redirect(url_for("admin_dashboard", status=status_filter))

@app.route("/admin/users")
@admin_required
def admin_users():
        """Страница управления пользователями."""
        try:
            # Получаем всех пользователей из таблицы public.users
            # Сортируем по дате создания (новые сверху)
            users_res = supabase_admin.table("users").select("*").order("created_at", desc=True).execute()
            users = users_res.data or []
            
            # Если нужно показать email из Auth (если он отличается), можно сделать доп. запрос, 
            # но обычно мы дублируем email в public.users при регистрации.
            
            return render_template("admin_users.html", users=users)
            
        except Exception as e:
            print(f"Error loading users: {e}")
            flash("Ошибка загрузки списка пользователей", "danger")
            return redirect(url_for("admin_dashboard"))

# Опционально: Функция для изменения роли (пункт 6.4 - Админ может менять роли)
@app.route("/admin/users/<user_id>/toggle_role", methods=["POST"])
@admin_required
def toggle_user_role(user_id):
     """Переключение роли пользователя (User <-> Admin)."""
     try:
        # Получаем текущую роль
        user_res = supabase_admin.table("users").select("role").eq("id", user_id).single().execute()
        current_role = user_res.data.get("role")
                
                # Нельзя понизить самого себя (защита от блокировки)
        if user_id == session['user']['id']:
            flash("Нельзя изменить роль самому себе.", "warning")
            return redirect(url_for("admin_users"))

        new_role = "user" if current_role in ["admin", "super_admin"] else "admin"
                
        supabase_admin.table("users").update({"role": new_role}).eq("id", user_id).execute()
        flash(f"Роль пользователя изменена на {new_role}", "success")
                
     except Exception as e:
        flash(f"Ошибка: {str(e)}", "danger")
                
     return redirect(url_for("admin_users"))

@app.route("/admin/users/<user_id>/edit", methods=["POST"])
@admin_required
def edit_user(user_id):
    """Редактирование данных пользователя администратором."""
    try:
        # Получаем данные из формы
        full_name = request.form.get("full_name", "").strip()
        role = request.form.get("role", "user")
        is_active = request.form.get("is_active") == "on" # Checkbox возвращает 'on' или None

        # Валидация
        if not full_name:
            flash("Имя не может быть пустым", "danger")
            return redirect(url_for("admin_users"))

        # Защита: нельзя понизить самого себя до обычного юзера или заблокировать
        if user_id == session['user']['id']:
            if role != session['user']['role']:
                flash("Нельзя изменить собственную роль.", "warning")
                return redirect(url_for("admin_users"))
            if not is_active:
                flash("Нельзя заблокировать самого себя.", "warning")
                return redirect(url_for("admin_users"))

        # Обновление в БД
        update_data = {
            "full_name": full_name,
            "role": role,
            "is_active": is_active,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        supabase_admin.table("users").update(update_data).eq("id", user_id).execute()
        
        # Если меняли роль текущего пользователя (например, super_admin -> admin), обновим сессию
        if user_id == session['user']['id']:
            session['user']['role'] = role
            session['user']['full_name'] = full_name

        flash("Данные пользователя успешно обновлены", "success")

    except Exception as e:
        print(f"Edit user error: {e}")
        flash(f"Ошибка сохранения: {str(e)}", "danger")

    return redirect(url_for("admin_users"))

if __name__ == "__main__":
    app.run(debug=True, port=5000)