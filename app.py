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

    if search: query = query.ilike("title", f"%{search}%")
    
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
    result = (
        supabase_anon.table("events")
        .select("*, categories(name), users!organizer_id(full_name)")
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
    # Аналитика (п. 8)
    total_regs = supabase_admin.table("registrations").select("*", count="exact").execute().count
    active_events = supabase_admin.table("events").select("*", count="exact").eq("status", "published").execute().count
    total_users = supabase_admin.table("users").select("*", count="exact").execute().count
    
    # Выручка (пример)
    # В реальном проекте нужен JOIN или отдельная таблица платежей, здесь упрощенно
    # Просто считаем сумму цен событий, на которые есть confirmed регистрации
    # Для простоты покажем просто количество подтвержденных
    confirmed_regs = supabase_admin.table("registrations").select("*", count="exact").eq("status", "confirmed").execute().count

    stats = {
        "total_regs": total_regs,
        "active_events": active_events,
        "total_users": total_users,
        "confirmed_regs": confirmed_regs
    }

    # В функции admin_dashboard замените запрос к registrations на запрос к view
    regs = (
        supabase_admin.table("admin_registrations_view") # Обращаемся к VIEW
        .select("*")
        .order("registered_at", desc=True)
        .limit(20)
        .execute()
        .data or []
    )

    return render_template("admin.html", stats=stats, registrations=regs)

if __name__ == "__main__":
    app.run(debug=True, port=5000)