"""Логика ЕНТ: сборка теста, разбор ответов из формы и подсчёт баллов.

Правила подсчёта (config.QUESTION_POINTS):
- один ответ / по контексту: 1 балл за верный ответ;
- соответствие и несколько ответов: 2 балла без ошибок, 1 балл при одной ошибке,
  0 баллов при двух и более ошибках.
"""

import time
from dataclasses import dataclass

import config
from app import database
from app.database import Attempt, AttemptQuestion

MOCK = "mock"
PRACTICE = "practice"


class TestBuildError(Exception):
    """Тест невозможно собрать (например, в банке нет ни одного вопроса)."""


@dataclass
class SubjectAvailability:
    """Сколько заданий по предмету есть в банке по сравнению с полным ЕНТ."""

    code: str
    name: str
    have: int
    need: int

    @property
    def is_complete(self) -> bool:
        """True, если банк позволяет собрать полный раздел."""
        return self.have >= self.need


@dataclass
class SubjectScore:
    """Результат по одному предмету в попытке."""

    code: str
    name: str
    score: int
    max_score: int          # максимум по заданиям, которые реально были в тесте
    nominal_max_score: int  # максимум по официальной структуре ЕНТ
    answered: int
    total: int


# ── Баллы ────────────────────────────────────────────────────────────────────

def question_max_points(qtype: str) -> int:
    """Максимальный балл за задание данного типа."""
    return config.QUESTION_POINTS[qtype]


def _two_point_score(mistakes: int) -> int:
    """Балл за двухбалльное задание: 0 ошибок — 2, одна ошибка — 1, иначе 0."""
    if mistakes == 0:
        return 2
    if mistakes == 1:
        return 1
    return 0


def score_answer(qtype: str, correct: list[str], answer: list[str] | None) -> int:
    """Считает баллы за ответ ученика на одно задание."""
    if not answer:
        return 0
    if qtype in (config.SINGLE, config.CONTEXT):
        return 1 if answer == correct else 0
    if qtype == config.MULTIPLE:
        # Ошибка — это лишний выбранный вариант или пропущенный верный.
        mistakes = len(set(answer) ^ set(correct))
        return _two_point_score(mistakes)
    if qtype == config.MATCHING:
        # Ошибка — каждая строка, сопоставленная неверно или не сопоставленная.
        mistakes = sum(
            1 for index, letter in enumerate(correct)
            if index >= len(answer) or answer[index] != letter
        )
        return _two_point_score(mistakes)
    return 0


# ── Разбор ответов из HTML-формы ─────────────────────────────────────────────

def field_name(aq: AttemptQuestion) -> str:
    """Имя поля формы для задания (у соответствия к нему добавляется _номер строки)."""
    return f"q{aq.id}"


def parse_answer(aq: AttemptQuestion, form: dict[str, list[str]]) -> list[str] | None:
    """Достаёт ответ на задание из данных формы. None — ответа нет.

    Значения, которых нет среди допустимых букв, отбрасываются,
    поэтому подделанная форма не может сломать подсчёт.
    """
    letters = config.OPTION_LETTERS[: len(aq.options)]
    name = field_name(aq)

    if aq.qtype in (config.SINGLE, config.CONTEXT):
        value = form.get(name, [""])[0]
        return [value] if value and value in letters else None

    if aq.qtype == config.MULTIPLE:
        chosen = sorted({value for value in form.get(name, []) if value and value in letters})
        return chosen or None

    if aq.qtype == config.MATCHING:
        row_answers = []
        for index in range(len(aq.left)):
            value = form.get(f"{name}_{index}", [""])[0]
            row_answers.append(value if value and value in letters else "")
        return row_answers if any(row_answers) else None

    return None


def parse_section_answers(
    questions: list[AttemptQuestion], form: dict[str, list[str]]
) -> dict[int, list[str] | None]:
    """Ответы на все задания раздела: {id задания попытки: ответ}."""
    return {aq.id: parse_answer(aq, form) for aq in questions}


def format_answer(aq: AttemptQuestion, answer: list[str] | None) -> str:
    """Человекочитаемый ответ для страницы разбора, например «B) 1991»."""
    if not answer:
        return "нет ответа"
    if aq.qtype == config.MATCHING:
        parts = []
        for index, left_item in enumerate(aq.left):
            letter = answer[index] if index < len(answer) else ""
            right = _option_text(aq, letter) if letter else "—"
            parts.append(f"{index + 1}) {left_item} → {right}")
        return "; ".join(parts)
    return "; ".join(_option_text(aq, letter) for letter in answer)


def _option_text(aq: AttemptQuestion, letter: str) -> str:
    """Текст варианта ответа по букве в виде «B) текст»."""
    index = config.OPTION_LETTERS.find(letter)
    if 0 <= index < len(aq.options):
        return f"{letter}) {aq.options[index]}"
    return letter


# ── Банк вопросов и сборка теста ─────────────────────────────────────────────

