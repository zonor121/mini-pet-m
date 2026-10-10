// ── Countdown timer ──────────────────────────────────────────
(function () {
    const banner = document.querySelector('.countdown-banner[data-event-date]');
    if (!banner) return;

    const targetDate = new Date(banner.dataset.eventDate);
    const pad = n => String(n).padStart(2, '0');

    function tick() {
        const diff = Math.max(0, targetDate - new Date());
        const d = document.getElementById('days');
        const h = document.getElementById('hours');
        const m = document.getElementById('minutes');
        if (d) d.textContent = pad(Math.floor(diff / 864e5));
        if (h) h.textContent = pad(Math.floor((diff % 864e5) / 36e5));
        if (m) m.textContent = pad(Math.floor((diff % 36e5) / 6e4));
    }

    tick();
    setInterval(tick, 1000);
})();

// ── Auto-hide flash messages ─────────────────────────────────
document.querySelectorAll('.flash').forEach(el => {
    setTimeout(() => el.classList.add('flash--hidden'), 4000);
});

// ── Tab switching (admin) ────────────────────────────────────
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('tab--active'));
        tab.classList.add('tab--active');
    });
});

// ── Auto-hide Toast Notifications ────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const toasts = document.querySelectorAll('.toast');

    toasts.forEach(toast => {
        // Удаляем через 4 секунды
        setTimeout(() => {
            toast.classList.add('hiding');
            // Ждем окончания анимации (0.3s) перед удалением из DOM
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, 4000);
    });
});

// ── Гарантированные переходы в ТОЙ ЖЕ вкладке ────────────────
// Перехватываем клики по внутренним ссылкам и навигируем через location.assign.
// Работает везде: не важно, iframe это, target="_blank" в разметке
// или расширение браузера — переход будет в текущей вкладке.
// Честные «новые вкладки» (Ctrl/Cmd/Shift+клик, средняя кнопка) уважаем.
document.addEventListener('click', function (e) {
    // Только обычный левый клик без модификаторов
    if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    if (e.defaultPrevented) return;

    var a = e.target.closest ? e.target.closest('a[href]') : null;
    if (!a) return;

    var url;
    try {
        url = new URL(a.getAttribute('href'), location.href);
    } catch (err) {
        return;
    }

    // Только наши страницы (тот же origin, http/https)
    if (url.origin !== location.origin) return;
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return;

    e.preventDefault();

    // Якорь на той же странице — без полной навигации
    if (url.pathname === location.pathname && url.search === location.search && url.hash) {
        if (location.hash === url.hash) {
            location.hash = ''; // переключить якорь повторно
        }
        location.hash = url.hash;
        return;
    }

    location.assign(url.href);
}, true); // capture-фаза: успеваем раньше других обработчиков