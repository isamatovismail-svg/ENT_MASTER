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

# Путь к файлу базы. Тесты подменяют его через configure().
_db_path: Path = config.DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    login         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    created_at    REAL NOT NULL
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
    UNIQUE (attempt_id, question_id)
);

CREATE INDEX IF NOT EXISTS idx_attempts_user ON attempts(user_id, status);
CREATE INDEX IF NOT EXISTS idx_attempt_questions_attempt ON attempt_questions(attempt_id);
CREATE INDEX IF NOT EXISTS idx_questions_subject ON questions(subject, qtype);
"""


# ── Классы данных, которые возвращают запросы ────────────────────────────────

@dataclass
class User:
    """Пользователь сайта (без пароля)."""

    id: int
    name: str
    login: str


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
    """Создаёт таблицы и индексы, если их ещё нет."""
    with connect() as connection:
        connection.executescript(SCHEMA)


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


def login_exists(login: str) -> bool:
    """Проверяет, зарегистрирован ли уже такой логин (почта или телефон)."""
    with connect() as connection:
        row = connection.execute("SELECT 1 FROM users WHERE login = ?", (login,)).fetchone()
        return row is not None


def get_user_credentials(login: str) -> sqlite3.Row | None:
    """Возвращает id, имя, логин, хеш и соль пользователя для проверки пароля."""
    with connect() as connection:
        return connection.execute(
            "SELECT id, name, login, password_hash, salt FROM users WHERE login = ?",
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
            "SELECT u.id, u.name, u.login, s.csrf_token "
            "FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ? AND s.expires_at > ?",
            (token_hash, now),
        ).fetchone()
    if row is None:
        return None
    return User(row["id"], row["name"], row["login"]), row["csrf_token"]


def delete_session(token_hash: str) -> None:
    """Удаляет сессию (выход из аккаунта)."""
    with connect() as connection:
        connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))


def delete_expired_sessions(now: float) -> None:
    """Удаляет все просроченные сессии."""
    with connect() as connection:
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))


# ── Банк вопросов ────────────────────────────────────────────────────────────

def upsert_question(
    subject: str,
    qtype: str,
    text: str,
    context: str,
    options: list[str],
    left: list[str],
    correct: list[str],
) -> None:
    """Добавляет вопрос или обновляет существующий с тем же предметом и текстом.

    Благодаря этому seed.py можно запускать повторно: исправления в JSON
    попадут в базу, а дубликаты не появятся.
    """
    with connect() as connection:
        connection.execute(
            "INSERT INTO questions "
            "(subject, qtype, text, context, options_json, left_json, correct_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (subject, text) DO UPDATE SET "
            "qtype = excluded.qtype, context = excluded.context, "
            "options_json = excluded.options_json, left_json = excluded.left_json, "
            "correct_json = excluded.correct_json",
            (
                subject,
                qtype,
                text,
                context,
                json.dumps(options, ensure_ascii=False),
                json.dumps(left, ensure_ascii=False),
                json.dumps(correct),
            ),
        )


def question_counts() -> dict[tuple[str, str], int]:
    """Сколько вопросов в банке: словарь {(предмет, тип): количество}."""
    with connect() as connection:
        rows = connection.execute(
            "SELECT subject, qtype, COUNT(*) AS n FROM questions GROUP BY subject, qtype"
        ).fetchall()
    return {(row["subject"], row["qtype"]): row["n"] for row in rows}


def random_questions(subject: str, qtype: str | None, limit: int) -> list[tuple[int, str]]:
    """Возвращает до limit случайных вопросов предмета в виде пар (id, тип).

    Если qtype указан, выбираются только вопросы этого типа.
    """
    with connect() as connection:
        if qtype is None:
            rows = connection.execute(
                "SELECT id, qtype FROM questions WHERE subject = ? ORDER BY RANDOM() LIMIT ?",
                (subject, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT id, qtype FROM questions WHERE subject = ? AND qtype = ? "
                "ORDER BY RANDOM() LIMIT ?",
                (subject, qtype, limit),
            ).fetchall()
    return [(row["id"], row["qtype"]) for row in rows]


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
    questions: list[tuple[int, str]],
) -> int:
    """Создаёт попытку вместе со всеми её заданиями в одной транзакции.

    questions — список пар (id вопроса, код предмета) в нужном порядке.
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
            "INSERT INTO attempt_questions (attempt_id, question_id, subject, position) "
            "VALUES (?, ?, ?, ?)",
            [
                (attempt_id, question_id, subject, position)
                for position, (question_id, subject) in enumerate(questions, start=1)
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


def get_best_attempt(user_id: int, mode: str) -> Attempt | None:
    """Лучшая завершённая попытка в режиме (по доле набранных баллов)."""
    with connect() as connection:
        row = connection.execute(
            f"SELECT {_ATTEMPT_COLUMNS} FROM attempts "
            "WHERE user_id = ? AND mode = ? AND status = 'finished' AND max_score > 0 "
            "ORDER BY CAST(score AS REAL) / max_score DESC, score DESC, id DESC LIMIT 1",
            (user_id, mode),
        ).fetchone()
    return _attempt_from_row(row) if row else None


def get_last_attempt(user_id: int) -> Attempt | None:
    """Последняя завершённая попытка в любом режиме."""
    with connect() as connection:
        row = connection.execute(
            f"SELECT {_ATTEMPT_COLUMNS} FROM attempts "
            "WHERE user_id = ? AND status = 'finished' "
            "ORDER BY finished_at DESC, id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    return _attempt_from_row(row) if row else None


def get_attempt_questions(attempt_id: int) -> list[AttemptQuestion]:
    """Все задания попытки в порядке их следования, вместе с текстом вопросов."""
    with connect() as connection:
        rows = connection.execute(
            "SELECT aq.id, aq.attempt_id, aq.question_id, aq.subject, aq.position, "
            "aq.answer_json, aq.points, q.qtype, q.text, q.context, q.options_json, "
            "q.left_json, q.correct_json "
            "FROM attempt_questions aq JOIN questions q ON q.id = aq.question_id "
            "WHERE aq.attempt_id = ? ORDER BY aq.position",
            (attempt_id,),
        ).fetchall()
    return [
        AttemptQuestion(
            id=row["id"],
            attempt_id=row["attempt_id"],
            question_id=row["question_id"],
            subject=row["subject"],
            position=row["position"],
            qtype=row["qtype"],
            text=row["text"],
            context=row["context"],
            options=json.loads(row["options_json"]),
            left=json.loads(row["left_json"]),
            correct=json.loads(row["correct_json"]),
            answer=json.loads(row["answer_json"]) if row["answer_json"] else None,
            points=row["points"],
        )
        for row in rows
    ]


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
