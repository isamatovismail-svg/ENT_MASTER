"""Работа с базой данных sqlite3.

Здесь собраны создание таблиц и ВСЕ SQL-запросы приложения.
Все запросы параметризованные (знаки ?), значения никогда не вставляются
в текст SQL напрямую — это защищает от SQL-инъекций.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import config

ROLE_USER = "user"
ROLE_TEACHER = "teacher"  # учитель — администратор своей школы
ROLE_ADMIN = "admin"      # главный администратор, полный доступ

# Статус вопроса: на проверке, одобрен (участвует в тестах), отклонён.
Q_PENDING = "pending"
Q_APPROVED = "approved"
Q_REJECTED = "rejected"

# Статус ученика в школе: ждёт подтверждения учителя, подтверждён, отклонён.
SCHOOL_PENDING = "pending"
SCHOOL_APPROVED = "approved"
SCHOOL_REJECTED = "rejected"

# Путь к файлу базы. Тесты подменяют его через configure().
_db_path: Path = config.DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    login         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    created_at    REAL NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',  -- 'user' или 'admin'
    telegram_id   INTEGER,                       -- привязанный аккаунт Telegram (или NULL)
    phone         TEXT,                          -- телефон +7XXXXXXXXXX (необязательно, не подтверждается)
    -- 0 — зарегистрировался по почте и ещё не ввёл код из письма (войти нельзя).
    -- Старые аккаунты (до подтверждения почты) считаются подтверждёнными.
    email_verified INTEGER NOT NULL DEFAULT 1,
    -- Школа: у ученика — куда он подал заявку (school_status), у учителя — его школа.
    school_id     INTEGER,
    school_status TEXT,                          -- pending / approved / rejected (или NULL)
    last_login_at REAL,                          -- время последнего входа
    language      TEXT NOT NULL DEFAULT 'ru'     -- язык интерфейса и вопросов: ru / kk
);

-- Школы: город + номер или название. key — нормализованная пара «город|школа»,
-- чтобы «Школа №12» и «12» в одном городе были одной школой.
CREATE TABLE IF NOT EXISTS schools (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    city       TEXT NOT NULL,
    name       TEXT NOT NULL,
    key        TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL
);

-- Задания учителя: N пробных ЕНТ (любая или конкретная пара) или N тренировок по предмету.
CREATE TABLE IF NOT EXISTS assignments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    school_id  INTEGER NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    mode       TEXT NOT NULL CHECK (mode IN ('mock', 'practice')),
    -- Тренировка: код предмета. Пробный ЕНТ: «math,physics» или '' — любая пара.
    target     TEXT NOT NULL DEFAULT '',
    count      INTEGER NOT NULL,
    for_all    INTEGER NOT NULL DEFAULT 1,  -- 1 — всем подтверждённым ученикам школы
    created_at REAL NOT NULL,
    deadline   REAL NOT NULL
);

-- Рекламные баннеры (свои, без JavaScript): картинка хранится в базе и попадает в резервные копии.
CREATE TABLE IF NOT EXISTS banners (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,            -- подпись (alt картинки) и название в админке
    link_url    TEXT NOT NULL,            -- куда ведёт баннер (http/https)
    image       BLOB NOT NULL,
    image_type  TEXT NOT NULL,            -- image/png, image/jpeg, image/gif, image/webp
    placements  TEXT NOT NULL,            -- места показа через запятую: landing,dashboard
    starts_on   TEXT NOT NULL,            -- ГГГГ-ММ-ДД, показывать с этого дня
    ends_on     TEXT NOT NULL,            -- ГГГГ-ММ-ДД, по этот день включительно
    active      INTEGER NOT NULL DEFAULT 1,
    impressions INTEGER NOT NULL DEFAULT 0,
    clicks      INTEGER NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL
);

-- Ученики, выбранные для задания (если for_all = 0).
CREATE TABLE IF NOT EXISTS assignment_students (
    assignment_id INTEGER NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (assignment_id, user_id)
);

-- Коды из писем: подтверждение почты (verify) и восстановление пароля (reset).
-- У пользователя не больше одного действующего кода каждого вида. Хранится только хеш.
CREATE TABLE IF NOT EXISTS email_codes (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose    TEXT NOT NULL CHECK (purpose IN ('verify', 'reset')),
    code_hash  TEXT NOT NULL,
    expires_at REAL NOT NULL,
    sent_at    REAL NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,  -- сколько раз ввели неверный код
    PRIMARY KEY (user_id, purpose)
);

-- Одноразовые ссылки входа из Telegram-бота. Хранится только SHA-256 от токена.
CREATE TABLE IF NOT EXISTS telegram_login_tokens (
    token_hash    TEXT PRIMARY KEY,
    telegram_id   INTEGER NOT NULL,
    telegram_name TEXT NOT NULL,
    expires_at    REAL NOT NULL,
    used_at       REAL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token TEXT NOT NULL,
    expires_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    subject      TEXT NOT NULL,
    qtype        TEXT NOT NULL,
    text         TEXT NOT NULL,
    context      TEXT NOT NULL DEFAULT '',
    options_json TEXT NOT NULL,
    left_json    TEXT NOT NULL DEFAULT '[]',
    correct_json TEXT NOT NULL,
    explanation  TEXT NOT NULL DEFAULT '',
    -- 1 — вопрос удалён в админке, но остаётся в базе, потому что есть в чьих-то попытках.
    -- Такой вопрос не попадает в новые тесты и в счётчики банка.
    deleted      INTEGER NOT NULL DEFAULT 0,
    -- 1 — вопрос создан или изменён в админке: seed.py его больше не перезаписывает.
    edited_by_admin INTEGER NOT NULL DEFAULT 0,
    -- Вопросы учителей проходят проверку: pending (на проверке), approved, rejected.
    -- В тесты и во все выборки банка попадают только approved.
    status         TEXT NOT NULL DEFAULT 'approved',
    author_id      INTEGER,                   -- учитель-автор (NULL — банк/админ)
    review_comment TEXT NOT NULL DEFAULT '',  -- комментарий администратора
    submitted_at   REAL,                      -- когда отправлен на проверку
    reviewed_at    REAL,                      -- когда проверен
    -- Тема по спецификации НЦТ: номер из app/topics.py («05»), '' — без темы.
    topic          TEXT NOT NULL DEFAULT '',
    UNIQUE (subject, text)
);

-- Уведомления (колокольчик в меню). Текст собирается при показе из kind + params_json,
-- чтобы его можно было показать на языке пользователя. dedup_key защищает от повторов
-- («до срока меньше суток» — один раз на ученика и задание).
CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    params_json TEXT NOT NULL DEFAULT '{}',
    link        TEXT NOT NULL DEFAULT '',   -- адрес страницы сайта («/dashboard»)
    created_at  REAL NOT NULL,
    read_at     REAL,                       -- NULL — не прочитано
    dedup_key   TEXT
);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, read_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_notifications_dedup ON notifications(user_id, dedup_key)
    WHERE dedup_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS attempts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mode          TEXT NOT NULL CHECK (mode IN ('mock', 'practice')),
    subjects_json TEXT NOT NULL,
    started_at    REAL NOT NULL,
    deadline      REAL,
    finished_at   REAL,
    status        TEXT NOT NULL DEFAULT 'in_progress'
                  CHECK (status IN ('in_progress', 'finished')),
    score         INTEGER NOT NULL DEFAULT 0,
    max_score     INTEGER NOT NULL DEFAULT 0,
    shortage_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS attempt_questions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id  INTEGER NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES questions(id),
    subject     TEXT NOT NULL,
    position    INTEGER NOT NULL,
    answer_json TEXT,
    points      INTEGER NOT NULL DEFAULT 0,
    -- Порядок вариантов, в котором их видит ученик: [индекс исходного варианта, ...].
    -- NULL — исходный порядок. Ответ ученика хранится в буквах ПОКАЗАННОГО порядка.
    option_order_json TEXT,
    -- Тренировка: 1 — ученик уже ответил на задание и увидел разбор.
    checked     INTEGER NOT NULL DEFAULT 0,
    UNIQUE (attempt_id, question_id)
);

CREATE INDEX IF NOT EXISTS idx_attempts_user ON attempts(user_id, status);
CREATE INDEX IF NOT EXISTS idx_attempt_questions_attempt ON attempt_questions(attempt_id);
CREATE INDEX IF NOT EXISTS idx_questions_subject ON questions(subject, qtype);
-- Для выбора «сначала невиденные вопросы»: сколько раз ученик видел вопрос.
CREATE INDEX IF NOT EXISTS idx_attempt_questions_question ON attempt_questions(question_id, attempt_id);
"""

