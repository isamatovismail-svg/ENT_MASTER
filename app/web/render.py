"""Загрузка HTML-шаблонов и безопасная подстановка данных.

Шаблоны — обычные HTML-файлы с метками $имя (string.Template).
Любое значение при подстановке экранируется через html.escape, поэтому
текст пользователя («<script>» и т.п.) выводится как текст, а не как код.
Исключение — значения типа SafeHTML: это HTML, который мы сами собрали
из уже экранированных частей.
"""

from collections.abc import Iterable
from functools import lru_cache
from html import escape as _html_escape
from string import Template

from app import config
from app import i18n


class SafeHTML(str):
    """Строка, которая уже является безопасным HTML и не требует экранирования."""


def escape(value: object) -> str:
    """Экранирует значение для вставки в HTML (включая кавычки в атрибутах)."""
    return _html_escape(str(value), quote=True)


def to_html(value: object) -> str:
    """SafeHTML оставляет как есть, всё остальное экранирует."""
    if isinstance(value, SafeHTML):
        return value
    return escape(value)


@lru_cache(maxsize=None)
def _source(name: str) -> str:
    """Читает шаблон из папки templates/ (один раз, затем берёт из кэша)."""
    return (config.TEMPLATES_DIR / name).read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def _load(name: str, lang: str) -> Template:
    """Шаблон, переведённый на язык lang (текст интерфейса — по словарю app/i18n.py)."""
    return Template(i18n.translate_markup(_source(name), lang))


def render(template_name: str, /, **context: object) -> SafeHTML:
    """Заполняет шаблон-файл значениями. Отсутствующая метка — ошибка (KeyError).

    Имя шаблона — только позиционный аргумент, поэтому в шаблоне можно
    свободно использовать метку $name.
    """
    values = {key: to_html(value) for key, value in context.items()}
    return SafeHTML(_load(template_name, i18n.get_language()).substitute(values))


def fragment(template: str, /, **context: object) -> SafeHTML:
    """Заполняет небольшой HTML-фрагмент, заданный строкой, с тем же экранированием.

    Текст самого фрагмента переводится на язык запроса, подставленные значения — нет.
    """
    values = {key: to_html(value) for key, value in context.items()}
    return SafeHTML(Template(i18n.translate_markup(template, i18n.get_language())).substitute(values))


def join(parts: Iterable[object]) -> SafeHTML:
    """Склеивает части в один HTML; обычные строки при этом экранируются."""
    return SafeHTML("".join(to_html(part) for part in parts))
