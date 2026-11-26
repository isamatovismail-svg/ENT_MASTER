"""Регистрация, вход, выход, хеширование паролей и сессии.

Пароль никогда не хранится в открытом виде: в базе лежат соль и результат
hashlib.pbkdf2_hmac (тысячи повторов SHA-256), что делает подбор очень медленным.
Сессия — случайный токен (secrets) в cookie с флагами HttpOnly и SameSite=Lax.
В базе хранится только SHA-256 от токена: утечка базы не даёт войти в чужой аккаунт.
"""

import hashlib
import hmac
import math
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from http.cookies import SimpleCookie

import config
from app import database, mailer, schools
from app.database import User
from app.web import Request

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
# Похоже на телефон: только цифры, «+», пробелы, скобки и дефисы.
PHONE_LIKE_RE = re.compile(r"^\+?[\d\s\-()]+$")
PHONE_ERROR = (
    "Номер телефона указан неверно: после кода страны (+7 или 8) должно быть 10 цифр. "
    "Пример: +7 705 123 45 67"
)
NAME_MAX_LENGTH = 60
TELEGRAM_NAME_FALLBACK = "Ученик"  # имя, если Telegram или Google его не сообщили


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

def normalize_phone(raw: str) -> str:
    """Приводит казахстанский номер к виду +7XXXXXXXXXX или выбрасывает ValueError.

    Принимаются «8 705 967 84 20», «+7 (705) 967-84-20», «87059678420»,
    «77059678420» и «7059678420»: пробелы, скобки и дефисы убираются,
    код страны (+7, 7 или 8) отбрасывается, остаться должно ровно 10 цифр.
    """
    value = raw.strip()
    if not PHONE_LIKE_RE.match(value) or "+" in value[1:]:
        raise ValueError(PHONE_ERROR)
    digits = re.sub(r"\D", "", value)
    if value.startswith("+"):
        if not digits.startswith("7"):
            raise ValueError(PHONE_ERROR)
        digits = digits[1:]
    elif len(digits) == 11 and digits[0] in "78":
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError(PHONE_ERROR)
    return "+7" + digits


def normalize_login(raw: str) -> str:
    """Приводит логин к единому виду.

    Почта — в нижний регистр, телефон — к виду +7XXXXXXXXXX (normalize_phone).
    Если телефон набран с ошибкой, из него только убираются пробелы, дефисы и скобки —
    такой логин просто не найдётся. Остальное (например, tg123) не меняется.
    """
    value = raw.strip()
    if "@" in value:
        return value.lower()
    if PHONE_LIKE_RE.match(value):
        try:
            return normalize_phone(value)
        except ValueError:
            return re.sub(r"[\s\-()]", "", value)
    return value


def _clean_text(raw: str) -> str:
    """Убирает лишние пробелы."""
    return " ".join(raw.split())


def _check_password(password: str, password2: str, errors: list[str]) -> None:
    """Проверяет длину пароля и повтор, дописывает ошибки в errors."""
    if len(password) < config.PASSWORD_MIN_LENGTH:
        errors.append(f"Пароль должен быть не короче {config.PASSWORD_MIN_LENGTH} символов.")
    elif password != password2:
        errors.append("Пароли не совпадают.")


def normalize_email(raw: str) -> str:
    """Почта без пробелов по краям и в нижнем регистре."""
    return raw.strip().lower()


def find_email_user(email: str) -> sqlite3.Row | None:
    """Аккаунт с такой почтой (id, name, login, email_verified, …) или None."""
    email = normalize_email(email)
    if "@" not in email:
        return None
    return database.get_user_credentials(email)


@dataclass
class Registration:
    """Проверенные поля формы регистрации."""

    name: str              # «Имя Фамилия»
    email: str
    phone: str | None
    pending_user_id: int   # неподтверждённый аккаунт с той же почтой (0 — нет)
    school: tuple[str, str] | None = None  # (город, школа) или None — без школы


def validate_registration(
    first_name: str, last_name: str, email: str, phone: str, password: str, password2: str,
    school_city: str = "", school_name: str = "",
) -> Registration:
    """Проверяет все поля регистрации или выбрасывает ValidationError со списком ошибок."""
    errors: list[str] = []
    first = _clean_text(first_name)
    last = _clean_text(last_name)
    clean_email = normalize_email(email)
    clean_phone: str | None = None

    if len(first) < 2:
        errors.append("Введите имя (не короче 2 символов).")
    if not last:
        errors.append("Введите фамилию.")
    if len(first) + len(last) + 1 > NAME_MAX_LENGTH:
        errors.append(f"Имя и фамилия слишком длинные (максимум {NAME_MAX_LENGTH} символов вместе).")

    if not clean_email:
        errors.append("Введите почту.")
    elif not EMAIL_RE.match(clean_email) or len(clean_email) > 254:
        errors.append("Почта указана неверно. Пример: aru@mail.kz")

    if phone.strip():
        try:
            clean_phone = normalize_phone(phone)
        except ValueError as error:
            errors.append(str(error))

    school = None
    try:
        school = schools.validate_school(school_city, school_name)
    except schools.SchoolError as error:
        errors.extend(error.errors)

    _check_password(password, password2, errors)

    pending_user_id = 0
    if not errors:
        existing = find_email_user(clean_email)
        if existing is not None and existing["email_verified"]:
            errors.append(
                "Пользователь с такой почтой уже зарегистрирован. Войдите или восстановите пароль."
            )
        elif existing is not None:
            pending_user_id = existing["id"]
        if clean_phone and database.phone_taken(clean_phone, pending_user_id):
            errors.append("Этот номер телефона уже указан в другом аккаунте.")

    if errors:
        raise ValidationError(errors)
    return Registration(f"{first} {last}", clean_email, clean_phone, pending_user_id, school)


