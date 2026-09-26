"""
Seeder для EventHUB
Запуск: python seed.py
Очищает и перезаполняет: categories, users, events, registrations, notifications
"""
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_KEY"],
)

TZ = timezone(timedelta(hours=3))  # Москва UTC+3


def now():
    return datetime.now(TZ)


def future(days=0, hours=0):
    return (now() + timedelta(days=days, hours=hours)).isoformat()


def past(days=0, hours=0):
    return (now() - timedelta(days=days, hours=hours)).isoformat()


# ============================================================
#  1. ОЧИСТКА (в правильном порядке из-за FK)
# ============================================================
print("🗑️  Очищаем таблицы...")
for table in ["notifications", "registrations", "events", "categories", "users"]:
    supabase.table(table).delete().neq("id", 0).execute()
print("   ✅ Таблицы очищены\n")


# ============================================================
#  2. КАТЕГОРИИ
# ============================================================
print("📂 Создаём категории...")
categories_data = [
    {"name": "Конференция",  "slug": "conference",  "description": "Крупные профессиональные конференции"},
    {"name": "Мастер-класс", "slug": "masterclass", "description": "Практические занятия с экспертами"},
    {"name": "Семинар",      "slug": "seminar",     "description": "Образовательные семинары и лекции"},
    {"name": "Хакатон",      "slug": "hackathon",   "description": "Соревнования разработчиков"},
    {"name": "Вебинар",      "slug": "webinar",     "description": "Онлайн-трансляции и вебинары"},
]
cat_result = supabase.table("categories").insert(categories_data).execute()
cats = {c["slug"]: c["id"] for c in cat_result.data}
print(f"   ✅ {len(cats)} категорий\n")


# ============================================================
#  3. ПОЛЬЗОВАТЕЛИ
# ============================================================
print("👤 Создаём пользователей...")
HASH = "$2b$12$LJ3m4ys3Gg0EwT7iHvPKHeGH5PnRBkIxlC3DnK9Wx3tN6uYpQKXMe"

users_data = [
    {"email": "admin@eventhub.ru",     "password_hash": HASH, "full_name": "Администратор",              "phone": "+7 (999) 000-00-00", "role": "super_admin"},
    {"email": "premium@eventhub.ru",   "password_hash": HASH, "full_name": "EventHUB Premium",           "phone": "+7 (999) 111-11-11", "role": "admin"},
    {"email": "alexander@example.com", "password_hash": HASH, "full_name": "Иванов Александр Сергеевич", "phone": "+7 (999) 222-22-22", "role": "user"},
    {"email": "maria@example.com",     "password_hash": HASH, "full_name": "Петрова Мария Ивановна",     "phone": "+7 (999) 333-33-33", "role": "user"},
    {"email": "dmitry@example.com",    "password_hash": HASH, "full_name": "Козлов Дмитрий Алексеевич",  "phone": "+7 (999) 444-44-44", "role": "user"},
]
usr_result = supabase.table("users").insert(users_data).execute()
users = {u["email"]: u["id"] for u in usr_result.data}
organizer_id = users["premium@eventhub.ru"]
print(f"   ✅ {len(users)} пользователей\n")


