"""Шаблоны для предметов «на знание фактов»: история, география, биология, право, литература.

Код не придумывает факты — он берёт их из таблиц (их проверяет человек) и собирает
из одной таблицы много разных вопросов. Неправильные варианты берутся из соседних
строк той же таблицы, поэтому они правдоподобные.

Таблицы:
  Event(year, clause, noun) — «В каком году {clause}?» и «Какое событие произошло в {year} году?»
  Fact(name, about, who, what) — «{who}» → name и «{what}» → about.
"""

import random
from dataclasses import dataclass
from typing import Callable

from app.generators.common import SkipQuestion, matching, multiple, single


@dataclass(frozen=True)
class Event:
    """Событие с датой."""

    year: int
    clause: str   # продолжение вопроса «В каком году …?»: «было образовано Казахское ханство»
    noun: str     # название события: «Образование Казахского ханства»
    note: str = ""  # пояснение для объяснения (по желанию)


@dataclass(frozen=True)
class Fact:
    """Факт «имя — описание» с двумя формулировками вопроса.

    name     — кто или что: «Тауке-хан», «Туркестан».
    about    — чем известен, короткой фразой: «свод законов «Жеті жарғы»».
    who      — вопрос, ответ на который name: «При каком хане был составлен свод «Жеті жарғы»?»
    what     — вопрос, ответ на который about: «С каким документом связано имя Тауке-хана?»
               (пустая строка — такого вопроса нет).
    group    — варианты берутся только из той же группы (ханы к ханам, города к городам).
    note     — объяснение, почему ответ верный.
    """

    name: str
    about: str
    who: str
    what: str = ""
    group: str = ""
    note: str = ""


def _year_options(rng: random.Random, events: list[Event], target: Event) -> list[str]:
    """Неправильные годы: даты других событий неподалёку и годы рядом с правильным."""
    others = sorted({e.year for e in events if e.year != target.year},
                    key=lambda y: abs(y - target.year))[:8]
    near = [target.year + d for d in (-10, -5, -3, -2, 2, 3, 5, 10)]
    pool = others[:5] + near
    rng.shuffle(pool)
    return [str(y) for y in pool if y != target.year]