# Колонки, добавленные после первой версии. init_db() добавляет их в старую базу,
# чтобы существующие пользователи и попытки сохранились.
_ADDED_COLUMNS = (
    ("users", "role", "TEXT NOT NULL DEFAULT 'user'"),
    ("users", "telegram_id", "INTEGER"),
    ("users", "phone", "TEXT"),
    ("users", "email_verified", "INTEGER NOT NULL DEFAULT 1"),
    ("users", "school_id", "INTEGER"),
    ("users", "school_status", "TEXT"),
    ("users", "last_login_at", "REAL"),
    ("users", "language", "TEXT NOT NULL DEFAULT 'ru'"),
    ("questions", "explanation", "TEXT NOT NULL DEFAULT ''"),
    ("questions", "deleted", "INTEGER NOT NULL DEFAULT 0"),
    ("questions", "edited_by_admin", "INTEGER NOT NULL DEFAULT 0"),
    ("questions", "status", "TEXT NOT NULL DEFAULT 'approved'"),
    ("questions", "author_id", "INTEGER"),
    ("questions", "review_comment", "TEXT NOT NULL DEFAULT ''"),
    ("questions", "submitted_at", "REAL"),
    ("questions", "reviewed_at", "REAL"),
    ("questions", "topic", "TEXT NOT NULL DEFAULT ''"),
    ("attempt_questions", "option_order_json", "TEXT"),
    ("attempt_questions", "checked", "INTEGER NOT NULL DEFAULT 0"),
)


# ── Классы данных, которые возвращают запросы ────────────────────────────────

@dataclass
class User:
    """Пользователь сайта (без пароля)."""

    id: int
    name: str
    login: str
    role: str = ROLE_USER
    email_verified: bool = True
    language: str = "ru"          # язык обучения: интерфейс и вопросы (ru / kk)

    @property
    def is_admin(self) -> bool:
        """True, если пользователь — главный администратор."""
        return self.role == ROLE_ADMIN

    @property
    def is_teacher(self) -> bool:
        """True, если пользователь — учитель (администратор своей школы)."""
        return self.role == ROLE_TEACHER


@dataclass
class Attempt:
    """Попытка прохождения теста: пробный ЕНТ или тренировка."""

    id: int
    user_id: int
    mode: str
    subjects: list[str]
    started_at: float
    deadline: float | None
    finished_at: float | None
    status: str
    score: int
    max_score: int
    shortage: list[dict]

    @property
    def is_finished(self) -> bool:
        """True, если попытка завершена и оценена."""
        return self.status == "finished"


@dataclass
class QuestionRef:
    """Вопрос из банка при сборке теста: id, тип и число вариантов ответа."""

    id: int
    qtype: str
    option_count: int


@dataclass
class AttemptQuestion:
    """Задание внутри попытки: сам вопрос + ответ ученика и полученные баллы."""

    id: int
    attempt_id: int
    question_id: int
    subject: str
    position: int
    qtype: str
    text: str
    context: str
    options: list[str]
    left: list[str]
    correct: list[str]
    answer: list[str] | None
    points: int
    explanation: str = ""
    checked: bool = False


# ── Подключение ──────────────────────────────────────────────────────────────