# ============================================================
#  4. МЕРОПРИЯТИЯ (20 штук)
# ============================================================
print("📅 Создаём мероприятия...")
events_data = [
    # ── Будущие (published) ──────────────────────────────
    {"category_id": cats["conference"],  "title": "TechFuture 2024: ИИ и робототехника",
     "slug": "techfuture-2024", "location": "Москва, Технополис «Москва»",
     "event_date": future(days=12), "total_seats": 200, "available_seats": 42,
     "price": 0, "status": "published",
     "description": "Главное событие осени! Ведущие эксперты обсудят прорывы в генеративном ИИ, робототехнике и машинном зрении. Панельные дискуссии, демо-зона и реальные кейсы."},

    {"category_id": cats["seminar"],     "title": "Проектирование сложных UI/UX систем в Figma",
     "slug": "uiux-figma-2024", "location": "Москва, Технополис «Москва»",
     "event_date": future(days=15), "total_seats": 50, "available_seats": 12,
     "price": 3500, "status": "published",
     "description": "Интенсивный курс по проектированию интерфейсов сложных enterprise-систем. Разбор дизайн-систем, токенов и автолейаутов."},

    {"category_id": cats["masterclass"], "title": "Современная кондитерская выпечка",
     "slug": "pastry-masterclass", "location": "Москва, Кулинарная студия «Вкус»",
     "event_date": future(days=30), "total_seats": 20, "available_seats": 5,
     "price": 5000, "status": "published",
     "description": "Практический мастер-класс от шеф-кондитера Мишленовского ресторана. Приготовите три десерта и заберёте рецепты."},

    {"category_id": cats["hackathon"],   "title": "FinTech Hack: Безопасные платёжные решения",
     "slug": "fintech-hack-2024", "location": "Москва, Технополис «Москва»",
     "event_date": future(days=20), "total_seats": 80, "available_seats": 30,
     "price": 0, "status": "published",
     "description": "Хакатон по разработке безопасных платёжных систем. Призовой фонд 500 000 ₽. Менторы из Сбера и Тинькофф."},

    {"category_id": cats["webinar"],     "title": "Введение в Rust для системного программирования",
     "slug": "rust-intro-webinar", "location": "Онлайн (Zoom)",
     "event_date": future(days=5), "total_seats": 500, "available_seats": 320,
     "price": 0, "status": "published",
     "description": "Бесплатный вебинар для тех, кто хочет начать писать на Rust. Основы ownership, borrowing и lifetimes."},

    {"category_id": cats["conference"],  "title": "DataFest: Большие данные и аналитика",
     "slug": "datafest-2024", "location": "Санкт-Петербург, Экспофорум",
     "event_date": future(days=25), "total_seats": 300, "available_seats": 85,
     "price": 2500, "status": "published",
     "description": "Конференция по работе с большими данными. Доклады от Яндекс, VK и Ozon по ML-pipeline, ClickHouse и Apache Spark."},

    {"category_id": cats["seminar"],     "title": "Юридические аспекты IT-стартапов",
     "slug": "legal-it-startups", "location": "Москва, Коворкинг «Точка»",
     "event_date": future(days=8), "total_seats": 40, "available_seats": 18,
     "price": 1500, "status": "published",
     "description": "Семинар для основателей: регистрация, IP, договоры с разработчиками, защита интеллектуальной собственности."},

    {"category_id": cats["masterclass"], "title": "Продвинутый Docker и Kubernetes",
     "slug": "docker-k8s-advanced", "location": "Онлайн (Zoom)",
     "event_date": future(days=18), "total_seats": 60, "available_seats": 22,
     "price": 4000, "status": "published",
     "description": "Практический мастер-класс: Helm-чарты, service mesh, мониторинг через Prometheus и Grafana."},

    {"category_id": cats["hackathon"],   "title": "GreenCode: Экологичный софт",
     "slug": "greencode-hack", "location": "Казань, Иннополис",
     "event_date": future(days=35), "total_seats": 100, "available_seats": 67,
     "price": 0, "status": "published",
     "description": "Хакатон по созданию энергоэффективного ПО. Оптимизация алгоритмов, green computing и carbon-aware development."},

    {"category_id": cats["conference"],  "title": "CyberSec Forum 2024",
     "slug": "cybersec-forum-2024", "location": "Москва, Крокус Экспо",
     "event_date": future(days=40), "total_seats": 500, "available_seats": 210,
     "price": 3000, "status": "published",
     "description": "Форум по кибербезопасности. Пентестинг, SOC, threat intelligence и zero-trust архитектуры."},

    {"category_id": cats["webinar"],     "title": "Карьера в Data Science: roadmap 2024",
     "slug": "ds-career-webinar", "location": "Онлайн (YouTube)",
     "event_date": future(days=3), "total_seats": 1000, "available_seats": 780,
     "price": 0, "status": "published",
     "description": "Открытый вебинар: какие навыки нужны DS в 2024, как проходить собеседования и строить карьеру."},

    {"category_id": cats["seminar"],     "title": "Go-разработка под высокими нагрузками",
     "slug": "go-highload-2024", "location": "Онлайн (Zoom)",
     "event_date": future(days=10), "total_seats": 100, "available_seats": 45,
     "price": 2000, "status": "published",
     "description": "Семинар для backend-разработчиков: паттерны высоконагруженных систем на Go, профилирование и оптимизация."},

    # ── Прошедшие (completed) ────────────────────────────
    {"category_id": cats["conference"],  "title": "AI Summit Moscow 2024",
     "slug": "ai-summit-moscow", "location": "Москва, Цифровое деловое пространство",
     "event_date": past(days=10), "total_seats": 150, "available_seats": 0,
     "price": 4000, "status": "completed",
     "description": "Саммит по искусственному интеллекту. Прошёл с аншлагом."},

    {"category_id": cats["masterclass"], "title": "Фуд-фотография для Instagram",
     "slug": "food-photo-masterclass", "location": "Москва, Студия «Свет»",
     "event_date": past(days=5), "total_seats": 15, "available_seats": 0,
     "price": 3000, "status": "completed",
     "description": "Мастер-класс по съёмке еды для соцсетей. Все места были раскуплены."},

    # ── Черновики (draft) ────────────────────────────────
    {"category_id": cats["conference"],  "title": "Blockchain & Web3 Conference",
     "slug": "blockchain-web3-conf", "location": "Москва, TBD",
     "event_date": future(days=60), "total_seats": 250, "available_seats": 250,
     "price": 5000, "status": "draft",
     "description": "Планируемая конференция по блокчейну. Пока в черновике."},

    # ── Отменённые (cancelled) ───────────────────────────
    {"category_id": cats["seminar"],     "title": "Крипто Весна 2024",
     "slug": "crypto-spring-2024", "location": "Москва, Loft Hall",
     "event_date": future(days=7), "total_seats": 80, "available_seats": 80,
     "price": 1000, "status": "cancelled",
     "description": "Отменено организатором по техническим причинам."},
]

