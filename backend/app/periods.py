from calendar import monthrange
from datetime import date, timedelta

RU_MONTHS = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]
RU_MONTHS_SHORT = [
    "янв", "фев", "мар", "апр", "май", "июн",
    "июл", "авг", "сен", "окт", "ноя", "дек",
]

# Границы для периода «всё время»: сравнение ISO-дат в SQLite строковое,
# поэтому достаточно заведомо крайних значений.
MIN_DATE = "0001-01-01"
MAX_DATE = "9999-12-31"

# Периоды скользящие: «последние 3 месяца» отсчитываются от сегодня,
# а не от начала календарного квартала.
PRESET_MONTHS = {"month": 1, "3m": 3, "6m": 6, "year": 12}

PRESET_LABELS = {
    "month": "Последний месяц",
    "3m": "Последние 3 месяца",
    "6m": "Последние 6 месяцев",
    "year": "Последний год",
    "all": "Всё время",
}

PERIOD_IDS = set(PRESET_MONTHS) | {"all", "custom"}


def shift_months(d: date, delta: int) -> date:
    """Сдвиг на месяцы с прижатием дня к длине месяца: 31 марта минус месяц = 28 февраля."""
    idx = d.year * 12 + (d.month - 1) + delta
    y, m = idx // 12, idx % 12 + 1
    return date(y, m, min(d.day, monthrange(y, m)[1]))


def fmt_ru(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def resolve_period(
    period: str, date_from: str | None = None, date_to: str | None = None
) -> tuple[str, str, str]:
    """Возвращает (start ISO, end ISO, подпись). Границы включительные."""
    today = date.today()

    if period == "custom":
        if not date_from or not date_to:
            raise ValueError("Для своего периода нужно указать обе даты")
        start = date.fromisoformat(date_from)
        end = date.fromisoformat(date_to)
        if start > end:
            start, end = end, start
        return start.isoformat(), end.isoformat(), f"{fmt_ru(start)} — {fmt_ru(end)}"

    if period == "all":
        return MIN_DATE, MAX_DATE, PRESET_LABELS["all"]

    months = PRESET_MONTHS.get(period)
    if months is None:
        raise ValueError("Неизвестный период")
    start = shift_months(today, -months)
    return start.isoformat(), today.isoformat(), PRESET_LABELS[period]


def choose_granularity(first: str, last: str) -> str:
    """Шаг графика подбираем по фактическому разбросу данных, а не по границам
    периода: у «всего времени» границы условные и дали бы бессмысленный масштаб."""
    span = (date.fromisoformat(last) - date.fromisoformat(first)).days
    if span <= 62:
        return "day"
    if span <= 240:
        return "week"
    return "month"


def bucket_key(iso: str, granularity: str) -> str:
    if granularity == "month":
        return iso[:7]
    d = date.fromisoformat(iso)
    if granularity == "week":
        return (d - timedelta(days=d.weekday())).isoformat()
    return iso


def bucket_label(key: str, granularity: str) -> str:
    if granularity == "month":
        y, m = key.split("-")
        return f"{RU_MONTHS_SHORT[int(m) - 1]} {y[2:]}"
    d = date.fromisoformat(key)
    return d.strftime("%d.%m")


def next_bucket(key: str, granularity: str) -> str:
    if granularity == "month":
        y, m = (int(x) for x in key.split("-"))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return f"{y:04d}-{m:02d}"
    d = date.fromisoformat(key)
    return (d + timedelta(days=7 if granularity == "week" else 1)).isoformat()
