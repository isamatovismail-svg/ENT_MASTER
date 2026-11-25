"""Проверка вопроса банка — общая для seed.py (JSON-файлы) и форм админки.

Вопрос описывается словарём в формате data/questions/*.json:
type, text, context (для «по контексту»), options, left (для соответствия),
correct (буквы правильных вариантов) и explanation.
"""

import config

MIN_OPTIONS = 2


def validate_question(question: dict) -> list[str]:
    """Проверяет один вопрос из JSON. Возвращает список ошибок (пустой — всё в порядке)."""
    errors: list[str] = []
    qtype = question.get("type")
    text = question.get("text")
    options = question.get("options")
    correct = question.get("correct")

    explanation = question.get("explanation")

    if qtype not in config.QUESTION_TYPES:
        return [f"неизвестный тип «{qtype}»"]
    if not isinstance(text, str) or not text.strip():
        errors.append("пустой текст вопроса")
    if not isinstance(explanation, str) or not explanation.strip():
        errors.append("нет объяснения explanation (почему ответ правильный)")
    if not isinstance(options, list) or not all(isinstance(o, str) and o.strip() for o in options):
        return errors + ["options должен быть списком непустых строк"]
    if not MIN_OPTIONS <= len(options) <= len(config.OPTION_LETTERS):
        errors.append(f"вариантов должно быть от {MIN_OPTIONS} до {len(config.OPTION_LETTERS)}")
    if len(set(options)) != len(options):
        errors.append("варианты ответов повторяются")
    if not isinstance(correct, list) or not correct:
        return errors + ["correct должен быть непустым списком букв"]

    letters = config.OPTION_LETTERS[: len(options)]
    if any(letter not in letters for letter in correct):
        errors.append(f"в correct есть буква вне диапазона {letters[0]}–{letters[-1]}")

    if qtype in (config.SINGLE, config.CONTEXT) and len(correct) != 1:
        errors.append("у задания с одним ответом должна быть ровно одна правильная буква")
    if qtype == config.CONTEXT and not str(question.get("context", "")).strip():
        errors.append("у задания по контексту нет текста context")
    if qtype == config.MULTIPLE and len(set(correct)) != len(correct):
        errors.append("в correct повторяются буквы")
    if qtype == config.MATCHING:
        left = question.get("left")
        if not isinstance(left, list) or len(left) < 2:
            errors.append("у соответствия должен быть список left минимум из 2 строк")
        elif not all(isinstance(item, str) and item.strip() for item in left):
            errors.append("строки left должны быть непустыми")
        elif len(left) != len(correct):
            errors.append("длина correct должна совпадать с числом строк left")
    return errors
