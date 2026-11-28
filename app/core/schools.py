"""Школы и задания учителя: проверка ввода, поиск школы без дубликатов, подсчёт выполнения.

Школа — это город + номер или название. Чтобы «Школа №12», «СОШ 12» и «12» в одном
городе считались одной школой, из названия убираются «№», кавычки и слова вроде
«школа»/«СОШ», а город и название приводятся к нижнему регистру (это ключ school.key).

Задание засчитывается по попыткам, ЗАВЕРШЁННЫМ после выдачи задания и не позже срока.
"""

import re
import time
from dataclasses import dataclass
from datetime import date, datetime

from app import config
from app.core import database
from app.core.database import Attempt
from app.i18n import t

CITY_MAX_LENGTH = 60
SCHOOL_MAX_LENGTH = 100
ASSIGNMENT_MAX_COUNT = 20

# Слова, которые не отличают одну школу от другой: «Школа №12» = «СОШ 12» = «12».
_NOISE_WORDS = {
    "школа", "сош", "средняя", "общеобразовательная", "мектеп", "мектебі", "мектебi",
    "жом", "school", "г", "город", "қ", "қаласы",
}
_PUNCTUATION_RE = re.compile(r"[№#\"'«»“”„.,;:()\-–—/]+")


class SchoolError(Exception):
    """Ошибка ввода школы или задания: список понятных сообщений."""

    def __init__(self, errors: list[str]) -> None:
        """Сохраняет сообщения."""
        super().__init__("; ".join(errors))
        self.errors = errors


def _clean(raw: str) -> str:
    """Убирает лишние пробелы."""
    return " ".join(raw.split())


def _normalized(raw: str) -> str:
    """Нижний регистр, без знаков препинания и слов вроде «школа»."""
    words = _PUNCTUATION_RE.sub(" ", raw.casefold().replace(t("ё"), t("е"))).split()
    meaningful = [word for word in words if word not in _NOISE_WORDS]
    return " ".join(meaningful or words)


def school_key(city: str, name: str) -> str:
    """Ключ школы для поиска дубликатов: «алматы|12»."""
    return f"{_normalized(city)}|{_normalized(name)}"


def school_title(city: str, name: str) -> str:
    """Название для показа: «Алматы, школа №12» или «Астана, НИШ»."""
    shown = t("школа №{n}", n=name) if name.isdigit() else name
    return f"{city}, {shown}"


def validate_school(city: str, name: str) -> tuple[str, str] | None:
    """Проверяет поля школы. None — «без школы» (оба поля пустые), иначе (город, школа)."""
    clean_city, clean_name = _clean(city), _clean(name)
    if not clean_city and not clean_name:
        return None
    errors: list[str] = []
    if not clean_city:
        errors.append(t("Укажите город школы (или оставьте оба поля школы пустыми)."))
    elif len(clean_city) > CITY_MAX_LENGTH or not _normalized(clean_city):
        errors.append(t("Город школы указан неверно."))
    if not clean_name:
        errors.append(t("Укажите номер или название школы (или оставьте оба поля школы пустыми)."))
    elif len(clean_name) > SCHOOL_MAX_LENGTH or not _normalized(clean_name):
        errors.append(t("Номер или название школы указаны неверно."))
    if errors:
        raise SchoolError(errors)
    digits = re.fullmatch(t(r"(?:школа|сош|мектеп)?\s*№?\s*(\d+)"), clean_name.casefold())
    return clean_city, digits.group(1) if digits else clean_name


def find_or_create_school(city: str, name: str) -> int:
    """id школы (создаётся, если такой ещё нет)."""
    return database.get_or_create_school(city, name, school_key(city, name), time.time())


def join_school(user_id: int, city: str, name: str) -> int | None:
    """Ученик выбирает школу: заявка ждёт подтверждения учителя.

    Пустые поля — «без школы» (ученик выходит из школы). Повторный выбор той же школы,
    где ученик уже подтверждён, ничего не меняет. Возвращает id школы или None.
    """
    school = validate_school(city, name)
    if school is None:
        database.set_user_school(user_id, None, None)
        return None
    school_id = find_or_create_school(*school)
    current = database.get_user_school(user_id)
    if current is not None and current["school_id"] == school_id and current["school_status"] in (
        database.SCHOOL_APPROVED, database.SCHOOL_PENDING
    ):
        return school_id
    database.set_user_school(user_id, school_id, database.SCHOOL_PENDING)
    from app.core import notifications  # импорт здесь: notifications сам использует этот модуль

    user = database.get_user(user_id)
    notifications.school_request(school_id, user["name"] if user is not None else "", user_id)
    return school_id


# ── Задания ──────────────────────────────────────────────────────────────────

@dataclass
class AssignmentProgress:
    """Выполнение задания одним учеником."""

    user_id: int
    name: str
    login: str
    done: int          # сколько засчитанных попыток (не больше нужного числа)
    scores: list[str]  # баллы засчитанных попыток: «86/140»
    status: str        # done / overdue / active


