"""Результаты учеников для кабинета учителя — без всяких заданий."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app import config
from app import i18n
from app.core import database, ent_logic
from app.core.database import Attempt
from app.core.ent_logic import MOCK, question_max_points

PERIODS = i18n.Translated({
    "today": "Сегодня",
    "yesterday": "Вчера",
    "7d": "7 дней",
    "30d": "30 дней",
    "all": "Всё время",
})
DEFAULT_PERIOD = "30d"

WEAK_SUBJECT_PERCENT = 60
MIN_SUBJECT_QUESTIONS = 3
LOW_RESULT_PERCENT = 50
INACTIVE_DAYS = 7
TREND_WINDOW = 3
TREND_MIN_CHANGE = 3
HELP_THRESHOLD = 3


def percent(score: int, max_score: int) -> int:
    """Процент набранных баллов."""
    return round(score * 100 / max_score) if max_score else 0


def day_start(day: date) -> float:
    """Начало дня (полночь по местному времени) как timestamp."""
    return datetime(day.year, day.month, day.day).timestamp()


def period_range(period: str, now: float) -> tuple[float, float]:
    """Границы периода [начало, конец) для фильтра."""
    today = datetime.fromtimestamp(now).date()
    if period == "today":
        return day_start(today), now + 1
    if period == "yesterday":
        return day_start(today - timedelta(days=1)), day_start(today)
    if period == "7d":
        return now - 7 * 86400, now + 1
    if period == "30d":
        return now - 30 * 86400, now + 1
    return 0.0, now + 1


@dataclass
class SubjectResult:
    """Результат по предмету: процент и число заданий."""

    code: str
    percent: int
    questions: int


@dataclass
class StudentRow:
    """Строка таблицы учителя."""

    user_id: int
    name: str
    login: str
    last_activity: float | None
    today: tuple[int, int]
    yesterday: tuple[int, int]
    week: tuple[int, int]
    attempts: int
    last: int | None
    last_mock_score: int | None
    average: int | None
    best: int | None
    trend: int | None
    weak: list[SubjectResult] = field(default_factory=list)
    help_score: int = 0

    @property
    def needs_help(self) -> bool:
        return self.help_score >= HELP_THRESHOLD


def subject_results(rows) -> list[SubjectResult]:
    """Проценты по предметам из строк attempt_subject_points (от слабого к сильному)."""
    points, maximum, count = ent_logic.subject_totals(rows)
    result = [SubjectResult(c, percent(points[c], maximum[c]), count[c]) for c in points]
    result.sort(key=lambda item: (item.percent, -item.questions, item.code))
    return result


def _counts(attempts: list[Attempt], start: float, end: float) -> tuple[int, int]:
    inside = [a for a in attempts if start <= (a.finished_at or 0) < end]
    mocks = sum(a.mode == MOCK for a in inside)
    return mocks, len(inside) - mocks


def _trend(results: list[int]) -> int | None:
    if len(results) < 2:
        return None
    window = min(TREND_WINDOW, len(results) // 2)
    recent = results[-window:]
    before = results[-2 * window:-window]
    return round(sum(recent) / len(recent) - sum(before) / len(before))


def _help_score(row: StudentRow, now: float) -> int:
    score = 0
    if row.last_activity is None or now - row.last_activity > INACTIVE_DAYS * 86400:
        score += 3
    if row.average is None:
        score += 1
    elif row.average < LOW_RESULT_PERCENT:
        score += 2
    elif row.average < 70:
        score += 1
    if row.trend is not None and row.trend <= -TREND_MIN_CHANGE:
        score += 2
    if row.weak:
        score += 1
    return score


def school_overview(school_id: int, period: str = DEFAULT_PERIOD, now: float | None = None) -> list[StudentRow]:
    """Строки таблицы учителя по всем подтверждённым ученикам школы."""
    import time

    now = time.time() if now is None else now
    if period not in PERIODS:
        period = DEFAULT_PERIOD
    start, end = period_range(period, now)
    today = datetime.fromtimestamp(now).date()
    today_start = day_start(today)
    yesterday_start = day_start(today - timedelta(days=1))

    students = database.list_school_members(school_id, database.SCHOOL_APPROVED)
    attempts = database.school_attempts(school_id)
    started = database.school_last_started(school_id)
    by_user: dict[int, list[Attempt]] = {}
    for attempt in attempts:
        by_user.setdefault(attempt.user_id, []).append(attempt)

    in_period_ids = [a.id for a in attempts if start <= (a.finished_at or 0) < end]
    subject_rows: dict[int, list] = {}
    owner = {a.id: a.user_id for a in attempts}
    for row in database.attempt_subject_points(in_period_ids):
        subject_rows.setdefault(owner[row["attempt_id"]], []).append(row)

    result = []
    for student in students:
        user_id = student["id"]
        own = by_user.get(user_id, [])
        moments = [m for m in (student["last_login_at"], started.get(user_id),
                               *(a.finished_at for a in own)) if m]
        period_attempts = [a for a in own if start <= (a.finished_at or 0) < end]
        results = [percent(a.score, a.max_score) for a in period_attempts]
        last = period_attempts[-1] if period_attempts else None
        weak = [item for item in subject_results(subject_rows.get(user_id, []))
                if item.percent < WEAK_SUBJECT_PERCENT and item.questions >= MIN_SUBJECT_QUESTIONS][:3]
        row = StudentRow(
            user_id=user_id, name=student["name"], login=student["login"],
            last_activity=max(moments) if moments else None,
            today=_counts(own, today_start, now + 1),
            yesterday=_counts(own, yesterday_start, today_start),
            week=_counts(own, now - 7 * 86400, now + 1),
            attempts=len(period_attempts),
            last=results[-1] if results else None,
            last_mock_score=last.score if last is not None and last.mode == MOCK else None,
            average=round(sum(results) / len(results)) if results else None,
            best=max(results) if results else None,
            trend=_trend(results),
            weak=weak,
        )
        row.help_score = _help_score(row, now)
        result.append(row)
    return result


def _num(value: int | float | None) -> float:
    return float("-inf") if value is None else float(value)


SORT_KEYS = {
    "help": lambda r: (r.help_score, -_num(r.average) if r.average is not None else 0),
    "name": lambda r: r.name.casefold(),
    "activity": lambda r: _num(r.last_activity),
    "today": lambda r: sum(r.today),
    "yesterday": lambda r: sum(r.yesterday),
    "week": lambda r: sum(r.week),
    "last": lambda r: _num(r.last),
    "average": lambda r: _num(r.average),
    "best": lambda r: _num(r.best),
    "trend": lambda r: _num(r.trend),
    "weak": lambda r: len(r.weak),
}
DEFAULT_SORT = "help"
DEFAULT_DESC = {"name": False}


def sort_rows(rows: list[StudentRow], key: str, descending: bool) -> list[StudentRow]:
    """Сортирует строки таблицы; при равенстве — по имени."""
    if key not in SORT_KEYS:
        key = DEFAULT_SORT
    by_name = sorted(rows, key=lambda r: (r.name.casefold(), r.user_id))
    return sorted(by_name, key=SORT_KEYS[key], reverse=descending)


@dataclass
class TimelineItem:
    """Одна попытка в ленте: что делал, когда, сколько баллов и по каким предметам."""

    attempt: Attempt
    percent: int
    subjects: list[tuple[str, int, int]]


def timeline(user_id: int, limit_days: int = 60) -> list[tuple[date, list[TimelineItem]]]:
    """Завершённые попытки ученика, сгруппированные по дням (новые сверху)."""
    attempts = database.get_finished_attempts(user_id)
    points: dict[int, dict[str, list[int]]] = {}
    for row in database.attempt_subject_points([a.id for a in attempts]):
        if row["qtype"] not in config.QUESTION_POINTS:
            continue
        item = points.setdefault(row["attempt_id"], {}).setdefault(row["subject"], [0, 0])
        item[0] += row["points"] or 0
        item[1] += row["n"] * question_max_points(row["qtype"])
    days: dict[date, list[TimelineItem]] = {}
    for attempt in attempts:
        day = datetime.fromtimestamp(attempt.finished_at or attempt.started_at).date()
        by_subject = points.get(attempt.id, {})
        subjects = [(code, *by_subject[code]) for code in attempt.subjects if code in by_subject]
        days.setdefault(day, []).append(
            TimelineItem(attempt, percent(attempt.score, attempt.max_score), subjects))
    ordered = sorted(days.items(), key=lambda pair: pair[0], reverse=True)[:limit_days]
    return [(day, sorted(items, key=lambda i: -(i.attempt.finished_at or 0))) for day, items in ordered]
