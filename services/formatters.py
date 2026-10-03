from datetime import datetime

MONTHS_FULL = ["Января", "Февраля", "Марта", "Апреля", "Мая", "Июня",
               "Июля", "Августа", "Сентября", "Октября", "Ноября", "Декабря"]
MONTHS_SHORT = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн",
                "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]


def _parse(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def fmt_date(value):
    dt = _parse(value)
    if not dt:
        return ""
    return f"{dt.day} {MONTHS_FULL[dt.month - 1]}, {dt:%H:%M}"


def fmt_short_date(value):
    dt = _parse(value)
    if not dt:
        return ""
    return f"{dt.day} {MONTHS_SHORT[dt.month - 1]} {dt.year}"