def availability(subject_code: str, counts: dict[tuple[str, str], int]) -> SubjectAvailability:
    """Сколько заданий предмета можно взять из банка с учётом квот по типам."""
    subject = config.SUBJECTS[subject_code]
    have = sum(min(counts.get((subject_code, qtype), 0), need) for qtype, need in subject.quota)
    return SubjectAvailability(subject_code, subject.name, have, subject.question_count)


def mock_subjects(pair_index: int) -> list[str]:
    """Пять предметов пробного ЕНТ: три обязательных и выбранная пара профильных."""
    if not 0 <= pair_index < len(config.PROFILE_PAIRS):
        raise TestBuildError("Такой пары профильных предметов нет.")
    return list(config.COMPULSORY_CODES) + list(config.PROFILE_PAIRS[pair_index])


def build_mock(user_id: int, pair_index: int, now: float | None = None) -> int:
    """Собирает пробный ЕНТ по квотам и возвращает id попытки.

    Если в банке не хватает заданий какого-то типа, берётся всё, что есть,
    а нехватка записывается в попытку, чтобы честно показать её ученику.
    """
    now = time.time() if now is None else now
    subjects = mock_subjects(pair_index)
    chosen: list[tuple[int, str]] = []
    shortage: list[dict] = []
    max_score = 0

    for code in subjects:
        for qtype, need in config.SUBJECTS[code].quota:
            found = database.random_questions(code, qtype, need)
            chosen.extend((question_id, code) for question_id, _ in found)
            max_score += len(found) * question_max_points(qtype)
            if len(found) < need:
                shortage.append(
                    {"subject": code, "type": qtype, "have": len(found), "need": need}
                )

    if not chosen:
        raise TestBuildError("В банке пока нет вопросов. Запустите python seed.py.")

    deadline = now + config.MOCK_DURATION_MINUTES * 60
    return database.create_attempt(
        user_id, MOCK, subjects, now, deadline, max_score, shortage, chosen
    )


def build_practice(user_id: int, subject_code: str, now: float | None = None) -> int:
    """Собирает тренировку: случайные задания одного предмета (любых типов)."""
    if subject_code not in config.SUBJECTS:
        raise TestBuildError("Такого предмета нет.")
    now = time.time() if now is None else now
    found = database.random_questions(subject_code, None, config.PRACTICE_QUESTION_COUNT)
    if not found:
        raise TestBuildError("По этому предмету пока нет вопросов в банке.")

    chosen = [(question_id, subject_code) for question_id, _ in found]
    max_score = sum(question_max_points(qtype) for _, qtype in found)
    return database.create_attempt(
        user_id, PRACTICE, [subject_code], now, None, max_score, [], chosen
    )


# ── Время и завершение ───────────────────────────────────────────────────────

def is_expired(attempt: Attempt, now: float | None = None) -> bool:
    """True, если у незавершённой попытки вышло время."""
    now = time.time() if now is None else now
    return (
        not attempt.is_finished
        and attempt.deadline is not None
        and now >= attempt.deadline
    )


def remaining_seconds(attempt: Attempt, now: float | None = None) -> int:
    """Сколько секунд осталось до конца теста (0, если время вышло или его нет)."""
    if attempt.deadline is None:
        return 0
    now = time.time() if now is None else now
    return max(0, int(attempt.deadline - now))


def finish_attempt(attempt: Attempt, now: float | None = None) -> None:
    """Оценивает все задания попытки и помечает её завершённой.

    Если время уже вышло, временем окончания считается дедлайн, а не момент запроса.
    """
    now = time.time() if now is None else now
    finished_at = min(now, attempt.deadline) if attempt.deadline is not None else now
    points = {
        aq.id: score_answer(aq.qtype, aq.correct, aq.answer)
        for aq in database.get_attempt_questions(attempt.id)
    }
    database.complete_attempt(attempt.id, points, sum(points.values()), finished_at)


def finish_expired_attempts(user_id: int, now: float | None = None) -> None:
    """Завершает все попытки пользователя, у которых вышло время."""
    now = time.time() if now is None else now
    for attempt_id in database.get_expired_attempt_ids(user_id, now):
        attempt = database.get_attempt(attempt_id, user_id)
        if attempt is not None:
            finish_attempt(attempt, now)


def subject_scores(attempt: Attempt, questions: list[AttemptQuestion]) -> list[SubjectScore]:
    """Баллы попытки по каждому предмету в порядке разделов."""
    result = []
    for code in attempt.subjects:
        subject_questions = [aq for aq in questions if aq.subject == code]
        subject = config.SUBJECTS[code]
        result.append(
            SubjectScore(
                code=code,
                name=subject.name,
                score=sum(aq.points for aq in subject_questions),
                max_score=sum(question_max_points(aq.qtype) for aq in subject_questions),
                nominal_max_score=subject.max_score,
                answered=sum(1 for aq in subject_questions if aq.answer),
                total=len(subject_questions),
            )
        )
    return result