evt_result = supabase.table("events").insert(events_data).execute()
events = {e["slug"]: e["id"] for e in evt_result.data}
print(f"   ✅ {len(events)} мероприятий\n")


# ============================================================
#  5. РЕГИСТРАЦИИ
# ============================================================
print("🎫 Создаём регистрации...")
alex_id = users["alexander@example.com"]
maria_id = users["maria@example.com"]
dmitry_id = users["dmitry@example.com"]

regs_data = [
    # Александр
    {"user_id": alex_id, "event_id": events["techfuture-2024"],    "status": "confirmed",          "ticket_code": "TF2024-ALEX-001",  "registered_at": past(days=14), "confirmed_at": past(days=14)},
    {"user_id": alex_id, "event_id": events["uiux-figma-2024"],    "status": "created",            "ticket_code": "UIUX-ALEX-002",    "registered_at": past(days=3)},
    {"user_id": alex_id, "event_id": events["go-highload-2024"],   "status": "cancelled_by_admin", "ticket_code": "GO-ALEX-003",      "registered_at": past(days=20), "confirmed_at": past(days=19), "cancelled_at": past(days=10)},
    {"user_id": alex_id, "event_id": events["pastry-masterclass"], "status": "cancelled_by_user",  "ticket_code": "PASTRY-ALEX-004",  "registered_at": past(days=7),  "confirmed_at": past(days=7),  "cancelled_at": past(days=2)},
    {"user_id": alex_id, "event_id": events["fintech-hack-2024"],  "status": "confirmed",          "ticket_code": "FHACK-ALEX-005",   "registered_at": past(days=5),  "confirmed_at": past(days=5)},
    # Мария
    {"user_id": maria_id, "event_id": events["techfuture-2024"],   "status": "confirmed",          "ticket_code": "TF2024-MARIA-001", "registered_at": past(days=12), "confirmed_at": past(days=12)},
    {"user_id": maria_id, "event_id": events["datafest-2024"],     "status": "confirmed",          "ticket_code": "DF2024-MARIA-002", "registered_at": past(days=8),  "confirmed_at": past(days=8)},
    {"user_id": maria_id, "event_id": events["rust-intro-webinar"],"status": "created",            "ticket_code": "RUST-MARIA-003",   "registered_at": past(days=1)},
    # Дмитрий
    {"user_id": dmitry_id, "event_id": events["cybersec-forum-2024"], "status": "confirmed",       "ticket_code": "CS2024-DIM-001",   "registered_at": past(days=6),  "confirmed_at": past(days=6)},
    {"user_id": dmitry_id, "event_id": events["docker-k8s-advanced"], "status": "confirmed",       "ticket_code": "DK2024-DIM-002",   "registered_at": past(days=4),  "confirmed_at": past(days=4)},
    {"user_id": dmitry_id, "event_id": events["legal-it-startups"],   "status": "rejected",        "ticket_code": "LEGAL-DIM-003",    "registered_at": past(days=2)},
]

supabase.table("registrations").insert(regs_data).execute()
print(f"   ✅ {len(regs_data)} регистраций\n")


# ============================================================
#  6. УВЕДОМЛЕНИЯ
# ============================================================
print("🔔 Создаём уведомления...")
notifs_data = [
    {"user_id": None, "type": "new_registration",   "priority": "info",
     "title": "Новая регистрация",
     "message": "Новая регистрация от пользователя Иванов Александр на событие TechFuture 2024.",
     "related_event_id": events["techfuture-2024"]},
    {"user_id": None, "type": "export_ready",       "priority": "success",
     "title": "Экспорт готов",
     "message": "Автоматический экспорт отчёта за прошлую неделю успешно сформирован."},
    {"user_id": None, "type": "moderation_request", "priority": "warning",
     "title": "Запрос на модерацию",
     "message": 'Запрос на модерацию события "Крипто Весна 2024" ожидает вашего решения.',
     "related_event_id": events.get("crypto-spring-2024")},
    {"user_id": None, "type": "status_changed",     "priority": "info",
     "title": "Статус изменён",
     "message": "Регистрация Дмитрия Козлова на CyberSec Forum подтверждена автоматически."},
    {"user_id": None, "type": "event_reminder",     "priority": "info",
     "title": "Напоминание о событии",
     "message": "До вебинара «Карьера в Data Science» осталось 3 дня. Не забудьте отправить рассылку участникам.",
     "related_event_id": events["ds-career-webinar"]},
]

supabase.table("notifications").insert(notifs_data).execute()
print(f"   ✅ {len(notifs_data)} уведомлений\n")


# ============================================================
#  ГОТОВО
# ============================================================
print("=" * 50)
print("🎉 Сидирование завершено!")
print(f"   Категории:     {len(cats)}")
print(f"   Пользователи:  {len(users)}")
print(f"   Мероприятия:   {len(events)}")
print(f"   Регистрации:   {len(regs_data)}")
print(f"   Уведомления:   {len(notifs_data)}")
print("=" * 50)
print("\nДля входа используйте любой email:")
for email in users:
    print(f"   • {email}")