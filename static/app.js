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