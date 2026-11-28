"""Общие инструменты генераторов вопросов."""

import random
import re
from fractions import Fraction

from app import config

MINUS = "−"


class SkipQuestion(Exception):
    """Генератор получил неудачные случайные числа — вопрос нужно собрать заново."""


def topic(code: str):
    """Декоратор: тема спецификации НЦТ (номер из app/topics.py), к которой относится шаблон."""

    def mark(function):
        function.topic = code
        return function

    return mark


def num(value: float | int | Fraction, digits: int = 2) -> str:
    """Число по-русски: десятичная запятая, пробелы между тысячами, знак «−»."""
    if isinstance(value, Fraction):
        if value.denominator == 1:
            return num(value.numerator)
        sign = MINUS if value < 0 else ""
        return f"{sign}{abs(value.numerator)}/{value.denominator}"
    if isinstance(value, float):
        value = round(value, digits)
        if value == int(value):
            value = int(value)
    sign = MINUS if value < 0 else ""
    value = abs(value)
    if isinstance(value, int):
        text = f"{value:,}".replace(",", " ")
    else:
        whole, frac = f"{value:.{digits}f}".rstrip("0").split(".")
        text = f"{int(whole):,}".replace(",", " ") + ("," + frac if frac else "")
    return sign + text


def plural(n: int, one: str, few: str, many: str) -> str:
    """Согласование с числом: plural(21, 'место', 'места', 'мест') → «место»."""
    n = abs(n) % 100
    if 11 <= n <= 14:
        return many
    if n % 10 == 1:
        return one
    if 2 <= n % 10 <= 4:
        return few
    return many


_BIG_NUMBER = re.compile(r"(?<![\d,.₀-₉⁰-⁹])(\d{4,})(?![\d,₀-₉⁰-⁹])")


def space_thousands(text: str) -> str:
    """Разбивает целые числа из 4+ цифр пробелами по тысячам: «18480» → «18 480»."""
    return _BIG_NUMBER.sub(lambda m: f"{int(m.group(1)):,}".replace(",", " "), text)


def polish(question: dict) -> dict:
    """Единое оформление чисел во всех текстовых полях вопроса."""
    for key in ("text", "context", "explanation"):
        if key in question:
            question[key] = space_thousands(question[key])
    for key in ("options", "left"):
        if key in question:
            question[key] = [space_thousands(item) for item in question[key]]
    return question


def unique_strings(correct: str, candidates: list[str], need: int) -> list[str]:
    """Отбирает need различных неправильных вариантов, не совпадающих с правильным."""
    result: list[str] = []
    for item in candidates:
        if item != correct and item not in result:
            result.append(item)
        if len(result) == need:
            return result
    raise SkipQuestion("не хватает различных неправильных вариантов")


def number_distractors(rng: random.Random, correct: float, typical: list[float],
                       unit: str = "", need: int = 3, digits: int = 2) -> list[str]:
    """Неправильные числовые варианты."""
    fmt = lambda x: num(x, digits) + unit
    if float(correct).is_integer():
        typical = [x for x in typical if float(x).is_integer()]
    pool = [fmt(x) for x in typical]
    step = max(1, abs(correct) * 0.1) if isinstance(correct, float) and correct != int(correct) else 1
    nearby = [correct + k * step for k in (1, -1, 2, -2, 3, -3, 5, -5, 10)]
    rng.shuffle(nearby)
    pool += [fmt(x) for x in nearby]
    return unique_strings(fmt(correct), pool, need)


def _shuffle_with_letters(rng: random.Random, options: list[str],
                          correct_values: list[str]) -> tuple[list[str], list[str]]:
    order = options[:]
    rng.shuffle(order)
    letters = [config.OPTION_LETTERS[order.index(value)] for value in correct_values]
    return order, letters


def single(rng: random.Random, text: str, correct: str, wrong: list[str],
           explanation: str, context: str = "") -> dict:
    """Задание с одним правильным ответом (4 варианта, как на ЕНТ)."""
    wrong = unique_strings(correct, wrong, 3)
    options, letters = _shuffle_with_letters(rng, [correct] + wrong, [correct])
    question = {
        "type": config.CONTEXT if context else config.SINGLE,
        "text": text,
        "options": options,
        "correct": letters,
        "explanation": explanation,
    }
    if context:
        question["context"] = context
    return question


def multiple(rng: random.Random, text: str, right: list[str], wrong: list[str],
             explanation: str) -> dict:
    """Задание с несколькими правильными ответами: 6 вариантов, правильных от 1 до 3."""
    right = list(dict.fromkeys(right))
    if not 1 <= len(right) <= 3:
        raise SkipQuestion("правильных вариантов должно быть от 1 до 3")
    wrong = [w for w in dict.fromkeys(wrong) if w not in right][: 6 - len(right)]
    if len(right) + len(wrong) != 6:
        raise SkipQuestion("не хватает неправильных вариантов")
    options, letters = _shuffle_with_letters(rng, right + wrong, right)
    return {
        "type": config.MULTIPLE,
        "text": text,
        "options": options,
        "correct": sorted(letters),
        "explanation": explanation,
    }


def matching(rng: random.Random, text: str, pairs: list[tuple[str, str]],
             extra: list[str], explanation: str) -> dict:
    """Задание на соответствие: 2 строки слева и 4 варианта справа (2 лишних)."""
    left = [a for a, _ in pairs]
    right = [b for _, b in pairs]
    if len(set(right)) != len(right):
        raise SkipQuestion("ответы для строк совпадают")
    extra = [e for e in dict.fromkeys(extra) if e not in right][: 4 - len(right)]
    if len(right) + len(extra) != 4:
        raise SkipQuestion("не хватает лишних вариантов")
    options, letters = _shuffle_with_letters(rng, right + extra, right)
    return {
        "type": config.MATCHING,
        "text": text,
        "left": left,
        "options": options,
        "correct": letters,
        "explanation": explanation,
    }


def quiz(items: list[tuple[str, str, list[str], str]], code: str):
    """Шаблон из готовых вопросов «текст — ответ — неверные варианты — объяснение» одной темы."""

    @topic(code)
    def ask(rng: random.Random) -> dict:
        text, answer, wrong, explanation = rng.choice(items)
        return single(rng, text, answer, list(wrong), explanation)

    ask.__name__ = f"quiz_{code}"
    return ask
