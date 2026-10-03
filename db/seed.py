"""
seed_events.py — Генератор тестовых мероприятий для EventHUB
Запуск:  python seed_events.py
"""

import os
import random
from datetime import datetime, timedelta

from dotenv import load_dotenv
from services.supabase_client import supabase_admin as supabase

load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_KEY"],
)

# ── Категории ────────────────────────────────────────────────
CATEGORIES = {
    "conference":  "Конференция",
    "masterclass": "Мастер-класс",
    "seminar":     "Семинар",
    "hackathon":   "Хакатон",
}

# ── Шаблоны мероприятий (20 штук) ────────────────────────────
EVENT_TEMPLATES = [

    # ── Конференции ──────────────────────────────────────────
    {
        "title":       "AI Summit 2025: Будущее искусственного интеллекта",
        "slug":        "ai-summit-2025",
        "category":    "conference",
        "description": "Крупнейшая конференция по ИИ в России. Более 50 докладчиков, панельные дискуссии, демо-зона стартапов и нетворкинг.",
        "location":    "Москва, Экспоцентр",
        "total_seats": 500,
        "price":       7500.00,
    },
    {
        "title":       "DevOps Conf 2025: Инфраструктура нового поколения",
        "slug":        "devops-conf-2025",
        "category":    "conference",
        "description": "Всё о CI/CD, Kubernetes, observability и платформенной инженерии. Реальные кейсы от Яндекса, Сбера и Тинькофф.",
        "location":    "Санкт-Петербург, Ленэкспо",
        "total_seats": 300,
        "price":       5000.00,
    },
    {
        "title":       "DataFest 2025: Данные как новая нефть",
        "slug":        "datafest-2025",
        "category":    "conference",
        "description": "Конференция для data-инженеров, аналитиков и ML-специалистов. Apache Spark, dbt, Airflow, feature stores и MLOps.",
        "location":    'Москва, Технополис "Москва"',
        "total_seats": 250,
        "price":       4500.00,
    },
    {
        "title":       "CyberSec Forum 2025: Защита цифровой инфраструктуры",
        "slug":        "cybersec-forum-2025",
        "category":    "conference",
        "description": "Форум по информационной безопасности. Пентестинг, SOC, zero trust, supply chain security и реагирование на инциденты.",
        "location":    "Москва, Центр международной торговли",
        "total_seats": 200,
        "price":       6000.00,
    },
    {
        "title":       "ProductCon 2025: Продакт-менеджмент в эпоху ИИ",
        "slug":        "productcon-2025",
        "category":    "conference",
        "description": "Конференция для продакт-менеджеров. Growth, retention, unit-экономика, AI-first продукты и управление командами.",
        "location":    "Москва, Digital October",
        "total_seats": 180,
        "price":       5500.00,
    },

    # ── Мастер-классы ────────────────────────────────────────
    {
        "title":       "Мастер-класс: Figma Advanced — Auto Layout и компоненты",
        "slug":        "figma-advanced-masterclass",
        "category":    "masterclass",
        "description": "Глубокое погружение в Figma для опытных дизайнеров. Auto Layout, variadic components, dev mode и дизайн-системы.",
        "location":    "Онлайн (Zoom)",
        "total_seats": 30,
        "price":       3000.00,
    },
    {
        "title":       "Мастер-класс: Python для автоматизации рутины",
        "slug":        "python-automation-masterclass",
        "category":    "masterclass",
        "description": "Научитесь автоматизировать ежедневные задачи: парсинг, работа с API, генерация отчётов, боты для Telegram.",
        "location":    'Москва, Коворкинг "Точка кипения"',
        "total_seats": 25,
        "price":       2500.00,
    },
    {
        "title":       "Мастер-класс: 3D-моделирование в Blender для начинающих",
        "slug":        "blender-3d-masterclass",
        "category":    "masterclass",
        "description": "Создайте свою первую 3D-сцену за 3 часа. Моделирование, текстурирование, освещение и рендер в Cycles.",
        "location":    "Онлайн (Zoom)",
        "total_seats": 20,
        "price":       2000.00,
    },
    {
        "title":       "Мастер-класс: Выпечка круассанов по французской технологии",
        "slug":        "croissant-masterclass",
        "category":    "masterclass",
        "description": "Практический мастер-класс от шеф-кондитера. Слоёное тесто, формовка, расстойка и выпечка идеальных круассанов.",
        "location":    'Москва, Кулинарная студия "Вкус"',
        "total_seats": 12,
        "price":       4500.00,
    },
    {
        "title":       "Мастер-класс: Нейросети для генерации изображений",
        "slug":        "ai-image-gen-masterclass",
        "category":    "masterclass",
        "description": "Stable Diffusion, Midjourney, ComfyUI. Промпт-инжиниринг, ControlNet, LoRA и создание собственных моделей.",
        "location":    "Онлайн (Zoom)",
        "total_seats": 40,
        "price":       3500.00,
    },

    # ── Семинары ─────────────────────────────────────────────
    {
        "title":       "Семинар: Go-разработка под высокими нагрузками",
        "slug":        "go-highload-seminar",
        "category":    "seminar",
        "description": "Паттерны высоконагруженных систем на Go: worker pools, connection pooling, graceful shutdown, profiling и оптимизация GC.",
        "location":    "Онлайн (Zoom)",
        "total_seats": 100,
        "price":       2000.00,
    },
    {
        "title":       "Семинар: Проектирование сложных UI/UX систем в Figma",
        "slug":        "uiux-systems-seminar",
        "category":    "seminar",
        "description": "Интенсивный курс по проектированию интерфейсов сложных enterprise-систем. Design tokens, accessibility, responsive design.",
        "location":    'Москва, Технополис "Москва"',
        "total_seats": 50,
        "price":       3500.00,
    },
    {
        "title":       "Семинар: PostgreSQL — продвинутая оптимизация запросов",
        "slug":        "postgres-optimization-seminar",
        "category":    "seminar",
        "description": "EXPLAIN ANALYZE, индексы (B-tree, GIN, GiST, BRIN), партиционирование, PgBouncer и материализованные представления.",
        "location":    "Онлайн (Zoom)",
        "total_seats": 80,
        "price":       2500.00,
    },
    {
        "title":       "Семинар: Юнит-экономика для IT-продуктов",
        "slug":        "unit-economics-seminar",
        "category":    "seminar",
        "description": "LTV, CAC, payback period, cohort analysis. Как считать экономику SaaS, маркетплейса и мобильного приложения.",
        "location":    'Москва, Коворкинг "Точка кипения"',
        "total_seats": 40,
        "price":       3000.00,
    },
    {
        "title":       "Семинар: Rust для системного программирования",
        "slug":        "rust-systems-seminar",
        "category":    "seminar",
        "description": "Ownership, borrowing, lifetimes, async runtime Tokio. Пишем быстрый и безопасный сетевой сервис с нуля.",
        "location":    "Онлайн (Zoom)",
        "total_seats": 60,
        "price":       2000.00,
    },

    # ── Хакатоны ─────────────────────────────────────────────
    {
        "title":       "FinTech Hack: Безопасные платежные решения",
        "slug":        "fintech-hack-2025",
        "category":    "hackathon",
        "description": "Хакатон по разработке безопасных платежных систем. Призовой фонд 500 000 ₽. Партнёры: Тинькофф, ЮMoney, CloudPayments.",
        "location":    'Москва, Технополис "Москва"',
        "total_seats": 80,
        "price":       0.00,
    },
    {
        "title":       "HealthTech Hackathon: Цифровое здравоохранение",
        "slug":        "healthtech-hack-2025",
        "category":    "hackathon",
        "description": "48 часов на создание прототипа в сфере HealthTech. Телемедицина, wearable devices, медицинский ИИ и электронные карты.",
        "location":    "Москва, Сколково",
        "total_seats": 100,
        "price":       0.00,
    },
    {
        "title":       "GreenCode Hack: Экологические IT-решения",
        "slug":        "greencode-hack-2025",
        "category":    "hackathon",
        "description": "Хакатон для тех, кто хочет менять мир. Carbon tracking, smart recycling, energy optimization и sustainable tech.",
        "location":    "Санкт-Петербург, Точка кипения",
        "total_seats": 60,
        "price":       0.00,
    },
    {
        "title":       "EduHack: Образование будущего",
        "slug":        "eduhack-2025",
        "category":    "hackathon",
        "description": "Хакатон по созданию образовательных технологий. AI-tutoring, gamification, adaptive learning и VR в образовании.",
        "location":    "Онлайн",
        "total_seats": 120,
        "price":       0.00,
    },
    {
        "title":       "GameDev Jam: Инди-игры за 72 часа",
        "slug":        "gamedev-jam-2025",
        "category":    "hackathon",
        "description": "Создайте игру с нуля за 72 часа. Unity, Godot, Unreal Engine. Тема объявляется на старте. Призы от VK Play и My.Games.",
        "location":    "Москва, Коворкинг Sreda",
        "total_seats": 50,
        "price":       0.00,
    },
]


