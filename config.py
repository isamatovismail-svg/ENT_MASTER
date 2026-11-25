"""Все настройки ENT MASTER и структура ЕНТ в одном месте.

Если меняется формат экзамена (число заданий, баллы, время, пары предметов),
править нужно только этот файл — остальной код берёт данные отсюда.
"""

import os
from dataclasses import dataclass
from pathlib import Path

# ── Пути и сервер ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8000
DATABASE_PATH = BASE_DIR / "ent_master.sqlite3"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
QUESTIONS_DIR = BASE_DIR / "data" / "questions"
ENV_PATH = BASE_DIR / ".env"


def load_env(path: Path) -> dict[str, str]:
    """Читает файл .env (строки КЛЮЧ=значение) и возвращает словарь.

    Пустые строки и строки с # пропускаются, кавычки вокруг значения снимаются.
    Файла может не быть — тогда словарь пустой.
    """
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


# Переменные окружения важнее файла .env.
_ENV = {**load_env(ENV_PATH), **os.environ}

# ── Безопасность ─────────────────────────────────────────────────────────────
SESSION_COOKIE_NAME = "ent_session"
SESSION_LIFETIME_SECONDS = 7 * 24 * 60 * 60  # сессия живёт неделю
PBKDF2_ITERATIONS = 200_000                   # чем больше, тем дороже подбор пароля
PASSWORD_MIN_LENGTH = 8
MAX_REQUEST_BODY_BYTES = 1_000_000            # защита от слишком больших POST-запросов

# ── Telegram-бот ─────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = _ENV.get("TELEGRAM_BOT_TOKEN", "").strip()
# Адрес сайта для ссылок из бота (без / в конце).
SITE_URL = _ENV.get("SITE_URL", f"http://localhost:{PORT}").strip().rstrip("/")
TELEGRAM_LOGIN_TOKEN_MINUTES = 10   # одноразовая ссылка входа действует 10 минут
TELEGRAM_POLL_TIMEOUT = 30          # long polling: сколько секунд Telegram держит запрос

# ── Режимы тестирования ──────────────────────────────────────────────────────
MOCK_DURATION_MINUTES = 240   # пробный ЕНТ — 4 часа на полные 120 заданий
PRACTICE_QUESTION_COUNT = 10  # тренировка — 10 случайных заданий по одному на странице

# ── Типы заданий и баллы ─────────────────────────────────────────────────────
SINGLE = "single"        # один правильный ответ
CONTEXT = "context"      # задание по тексту/контексту, один правильный ответ
MATCHING = "matching"    # задание на соответствие
MULTIPLE = "multiple"    # один или несколько правильных ответов

QUESTION_TYPES = (SINGLE, CONTEXT, MATCHING, MULTIPLE)

QUESTION_TYPE_NAMES = {
    SINGLE: "Один ответ",
    CONTEXT: "По контексту",
    MATCHING: "Соответствие",
    MULTIPLE: "Несколько ответов",
}

# Максимальный балл за одно задание каждого типа.
# Для соответствия и нескольких ответов: 2 балла без ошибок, 1 балл при одной ошибке.
QUESTION_POINTS = {SINGLE: 1, CONTEXT: 1, MATCHING: 2, MULTIPLE: 2}

# Буквы вариантов ответа (A, B, C, ...).
OPTION_LETTERS = "ABCDEFGH"


@dataclass(frozen=True)
class SubjectInfo:
    """Описание предмета ЕНТ: код, название и квота заданий по типам."""

    code: str
    name: str
    icon: str                           # эмодзи-иконка предмета (цвет задан в style.css)
    compulsory: bool
    quota: tuple[tuple[str, int], ...]  # пары (тип задания, количество)

    @property
    def question_count(self) -> int:
        """Сколько заданий по предмету в полном пробном ЕНТ."""
        return sum(count for _, count in self.quota)

    @property
    def max_score(self) -> int:
        """Максимальный балл по предмету в полном пробном ЕНТ."""
        return sum(count * QUESTION_POINTS[qtype] for qtype, count in self.quota)


# Профильный предмет: 25 одиночных + 5 по контексту + 5 соответствий + 5 множественных
# = 40 заданий, 25 + 5 + 10 + 10 = 50 баллов.
PROFILE_QUOTA = ((SINGLE, 25), (CONTEXT, 5), (MATCHING, 5), (MULTIPLE, 5))


def _profile(code: str, name: str, icon: str) -> SubjectInfo:
    """Создаёт описание профильного предмета со стандартной квотой."""
    return SubjectInfo(code, name, icon, False, PROFILE_QUOTA)


_ALL_SUBJECTS = (
    # Обязательные предметы
    SubjectInfo("kz_history", "История Казахстана", "🏛️", True, ((SINGLE, 20),)),
    SubjectInfo("math_literacy", "Математическая грамотность", "🧮", True, ((SINGLE, 10),)),
    SubjectInfo("reading_literacy", "Грамотность чтения", "📖", True, ((CONTEXT, 10),)),
    # Профильные предметы
    _profile("math", "Математика", "📐"),
    _profile("physics", "Физика", "⚛️"),
    _profile("informatics", "Информатика", "💻"),
    _profile("geography", "География", "🌍"),
    _profile("biology", "Биология", "🧬"),
    _profile("chemistry", "Химия", "🧪"),
    _profile("world_history", "Всемирная история", "🗺️"),
    _profile("law", "Основы права", "⚖️"),
    _profile("kazakh_language", "Казахский язык", "🔤"),
    _profile("kazakh_literature", "Казахская литература", "📜"),
    _profile("russian_language", "Русский язык", "✍️"),
    _profile("russian_literature", "Русская литература", "📚"),
    _profile("foreign_language", "Иностранный язык", "🌐"),
)

SUBJECTS: dict[str, SubjectInfo] = {subject.code: subject for subject in _ALL_SUBJECTS}

COMPULSORY_CODES: tuple[str, ...] = tuple(s.code for s in _ALL_SUBJECTS if s.compulsory)

# Разрешённые пары профильных предметов.
PROFILE_PAIRS: tuple[tuple[str, str], ...] = (
    ("math", "physics"),
    ("math", "informatics"),
    ("math", "geography"),
    ("biology", "chemistry"),
    ("biology", "geography"),
    ("chemistry", "physics"),
    ("world_history", "geography"),
    ("world_history", "law"),
    ("kazakh_language", "kazakh_literature"),
    ("russian_language", "russian_literature"),
    ("foreign_language", "world_history"),
)

# Итоговые числа пробного ЕНТ считаются из квот, а не пишутся вручную:
# 20 + 10 + 10 + 40 + 40 = 120 заданий, 20 + 10 + 10 + 50 + 50 = 140 баллов.
_PROFILE_EXAMPLE = SUBJECTS[PROFILE_PAIRS[0][0]]
MOCK_TOTAL_QUESTIONS = (
    sum(SUBJECTS[c].question_count for c in COMPULSORY_CODES)
    + 2 * _PROFILE_EXAMPLE.question_count
)
MOCK_MAX_SCORE = (
    sum(SUBJECTS[c].max_score for c in COMPULSORY_CODES)
    + 2 * _PROFILE_EXAMPLE.max_score
)