def configure(path: Path) -> None:
    """Задаёт другой файл базы данных (используется в тестах)."""
    global _db_path
    _db_path = Path(path)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Открывает соединение, фиксирует изменения при успехе и всегда закрывает его.

    Для каждого запроса создаётся своё соединение: сервер многопоточный,
    а соединение sqlite3 нельзя делить между потоками.
    """
    connection = sqlite3.connect(_db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    """Создаёт таблицы и индексы, если их ещё нет, и добавляет новые колонки в старую базу."""
    with connect() as connection:
        connection.executescript(SCHEMA)
        for table, column, definition in _ADDED_COLUMNS:
            existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                # Имена таблиц и колонок — константы этого модуля, не данные пользователя.
                try:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                except sqlite3.OperationalError as error:
                    # run.py запускает сайт и бота одновременно: оба видят старую базу,
                    # и колонку может успеть добавить второй процесс. Это не ошибка.
                    if "duplicate column name" not in str(error):
                        raise
        # Индекс создаётся после миграции: в старой базе колонки telegram_id ещё не было.
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram ON users(telegram_id) "
            "WHERE telegram_id IS NOT NULL"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone ON users(phone) "
            "WHERE phone IS NOT NULL"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_school ON users(school_id, school_status)"
        )


# ── Пользователи ─────────────────────────────────────────────────────────────

def create_user(
    name: str,
    login: str,
    password_hash: str,
    salt: str,
    created_at: float,
    phone: str | None = None,
    email_verified: bool = True,
) -> int:
    """Добавляет пользователя и возвращает его id.

    Если логин или телефон заняты, sqlite3 выбросит IntegrityError (ограничение UNIQUE).
    """
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO users (name, login, password_hash, salt, created_at, phone, email_verified) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, login, password_hash, salt, created_at, phone, int(email_verified)),
        )
        return int(cursor.lastrowid)


def update_unverified_user(
    user_id: int, name: str, phone: str | None, password_hash: str, salt: str
) -> bool:
    """Повторная регистрация на ту же почту до подтверждения: новые имя, телефон и пароль.

    False — аккаунт уже подтверждён (тогда его менять нельзя) или не найден.
    """
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE users SET name = ?, phone = ?, password_hash = ?, salt = ? "
            "WHERE id = ? AND email_verified = 0",
            (name, phone, password_hash, salt, user_id),
        )
        return cursor.rowcount == 1


def set_email_verified(user_id: int) -> None:
    """Отмечает почту пользователя подтверждённой."""
    with connect() as connection:
        connection.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (user_id,))


def set_password(user_id: int, password_hash: str, salt: str) -> None:
    """Меняет пароль и завершает все сессии пользователя (на всех устройствах)."""
    with connect() as connection:
        connection.execute(
            "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
            (password_hash, salt, user_id),
        )
        connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def set_user_role(login: str, role: str) -> bool:
    """Меняет роль пользователя по логину или телефону. False — такого пользователя нет."""
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE users SET role = ? WHERE id = "
            "(SELECT id FROM users WHERE login = ? OR phone = ? ORDER BY login = ? DESC LIMIT 1)",
            (role, login, login, login),
        )
        return cursor.rowcount == 1


# ── Коды из писем ────────────────────────────────────────────────────────────

def save_email_code(
    user_id: int, purpose: str, code_hash: str, expires_at: float, sent_at: float
) -> None:
    """Сохраняет новый код (прежний код того же вида перестаёт действовать)."""
    with connect() as connection:
        connection.execute(
            "INSERT INTO email_codes (user_id, purpose, code_hash, expires_at, sent_at, attempts) "
            "VALUES (?, ?, ?, ?, ?, 0) "
            "ON CONFLICT (user_id, purpose) DO UPDATE SET code_hash = excluded.code_hash, "
            "expires_at = excluded.expires_at, sent_at = excluded.sent_at, attempts = 0",
            (user_id, purpose, code_hash, expires_at, sent_at),
        )


def get_email_code(user_id: int, purpose: str) -> sqlite3.Row | None:
    """Код пользователя: хеш, срок, время отправки и число неверных попыток."""
    with connect() as connection:
        return connection.execute(
            "SELECT code_hash, expires_at, sent_at, attempts FROM email_codes "
            "WHERE user_id = ? AND purpose = ?",
            (user_id, purpose),
        ).fetchone()


def add_email_code_attempt(user_id: int, purpose: str) -> None:
    """Учитывает ещё одну неверную попытку ввода кода."""
    with connect() as connection:
        connection.execute(
            "UPDATE email_codes SET attempts = attempts + 1 WHERE user_id = ? AND purpose = ?",
            (user_id, purpose),
        )


def delete_email_code(user_id: int, purpose: str) -> None:
    """Удаляет код (он использован)."""
    with connect() as connection:
        connection.execute(
            "DELETE FROM email_codes WHERE user_id = ? AND purpose = ?", (user_id, purpose)
        )


# ── Telegram ─────────────────────────────────────────────────────────────────

def get_user_by_telegram(telegram_id: int) -> User | None:
    """Пользователь сайта, к которому привязан этот аккаунт Telegram."""
    with connect() as connection:
        row = connection.execute(
            "SELECT id, name, login, role, language FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
    return User(row["id"], row["name"], row["login"], row["role"], language=row["language"]) if row else None


def admin_telegram_ids() -> list[int]:
    """Telegram главных администраторов, привязавших аккаунт (для оповещений о сбоях)."""
    with connect() as connection:
        rows = connection.execute(
            "SELECT telegram_id FROM users WHERE role = ? AND telegram_id IS NOT NULL ORDER BY id",
            (ROLE_ADMIN,),
        ).fetchall()
    return [row["telegram_id"] for row in rows]


def get_user_language(user_id: int) -> str:
    """Язык пользователя (ru / kk); для неизвестного — ru."""
    with connect() as connection:
        row = connection.execute("SELECT language FROM users WHERE id = ?", (user_id,)).fetchone()
    return row["language"] if row is not None and row["language"] else "ru"


def set_user_language(user_id: int, language: str) -> None:
    """Меняет язык интерфейса и вопросов пользователя."""
    with connect() as connection:
        connection.execute("UPDATE users SET language = ? WHERE id = ?", (language, user_id))


def admin_credentials() -> list[sqlite3.Row]:
    """Логины и хеши паролей главных администраторов — для проверки на слабый пароль."""
    with connect() as connection:
        return connection.execute(
            "SELECT login, salt, password_hash FROM users WHERE role = ?", (ROLE_ADMIN,)
        ).fetchall()


def bind_telegram(user_id: int, telegram_id: int) -> None:
    """Привязывает Telegram к пользователю (и отвязывает его от прежнего аккаунта)."""
    with connect() as connection:
        connection.execute(
            "UPDATE users SET telegram_id = NULL WHERE telegram_id = ? AND id != ?",
            (telegram_id, user_id),
        )
        connection.execute("UPDATE users SET telegram_id = ? WHERE id = ?", (telegram_id, user_id))


def create_telegram_login_token(
    token_hash: str, telegram_id: int, telegram_name: str, expires_at: float
) -> None:
    """Сохраняет одноразовый токен входа из бота."""
    with connect() as connection:
        connection.execute(
            "INSERT INTO telegram_login_tokens "
            "(token_hash, telegram_id, telegram_name, expires_at) VALUES (?, ?, ?, ?)",
            (token_hash, telegram_id, telegram_name, expires_at),
        )


def get_telegram_login_token(token_hash: str, now: float) -> sqlite3.Row | None:
    """Действующий (не использованный и не просроченный) токен входа."""
    with connect() as connection:
        return connection.execute(
            "SELECT telegram_id, telegram_name FROM telegram_login_tokens "
            "WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?",
            (token_hash, now),
        ).fetchone()


def use_telegram_login_token(token_hash: str, now: float) -> bool:
    """Помечает токен использованным. False — он уже использован или просрочен."""
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE telegram_login_tokens SET used_at = ? "
            "WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?",
            (now, token_hash, now),
        )
        # Заодно чистим старые токены, чтобы таблица не росла.
        connection.execute(
            "DELETE FROM telegram_login_tokens WHERE expires_at < ?", (now - 24 * 60 * 60,)
        )
        return cursor.rowcount == 1


def get_user(user_id: int) -> sqlite3.Row | None:
    """Пользователь по id (без пароля) — для админки."""
    with connect() as connection:
        return connection.execute(
            "SELECT id, name, login, role, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()


def list_users_with_stats() -> list[sqlite3.Row]:
    """Все пользователи со сводкой попыток (для админки), новые сверху."""
    with connect() as connection:
        return connection.execute(
            "SELECT u.id, u.name, u.login, u.role, u.created_at, u.phone, u.email_verified, "
            "COUNT(a.id) AS attempts, "
            "SUM(a.mode = 'mock') AS mocks, "
            "MAX(CASE WHEN a.mode = 'mock' THEN a.score END) AS best_mock, "
            "MAX(a.finished_at) AS last_finished "
            "FROM users u LEFT JOIN attempts a ON a.user_id = u.id AND a.status = 'finished' "
            "GROUP BY u.id ORDER BY u.id DESC"
        ).fetchall()


def site_stats() -> sqlite3.Row:
    """Общая статистика сайта: пользователи, завершённые попытки и средние результаты."""
    with connect() as connection:
        return connection.execute(
            "SELECT (SELECT COUNT(*) FROM users) AS users, "
            "(SELECT COUNT(*) FROM users WHERE role = 'admin') AS admins, "
            "COUNT(*) AS attempts, "
            "COALESCE(SUM(mode = 'mock'), 0) AS mocks, "
            "COALESCE(SUM(mode = 'practice'), 0) AS practices, "
            "AVG(CASE WHEN mode = 'mock' THEN score END) AS avg_mock_score, "
            "AVG(CASE WHEN max_score > 0 THEN score * 100.0 / max_score END) AS avg_percent "
            "FROM attempts WHERE status = 'finished'"
        ).fetchone()


def login_exists(login: str) -> bool:
    """Проверяет, зарегистрирован ли уже такой логин (почта или телефон)."""
    with connect() as connection:
        row = connection.execute("SELECT 1 FROM users WHERE login = ?", (login,)).fetchone()
        return row is not None


def phone_taken(phone: str, except_user_id: int = 0) -> bool:
    """Телефон уже есть у другого аккаунта: как логин (старые аккаунты) или в профиле."""
    with connect() as connection:
        row = connection.execute(
            "SELECT 1 FROM users WHERE (login = ? OR phone = ?) AND id != ?",
            (phone, phone, except_user_id),
        ).fetchone()
        return row is not None


def get_user_credentials(login: str) -> sqlite3.Row | None:
    """Данные для проверки пароля: id, имя, логин, роль, подтверждена ли почта, хеш и соль.

    Искать можно по логину (почта, старый телефонный логин, tg…) или по телефону из профиля.
    """
    with connect() as connection:
        return connection.execute(
            "SELECT id, name, login, role, email_verified, password_hash, salt, language FROM users "
            "WHERE login = ? OR phone = ? ORDER BY login = ? DESC LIMIT 1",
            (login, login, login),
        ).fetchone()


# ── Сессии ───────────────────────────────────────────────────────────────────

def create_session(
    token_hash: str, user_id: int, csrf_token: str, expires_at: float, now: float | None = None
) -> None:
    """Сохраняет новую сессию (в базе только хеш токена) и время входа пользователя."""
    with connect() as connection:
        connection.execute(
            "INSERT INTO sessions (token_hash, user_id, csrf_token, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (token_hash, user_id, csrf_token, expires_at),
        )
        if now is not None:
            connection.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, user_id))


def get_session_user(token_hash: str, now: float) -> tuple[User, str] | None:
    """Находит пользователя по хешу токена сессии. Возвращает (пользователь, csrf-токен)."""
    with connect() as connection:
        row = connection.execute(
            "SELECT u.id, u.name, u.login, u.role, u.language, s.csrf_token "
            "FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ? AND s.expires_at > ?",
            (token_hash, now),
        ).fetchone()
    if row is None:
        return None
    return (User(row["id"], row["name"], row["login"], row["role"], language=row["language"]),
            row["csrf_token"])


def delete_session(token_hash: str) -> None:
    """Удаляет сессию (выход из аккаунта)."""
    with connect() as connection:
        connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))


def delete_expired_sessions(now: float) -> None:
    """Удаляет все просроченные сессии."""
    with connect() as connection:
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))


# ── Банк вопросов ────────────────────────────────────────────────────────────

_UPSERT_SQL = (
    "INSERT INTO questions "
    "(subject, qtype, text, context, options_json, left_json, correct_json, explanation, topic) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT (subject, text) DO UPDATE SET topic = excluded.topic, "
    "qtype = excluded.qtype, context = excluded.context, "
    "options_json = excluded.options_json, left_json = excluded.left_json, "
    "correct_json = excluded.correct_json, explanation = excluded.explanation, "
    "deleted = 0 "
    # Вопросы, исправленные в админке, и вопросы учителей не трогаем:
    # ручная правка важнее файла.
    "WHERE questions.edited_by_admin = 0 AND questions.author_id IS NULL"
)


def _upsert_values(subject: str, question: dict) -> tuple:
    """Значения для _UPSERT_SQL из вопроса в формате data/questions/*.json."""
    return (
        subject,
        question["type"],
        question["text"].strip(),
        question.get("context", "").strip(),
        json.dumps(question["options"], ensure_ascii=False),
        json.dumps(question.get("left", []), ensure_ascii=False),
        json.dumps(question["correct"]),
        question.get("explanation", "").strip(),
        question.get("topic", ""),
    )


def upsert_question(
    subject: str,
    qtype: str,
    text: str,
    context: str,
    options: list[str],
    left: list[str],
    correct: list[str],
    explanation: str = "",
    topic: str = "",
) -> None:
    """Добавляет вопрос или обновляет существующий с тем же предметом и текстом.

    Благодаря этому seed.py можно запускать повторно: исправления в JSON
    попадут в базу, а дубликаты не появятся.
    """
    question = {"type": qtype, "text": text, "context": context, "options": options,
                "left": left, "correct": correct, "explanation": explanation, "topic": topic}
    with connect() as connection:
        connection.execute(_UPSERT_SQL, _upsert_values(subject, question))


def upsert_questions(subject: str, questions: list[dict]) -> None:
    """То же, что upsert_question, но для многих вопросов в одной транзакции.

    Тысячи сгенерированных вопросов так загружаются за секунды, а не минуты.
    """
    with connect() as connection:
        connection.executemany(_UPSERT_SQL, [_upsert_values(subject, q) for q in questions])


@dataclass
class Question:
    """Вопрос банка в исходном виде (для админки)."""

    id: int
    subject: str
    qtype: str
    text: str
    context: str
    options: list[str]
    left: list[str]
    correct: list[str]
    explanation: str
    used: int = 0  # в скольких попытках встречался
    topic: str = ""  # номер темы спецификации (app/topics.py)
    status: str = Q_APPROVED
    author_id: int | None = None
    review_comment: str = ""
    submitted_at: float | None = None


_QUESTION_COLUMNS = (
    "q.id, q.subject, q.qtype, q.text, q.context, q.options_json, q.left_json, "
    "q.correct_json, q.explanation, q.topic, q.status, q.author_id, q.review_comment, q.submitted_at, "
    "(SELECT COUNT(*) FROM attempt_questions aq WHERE aq.question_id = q.id) AS used"
)


def _question_from_row(row: sqlite3.Row) -> Question:
    """Строка таблицы questions → Question."""
    return Question(
        id=row["id"],
        subject=row["subject"],
        qtype=row["qtype"],
        text=row["text"],
        context=row["context"],
        options=json.loads(row["options_json"]),
        left=json.loads(row["left_json"]),
        correct=json.loads(row["correct_json"]),
        explanation=row["explanation"],
        used=row["used"],
        topic=row["topic"],
        status=row["status"],
        author_id=row["author_id"],
        review_comment=row["review_comment"],
        submitted_at=row["submitted_at"],
    )


def list_questions(subject: str | None = None) -> list[Question]:
    """Действующие (не удалённые и одобренные) вопросы банка, по предмету или все; новые сверху."""
    with connect() as connection:
        if subject is None:
            rows = connection.execute(
                f"SELECT {_QUESTION_COLUMNS} FROM questions q "
                "WHERE q.deleted = 0 AND q.status = 'approved' ORDER BY q.id DESC"
            ).fetchall()
        else:
            rows = connection.execute(
                f"SELECT {_QUESTION_COLUMNS} FROM questions q "
                "WHERE q.deleted = 0 AND q.status = 'approved' AND q.subject = ? "
                "ORDER BY q.id DESC",
                (subject,),
            ).fetchall()
    return [_question_from_row(row) for row in rows]


def get_question(question_id: int) -> Question | None:
    """Действующий (не удалённый и одобренный) вопрос банка по id."""
    with connect() as connection:
        row = connection.execute(
            f"SELECT {_QUESTION_COLUMNS} FROM questions q "
            "WHERE q.id = ? AND q.deleted = 0 AND q.status = 'approved'",
            (question_id,),
        ).fetchone()
    return _question_from_row(row) if row else None


def _question_values(question: Question) -> tuple:
    """Значения колонок вопроса для INSERT/UPDATE."""
    return (
        question.subject,
        question.qtype,
        question.text,
        question.context,
        json.dumps(question.options, ensure_ascii=False),
        json.dumps(question.left, ensure_ascii=False),
        json.dumps(question.correct),
        question.explanation,
        question.topic,
    )


def insert_question(question: Question) -> int:
    """Добавляет вопрос из админки (с пометкой edited_by_admin) и возвращает его id.

    Если у предмета уже есть вопрос с таким текстом, sqlite3 выбросит IntegrityError.
    """
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO questions "
            "(subject, qtype, text, context, options_json, left_json, correct_json, explanation, "
            "topic, edited_by_admin) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
            _question_values(question),
        )
        return int(cursor.lastrowid)


def update_question(question: Question) -> bool:
    """Сохраняет правку из админки и помечает вопрос edited_by_admin (seed.py его не тронет).

    False — вопроса нет. Дубликат текста — IntegrityError.
    """
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE questions SET subject = ?, qtype = ?, text = ?, context = ?, "
            "options_json = ?, left_json = ?, correct_json = ?, explanation = ?, topic = ?, "
            "edited_by_admin = 1 WHERE id = ? AND deleted = 0 AND status = 'approved'",
            (*_question_values(question), question.id),
        )
        return cursor.rowcount == 1


def delete_question(question_id: int) -> str:
    """Удаляет вопрос из банка.

    Если вопрос уже был в чьих-то попытках, он только помечается удалённым,
    чтобы разбор старых попыток продолжал работать. Возвращает
    "deleted", "archived" или "missing".
    """
    with connect() as connection:
        row = connection.execute(
            "SELECT (SELECT COUNT(*) FROM attempt_questions WHERE question_id = q.id) AS used "
            "FROM questions q WHERE q.id = ? AND q.deleted = 0 AND q.status = 'approved'",
            (question_id,),
        ).fetchone()
        if row is None:
            return "missing"
        if row["used"]:
            connection.execute("UPDATE questions SET deleted = 1 WHERE id = ?", (question_id,))
            return "archived"
        connection.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        return "deleted"


# ── Вопросы учителей и проверка ──────────────────────────────────────────────

def insert_teacher_question(question: Question, author_id: int, now: float) -> int:
    """Вопрос учителя: сохраняется со статусом «на проверке» и в тесты не попадает.

    Дубликат текста в предмете — IntegrityError.
    """
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO questions "
            "(subject, qtype, text, context, options_json, left_json, correct_json, explanation, "
            "topic, status, author_id, submitted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (*_question_values(question), Q_PENDING, author_id, now),
        )
        return int(cursor.lastrowid)


def list_author_questions(author_id: int) -> list[Question]:
    """Все вопросы учителя (любой статус), новые сверху."""
    with connect() as connection:
        rows = connection.execute(
            f"SELECT {_QUESTION_COLUMNS} FROM questions q "
            "WHERE q.author_id = ? AND q.deleted = 0 ORDER BY q.id DESC",
            (author_id,),
        ).fetchall()
    return [_question_from_row(row) for row in rows]


def get_author_question(question_id: int, author_id: int) -> Question | None:
    """Вопрос учителя — только если он автор."""
    with connect() as connection:
        row = connection.execute(
            f"SELECT {_QUESTION_COLUMNS} FROM questions q "
            "WHERE q.id = ? AND q.author_id = ? AND q.deleted = 0",
            (question_id, author_id),
        ).fetchone()
    return _question_from_row(row) if row else None


def resubmit_author_question(question: Question, author_id: int, now: float) -> bool:
    """Учитель исправил вопрос на проверке или отклонённый — он снова уходит на проверку.

    Одобренный вопрос учитель изменить не может (False). Дубликат текста — IntegrityError.
    """
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE questions SET subject = ?, qtype = ?, text = ?, context = ?, "
            "options_json = ?, left_json = ?, correct_json = ?, explanation = ?, topic = ?, "
            "status = 'pending', review_comment = '', submitted_at = ?, reviewed_at = NULL "
            "WHERE id = ? AND author_id = ? AND deleted = 0 AND status != 'approved'",
            (*_question_values(question), now, question.id, author_id),
        )
        return cursor.rowcount == 1


def delete_author_question(question_id: int, author_id: int) -> bool:
    """Учитель удаляет свой вопрос на проверке или отклонённый (в тестах он не был)."""
    with connect() as connection:
        cursor = connection.execute(
            "DELETE FROM questions WHERE id = ? AND author_id = ? AND status != 'approved' "
            "AND NOT EXISTS (SELECT 1 FROM attempt_questions WHERE question_id = questions.id)",
            (question_id, author_id),
        )
        return cursor.rowcount == 1


def list_pending_questions() -> list[tuple[Question, sqlite3.Row]]:
    """Очередь проверки: вопросы на проверке (старые сверху) и их авторы со школами."""
    with connect() as connection:
        rows = connection.execute(
            f"SELECT {_QUESTION_COLUMNS}, u.name AS author_name, u.login AS author_login, "
            "s.city AS school_city, s.name AS school_name "
            "FROM questions q LEFT JOIN users u ON u.id = q.author_id "
            "LEFT JOIN schools s ON s.id = u.school_id "
            "WHERE q.status = 'pending' AND q.deleted = 0 ORDER BY q.submitted_at, q.id"
        ).fetchall()
    return [(_question_from_row(row), row) for row in rows]


def count_pending_questions() -> int:
    """Сколько вопросов ждут проверки."""
    with connect() as connection:
        return connection.execute(
            "SELECT COUNT(*) FROM questions WHERE status = 'pending' AND deleted = 0"
        ).fetchone()[0]


def get_pending_question(question_id: int) -> Question | None:
    """Вопрос из очереди проверки."""
    with connect() as connection:
        row = connection.execute(
            f"SELECT {_QUESTION_COLUMNS} FROM questions q "
            "WHERE q.id = ? AND q.status = 'pending' AND q.deleted = 0",
            (question_id,),
        ).fetchone()
    return _question_from_row(row) if row else None


def review_question(question_id: int, status: str, comment: str, now: float) -> bool:
    """Одобряет (approved) или отклоняет (rejected) вопрос на проверке. False — его нет."""
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE questions SET status = ?, review_comment = ?, reviewed_at = ? "
            "WHERE id = ? AND status = 'pending' AND deleted = 0",
            (status, comment, now, question_id),
        )
        return cursor.rowcount == 1


def approve_with_changes(question: Question, comment: str, now: float) -> bool:
    """Администратор исправляет вопрос на проверке и сразу одобряет его.

    Вопрос помечается edited_by_admin. Дубликат текста — IntegrityError.
    """
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE questions SET subject = ?, qtype = ?, text = ?, context = ?, "
            "options_json = ?, left_json = ?, correct_json = ?, explanation = ?, topic = ?, "
            "edited_by_admin = 1, status = 'approved', review_comment = ?, reviewed_at = ? "
            "WHERE id = ? AND status = 'pending' AND deleted = 0",
            (*_question_values(question), comment, now, question.id),
        )
        return cursor.rowcount == 1


def retire_untagged_questions() -> int:
    """Помечает удалёнными вопросы банка без темы (кроме вопросов из админки и от учителей).

    Возвращает, сколько вопросов убрано. Используется seed.py после полной загрузки.
    """
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE questions SET deleted = 1 WHERE topic = '' AND deleted = 0 "
            "AND author_id IS NULL AND edited_by_admin = 0"
        )
        return cursor.rowcount


def topic_counts() -> dict[tuple[str, str], int]:
    """Сколько вопросов банка (одобренных, не удалённых) на каждую тему: {(предмет, тема): n}."""
    with connect() as connection:
        rows = connection.execute(
            "SELECT subject, topic, COUNT(*) AS n FROM questions "
            "WHERE deleted = 0 AND status = 'approved' GROUP BY subject, topic"
        ).fetchall()
    return {(row["subject"], row["topic"]): row["n"] for row in rows}


def get_topic_results(user_id: int) -> list[sqlite3.Row]:
    """Итоги ученика по темам во всех завершённых попытках: предмет, тема, тип, число, баллы."""
    with connect() as connection:
        return connection.execute(
            "SELECT aq.subject, q.topic, q.qtype, COUNT(*) AS n, SUM(aq.points) AS points "
            "FROM attempt_questions aq "
            "JOIN attempts a ON a.id = aq.attempt_id "
            "JOIN questions q ON q.id = aq.question_id "
            "WHERE a.user_id = ? AND a.status = 'finished' AND q.topic != '' "
            "GROUP BY aq.subject, q.topic, q.qtype",
            (user_id,),
        ).fetchall()


def question_counts() -> dict[tuple[str, str], int]:
    """Сколько вопросов в банке: словарь {(предмет, тип): количество}."""
    with connect() as connection:
        rows = connection.execute(
            "SELECT subject, qtype, COUNT(*) AS n FROM questions "
            "WHERE deleted = 0 AND status = 'approved' GROUP BY subject, qtype"
        ).fetchall()
    return {(row["subject"], row["qtype"]): row["n"] for row in rows}


def random_questions(
    subject: str, qtype: str | None, limit: int, user_id: int | None = None
) -> list[QuestionRef]:
    """Возвращает до limit случайных вопросов предмета.

    Если qtype указан, выбираются только вопросы этого типа.
    Если указан user_id, сначала идут вопросы, которые ученик ещё не видел,
    затем те, что встречались реже всего, — так повторы появляются только
    когда новые вопросы закончились.
    """
    seen_order = ""
    params: list = [subject]
    if user_id is not None:
        seen_order = (
            "(SELECT COUNT(*) FROM attempt_questions aq "
            "JOIN attempts a ON a.id = aq.attempt_id "
            "WHERE a.user_id = ? AND aq.question_id = q.id), "
        )
    type_filter = ""
    if qtype is not None:
        type_filter = "AND q.qtype = ? "
        params.append(qtype)
    if user_id is not None:
        params.append(user_id)
    params.append(limit)
    with connect() as connection:
        rows = connection.execute(
            "SELECT q.id, q.qtype, q.options_json FROM questions q "
            f"WHERE q.subject = ? AND q.deleted = 0 AND q.status = 'approved' {type_filter}"
            f"ORDER BY {seen_order}RANDOM() LIMIT ?",
            params,
        ).fetchall()
    return [
        QuestionRef(row["id"], row["qtype"], len(json.loads(row["options_json"])))
        for row in rows
    ]


# ── Попытки ──────────────────────────────────────────────────────────────────

_ATTEMPT_COLUMNS = (
    "id, user_id, mode, subjects_json, started_at, deadline, finished_at, "
    "status, score, max_score, shortage_json"
)


def _attempt_from_row(row: sqlite3.Row) -> Attempt:
    """Превращает строку таблицы attempts в объект Attempt."""
    return Attempt(
        id=row["id"],
        user_id=row["user_id"],
        mode=row["mode"],
        subjects=json.loads(row["subjects_json"]),
        started_at=row["started_at"],
        deadline=row["deadline"],
        finished_at=row["finished_at"],
        status=row["status"],
        score=row["score"],
        max_score=row["max_score"],
        shortage=json.loads(row["shortage_json"]),
    )


def create_attempt(
    user_id: int,
    mode: str,
    subjects: list[str],
    started_at: float,
    deadline: float | None,
    max_score: int,
    shortage: list[dict],
    questions: list[tuple[int, str, list[int]]],
) -> int:
    """Создаёт попытку вместе со всеми её заданиями в одной транзакции.

    questions — список (id вопроса, код предмета, порядок вариантов) в нужном порядке.
    """
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO attempts "
            "(user_id, mode, subjects_json, started_at, deadline, max_score, shortage_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                mode,
                json.dumps(subjects),
                started_at,
                deadline,
                max_score,
                json.dumps(shortage, ensure_ascii=False),
            ),
        )
        attempt_id = int(cursor.lastrowid)
        connection.executemany(
            "INSERT INTO attempt_questions "
            "(attempt_id, question_id, subject, position, option_order_json) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (attempt_id, question_id, subject, position, json.dumps(order))
                for position, (question_id, subject, order) in enumerate(questions, start=1)
            ],
        )
    return attempt_id


def get_attempt(attempt_id: int, user_id: int) -> Attempt | None:
    """Возвращает попытку, только если она принадлежит этому пользователю."""
    with connect() as connection:
        row = connection.execute(
            f"SELECT {_ATTEMPT_COLUMNS} FROM attempts WHERE id = ? AND user_id = ?",
            (attempt_id, user_id),
        ).fetchone()
    return _attempt_from_row(row) if row else None


def get_in_progress_attempt(user_id: int, mode: str) -> Attempt | None:
    """Возвращает последнюю незавершённую попытку пользователя в данном режиме."""
    with connect() as connection:
        row = connection.execute(
            f"SELECT {_ATTEMPT_COLUMNS} FROM attempts "
            "WHERE user_id = ? AND mode = ? AND status = 'in_progress' "
            "ORDER BY id DESC LIMIT 1",
            (user_id, mode),
        ).fetchone()
    return _attempt_from_row(row) if row else None


def get_expired_attempt_ids(user_id: int, now: float) -> list[int]:
    """Возвращает id незавершённых попыток пользователя, у которых вышло время."""
    with connect() as connection:
        rows = connection.execute(
            "SELECT id FROM attempts WHERE user_id = ? AND status = 'in_progress' "
            "AND deadline IS NOT NULL AND deadline <= ?",
            (user_id, now),
        ).fetchall()
    return [row["id"] for row in rows]


def get_finished_attempts(user_id: int) -> list[Attempt]:
    """Все завершённые попытки пользователя, новые сверху."""
    with connect() as connection:
        rows = connection.execute(
            f"SELECT {_ATTEMPT_COLUMNS} FROM attempts "
            "WHERE user_id = ? AND status = 'finished' ORDER BY finished_at DESC, id DESC",
            (user_id,),
        ).fetchall()
    return [_attempt_from_row(row) for row in rows]


def _apply_option_order(
    options: list[str], correct: list[str], qtype: str, order_json: str | None
) -> tuple[list[str], list[str]]:
    """Переставляет варианты в показанный ученику порядок и пересчитывает буквы ответа.

    order[i] — индекс исходного варианта, который показан под буквой номер i.
    Битый или устаревший порядок игнорируется — тогда остаётся исходный.
    """
    order = json.loads(order_json) if order_json else None
    if not isinstance(order, list) or sorted(order) != list(range(len(options))):
        return options, correct
    letters = config.OPTION_LETTERS
    new_letter = {letters[original]: letters[shown] for shown, original in enumerate(order)}
    shown_options = [options[original] for original in order]
    shown_correct = [new_letter.get(letter, letter) for letter in correct]
    if qtype != config.MATCHING:
        # Для соответствия порядок букв важен (по строкам), для остальных — нет.
        shown_correct.sort()
    return shown_options, shown_correct


def get_attempt_questions(attempt_id: int) -> list[AttemptQuestion]:
    """Все задания попытки в порядке их следования, вместе с текстом вопросов.

    Варианты ответа и правильные буквы уже приведены к порядку, который видит ученик.
    """
    with connect() as connection:
        rows = connection.execute(
            "SELECT aq.id, aq.attempt_id, aq.question_id, aq.subject, aq.position, "
            "aq.answer_json, aq.points, aq.option_order_json, aq.checked, "
            "q.qtype, q.text, q.context, q.options_json, q.left_json, q.correct_json, "
            "q.explanation "
            "FROM attempt_questions aq JOIN questions q ON q.id = aq.question_id "
            "WHERE aq.attempt_id = ? ORDER BY aq.position",
            (attempt_id,),
        ).fetchall()
    result = []
    for row in rows:
        options, correct = _apply_option_order(
            json.loads(row["options_json"]),
            json.loads(row["correct_json"]),
            row["qtype"],
            row["option_order_json"],
        )
        result.append(AttemptQuestion(
            id=row["id"],
            attempt_id=row["attempt_id"],
            question_id=row["question_id"],
            subject=row["subject"],
            position=row["position"],
            qtype=row["qtype"],
            text=row["text"],
            context=row["context"],
            options=options,
            left=json.loads(row["left_json"]),
            correct=correct,
            answer=json.loads(row["answer_json"]) if row["answer_json"] else None,
            points=row["points"],
            explanation=row["explanation"],
            checked=bool(row["checked"]),
        ))
    return result


def save_answers(attempt_id: int, answers: dict[int, list[str] | None]) -> None:
    """Сохраняет ответы раздела: {id задания попытки: ответ или None}.

    Условие status = 'in_progress' не даёт изменить ответы завершённого теста.
    """
    with connect() as connection:
        connection.executemany(
            "UPDATE attempt_questions SET answer_json = ? "
            "WHERE id = ? AND attempt_id = ? AND attempt_id IN "
            "(SELECT id FROM attempts WHERE status = 'in_progress')",
            [
                (json.dumps(answer) if answer is not None else None, aq_id, attempt_id)
                for aq_id, answer in answers.items()
            ],
        )


def check_question(attempt_id: int, aq_id: int, answer: list[str] | None, points: int) -> bool:
    """Тренировка: сохраняет ответ на одно задание, его баллы и отметку «проверено».

    Ответ на уже проверенное задание или в завершённой попытке не меняется
    (возвращается False) — повторная отправка формы ничего не испортит.
    """
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE attempt_questions SET answer_json = ?, points = ?, checked = 1 "
            "WHERE id = ? AND attempt_id = ? AND checked = 0 AND attempt_id IN "
            "(SELECT id FROM attempts WHERE status = 'in_progress')",
            (json.dumps(answer) if answer is not None else None, points, aq_id, attempt_id),
        )
        return cursor.rowcount == 1


def get_subject_results(user_id: int) -> list[sqlite3.Row]:
    """Итоги пользователя по всем завершённым попыткам: предмет, тип, число заданий, баллы."""
    with connect() as connection:
        return connection.execute(
            "SELECT aq.subject, q.qtype, COUNT(*) AS n, SUM(aq.points) AS points "
            "FROM attempt_questions aq "
            "JOIN attempts a ON a.id = aq.attempt_id "
            "JOIN questions q ON q.id = aq.question_id "
            "WHERE a.user_id = ? AND a.status = 'finished' "
            "GROUP BY aq.subject, q.qtype",
            (user_id,),
        ).fetchall()


def complete_attempt(
    attempt_id: int, points: dict[int, int], score: int, finished_at: float
) -> bool:
    """Записывает баллы за задания и завершает попытку.

    Возвращает False, если попытка уже была завершена (например, в соседнем запросе).
    """
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE attempts SET status = 'finished', score = ?, finished_at = ? "
            "WHERE id = ? AND status = 'in_progress'",
            (score, finished_at, attempt_id),
        )
        if cursor.rowcount == 0:
            return False
        connection.executemany(
            "UPDATE attempt_questions SET points = ? WHERE id = ? AND attempt_id = ?",
            [(value, aq_id, attempt_id) for aq_id, value in points.items()],
        )
    return True


# ── Школы ────────────────────────────────────────────────────────────────────

def get_or_create_school(city: str, name: str, key: str, now: float) -> int:
    """id школы с таким ключом; если её нет — создаёт (дубликатов не бывает: key UNIQUE)."""
    with connect() as connection:
        connection.execute(
            "INSERT INTO schools (city, name, key, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (key) DO NOTHING",
            (city, name, key, now),
        )
        row = connection.execute("SELECT id FROM schools WHERE key = ?", (key,)).fetchone()
        return int(row["id"])


def get_school(school_id: int) -> sqlite3.Row | None:
    """Школа по id: id, city, name."""
    with connect() as connection:
        return connection.execute(
            "SELECT id, city, name FROM schools WHERE id = ?", (school_id,)
        ).fetchone()


def list_schools() -> list[sqlite3.Row]:
    """Все школы со счётчиками учеников, заявок и учителей (для главного администратора)."""
    with connect() as connection:
        return connection.execute(
            "SELECT s.id, s.city, s.name, "
            "SUM(u.role != 'teacher' AND u.school_status = 'approved') AS students, "
            "SUM(u.role != 'teacher' AND u.school_status = 'pending') AS pending, "
            "SUM(u.role = 'teacher') AS teachers "
            "FROM schools s LEFT JOIN users u ON u.school_id = s.id "
            "GROUP BY s.id ORDER BY s.city, s.name"
        ).fetchall()


def get_user_school(user_id: int) -> sqlite3.Row | None:
    """Школа пользователя и его статус в ней: school_id, school_status, role, city, name."""
    with connect() as connection:
        return connection.execute(
            "SELECT u.school_id, u.school_status, u.role, s.city, s.name "
            "FROM users u JOIN schools s ON s.id = u.school_id WHERE u.id = ?",
            (user_id,),
        ).fetchone()


def set_user_school(user_id: int, school_id: int | None, status: str | None) -> None:
    """Записывает ученика в школу с заданным статусом (None, None — без школы).

    Учителя так не меняются: их школу назначает главный администратор.
    """
    with connect() as connection:
        connection.execute(
            "UPDATE users SET school_id = ?, school_status = ? WHERE id = ? AND role != 'teacher'",
            (school_id, status, user_id),
        )


def set_member_status(school_id: int, user_id: int, status: str | None) -> bool:
    """Учитель подтверждает, отклоняет (rejected) или исключает (None) ученика своей школы.

    False — такого ученика в этой школе нет.
    """
    with connect() as connection:
        if status is None:
            cursor = connection.execute(
                "UPDATE users SET school_id = NULL, school_status = NULL "
                "WHERE id = ? AND school_id = ? AND role != 'teacher'",
                (user_id, school_id),
            )
        else:
            cursor = connection.execute(
                "UPDATE users SET school_status = ? "
                "WHERE id = ? AND school_id = ? AND role != 'teacher' AND school_status IS NOT NULL",
                (status, user_id, school_id),
            )
        return cursor.rowcount == 1


def make_teacher(login: str, school_id: int) -> bool:
    """Назначает пользователя (по логину или телефону) учителем школы. False — не найден."""
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE users SET role = ?, school_id = ?, school_status = ? WHERE id = "
            "(SELECT id FROM users WHERE login = ? OR phone = ? ORDER BY login = ? DESC LIMIT 1)",
            (ROLE_TEACHER, school_id, SCHOOL_APPROVED, login, login, login),
        )
        return cursor.rowcount == 1


def revoke_role(login: str) -> bool:
    """Снимает роль администратора или учителя (учитель при этом уходит из школы)."""
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE users SET "
            "school_id = CASE WHEN role = 'teacher' THEN NULL ELSE school_id END, "
            "school_status = CASE WHEN role = 'teacher' THEN NULL ELSE school_status END, "
            "role = 'user' WHERE id = "
            "(SELECT id FROM users WHERE login = ? OR phone = ? ORDER BY login = ? DESC LIMIT 1)",
            (login, login, login),
        )
        return cursor.rowcount == 1


def list_school_members(school_id: int, status: str) -> list[sqlite3.Row]:
    """Ученики школы с этим статусом и сводкой их завершённых попыток.

    mocks/practices — число пробных и тренировок, avg_mock/best_mock — средний и лучший
    балл пробного ЕНТ, avg_percent — средний процент по всем попыткам.
    """
    with connect() as connection:
        return connection.execute(
            "SELECT u.id, u.name, u.login, u.phone, u.created_at, u.last_login_at, "
            "COALESCE(SUM(a.mode = 'mock'), 0) AS mocks, "
            "COALESCE(SUM(a.mode = 'practice'), 0) AS practices, "
            "AVG(CASE WHEN a.mode = 'mock' THEN a.score END) AS avg_mock, "
            "MAX(CASE WHEN a.mode = 'mock' THEN a.score END) AS best_mock, "
            "AVG(CASE WHEN a.max_score > 0 THEN a.score * 100.0 / a.max_score END) AS avg_percent "
            "FROM users u LEFT JOIN attempts a ON a.user_id = u.id AND a.status = 'finished' "
            "WHERE u.school_id = ? AND u.school_status = ? AND u.role != 'teacher' "
            "GROUP BY u.id ORDER BY u.name COLLATE NOCASE, u.id",
            (school_id, status),
        ).fetchall()


def get_school_student(school_id: int, user_id: int) -> sqlite3.Row | None:
    """Подтверждённый ученик этой школы (id, name, login, phone, created_at, last_login_at)."""
    with connect() as connection:
        return connection.execute(
            "SELECT id, name, login, phone, created_at, last_login_at FROM users "
            "WHERE id = ? AND school_id = ? AND school_status = 'approved' AND role != 'teacher'",
            (user_id, school_id),
        ).fetchone()


# ── Задания учителя ──────────────────────────────────────────────────────────

_ASSIGNMENT_COLUMNS = (
    "id, school_id, created_by, mode, target, count, for_all, created_at, deadline"
)


def create_assignment(
    school_id: int, created_by: int, mode: str, target: str, count: int,
    created_at: float, deadline: float, student_ids: list[int] | None,
) -> int:
    """Создаёт задание. student_ids = None — для всех учеников школы."""
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO assignments "
            "(school_id, created_by, mode, target, count, for_all, created_at, deadline) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (school_id, created_by, mode, target, count, int(student_ids is None),
             created_at, deadline),
        )
        assignment_id = int(cursor.lastrowid)
        connection.executemany(
            "INSERT OR IGNORE INTO assignment_students (assignment_id, user_id) VALUES (?, ?)",
            [(assignment_id, user_id) for user_id in student_ids or []],
        )
        return assignment_id


def list_assignments(school_id: int) -> list[sqlite3.Row]:
    """Задания школы, новые сверху."""
    with connect() as connection:
        return connection.execute(
            f"SELECT {_ASSIGNMENT_COLUMNS} FROM assignments WHERE school_id = ? "
            "ORDER BY created_at DESC, id DESC",
            (school_id,),
        ).fetchall()


def get_assignment(assignment_id: int, school_id: int) -> sqlite3.Row | None:
    """Задание, только если оно принадлежит этой школе."""
    with connect() as connection:
        return connection.execute(
            f"SELECT {_ASSIGNMENT_COLUMNS} FROM assignments WHERE id = ? AND school_id = ?",
            (assignment_id, school_id),
        ).fetchone()


def delete_assignment(assignment_id: int, school_id: int) -> bool:
    """Удаляет задание своей школы. False — его нет."""
    with connect() as connection:
        cursor = connection.execute(
            "DELETE FROM assignments WHERE id = ? AND school_id = ?", (assignment_id, school_id)
        )
        return cursor.rowcount == 1


def assignment_students(assignment: sqlite3.Row) -> list[sqlite3.Row]:
    """Кому выдано задание: подтверждённые ученики школы (все или выбранные), по имени."""
    query = (
        "SELECT u.id, u.name, u.login FROM users u "
        "WHERE u.school_id = ? AND u.school_status = 'approved' AND u.role != 'teacher' "
    )
    params: tuple = (assignment["school_id"],)
    if not assignment["for_all"]:
        query += (
            "AND u.id IN (SELECT user_id FROM assignment_students WHERE assignment_id = ?) "
        )
        params += (assignment["id"],)
    with connect() as connection:
        return connection.execute(query + "ORDER BY u.name COLLATE NOCASE, u.id", params).fetchall()


def list_student_assignments(user_id: int) -> list[sqlite3.Row]:
    """Задания ученика: только из школы, где он подтверждён; ближайший срок сверху."""
    with connect() as connection:
        return connection.execute(
            f"SELECT {', '.join('a.' + c for c in _ASSIGNMENT_COLUMNS.split(', '))} "
            "FROM assignments a JOIN users u ON u.school_id = a.school_id "
            "WHERE u.id = ? AND u.school_status = 'approved' AND u.role != 'teacher' "
            "AND (a.for_all = 1 OR EXISTS (SELECT 1 FROM assignment_students s "
            "WHERE s.assignment_id = a.id AND s.user_id = u.id)) "
            "ORDER BY a.deadline, a.id",
            (user_id,),
        ).fetchall()


def get_finished_attempts_between(
    user_ids: list[int], mode: str, after: float, until: float
) -> list[Attempt]:
    """Завершённые попытки учеников в режиме mode с after < finished_at <= until."""
    if not user_ids:
        return []
    marks = ", ".join("?" * len(user_ids))  # в текст SQL идут только знаки «?»
    with connect() as connection:
        rows = connection.execute(
            f"SELECT {_ATTEMPT_COLUMNS} FROM attempts "
            f"WHERE user_id IN ({marks}) AND mode = ? AND status = 'finished' "
            "AND finished_at > ? AND finished_at <= ? ORDER BY finished_at, id",
            (*user_ids, mode, after, until),
        ).fetchall()
    return [_attempt_from_row(row) for row in rows]


def school_teachers(school_id: int) -> list[int]:
    """id учителей школы (им приходят уведомления о заявках)."""
    with connect() as connection:
        rows = connection.execute(
            "SELECT id FROM users WHERE school_id = ? AND role = ?", (school_id, ROLE_TEACHER)
        ).fetchall()
    return [row["id"] for row in rows]


def active_assignments(now: float, until: float) -> list[sqlite3.Row]:
    """Задания всех школ, срок которых ещё не прошёл и наступит не позже until."""
    with connect() as connection:
        return connection.execute(
            f"SELECT {_ASSIGNMENT_COLUMNS} FROM assignments WHERE deadline > ? AND deadline <= ? "
            "ORDER BY deadline, id",
            (now, until),
        ).fetchall()


def school_attempts(school_id: int) -> list[Attempt]:
    """Завершённые попытки подтверждённых учеников школы (для таблицы учителя)."""
    columns = ", ".join("a." + c for c in _ATTEMPT_COLUMNS.split(", "))
    with connect() as connection:
        rows = connection.execute(
            f"SELECT {columns} FROM attempts a JOIN users u ON u.id = a.user_id "
            "WHERE u.school_id = ? AND u.school_status = 'approved' AND u.role != 'teacher' "
            "AND a.status = 'finished' ORDER BY a.finished_at, a.id",
            (school_id,),
        ).fetchall()
    return [_attempt_from_row(row) for row in rows]


def school_last_started(school_id: int) -> dict[int, float]:
    """Когда каждый ученик школы последний раз начинал тест (активность без завершения)."""
    with connect() as connection:
        rows = connection.execute(
            "SELECT a.user_id, MAX(a.started_at) AS started FROM attempts a "
            "JOIN users u ON u.id = a.user_id WHERE u.school_id = ? GROUP BY a.user_id",
            (school_id,),
        ).fetchall()
    return {row["user_id"]: row["started"] for row in rows}


def attempt_subject_points(attempt_ids: list[int]) -> list[sqlite3.Row]:
    """Баллы попыток по предметам и типам заданий: attempt_id, subject, qtype, n, points."""
    if not attempt_ids:
        return []
    result: list[sqlite3.Row] = []
    with connect() as connection:
        for start in range(0, len(attempt_ids), 500):  # ограничение числа «?» в SQLite
            chunk = attempt_ids[start:start + 500]
            marks = ", ".join("?" * len(chunk))
            result += connection.execute(
                "SELECT aq.attempt_id, aq.subject, q.qtype, COUNT(*) AS n, SUM(aq.points) AS points "
                "FROM attempt_questions aq JOIN questions q ON q.id = aq.question_id "
                f"WHERE aq.attempt_id IN ({marks}) GROUP BY aq.attempt_id, aq.subject, q.qtype",
                chunk,
            ).fetchall()
    return result


# ── Уведомления ──────────────────────────────────────────────────────────────

def add_notification(user_id: int, kind: str, params_json: str, link: str, now: float,
                     dedup_key: str | None = None) -> int | None:
    """Добавляет уведомление. None — такое (с этим dedup_key) уже было."""
    with connect() as connection:
        cursor = connection.execute(
            "INSERT OR IGNORE INTO notifications (user_id, kind, params_json, link, created_at, dedup_key) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, kind, params_json, link, now, dedup_key),
        )
        return int(cursor.lastrowid) if cursor.rowcount == 1 else None


def list_notifications(user_id: int, limit: int = 100) -> list[sqlite3.Row]:
    """Уведомления пользователя, новые сверху."""
    with connect() as connection:
        return connection.execute(
            "SELECT id, kind, params_json, link, created_at, read_at FROM notifications "
            "WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()


def unread_notifications(user_id: int) -> int:
    """Сколько непрочитанных уведомлений (число на колокольчике)."""
    with connect() as connection:
        return connection.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_at IS NULL", (user_id,)
        ).fetchone()[0]


def get_notification(notification_id: int, user_id: int) -> sqlite3.Row | None:
    """Уведомление, только если оно принадлежит этому пользователю."""
    with connect() as connection:
        return connection.execute(
            "SELECT id, kind, params_json, link, created_at, read_at FROM notifications "
            "WHERE id = ? AND user_id = ?",
            (notification_id, user_id),
        ).fetchone()


def mark_notifications_read(user_id: int, now: float, notification_id: int | None = None) -> int:
    """Отмечает прочитанными все уведомления пользователя или одно."""
    query = "UPDATE notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL"
    params: tuple = (now, user_id)
    if notification_id is not None:
        query += " AND id = ?"
        params += (notification_id,)
    with connect() as connection:
        return connection.execute(query, params).rowcount


def get_telegram_id(user_id: int) -> int | None:
    """Telegram, привязанный к аккаунту (None — не привязан)."""
    with connect() as connection:
        row = connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()
    return row["telegram_id"] if row is not None else None


# ── Рекламные баннеры ────────────────────────────────────────────────────────

_BANNER_COLUMNS = (
    "id, title, link_url, image_type, placements, starts_on, ends_on, active, impressions, clicks, "
    "created_at, length(image) AS image_size"
)


def create_banner(title: str, link_url: str, image: bytes, image_type: str, placements: str,
                  starts_on: str, ends_on: str, active: bool, now: float) -> int:
    """Добавляет баннер и возвращает его id."""
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO banners (title, link_url, image, image_type, placements, starts_on, ends_on, "
            "active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (title, link_url, image, image_type, placements, starts_on, ends_on, int(active), now),
        )
        return int(cursor.lastrowid)


def update_banner(banner_id: int, title: str, link_url: str, placements: str, starts_on: str,
                  ends_on: str, active: bool, image: bytes | None = None,
                  image_type: str = "") -> bool:
    """Меняет баннер; картинка меняется, только если передана новая. False — баннера нет."""
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE banners SET title = ?, link_url = ?, placements = ?, starts_on = ?, ends_on = ?, "
            "active = ? WHERE id = ?",
            (title, link_url, placements, starts_on, ends_on, int(active), banner_id),
        )
        if cursor.rowcount and image is not None:
            connection.execute("UPDATE banners SET image = ?, image_type = ? WHERE id = ?",
                               (image, image_type, banner_id))
        return cursor.rowcount == 1


def delete_banner(banner_id: int) -> bool:
    """Удаляет баннер. False — его нет."""
    with connect() as connection:
        return connection.execute("DELETE FROM banners WHERE id = ?", (banner_id,)).rowcount == 1


def list_banners() -> list[sqlite3.Row]:
    """Все баннеры (без картинок), новые сверху."""
    with connect() as connection:
        return connection.execute(
            f"SELECT {_BANNER_COLUMNS} FROM banners ORDER BY id DESC"
        ).fetchall()


def get_banner(banner_id: int) -> sqlite3.Row | None:
    """Баннер без картинки."""
    with connect() as connection:
        return connection.execute(
            f"SELECT {_BANNER_COLUMNS} FROM banners WHERE id = ?", (banner_id,)
        ).fetchone()


def get_banner_image(banner_id: int) -> tuple[bytes, str] | None:
    """Картинка баннера и её тип."""
    with connect() as connection:
        row = connection.execute(
            "SELECT image, image_type FROM banners WHERE id = ?", (banner_id,)
        ).fetchone()
    return (bytes(row["image"]), row["image_type"]) if row else None


def active_banners(placement: str, today: str) -> list[sqlite3.Row]:
    """Включённые баннеры для места показа, срок которых включает сегодняшний день."""
    with connect() as connection:
        return connection.execute(
            f"SELECT {_BANNER_COLUMNS} FROM banners WHERE active = 1 AND starts_on <= ? AND ends_on >= ? "
            "AND (',' || placements || ',') LIKE ('%,' || ? || ',%')",
            (today, today, placement),
        ).fetchall()


def count_banner_impression(banner_id: int) -> None:
    """Учитывает показ баннера."""
    with connect() as connection:
        connection.execute("UPDATE banners SET impressions = impressions + 1 WHERE id = ?", (banner_id,))


def count_banner_click(banner_id: int) -> str | None:
    """Учитывает переход по баннеру и возвращает его ссылку (None — баннера нет)."""
    with connect() as connection:
        row = connection.execute("SELECT link_url FROM banners WHERE id = ?", (banner_id,)).fetchone()
        if row is None:
            return None
        connection.execute("UPDATE banners SET clicks = clicks + 1 WHERE id = ?", (banner_id,))
        return row["link_url"]
