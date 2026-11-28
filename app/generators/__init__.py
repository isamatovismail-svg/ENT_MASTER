"""Генераторы вопросов: тысячи расчётных задач по шаблонам."""

import random

from app import config
from app.core.question_bank import validate_question
from app.generators import (
    biology_gen, chemistry_gen, foreign_language_gen, geography_gen, informatics_gen, kazakh_language_gen,
    kazakh_literature_gen, kz_history_gen, law_gen, math_gen, math_literacy_gen, physics_gen,
    russian_language_gen, russian_literature_gen, world_history_gen,
)
from app.generators.common import SkipQuestion, polish

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
    "russian_language": russian_language_gen.TEMPLATES,
    "russian_literature": russian_literature_gen.TEMPLATES,
    "kazakh_language": kazakh_language_gen.TEMPLATES,
    "kazakh_literature": kazakh_literature_gen.TEMPLATES,
    "foreign_language": foreign_language_gen.TEMPLATES,
}

from app.generators import kk_gen

KK_TEMPLATES = kk_gen.TEMPLATES


def templates_for(subject: str, lang: str = "ru") -> dict:
    """Шаблоны предмета для языка вопросов: ru — исходные, kk — казахские версии."""
    if lang == "kk" and subject not in config.SUBJECT_OWN_LANGUAGE and subject not in config.SHARED_LANGUAGE_SUBJECTS:
        return KK_TEMPLATES.get(subject, {})
    return SUBJECT_TEMPLATES[subject]


NUMERIC_SUBJECTS = {"math", "math_literacy", "physics", "chemistry", "informatics"}

DEFAULT_COUNTS = {"single": 600, "context": 120, "matching": 120, "multiple": 120}


def generate(subject: str, qtype: str, count: int, seed: int = 2026, lang: str = "ru") -> list[dict]:
    """Создаёт до count разных вопросов (тексты не повторяются)."""
    templates = templates_for(subject, lang).get(qtype, [])
    if not templates:
        return []
    rng = random.Random(f"{seed}:{subject}:{qtype}" + ("" if lang == "ru" else f":{lang}"))
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
            question.setdefault("topic", getattr(templates[number], "topic", ""))
            if subject in NUMERIC_SUBJECTS:
                question = polish(question)
        except (SkipQuestion, ZeroDivisionError):
            misses[number] += 1
            if misses[number] > 200:
                exhausted.add(number)
            continue
        if len(set(question["options"])) != len(question["options"]):
            continue
        key = question["text"]
        if key in seen:
            misses[number] += 1
            if misses[number] > 200:
                exhausted.add(number)
            continue
        problems = validate_question(question, subject)
        if problems:
            raise ValueError(f"{templates[number].__name__}: {problems}")
        misses[number] = 0
        seen.add(key)
        question["language"] = config.question_language(subject, lang)
        questions.append(question)
    return questions
