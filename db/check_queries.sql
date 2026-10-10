-- ============================================================
-- EventHUB — проверочные SQL-запросы (п. 4.2 лабораторной)
-- База: PostgreSQL в Supabase
-- Как пользоваться: Supabase → SQL Editor → New query →
-- выполнить запросы по одному и приложить скриншоты результатов.
-- ============================================================


-- ── 1. Выборка с условием WHERE ──────────────────────────────
-- Все опубликованные мероприятия в Москве, которые ещё не прошли
select id, title, event_date, location, available_seats, total_seats
from public.events
where status = 'published'
  and location ilike '%Москва%'
  and event_date >= now()
order by event_date;


-- ── 2. Сортировка ORDER BY ───────────────────────────────────
-- 10 последних регистраций (самые свежие сверху)
select id, event_id, user_id, status, registered_at
from public.registrations
order by registered_at desc
limit 10;


-- ── 3. JOIN не менее двух таблиц ─────────────────────────────
-- Реестр регистраций: участник + мероприятие + дата события
select r.id          as registration_id,
       u.full_name   as participant,
       u.email,
       e.title       as event_title,
       e.event_date,
       r.status,
       r.registered_at
from public.registrations r
join public.users   u on u.id = r.user_id
join public.events  e on e.id = r.event_id
order by r.registered_at desc
limit 20;


-- ── 4. Агрегатный запрос с COUNT ─────────────────────────────
-- Общее количество подтверждённых регистраций
select count(*) as confirmed_registrations
from public.registrations
where status = 'confirmed';


-- ── 5. Запрос с GROUP BY ─────────────────────────────────────
-- Топ мероприятий по числу регистраций (любые, кроме отменённых)
select e.title,
       e.event_date,
       count(r.id) as registrations_count
from public.events e
join public.registrations r on r.event_id = e.id
where r.status not in ('cancelled_by_user', 'cancelled_by_admin', 'rejected')
group by e.id, e.title, e.event_date
order by registrations_count desc
limit 10;


-- ── 6. Запрос показателя административной панели ─────────────
-- Общие сборы: сумма цен мероприятий по подтверждённым
-- и посещенным регистрациям (метрика «Общие сборы» админки)
select coalesce(sum(e.price), 0) as total_revenue
from public.registrations r
join public.events e on e.id = r.event_id
where r.status in ('confirmed', 'attended');


-- ── Дополнительно: запрос для диаграммы админки (п. 8.2) ─────
-- Распределение регистраций по статусам (столбчатая диаграмма)
select case
           when status = 'confirmed' then 'Подтверждена'
           when status = 'attended'  then 'Посещено'
           when status = 'created'   then 'Создана'
           else 'Отменена'
       end as status_label,
       count(*) as cnt
from public.registrations
group by status_label
order by cnt desc;