def pair_codes(target: str) -> tuple[str, str] | None:
    """Пара из поля target пробного ЕНТ («math,physics») или None — любая пара."""
    codes = tuple(code for code in target.split(",") if code)
    return codes if len(codes) == 2 else None  # type: ignore[return-value]


def assignment_title(mode: str, target: str, count: int) -> str:
    """«3 пробных ЕНТ: Математика + Физика» или «5 тренировок: Химия»."""
    if mode == "mock":
        pair = pair_codes(target)
        what = " + ".join(config.SUBJECTS[c].name for c in pair) if pair else t("любая пара")
        return t("Пробный ЕНТ × {count}: {what}", count=count, what=what)
    subject = config.SUBJECTS.get(target)
    return t("Тренировка × {count}: {what}", count=count, what=subject.name if subject else target)


def attempt_counts(assignment, attempt: Attempt) -> bool:
    """Подходит ли попытка под задание (режим, предмет или пара, время завершения)."""
    if attempt.mode != assignment["mode"] or attempt.finished_at is None:
        return False
    if not assignment["created_at"] < attempt.finished_at <= assignment["deadline"]:
        return False
    if assignment["mode"] == "practice":
        return attempt.subjects == [assignment["target"]]
    pair = pair_codes(assignment["target"])
    if pair is None:
        return True
    return sorted(attempt.subjects[len(config.COMPULSORY_CODES):]) == sorted(pair)


def assignment_progress(assignment, now: float | None = None) -> list[AssignmentProgress]:
    """Таблица выполнения задания: по строке на каждого ученика, которому оно выдано."""
    now = time.time() if now is None else now
    students = database.assignment_students(assignment)
    attempts = database.get_finished_attempts_between(
        [row["id"] for row in students], assignment["mode"],
        assignment["created_at"], assignment["deadline"],
    )
    by_user: dict[int, list[Attempt]] = {}
    for attempt in attempts:
        if attempt_counts(assignment, attempt):
            by_user.setdefault(attempt.user_id, []).append(attempt)
    result = []
    for row in students:
        counted = by_user.get(row["id"], [])[: assignment["count"]]
        done = len(counted)
        if done >= assignment["count"]:
            status = "done"
        elif now > assignment["deadline"]:
            status = "overdue"
        else:
            status = "active"
        result.append(AssignmentProgress(
            user_id=row["id"], name=row["name"], login=row["login"], done=done,
            scores=[f"{a.score}/{a.max_score}" for a in counted], status=status,
        ))
    return result


def student_progress(assignment, user_id: int, now: float | None = None) -> AssignmentProgress | None:
    """Выполнение задания конкретным учеником (для его кабинета)."""
    for item in assignment_progress(assignment, now):
        if item.user_id == user_id:
            return item
    return None


def parse_deadline(raw: str, today: date | None = None) -> float:
    """Срок из поля <input type="date"> (ГГГГ-ММ-ДД) → конец этого дня по местному времени."""
    today = date.today() if today is None else today
    try:
        day = date.fromisoformat(raw.strip())
    except ValueError as error:
        raise SchoolError([t("Укажите срок выполнения задания.")]) from error
    if day < today:
        raise SchoolError([t("Срок не может быть в прошлом.")])
    return datetime(day.year, day.month, day.day, 23, 59, 59).timestamp()


def create_assignment(
    school_id: int, teacher_id: int, mode: str, subject: str, pair: str, count_raw: str,
    deadline_raw: str, for_all: bool, student_ids: list[int],
) -> int:
    """Проверяет форму задания и сохраняет его. Ошибки — SchoolError."""
    errors: list[str] = []
    target = ""
    if mode == "practice":
        if subject not in config.SUBJECTS:
            errors.append(t("Выберите предмет тренировки."))
        target = subject
    elif mode == "mock":
        if pair:
            codes = pair_codes(pair)
            if codes is None or codes not in config.PROFILE_PAIRS:
                errors.append(t("Выберите пару профильных предметов из списка."))
            target = pair
    else:
        errors.append(t("Выберите вид задания: пробный ЕНТ или тренировка."))
    try:
        count = int(count_raw)
    except ValueError:
        count = 0
    if not 1 <= count <= ASSIGNMENT_MAX_COUNT:
        errors.append(t("Количество — от 1 до {n}.", n=ASSIGNMENT_MAX_COUNT))
    try:
        deadline = parse_deadline(deadline_raw)
    except SchoolError as error:
        errors.extend(error.errors)
        deadline = 0.0
    chosen: list[int] | None = None
    if not for_all:
        allowed = {row["id"] for row in database.list_school_members(
            school_id, database.SCHOOL_APPROVED)}
        chosen = sorted(set(student_ids) & allowed)
        if not chosen:
            errors.append(t("Отметьте хотя бы одного ученика или выберите «всем ученикам»."))
    if errors:
        raise SchoolError(errors)
    assignment_id = database.create_assignment(
        school_id, teacher_id, mode, target, count, time.time(), deadline, chosen
    )
    from app.core import notifications

    notifications.assignment_created(assignment_id, school_id)
    return assignment_id