def register_user(
    first_name: str, last_name: str, email: str, phone: str, password: str, password2: str,
    school_city: str = "", school_name: str = "",
) -> int:
    """Создаёт неподтверждённый аккаунт и возвращает его id (или выбрасывает ValidationError).

    Войти в аккаунт можно только после ввода кода из письма (send_email_code + verify_email).
    Если на эту почту уже начинали регистрацию и не подтвердили её, прежние данные
    заменяются новыми: без кода из письма такой аккаунт всё равно бесполезен.
    """
    form = validate_registration(first_name, last_name, email, phone, password, password2,
                                 school_city, school_name)
    password_hash, salt = hash_password(password)
    try:
        if form.pending_user_id and database.update_unverified_user(
            form.pending_user_id, form.name, form.phone, password_hash, salt
        ):
            user_id = form.pending_user_id
        else:
            user_id = database.create_user(form.name, form.email, password_hash, salt,
                                           time.time(), phone=form.phone, email_verified=False)
    except sqlite3.IntegrityError as error:
        # Почту или телефон могли занять между проверкой и записью (два запроса одновременно).
        raise ValidationError(
            ["Пользователь с такой почтой или телефоном уже зарегистрирован."]
        ) from error
    # Школа: заявка ждёт подтверждения учителя (или «без школы»).
    if form.school is None:
        database.set_user_school(user_id, None, None)
    else:
        database.set_user_school(user_id, schools.find_or_create_school(*form.school),
                                 database.SCHOOL_PENDING)
    return user_id


def create_account(name: str, login: str, password: str, phone: str | None = None) -> int:
    """Сразу подтверждённый аккаунт (вход через Google, тесты). Возвращает id."""
    password_hash, salt = hash_password(password)
    clean_name = _clean_text(name)[:NAME_MAX_LENGTH] or TELEGRAM_NAME_FALLBACK
    return database.create_user(clean_name, login, password_hash, salt, time.time(), phone=phone)


def authenticate(login: str, password: str) -> User | None:
    """Проверяет логин и пароль. Возвращает пользователя или None.

    Если почта ещё не подтверждена, у пользователя email_verified = False — вход
    в этом случае не выполняется, а ученика отправляют вводить код.
    """
    row = database.get_user_credentials(normalize_login(login))
    if row is None:
        # Считаем хеш и для несуществующего логина, чтобы по времени ответа
        # нельзя было понять, зарегистрирован ли такой пользователь.
        verify_password(password, "00" * 16, "0" * 64)
        return None
    if not verify_password(password, row["salt"], row["password_hash"]):
        return None
    return User(row["id"], row["name"], row["login"], row["role"], bool(row["email_verified"]))


# ── Коды из писем ────────────────────────────────────────────────────────────

VERIFY = "verify"  # подтверждение почты после регистрации
RESET = "reset"    # восстановление пароля

_MAIL_TEXTS = {
    VERIFY: (
        "Код подтверждения ENT MASTER: {code}",
        "Здравствуйте!\n\nВаш код подтверждения почты на ENT MASTER: {code}\n\n"
        "Код действует {minutes} минут. Если вы не регистрировались, просто проигнорируйте письмо.",
    ),
    RESET: (
        "Восстановление пароля ENT MASTER: {code}",
        "Здравствуйте!\n\nКод для смены пароля на ENT MASTER: {code}\n\n"
        "Код действует {minutes} минут. Если вы не просили сменить пароль, "
        "просто проигнорируйте письмо — пароль останется прежним.",
    ),
}

CODE_ERRORS = {
    "wrong": "Неверный код. Осталось попыток: {left}.",
    "expired": "Срок действия кода истёк. Нажмите «Отправить код ещё раз».",
    "blocked": "Слишком много неверных попыток. Нажмите «Отправить код ещё раз».",
    "missing": "Код не найден или уже использован. Нажмите «Отправить код ещё раз».",
}


def _code_hash(user_id: int, purpose: str, code: str) -> str:
    """SHA-256 от кода (вместе с id и видом кода) — только он хранится в базе."""
    return hashlib.sha256(f"{purpose}:{user_id}:{code}".encode("utf-8")).hexdigest()


