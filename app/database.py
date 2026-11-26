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
ROLE_ADMIN = "admin"

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
    telegram_id   INTEGER                        -- привязанный аккаунт Telegram (или NULL)
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
    UNIQUE (subject, text)
);

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
    ("questions", "explanation", "TEXT NOT NULL DEFAULT ''"),
    ("questions", "deleted", "INTEGER NOT NULL DEFAULT 0"),
    ("questions", "edited_by_admin", "INTEGER NOT NULL DEFAULT 0"),
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

    @property
    def is_admin(self) -> bool:
        """True, если пользователь — администратор."""
        return self.role == ROLE_ADMIN


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
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        # Индекс создаётся после миграции: в старой базе колонки telegram_id ещё не было.
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram ON users(telegram_id) "
            "WHERE telegram_id IS NOT NULL"
        )


# ── Пользователи ─────────────────────────────────────────────────────────────

def create_user(name: str, login: str, password_hash: str, salt: str, created_at: float) -> int:
    """Добавляет пользователя и возвращает его id.

    Если логин занят, sqlite3 выбросит IntegrityError (ограничение UNIQUE).
    """
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO users (name, login, password_hash, salt, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, login, password_hash, salt, created_at),
        )
        return int(cursor.lastrowid)


def set_user_role(login: str, role: str) -> bool:
    """Меняет роль пользователя по логину. False — такого пользователя нет."""
    with connect() as connection:
        cursor = connection.execute("UPDATE users SET role = ? WHERE login = ?", (role, login))
        return cursor.rowcount == 1


# ── Telegram ─────────────────────────────────────────────────────────────────

def get_user_by_telegram(telegram_id: int) -> User | None:
    """Пользователь сайта, к которому привязан этот аккаунт Telegram."""
    with connect() as connection:
        row = connection.execute(
            "SELECT id, name, login, role FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
    return User(row["id"], row["name"], row["login"], row["role"]) if row else None


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
            "SELECT u.id, u.name, u.login, u.role, u.created_at, "
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


def get_user_credentials(login: str) -> sqlite3.Row | None:
    """Возвращает id, имя, логин, хеш и соль пользователя для проверки пароля."""
    with connect() as connection:
        return connection.execute(
            "SELECT id, name, login, role, password_hash, salt FROM users WHERE login = ?",
            (login,),
        ).fetchone()


# ── Сессии ───────────────────────────────────────────────────────────────────

def create_session(token_hash: str, user_id: int, csrf_token: str, expires_at: float) -> None:
    """Сохраняет новую сессию. В базе хранится только хеш токена, не сам токен."""
    with connect() as connection:
        connection.execute(
            "INSERT INTO sessions (token_hash, user_id, csrf_token, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (token_hash, user_id, csrf_token, expires_at),
        )


def get_session_user(token_hash: str, now: float) -> tuple[User, str] | None:
    """Находит пользователя по хешу токена сессии. Возвращает (пользователь, csrf-токен)."""
    with connect() as connection:
        row = connection.execute(
            "SELECT u.id, u.name, u.login, u.role, s.csrf_token "
            "FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ? AND s.expires_at > ?",
            (token_hash, now),
        ).fetchone()
    if row is None:
        return None
    return User(row["id"], row["name"], row["login"], row["role"]), row["csrf_token"]


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
    "(subject, qtype, text, context, options_json, left_json, correct_json, explanation) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT (subject, text) DO UPDATE SET "
    "qtype = excluded.qtype, context = excluded.context, "
    "options_json = excluded.options_json, left_json = excluded.left_json, "
    "correct_json = excluded.correct_json, explanation = excluded.explanation, "
    "deleted = 0 "
    # Вопросы, исправленные в админке, не трогаем: ручная правка важнее файла.
    "WHERE questions.edited_by_admin = 0"
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
) -> None:
    """Добавляет вопрос или обновляет существующий с тем же предметом и текстом.

    Благодаря этому seed.py можно запускать повторно: исправления в JSON
    попадут в базу, а дубликаты не появятся.
    """
    question = {"type": qtype, "text": text, "context": context, "options": options,
                "left": left, "correct": correct, "explanation": explanation}
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


_QUESTION_COLUMNS = (
    "q.id, q.subject, q.qtype, q.text, q.context, q.options_json, q.left_json, "
    "q.correct_json, q.explanation, "
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
    )


def list_questions(subject: str | None = None) -> list[Question]:
    """Действующие (не удалённые) вопросы банка, по предмету или все; новые сверху."""
    with connect() as connection:
        if subject is None:
            rows = connection.execute(
                f"SELECT {_QUESTION_COLUMNS} FROM questions q WHERE q.deleted = 0 "
                "ORDER BY q.id DESC"
            ).fetchall()
        else:
            rows = connection.execute(
                f"SELECT {_QUESTION_COLUMNS} FROM questions q "
                "WHERE q.deleted = 0 AND q.subject = ? ORDER BY q.id DESC",
                (subject,),
            ).fetchall()
    return [_question_from_row(row) for row in rows]


def get_question(question_id: int) -> Question | None:
    """Действующий вопрос по id."""
    with connect() as connection:
        row = connection.execute(
            f"SELECT {_QUESTION_COLUMNS} FROM questions q WHERE q.id = ? AND q.deleted = 0",
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
    )


def insert_question(question: Question) -> int:
    """Добавляет вопрос из админки (с пометкой edited_by_admin) и возвращает его id.

    Если у предмета уже есть вопрос с таким текстом, sqlite3 выбросит IntegrityError.
    """
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO questions "
            "(subject, qtype, text, context, options_json, left_json, correct_json, explanation, "
            "edited_by_admin) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
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
            "options_json = ?, left_json = ?, correct_json = ?, explanation = ?, "
            "edited_by_admin = 1 WHERE id = ? AND deleted = 0",
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
            "FROM questions q WHERE q.id = ? AND q.deleted = 0",
            (question_id,),
        ).fetchone()
        if row is None:
            return "missing"
        if row["used"]:
            connection.execute("UPDATE questions SET deleted = 1 WHERE id = ?", (question_id,))
            return "archived"
        connection.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        return "deleted"


def question_counts() -> dict[tuple[str, str], int]:
    """Сколько вопросов в банке: словарь {(предмет, тип): количество}."""
    with connect() as connection:
        rows = connection.execute(
            "SELECT subject, qtype, COUNT(*) AS n FROM questions WHERE deleted = 0 "
            "GROUP BY subject, qtype"
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
            f"WHERE q.subject = ? AND q.deleted = 0 {type_filter}"
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
