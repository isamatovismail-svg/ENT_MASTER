"""Все настройки ENT MASTER и структура ЕНТ в одном месте."""

import os
from dataclasses import dataclass
from pathlib import Path

from app.i18n import Translated, t

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "app" / "web"
HOST = "127.0.0.1"
PORT = 8000
DATABASE_PATH = BASE_DIR / "ent_master.sqlite3"
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
QUESTIONS_DIR = BASE_DIR / "data" / "questions"
ENV_PATH = BASE_DIR / ".env"


def load_env(path: Path) -> dict[str, str]:
    """Читает файл .env (строки КЛЮЧ=значение) и возвращает словарь."""
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


_ENV = {**load_env(ENV_PATH), **os.environ}

HOST = _ENV.get("HOST", HOST).strip() or HOST
PORT = int(_ENV.get("PORT", str(PORT)).strip() or PORT)
if _ENV.get("DATABASE_PATH", "").strip():
    DATABASE_PATH = Path(_ENV["DATABASE_PATH"].strip())
COOKIE_SECURE = _ENV.get("COOKIE_SECURE", "").strip() == "1"
BACKUP_DIR = Path(_ENV.get("BACKUP_DIR", "").strip() or BASE_DIR / "backups")
BACKUP_KEEP = int(_ENV.get("BACKUP_KEEP", "14").strip() or 14)
LOCAL_URL = f"http://localhost:{PORT}" if HOST in ("127.0.0.1", "localhost", "0.0.0.0", "::", "::1") \
    else f"http://{HOST}:{PORT}"

SHARE_MODE = _ENV.get("SHARE_MODE", "").strip() == "1"
DEMO_EMAIL_DOMAIN = "entmaster.demo"

SESSION_COOKIE_NAME = "ent_session"
SESSION_LIFETIME_SECONDS = 7 * 24 * 60 * 60
PBKDF2_ITERATIONS = 200_000
PASSWORD_MIN_LENGTH = 8
MAX_REQUEST_BODY_BYTES = 2_000_000
BANNER_MAX_BYTES = 1_000_000

EMAIL_CODE_MINUTES = 15
EMAIL_CODE_MAX_ATTEMPTS = 5
EMAIL_CODE_RESEND_SECONDS = 60
SMTP_HOST = _ENV.get("SMTP_HOST", "").strip()
SMTP_PORT = int(_ENV.get("SMTP_PORT", "465").strip() or 465)
SMTP_USER = _ENV.get("SMTP_USER", "").strip()
SMTP_PASSWORD = _ENV.get("SMTP_PASSWORD", "").strip()
MAIL_FROM = _ENV.get("MAIL_FROM", "").strip() or SMTP_USER