def resend_wait_seconds(user_id: int, purpose: str) -> int:
    """Сколько секунд ждать до следующей отправки кода (0 — можно отправлять)."""
    row = database.get_email_code(user_id, purpose)
    if row is None:
        return 0
    left = row["sent_at"] + config.EMAIL_CODE_RESEND_SECONDS - time.time()
    return max(0, math.ceil(left))


def send_email_code(user_id: int, email: str, purpose: str) -> int:
    """Отправляет на почту новый 6-значный код.

    Возвращает 0, если письмо отправлено, или сколько секунд ещё ждать
    (новый код — не чаще раза в минуту). Ошибка отправки — mailer.MailError.
    """
    wait = resend_wait_seconds(user_id, purpose)
    if wait:
        return wait
    code = f"{secrets.randbelow(10 ** 6):06d}"
    subject, body = _MAIL_TEXTS[purpose]
    minutes = config.EMAIL_CODE_MINUTES
    mailer.send(email, subject.format(code=code), body.format(code=code, minutes=minutes))
    now = time.time()
    database.save_email_code(user_id, purpose, _code_hash(user_id, purpose, code),
                             now + minutes * 60, now)
    return 0


def check_email_code(user_id: int, purpose: str, code: str) -> str | None:
    """Проверяет код. None — код верный (и больше не действует), иначе текст ошибки.

    После EMAIL_CODE_MAX_ATTEMPTS неверных вводов код перестаёт действовать.
    """
    code = re.sub(r"\s", "", code)
    row = database.get_email_code(user_id, purpose)
    if row is None:
        return CODE_ERRORS["missing"]
    if row["attempts"] >= config.EMAIL_CODE_MAX_ATTEMPTS:
        return CODE_ERRORS["blocked"]
    if row["expires_at"] < time.time():
        return CODE_ERRORS["expired"]
    if hmac.compare_digest(_code_hash(user_id, purpose, code), row["code_hash"]):
        database.delete_email_code(user_id, purpose)
        return None
    database.add_email_code_attempt(user_id, purpose)
    left = config.EMAIL_CODE_MAX_ATTEMPTS - row["attempts"] - 1
    if left <= 0:
        return CODE_ERRORS["blocked"]
    return CODE_ERRORS["wrong"].format(left=left)


def verify_email(email: str, code: str) -> int:
    """Подтверждает почту кодом из письма и возвращает id пользователя.

    Ошибка (неверный код, аккаунта нет или он уже подтверждён) — ValidationError.
    """
    user = find_email_user(email)
    if user is None or user["email_verified"]:
        raise ValidationError([CODE_ERRORS["missing"]])
    error = check_email_code(user["id"], VERIFY, code)
    if error:
        raise ValidationError([error])
    database.set_email_verified(user["id"])
    return int(user["id"])


def reset_password(email: str, code: str, password: str, password2: str) -> int:
    """Меняет пароль по коду из письма и возвращает id пользователя.

    Все прежние сессии завершаются. Раз код пришёл на почту, она считается подтверждённой.
    """
    errors: list[str] = []
    _check_password(password, password2, errors)
    if errors:
        raise ValidationError(errors)
    user = find_email_user(email)
    if user is None:
        raise ValidationError([CODE_ERRORS["missing"]])
    error = check_email_code(user["id"], RESET, code)
    if error:
        raise ValidationError([error])
    password_hash, salt = hash_password(password)
    database.set_password(user["id"], password_hash, salt)
    database.set_email_verified(user["id"])
    database.delete_email_code(user["id"], VERIFY)
    return int(user["id"])


# ── Вход через Google ────────────────────────────────────────────────────────

def google_user(email: str, first_name: str, last_name: str) -> int:
    """Аккаунт для входа через Google: найденный по почте или новый. Возвращает id.

    Google уже подтвердил почту. Если на неё была начата, но не подтверждена
    регистрация, пароль из той регистрации сбрасывается на случайный: его мог
    задать кто-то чужой, кто вписал эту почту.
    """
    email = normalize_email(email)
    existing = find_email_user(email)
    if existing is not None:
        if not existing["email_verified"]:
            password_hash, salt = hash_password(secrets.token_urlsafe(32))
            database.set_password(existing["id"], password_hash, salt)
            database.set_email_verified(existing["id"])
            database.delete_email_code(existing["id"], VERIFY)
        return int(existing["id"])
    name = _clean_text(f"{first_name} {last_name}") or email.split("@", 1)[0]
    try:
        return create_account(name, email, secrets.token_urlsafe(32))
    except sqlite3.IntegrityError:
        # Тот же аккаунт создал параллельный запрос.
        row = find_email_user(email)
        assert row is not None
        return int(row["id"])


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
    if config.COOKIE_SECURE:
        morsel["secure"] = True  # на сервере с HTTPS cookie не уходит по незащищённому http
    return morsel.OutputString()


def start_session(user_id: int) -> str:
    """Создаёт новую сессию и возвращает значение заголовка Set-Cookie."""
    now = time.time()
    database.delete_expired_sessions(now)
    token = secrets.token_urlsafe(32)
    database.create_session(
        _token_hash(token), user_id, secrets.token_urlsafe(32),
        now + config.SESSION_LIFETIME_SECONDS, now=now,
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
