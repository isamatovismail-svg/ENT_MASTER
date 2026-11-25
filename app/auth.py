"""Регистрация, вход, выход, хеширование паролей и сессии.

Пароль никогда не хранится в открытом виде: в базе лежат соль и результат
hashlib.pbkdf2_hmac (тысячи повторов SHA-256), что делает подбор очень медленным.
Сессия — случайный токен (secrets) в cookie с флагами HttpOnly и SameSite=Lax.
В базе хранится только SHA-256 от токена: утечка базы не даёт войти в чужой аккаунт.
"""

import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from http.cookies import SimpleCookie

import config
from app import database
from app.database import User
from app.web import Request

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^\+7\d{10}$")
NAME_MAX_LENGTH = 60


class ValidationError(Exception):
    """Ошибка проверки формы: содержит список понятных пользователю сообщений."""

    def __init__(self, errors: list[str]) -> None:
        """Сохраняет список сообщений об ошибках."""
        super().__init__("; ".join(errors))
        self.errors = errors


# ── Пароли ───────────────────────────────────────────────────────────────────

def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    """Хеширует пароль с солью. Возвращает (хеш, соль) в шестнадцатеричном виде.

    Если соль не передана, создаётся новая случайная соль (16 байт).
    """
    if salt_hex is None:
        salt_hex = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), config.PBKDF2_ITERATIONS
    )
    return digest.hex(), salt_hex


def verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    """Проверяет пароль. compare_digest сравнивает за постоянное время."""
    actual_hash, _ = hash_password(password, salt_hex)
    return hmac.compare_digest(actual_hash, expected_hash)


# ── Проверка формы регистрации ───────────────────────────────────────────────

def normalize_login(raw: str) -> str:
    """Приводит логин к единому виду.

    Почта — в нижний регистр, из телефона убираются пробелы, дефисы и скобки.
    """
    value = raw.strip()
    if "@" in value:
        return value.lower()
    return re.sub(r"[\s\-()]", "", value)


def validate_registration(name: str, login: str, password: str, password2: str) -> tuple[str, str]:
    """Проверяет все поля регистрации. Возвращает (имя, логин) или выбрасывает ValidationError."""
    errors: list[str] = []
    clean_name = " ".join(name.split())
    clean_login = normalize_login(login)

    if len(clean_name) < 2:
        errors.append("Введите имя (не короче 2 символов).")
    elif len(clean_name) > NAME_MAX_LENGTH:
        errors.append(f"Имя слишком длинное (максимум {NAME_MAX_LENGTH} символов).")

    if not clean_login:
        errors.append("Введите почту или номер телефона.")
    elif "@" in clean_login:
        if not EMAIL_RE.match(clean_login) or len(clean_login) > 254:
            errors.append("Почта указана неверно. Пример: aru@mail.kz")
    elif not PHONE_RE.match(clean_login):
        errors.append("Телефон должен быть в формате +7XXXXXXXXXX (11 цифр после «+»).")

    if len(password) < config.PASSWORD_MIN_LENGTH:
        errors.append(f"Пароль должен быть не короче {config.PASSWORD_MIN_LENGTH} символов.")
    elif password != password2:
        errors.append("Пароли не совпадают.")

    if not errors and database.login_exists(clean_login):
        errors.append("Пользователь с такой почтой или телефоном уже зарегистрирован.")

    if errors:
        raise ValidationError(errors)
    return clean_name, clean_login


def register_user(name: str, login: str, password: str, password2: str) -> int:
    """Регистрирует пользователя и возвращает его id (или выбрасывает ValidationError)."""
    clean_name, clean_login = validate_registration(name, login, password, password2)
    password_hash, salt = hash_password(password)
    try:
        return database.create_user(clean_name, clean_login, password_hash, salt, time.time())
    except sqlite3.IntegrityError as error:
        # Логин могли занять между проверкой и вставкой (два запроса одновременно).
        raise ValidationError(
            ["Пользователь с такой почтой или телефоном уже зарегистрирован."]
        ) from error


def authenticate(login: str, password: str) -> User | None:
    """Проверяет логин и пароль. Возвращает пользователя или None."""
    row = database.get_user_credentials(normalize_login(login))
    if row is None:
        # Считаем хеш и для несуществующего логина, чтобы по времени ответа
        # нельзя было понять, зарегистрирован ли такой пользователь.
        verify_password(password, "00" * 16, "0" * 64)
        return None
    if not verify_password(password, row["salt"], row["password_hash"]):
        return None
    return User(row["id"], row["name"], row["login"], row["role"])