GOOGLE_CLIENT_ID = _ENV.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = _ENV.get("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URI = _ENV.get("GOOGLE_REDIRECT_URI", "").strip()
OAUTH_STATE_COOKIE_NAME = "ent_oauth_state"
OAUTH_STATE_LIFETIME_SECONDS = 10 * 60

TELEGRAM_BOT_TOKEN = _ENV.get("TELEGRAM_BOT_TOKEN", "").strip()
SITE_URL = _ENV.get("SITE_URL", f"http://localhost:{PORT}").strip().rstrip("/")
TELEGRAM_LOGIN_TOKEN_MINUTES = 10
TELEGRAM_POLL_TIMEOUT = 30
ADMIN_TELEGRAM_CHAT_IDS = [int(x) for x in _ENV.get("ADMIN_TELEGRAM_CHAT_ID", "").replace(" ", "").split(",")
                           if x.lstrip("-").isdigit()]
HEALTHCHECK_URL = _ENV.get("HEALTHCHECK_URL", "").strip() or f"http://{HOST}:{PORT}/"
ALERT_STATE_PATH = Path(_ENV.get("ALERT_STATE_PATH", "").strip() or BASE_DIR / ".alert_state.json")
ALERT_COOLDOWN_SECONDS = 10 * 60
TELEGRAM_FILE_LIMIT_BYTES = 50 * 1024 * 1024

MOCK_DURATION_MINUTES = 240
PRACTICE_QUESTION_COUNT = 10

SINGLE = "single"
CONTEXT = "context"
MATCHING = "matching"
MULTIPLE = "multiple"

QUESTION_TYPES = (SINGLE, CONTEXT, MATCHING, MULTIPLE)

QUESTION_TYPE_NAMES = Translated({
    SINGLE: "Один ответ",
    CONTEXT: "По контексту",
    MATCHING: "Соответствие",
    MULTIPLE: "Несколько ответов",
})

QUESTION_POINTS = {SINGLE: 1, CONTEXT: 1, MATCHING: 2, MULTIPLE: 2}

OPTION_LETTERS = "ABCDEFGH"


@dataclass(frozen=True)
class SubjectInfo:
    """Описание предмета ЕНТ: код, название и квота заданий по типам."""

    code: str
    title: str
    icon: str
    compulsory: bool
    quota: tuple[tuple[str, int], ...]

    @property
    def name(self) -> str:
        """Название предмета на языке текущего запроса."""
        return t(self.title)

    @property
    def question_count(self) -> int:
        """Сколько заданий по предмету в полном пробном ЕНТ."""
        return sum(count for _, count in self.quota)

    @property
    def max_score(self) -> int:
        """Максимальный балл по предмету в полном пробном ЕНТ."""
        return sum(count * QUESTION_POINTS[qtype] for qtype, count in self.quota)


PROFILE_QUOTA = ((SINGLE, 25), (CONTEXT, 5), (MATCHING, 5), (MULTIPLE, 5))


def _profile(code: str, name: str, icon: str) -> SubjectInfo:
    return SubjectInfo(code, name, icon, False, PROFILE_QUOTA)


_ALL_SUBJECTS = (
    SubjectInfo("kz_history", "История Казахстана", "🏛️", True, ((SINGLE, 20),)),
    SubjectInfo("math_literacy", "Математическая грамотность", "🧮", True, ((SINGLE, 10),)),
    SubjectInfo("reading_literacy", "Грамотность чтения", "📖", True, ((CONTEXT, 10),)),
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

LANGUAGES = ("ru", "kk")
SHARED_LANGUAGE_SUBJECTS: tuple[str, ...] = ("foreign_language",)
SUBJECT_OWN_LANGUAGE = {
    "kazakh_language": "kk", "kazakh_literature": "kk",
    "russian_language": "ru", "russian_literature": "ru",
}
LANGUAGE_ONLY_PAIRS = {
    ("kazakh_language", "kazakh_literature"): "kk",
    ("russian_language", "russian_literature"): "ru",
}


def pairs_for(language: str) -> list[int]:
    """Индексы пар PROFILE_PAIRS, доступных для языка обучения."""
    return [index for index, pair in enumerate(PROFILE_PAIRS)
            if LANGUAGE_ONLY_PAIRS.get(pair, language) == language]


def question_language(subject: str, language: str) -> str:
    """На каком языке хранится вопрос предмета для ученика с этим языком обучения."""
    if subject in SHARED_LANGUAGE_SUBJECTS:
        return "en"
    return SUBJECT_OWN_LANGUAGE.get(subject, language)


_PROFILE_EXAMPLE = SUBJECTS[PROFILE_PAIRS[0][0]]
MOCK_TOTAL_QUESTIONS = (
    sum(SUBJECTS[c].question_count for c in COMPULSORY_CODES)
    + 2 * _PROFILE_EXAMPLE.question_count
)
MOCK_MAX_SCORE = (
    sum(SUBJECTS[c].max_score for c in COMPULSORY_CODES)
    + 2 * _PROFILE_EXAMPLE.max_score
)
