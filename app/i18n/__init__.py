"""Двуязычный интерфейс: русский (ru) и казахский (kk) — без сторонних библиотек.

Как устроено:
- исходный текст интерфейса пишется по-русски, он же — ключ словаря KK (русский → казахский);
- язык текущего запроса хранится в contextvar (у каждого потока сервера — свой):
  сервер ставит его по пользователю (users.language) или cookie гостя;
- t("Текст {n}", n=5) — перевод строки из кода Python;
- текст в HTML-шаблонах и фрагментах (render/fragment) переводится автоматически:
  каждый текстовый узел и атрибуты placeholder/title/aria-label/alt ищутся в том же словаре
  (лишние пробелы не важны). Данные пользователя (имена, вопросы) подставляются ПОСЛЕ
  перевода и поэтому не переводятся никогда;
- use("kk") — временно сменить язык (письмо, уведомление или сообщение бота другому человеку).

Слова без перевода остаются русскими; tests/test_i18n.py следит, чтобы у каждой строки
интерфейса был казахский перевод и на казахских страницах не оставалось русского текста.
Словарь KK_DICT — в app/i18n/kk.py.
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache

from app.i18n.kk import KK_DICT

RU = "ru"
KK = "kk"
LANGUAGES = (RU, KK)
DEFAULT = RU
# Подписи переключателя в шапке и названия языков в формах.
SWITCH_LABELS = {RU: "РУС", KK: "ҚАЗ"}
LANGUAGE_NAMES = {RU: "Русский", KK: "Қазақ тілі"}
COOKIE_NAME = "ent_lang"
COOKIE_MAX_AGE = 365 * 24 * 60 * 60

_current: ContextVar[str] = ContextVar("ent_language", default=DEFAULT)


def normalize(lang: str | None) -> str:
    """Код языка из списка LANGUAGES (неизвестный — язык по умолчанию)."""
    return lang if lang in LANGUAGES else DEFAULT


def set_language(lang: str | None) -> None:
    """Язык текущего запроса (потока)."""
    _current.set(normalize(lang))


def get_language() -> str:
    """Язык текущего запроса."""
    return _current.get()


@contextmanager
def use(lang: str | None) -> Iterator[None]:
    """Временно сменить язык: with use("kk"): text = t("...")."""
    token = _current.set(normalize(lang))
    try:
        yield
    finally:
        _current.reset(token)


def _key(text: str) -> str:
    return " ".join(text.split())


def lookup(text: str, lang: str | None = None) -> str | None:
    """Перевод строки или None, если его нет (для русского — сама строка)."""
    lang = normalize(lang or get_language())
    if lang == RU:
        return text
    return KK_DICT.get(_key(text))


def t(text: str, /, **values: object) -> str:
    """Перевод строки интерфейса на язык запроса; {name} заменяются значениями values."""
    translated = lookup(text)
    if translated is None:
        translated = text
    elif translated != text:
        # пробелы по краям («Текст. » + …) сохраняются, как в исходной строке
        translated = text[: len(text) - len(text.lstrip())] + translated + text[len(text.rstrip()):]
    return translated.format(**values) if values else translated


class Translated(dict):
    """Словарь подписей (код → русский текст), который отдаёт их на языке запроса."""

    def __getitem__(self, key):
        return t(super().__getitem__(key))

    def get(self, key, default=None):
        return self[key] if key in self else default

    def values(self):
        return [self[key] for key in self]

    def items(self):
        return [(key, self[key]) for key in self]


# ── Перевод HTML-шаблонов ───────────────────────────────────────────────────

_CYRILLIC = re.compile("[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]")
_TEXT_NODE = re.compile(r">([^<>]+)<")
_ATTRIBUTE = re.compile(r'\b(placeholder|title|aria-label|alt)="([^"]*)"')


def _translate_segment(segment: str, lang: str) -> str:
    if not _CYRILLIC.search(segment):
        return segment
    stripped = segment.strip()
    translated = lookup(stripped, lang)
    if translated is None or translated == stripped:
        return segment
    start = segment[: len(segment) - len(segment.lstrip())]
    end = segment[len(segment.rstrip()):]
    return f"{start}{translated}{end}"


@lru_cache(maxsize=4096)
def translate_markup(source: str, lang: str) -> str:
    """Переводит текстовые узлы и атрибуты HTML-шаблона (до подстановки данных)."""
    if lang == RU:
        return source
    wrapped = f">{source}<"  # чтобы текст в начале и в конце тоже был «узлом»
    wrapped = _TEXT_NODE.sub(lambda m: f">{_translate_segment(m.group(1), lang)}<", wrapped)
    wrapped = _ATTRIBUTE.sub(lambda m: f'{m.group(1)}="{_translate_segment(m.group(2), lang)}"', wrapped)
    return wrapped[1:-1]


def markup_segments(source: str) -> list[str]:
    """Все строки шаблона, которые переводятся (для проверки словаря в тестах)."""
    wrapped = f">{source}<"
    found = [m.group(1) for m in _TEXT_NODE.finditer(wrapped)]
    found += [m.group(2) for m in _ATTRIBUTE.finditer(wrapped)]
    return [_key(s) for s in found if _CYRILLIC.search(s)]
