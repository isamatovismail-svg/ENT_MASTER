"""Общие шаблоны литературы: «автор → произведения», «герой → произведение», термины.

Произведения берутся из списка спецификации НЦТ; work_topics — {произведение: номер темы}
(app/topics.py), по нему каждый вопрос получает тему своего произведения.
"""

import random
from typing import Callable

from app.generators.common import single
from app.generators.facts import Category, Fact, with_topic


def author_facts(works: dict[str, list[str]], who: str,
                 work_topics: dict[str, str] | None = None) -> list[Fact]:
    """Факты «автор — произведение». who — шаблон вопроса с {work}: «Кто автор произведения «{work}»?»."""
    work_topics = work_topics or {}
    return [Fact(author, f"«{work}»", who.format(work=work), "1", "автор", topic=work_topics.get(work, ""))
            for author, titles in works.items() for work in titles]


def character_facts(characters: list[tuple[str, str]], who: str,
                    work_topics: dict[str, str] | None = None) -> list[Fact]:
    """Факты «герой — произведение». who — шаблон с {work}: «Кто главный герой произведения «{work}»?»."""
    work_topics = work_topics or {}
    return [Fact(name, f"«{work}»", who.format(work=work), "1", "герой", topic=work_topics.get(work, ""))
            for name, work in characters]


def author_categories(works: dict[str, list[str]], question: str, note: str,
                      work_topics: dict[str, str] | None = None) -> list[Category]:
    """«Выберите произведения автора X»: для каждого автора, у которого больше одного произведения.

    Тема задания — тема первого произведения автора в списке.
    """
    work_topics = work_topics or {}
    categories = []
    for author, titles in works.items():
        if len(titles) < 2:
            continue
        others = tuple(f"«{w}»" for other, ws in works.items() if other != author for w in ws)
        categories.append(Category(question.format(author=author), tuple(f"«{w}»" for w in titles), others,
                                   note.format(author=author), topic=work_topics.get(titles[0], "")))
    return categories


def hero_context(works: dict[str, list[str]], characters: list[tuple[str, str]],
                 context_tpl: str, question_tpl: str, explanation_tpl: str,
                 work_topics: dict[str, str] | None = None) -> list[Callable]:
    """Задание по контексту: справка «кто написал» + вопрос о герое этого произведения."""
    author_of = {work: author for author, titles in works.items() for work in titles}
    usable = [(hero, work) for hero, work in characters if work in author_of]

    def hero_by_work(rng: random.Random) -> dict:
        hero, work = rng.choice(usable)
        wrong = [h for h, w in rng.sample([c for c in usable if c[1] != work], 3)]
        author = author_of[work]
        question = single(rng, question_tpl.format(author=author, work=work), hero, wrong,
                          explanation_tpl.format(hero=hero, work=work, author=author),
                          context=context_tpl.format(author=author, work=work))
        return with_topic(question, (work_topics or {}).get(work, ""))

    return [hero_by_work] if len(usable) >= 4 else []