def event_templates(events: list[Event]) -> tuple[list[Callable], list[Callable], list[Callable]]:
    """Шаблоны по таблице событий: (один ответ, несколько ответов, соответствие)."""

    def event_to_year(rng: random.Random) -> dict:
        event = rng.choice(events)
        explanation = f"{event.noun} — {event.year} год."
        if event.note:
            explanation += " " + event.note
        return single(rng, f"В каком году {event.clause}?", str(event.year),
                      _year_options(rng, events, event), explanation)

    def year_to_event(rng: random.Random) -> dict:
        event = rng.choice(events)
        # Неправильные варианты — события других лет, иначе было бы два верных ответа.
        candidates = [e for e in events if abs(e.year - event.year) >= 3]
        candidates.sort(key=lambda e: abs(e.year - event.year))
        wrong_events = rng.sample(candidates[:12], 3)
        explanation = f"В {event.year} году — {event.noun[0].lower() + event.noun[1:]}." + (
            f" {event.note}" if event.note else "")
        explanation += " Остальные события: " + "; ".join(
            f"{e.noun[0].lower() + e.noun[1:]} — {e.year}" for e in wrong_events) + "."
        return single(rng, f"Какое событие произошло в {event.year} году?", event.noun,
                      [e.noun for e in wrong_events], explanation)

    def chronology_multiple(rng: random.Random) -> dict:
        # Век года y: (y − 1) // 100 + 1, т.е. XIX век — это 1801–1900 годы.
        index = rng.choice(sorted({(e.year - 1) // 100 for e in events}))
        inside = [e for e in events if (e.year - 1) // 100 == index]
        outside = [e for e in events if (e.year - 1) // 100 != index]
        if not inside or len(outside) < 5:
            raise SkipQuestion
        right = rng.sample(inside, min(len(inside), rng.randint(1, 3)))
        wrong = rng.sample(outside, 6 - len(right))
        century = _century(index * 100)
        names = ", ".join(_lower_first(e.noun) for e in sorted(right + wrong, key=lambda e: e.noun))
        text = f"Какие события произошли в {century} веке? ({names})"
        explanation = (f"{century} век — это {index * 100 + 1}–{index * 100 + 100} годы. В него попадают: "
                       + "; ".join(f"{_lower_first(e.noun)} ({e.year})" for e in right) + ".")
        return multiple(rng, text, [e.noun for e in right], [e.noun for e in wrong], explanation)

    def years_matching(rng: random.Random) -> dict:
        picked = rng.sample(events, 4)
        if len({e.year for e in picked}) < 4:
            raise SkipQuestion
        first, second = picked[0], picked[1]
        text = (f"Установите соответствие между событием и годом: 1) {_lower_first(first.noun)}; "
                f"2) {_lower_first(second.noun)}.")
        explanation = f"{first.noun} — {first.year} год. {second.noun} — {second.year} год."
        return matching(rng, text, [(first.noun, str(first.year)), (second.noun, str(second.year))],
                        [str(picked[2].year), str(picked[3].year)], explanation)

    return [event_to_year, year_to_event], [chronology_multiple], [years_matching]


def _lower_first(text: str) -> str:
    """Первая буква строчная, остальные как были: «Открытие Америки» → «открытие Америки»."""
    return text[:1].lower() + text[1:]


def _century(start: int) -> str:
    """Римская запись века для года-начала столетия (1800 → XIX)."""
    number = start // 100 + 1
    romans = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    result = ""
    for value, letter in romans:
        while number >= value:
            result += letter
            number -= value
    return result


def fact_templates(facts: list[Fact], titles: dict[str, str],
                   what_phrases: dict[str, str] | None = None) -> tuple[list[Callable], list[Callable]]:
    """Шаблоны по таблице фактов: (один ответ, соответствие).

    titles — заголовки заданий на соответствие по группам:
    {"хан": "между ханом и связанным с ним событием"}.
    what_phrases — общая формулировка вопроса «чем известен» для группы, например
    {"деятель": "Чем известен в истории деятель {name}?"}. Она заменяет fact.what,
    чтобы вопрос подходил ко всем вариантам ответа из группы.
    """
    what_phrases = what_phrases or {}

    def same_group(fact: Fact) -> list[Fact]:
        return [f for f in facts if f.group == fact.group and f.name != fact.name and f.about != fact.about]

    def explain(fact: Fact, answer: str) -> str:
        return f"{fact.name} — {fact.about}." + (f" {fact.note}" if fact.note else "")

    def who(rng: random.Random) -> dict:
        fact = rng.choice(facts)
        others = same_group(fact)
        if len(others) < 3:
            raise SkipQuestion
        wrong = [f.name for f in rng.sample(others, min(len(others), 6))]
        return single(rng, fact.who, fact.name, wrong, explain(fact, fact.name))

    def what(rng: random.Random) -> dict:
        fact = rng.choice([f for f in facts if f.what])
        others = same_group(fact)
        if len(others) < 3:
            raise SkipQuestion
        wrong = [f.about for f in rng.sample(others, min(len(others), 6))]
        text = what_phrases.get(fact.group, fact.what).format(name=fact.name)
        return single(rng, text, fact.about, wrong, explain(fact, fact.about))

    def pair_matching(rng: random.Random) -> dict:
        group = rng.choice(sorted(titles))
        members = [f for f in facts if f.group == group]
        if len(members) < 4:
            raise SkipQuestion
        picked = rng.sample(members, 4)
        if len({f.about for f in picked}) < 4:
            raise SkipQuestion
        a, b = picked[0], picked[1]
        text = f"Установите соответствие {titles[group]}: 1) {a.name}; 2) {b.name}."
        explanation = f"{a.name} — {a.about}. {b.name} — {b.about}."
        return matching(rng, text, [(a.name, a.about), (b.name, b.about)],
                        [picked[2].about, picked[3].about], explanation)

    templates = [who]
    if any(f.what for f in facts):
        templates.append(what)
    return templates, [pair_matching]


@dataclass(frozen=True)
class Category:
    """Группа для заданий «выберите все…»: вопрос, подходящие и неподходящие варианты."""

    question: str            # «Какие из рек впадают в Каспийское море»
    right: tuple[str, ...]   # подходящие
    wrong: tuple[str, ...]   # неподходящие (правдоподобные)
    note: str = ""           # общее объяснение правила


def category_templates(categories: list[Category]) -> list[Callable]:
    """Задания с несколькими ответами: 1–3 правильных из 6 вариантов."""

    def choose_all(rng: random.Random) -> dict:
        cat = rng.choice(categories)
        right = rng.sample(cat.right, min(len(cat.right), rng.randint(1, 3)))
        if len(cat.wrong) < 6 - len(right):
            raise SkipQuestion
        wrong = rng.sample(cat.wrong, 6 - len(right))
        names = sorted(right + wrong)
        text = f"{cat.question}: {', '.join(names)}?"
        explanation = (cat.note + " " if cat.note else "") + "Подходят: " + ", ".join(sorted(right)) + "."
        return multiple(rng, text, right, wrong, explanation)

    return [choose_all]


def context_templates(facts: list[Fact]) -> list[Callable]:
    """Задания по контексту: описание (note) без имени, нужно узнать, о ком или о чём речь."""
    usable = [f for f in facts if f.note and f.name.split()[0].lower() not in f.note.lower()]

    def by_description(rng: random.Random) -> dict:
        if not usable:
            raise SkipQuestion
        fact = rng.choice(usable)
        others = [f for f in facts if f.group == fact.group and f.name != fact.name]
        if len(others) < 3:
            raise SkipQuestion
        wrong = [f.name for f in rng.sample(others, min(6, len(others)))]
        explanation = f"В тексте описан объект «{fact.name}»: {fact.about}."
        return single(rng, f"Прочитайте описание и ответьте на вопрос. {fact.who}", fact.name, wrong, explanation,
                      context=fact.note)

    def by_about(rng: random.Random) -> dict:
        fact = rng.choice(facts)
        others = [f for f in facts if f.group == fact.group and f.name != fact.name]
        if len(others) < 3:
            raise SkipQuestion
        wrong = [f.name for f in rng.sample(others, min(6, len(others)))]
        context = f"Описание: {fact.about}." + (f" {fact.note}" if fact.note and fact.name.split()[0].lower()
                                                not in fact.note.lower() else "")
        explanation = f"Это описание подходит к варианту «{fact.name}»: {fact.about}."
        return single(rng, f"О ком или о чём идёт речь в описании «{fact.about}»?", fact.name, wrong,
                      explanation, context=context)

    return ([by_description] if usable else []) + [by_about]


def event_context_templates(events: list[Event]) -> list[Callable]:
    """Задания по контексту о событии: текст-описание и вопрос о дате."""
    usable = [e for e in events if e.note]

    def event_context(rng: random.Random) -> dict:
        if not usable:
            raise SkipQuestion
        event = rng.choice(usable)
        context = f"{event.noun}. {event.note}"
        return single(rng, f"Прочитайте текст. В каком году {event.clause}?", str(event.year),
                      _year_options(rng, events, event), f"{event.noun} — {event.year} год.", context=context)

    return [event_context] if usable else []


def build(events: list[Event] | None = None, facts: list[Fact] | None = None,
          titles: dict[str, str] | None = None, what_phrases: dict[str, str] | None = None,
          categories: list[Category] | None = None, extra: dict[str, list[Callable]] | None = None
          ) -> dict[str, list[Callable]]:
    """Собирает TEMPLATES профильного предмета из таблиц: все четыре типа заданий ЕНТ."""
    templates: dict[str, list[Callable]] = {"single": [], "context": [], "matching": [], "multiple": []}
    if events:
        single_t, multiple_t, matching_t = event_templates(events)
        templates["single"] += single_t
        templates["multiple"] += multiple_t
        templates["matching"] += matching_t
        templates["context"] += event_context_templates(events)
    if facts:
        single_t, matching_t = fact_templates(facts, titles or {}, what_phrases)
        templates["single"] += single_t
        if titles:
            templates["matching"] += matching_t
        templates["context"] += context_templates(facts)
    if categories:
        templates["multiple"] += category_templates(categories)
    for qtype, functions in (extra or {}).items():
        templates[qtype] += functions
    return {qtype: functions for qtype, functions in templates.items() if functions}
