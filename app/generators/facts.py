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
        start = rng.choice(sorted({e.year // 100 * 100 for e in events}))
        inside = [e for e in events if start <= e.year < start + 100]
        outside = [e for e in events if not start <= e.year < start + 100]
        if not inside or len(outside) < 5:
            raise SkipQuestion
        right = rng.sample(inside, min(len(inside), rng.randint(1, 3)))
        wrong = rng.sample(outside, 6 - len(right))
        century = _century(start)
        names = ", ".join(e.noun[0].lower() + e.noun[1:] for e in sorted(right + wrong, key=lambda e: e.noun))
        text = f"Какие события произошли в {century} веке? ({names})"
        explanation = (f"{century} век — это {start + 1}–{start + 100} годы. В него попадают: "
                       + "; ".join(f"{e.noun[0].lower() + e.noun[1:]} ({e.year})" for e in right) + ".")
        return multiple(rng, text, [e.noun for e in right], [e.noun for e in wrong], explanation)

    def years_matching(rng: random.Random) -> dict:
        picked = rng.sample(events, 4)
        if len({e.year for e in picked}) < 4:
            raise SkipQuestion
        first, second = picked[0], picked[1]
        text = f"Установите соответствие между событием и годом: 1) {first.noun.lower()}; 2) {second.noun.lower()}."
        explanation = f"{first.noun} — {first.year} год. {second.noun} — {second.year} год."
        return matching(rng, text, [(first.noun, str(first.year)), (second.noun, str(second.year))],
                        [str(picked[2].year), str(picked[3].year)], explanation)

    return [event_to_year, year_to_event], [chronology_multiple], [years_matching]


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
