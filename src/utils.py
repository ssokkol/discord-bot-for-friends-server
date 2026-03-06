import logging

logger = logging.getLogger(__name__)


def _day_word(days: int) -> str:
    """Возвращает правильное склонение слова 'день'"""
    if 11 <= days % 100 <= 19:
        return "дней"
    mod10 = days % 10
    if mod10 == 1:
        return "день"
    elif 2 <= mod10 <= 4:
        return "дня"
    else:
        return "дней"


def format_time(minutes: int) -> str:
    """Formats minutes into human-readable Russian string"""
    try:
        if minutes < 60:
            return f"{minutes} мин"
        elif minutes < 1440:
            hours = minutes // 60
            mins = minutes % 60
            if mins == 0:
                return f"{hours} ч"
            return f"{hours} ч {mins} мин"
        else:
            days = minutes // 1440
            remaining = minutes % 1440
            hours = remaining // 60
            mins = remaining % 60

            parts = [f"{days} {_day_word(days)}"]
            if hours > 0:
                parts.append(f"{hours} ч")
            if mins > 0:
                parts.append(f"{mins} мин")
            return " ".join(parts)
    except Exception:
        return f"{minutes} мин"