# ── Функции ──────────────────────────────────────────────────

def get_organizer_id():
    """Берёт первого пользователя с ролью admin или super_admin."""
    result = (
        supabase.table("users")
        .select("id")
        .in_("role", ["admin", "super_admin"])
        .limit(1)
        .execute()
    )
    if not result.data:
        raise RuntimeError("Нет пользователя с ролью admin/super_admin в таблице users")
    return result.data[0]["id"]


def seed_categories():
    """Создаёт категории, если их ещё нет."""
    for slug, name in CATEGORIES.items():
        existing = supabase.table("categories").select("id").eq("slug", slug).execute()
        if not existing.data:
            supabase.table("categories").insert({
                "name":        name,
                "slug":        slug,
                "description": f"Категория: {name}",
            }).execute()
            print(f"  + Создана категория: {name}")
        else:
            print(f"  = Категория существует: {name}")


def seed_events(count=None):
    """
    Создаёт мероприятия из шаблонов.
    count — сколько создать (None = все 20).
    Даты: случайные от +3 до +90 дней от сегодня.
    Занятые места: случайные от 10% до 70%.
    """
    organizer_id = get_organizer_id()
    print(f"  Организатор ID: {organizer_id}")

    # mapping slug → id
    cats = supabase.table("categories").select("id, slug").execute().data or []
    cat_map = {c["slug"]: c["id"] for c in cats}

    templates = EVENT_TEMPLATES[:count] if count else EVENT_TEMPLATES
    now = datetime.utcnow()
    created = 0
    skipped = 0

    for tpl in templates:
        # Пропускаем, если уже есть
        existing = supabase.table("events").select("id").eq("slug", tpl["slug"]).execute()
        if existing.data:
            print(f"  = Пропуск (уже есть): {tpl['title']}")
            skipped += 1
            continue

        # Случайная дата
        days_ahead = random.randint(3, 90)
        event_date = (now + timedelta(days=days_ahead)).replace(
            hour=random.choice([9, 10, 11, 14, 18]),
            minute=0, second=0, microsecond=0,
        )

        # Случайная занятость
        total_seats     = tpl["total_seats"]
        booked          = random.randint(int(total_seats * 0.1), int(total_seats * 0.7))
        available_seats = total_seats - booked

        cat_id = cat_map.get(tpl["category"])
        if not cat_id:
            print(f"  ! Категория не найдена: {tpl['category']} — пропуск")
            skipped += 1
            continue

        supabase.table("events").insert({
            "category_id":     cat_id,
            "organizer_id":    organizer_id,
            "title":           tpl["title"],
            "slug":            tpl["slug"],
            "description":     tpl["description"],
            "location":        tpl["location"],
            "event_date":      event_date.isoformat() + "+00:00",
            "total_seats":     total_seats,
            "available_seats": available_seats,
            "price":           tpl["price"],
            "status":          "published",
        }).execute()

        price_str = f"{tpl['price']:.0f} ₽" if tpl["price"] > 0 else "бесплатно"
        date_str  = event_date.strftime("%d.%m.%Y %H:%M")
        print(f"  + {tpl['title']}")
        print(f"    {date_str}  |  {price_str}  |  мест: {available_seats}/{total_seats}")
        created += 1

    print(f"\n  Итого: создано {created}, пропущено {skipped}")


# ── Запуск ───────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n=== EventHUB Seeder ===\n")

    print("[1/2] Категории:")
    seed_categories()

    print("\n[2/2] Мероприятия:")
    # seed_events(count=5)   # раскомментировать для частичной загрузки
    seed_events()

    print("\n=== Готово! ===\n")