# ── Сессии ───────────────────────────────────────────────────────────────────

def _token_hash(token: str) -> str:
    """SHA-256 от токена сессии — именно он хранится в базе."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _cookie_header(value: str, max_age: int) -> str:
    """Формирует заголовок Set-Cookie для сессии с флагами HttpOnly и SameSite=Lax."""
    cookie = SimpleCookie()
    cookie[config.SESSION_COOKIE_NAME] = value
    morsel = cookie[config.SESSION_COOKIE_NAME]
    morsel["path"] = "/"
    morsel["max-age"] = max_age
    morsel["httponly"] = True
    morsel["samesite"] = "Lax"
    return morsel.OutputString()


def start_session(user_id: int) -> str:
    """Создаёт новую сессию и возвращает значение заголовка Set-Cookie."""
    now = time.time()
    database.delete_expired_sessions(now)
    token = secrets.token_urlsafe(32)
    database.create_session(
        _token_hash(token), user_id, secrets.token_urlsafe(32),
        now + config.SESSION_LIFETIME_SECONDS,
    )
    return _cookie_header(token, config.SESSION_LIFETIME_SECONDS)


def end_session(request: Request) -> str:
    """Удаляет текущую сессию и возвращает Set-Cookie, стирающий cookie в браузере."""
    if request.session_key:
        database.delete_session(request.session_key)
    return _cookie_header("", 0)


def attach_user(request: Request) -> None:
    """Определяет пользователя по cookie и записывает его в request.user."""
    token = request.cookies.get(config.SESSION_COOKIE_NAME, "")
    if not token:
        return
    key = _token_hash(token)
    found = database.get_session_user(key, time.time())
    if found is None:
        return
    request.user, request.csrf_token = found
    request.session_key = key


def check_csrf(request: Request) -> bool:
    """Проверяет, что форма содержит csrf-токен текущей сессии (защита от подделки запросов)."""
    sent = request.form_value("csrf_token")
    return bool(request.csrf_token) and hmac.compare_digest(sent, request.csrf_token)


# ── Вход через Telegram-бота ─────────────────────────────────────────────────

TELEGRAM_NAME_FALLBACK = "Ученик"


def telegram_login_url(telegram_id: int, telegram_name: str) -> str:
    """Создаёт одноразовую ссылку входа на сайт (действует TELEGRAM_LOGIN_TOKEN_MINUTES минут)."""
    token = secrets.token_urlsafe(32)
    name = " ".join(telegram_name.split())[:NAME_MAX_LENGTH] or TELEGRAM_NAME_FALLBACK
    database.create_telegram_login_token(
        _token_hash(token), telegram_id, name,
        time.time() + config.TELEGRAM_LOGIN_TOKEN_MINUTES * 60,
    )
    return f"{config.SITE_URL}/tg/login?token={token}"


def peek_telegram_token(token: str) -> sqlite3.Row | None:
    """Данные действующего токена (telegram_id, telegram_name) без его использования."""
    if not token or len(token) > 200:
        return None
    return database.get_telegram_login_token(_token_hash(token), time.time())


def use_telegram_token(token: str) -> bool:
    """Использует токен один раз. False — он уже использован, просрочен или неверен."""
    if not token or len(token) > 200:
        return False
    return database.use_telegram_login_token(_token_hash(token), time.time())


def create_telegram_user(telegram_id: int, name: str) -> int:
    """Регистрирует пользователя, который входит только через Telegram.

    Логин — tg<telegram_id>, пароль — случайный и никому не известный:
    войти в такой аккаунт можно только по ссылке из бота.
    """
    login = f"tg{telegram_id}"
    password_hash, salt = hash_password(secrets.token_urlsafe(32))
    clean_name = " ".join(name.split())[:NAME_MAX_LENGTH] or TELEGRAM_NAME_FALLBACK
    try:
        user_id = database.create_user(clean_name, login, password_hash, salt, time.time())
    except sqlite3.IntegrityError:
        # Такой аккаунт уже создавался раньше (а Telegram потом привязали к другому) —
        # возвращаемся к нему.
        row = database.get_user_credentials(login)
        assert row is not None
        user_id = row["id"]
    database.bind_telegram(user_id, telegram_id)
    return user_id
