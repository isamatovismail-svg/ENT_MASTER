"""Генераторы вопросов: тысячи расчётных задач по шаблонам.

Каждый модуль предмета содержит словарь TEMPLATES {тип задания: [функции]}.
Функция-шаблон принимает random.Random и возвращает готовый вопрос.
"""

import random

from app.question_bank import validate_question
from app.generators import (
    biology_gen, chemistry_gen, geography_gen, informatics_gen, kz_history_gen, law_gen, math_gen,
    math_literacy_gen, physics_gen, world_history_gen,
)
from app.generators.common import SkipQuestion, polish

# Предмет → шаблоны по типам заданий.
SUBJECT_TEMPLATES = {
    "math": math_gen.TEMPLATES,
    "math_literacy": math_literacy_gen.TEMPLATES,
    "physics": physics_gen.TEMPLATES,
    "kz_history": kz_history_gen.TEMPLATES,
    "chemistry": chemistry_gen.TEMPLATES,
    "informatics": informatics_gen.TEMPLATES,
    "geography": geography_gen.TEMPLATES,
    "biology": biology_gen.TEMPLATES,
    "world_history": world_history_gen.TEMPLATES,
    "law": law_gen.TEMPLATES,
}

# Расчётные предметы: в них большие числа разбиваются пробелами (18 480).
# В остальных числа — это обычно годы, их трогать нельзя (1771, а не 1 771).
NUMERIC_SUBJECTS = {"math", "math_literacy", "physics", "chemistry", "informatics"}

# Сколько вопросов каждого типа создавать по умолчанию.
DEFAULT_COUNTS = {"single": 600, "context": 120, "matching": 120, "multiple": 120}


def generate(subject: str, qtype: str, count: int, seed: int = 2026) -> list[dict]:
    """Создаёт до count разных вопросов (тексты не повторяются).

    seed делает результат воспроизводимым: повторный запуск даёт те же вопросы,
    и seed.py не наплодит дубликатов. Шаблоны используются по очереди,
    чтобы задачи были разнообразными.
    """
    templates = SUBJECT_TEMPLATES[subject].get(qtype, [])
    if not templates:
        return []
    rng = random.Random(f"{seed}:{subject}:{qtype}")
    questions: list[dict] = []
    seen: set[str] = set()
    exhausted: set[int] = set()
    misses = [0] * len(templates)
    index = 0
    while len(questions) < count and len(exhausted) < len(templates):
        number = index % len(templates)
        index += 1
        if number in exhausted:
            continue
        try:
            question = templates[number](rng)
            if subject in NUMERIC_SUBJECTS:
                question = polish(question)
        except (SkipQuestion, ZeroDivisionError):
            misses[number] += 1  # шаблон, который всё время пропускает, тоже считается исчерпанным
            if misses[number] > 200:
                exhausted.add(number)
            continue
        if len(set(question["options"])) != len(question["options"]):
            continue  # после оформления два варианта могли совпасть
        # В базе вопрос уникален по (предмет, текст), поэтому тексты не должны повторяться.
        key = question["text"]
        if key in seen:
            misses[number] += 1
            if misses[number] > 200:  # шаблон исчерпал свои варианты
                exhausted.add(number)
            continue
        problems = validate_question(question)
        if problems:  # защита от ошибок в шаблонах
            raise ValueError(f"{templates[number].__name__}: {problems}")
        misses[number] = 0
        seen.add(key)
        questions.append(question)
    return questions
