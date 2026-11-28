"""Проверка вопроса банка — общая для seed.py (JSON-файлы) и форм админки.

Вопрос описывается словарём в формате data/questions/*.json:
type, text, context (для «по контексту»), options, left (для соответствия),
correct (буквы правильных вариантов), explanation и, по желанию, topic —
номер темы спецификации НЦТ из app/topics.py.
"""

from app import config
from app.core import topics
from app.i18n import t

MIN_OPTIONS = 2


def validate_question(question: dict, subject: str | None = None) -> list[str]:
    """Проверяет один вопрос из JSON. Возвращает список ошибок (пустой — всё в порядке).

    Если передан subject, тема topic (если указана) должна быть темой этого предмета.
    """
    errors: list[str] = []
    topic = question.get("topic", "")
    if not isinstance(topic, str):
        errors.append(t("topic должен быть строкой — номером темы («05»)"))
    elif topic and subject is not None and topics.get_topic(subject, topic) is None:
        errors.append(t("неизвестная тема «{topic}» для предмета {subject}", topic=topic, subject=subject))
    qtype = question.get("type")
    text = question.get("text")
    options = question.get("options")
    correct = question.get("correct")

    explanation = question.get("explanation")

    if qtype not in config.QUESTION_TYPES:
        return [t("неизвестный тип «{qtype}»", qtype=qtype)]
    if not isinstance(text, str) or not text.strip():
        errors.append(t("пустой текст вопроса"))
    if not isinstance(explanation, str) or not explanation.strip():
        errors.append(t("нет объяснения explanation (почему ответ правильный)"))
    if not isinstance(options, list) or not all(isinstance(o, str) and o.strip() for o in options):
        return errors + [t("options должен быть списком непустых строк")]
    if not MIN_OPTIONS <= len(options) <= len(config.OPTION_LETTERS):
        errors.append(t("вариантов должно быть от {a} до {b}", a=MIN_OPTIONS, b=len(config.OPTION_LETTERS)))
    if len(set(options)) != len(options):
        errors.append(t("варианты ответов повторяются"))
    if not isinstance(correct, list) or not correct:
        return errors + [t("correct должен быть непустым списком букв")]

    letters = config.OPTION_LETTERS[: len(options)]
    if any(letter not in letters for letter in correct):
        errors.append(t("в correct есть буква вне диапазона {a}–{b}", a=letters[0], b=letters[-1]))

    if qtype in (config.SINGLE, config.CONTEXT) and len(correct) != 1:
        errors.append(t("у задания с одним ответом должна быть ровно одна правильная буква"))
    if qtype == config.CONTEXT and not str(question.get("context", "")).strip():
        errors.append(t("у задания по контексту нет текста context"))
    if qtype == config.MULTIPLE and len(set(correct)) != len(correct):
        errors.append(t("в correct повторяются буквы"))
    if qtype == config.MATCHING:
        left = question.get("left")
        if not isinstance(left, list) or len(left) < 2:
            errors.append(t("у соответствия должен быть список left минимум из 2 строк"))
        elif not all(isinstance(item, str) and item.strip() for item in left):
            errors.append(t("строки left должны быть непустыми"))
        elif len(left) != len(correct):
            errors.append(t("длина correct должна совпадать с числом строк left"))
    return errors
