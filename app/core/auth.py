"""Регистрация, вход, выход, хеширование паролей и сессии."""

import hashlib
import hmac
import math
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from http.cookies import SimpleCookie

from app import config
from app import i18n
from app.core import database, mailer, schools
from app.core.database import User
from app.web.http import Request
from app.i18n import t

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_LIKE_RE = re.compile(r"^\+?[\d\s\-()]+$")
PHONE_ERROR = (
    "Номер телефона указан неверно: после кода страны (+7 или 8) должно быть 10 цифр. "
    "Пример: +7 705 123 45 67"
)
NAME_MAX_LENGTH = 60
TELEGRAM_NAME_FALLBACK = "Ученик"


class ValidationError(Exception):
    """Ошибка проверки формы: содержит список понятных пользователю сообщений."""

    def __init__(self, errors: list[str]) -> None:
        """Сохраняет список сообщений об ошибках."""
        super().__init__("; ".join(errors))
        self.errors = errors


def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    """Хеширует пароль с солью. Возвращает (хеш, соль) в шестнадцатеричном виде."""
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


def normalize_phone(raw: str) -> str:
    """Приводит казахстанский номер к виду +7XXXXXXXXXX или выбрасывает ValueError."""
    value = raw.strip()
    if not PHONE_LIKE_RE.match(value) or "+" in value[1:]:
        raise ValueError(t(PHONE_ERROR))
    digits = re.sub(r"\D", "", value)
    if value.startswith("+"):
        if not digits.startswith("7"):
            raise ValueError(t(PHONE_ERROR))
        digits = digits[1:]
    elif len(digits) == 11 and digits[0] in "78":
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError(t(PHONE_ERROR))
    return "+7" + digits


def normalize_login(raw: str) -> str:
    """Приводит логин к единому виду."""
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
    return " ".join(raw.split())


def _check_password(password: str, password2: str, errors: list[str]) -> None:
    if len(password) < config.PASSWORD_MIN_LENGTH:
        errors.append(t("Пароль должен быть не короче {n} символов.", n=config.PASSWORD_MIN_LENGTH))
    elif password != password2:
        errors.append(t("Пароли не совпадают."))


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

    name: str
    email: str
    phone: str | None
    pending_user_id: int
    school: tuple[str, str] | None = None


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
        errors.append(t("Введите имя (не короче 2 символов)."))
    if not last:
        errors.append(t("Введите фамилию."))
    if len(first) + len(last) + 1 > NAME_MAX_LENGTH:
        errors.append(t("Имя и фамилия слишком длинные (максимум {n} символов вместе).", n=NAME_MAX_LENGTH))

    if not clean_email:
        errors.append(t("Введите почту."))
    elif not EMAIL_RE.match(clean_email) or len(clean_email) > 254:
        errors.append(t("Почта указана неверно. Пример: aru@mail.kz"))

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
                t("Пользователь с такой почтой уже зарегистрирован. Войдите или восстановите пароль.")
            )
        elif existing is not None:
            pending_user_id = existing["id"]
        if clean_phone and database.phone_taken(clean_phone, pending_user_id):
            errors.append(t("Этот номер телефона уже указан в другом аккаунте."))

    if errors:
        raise ValidationError(errors)
    return Registration(f"{first} {last}", clean_email, clean_phone, pending_user_id, school)


def register_user(
    first_name: str, last_name: str, email: str, phone: str, password: str, password2: str,
    school_city: str = "", school_name: str = "", language: str = i18n.RU,
) -> int:
    """Создаёт неподтверждённый аккаунт и возвращает его id (или выбрасывает ValidationError)."""
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
        raise ValidationError(
            [t("Пользователь с такой почтой или телефоном уже зарегистрирован.")]
        ) from error
    database.set_user_language(user_id, i18n.normalize(language))
    if form.school is None:
        database.set_user_school(user_id, None, None)
    else:
        school_id = schools.find_or_create_school(*form.school)
        database.set_user_school(user_id, school_id, database.SCHOOL_PENDING)
        from app.core import notifications

        notifications.school_request(school_id, form.name, user_id)
    return user_id


def create_account(name: str, login: str, password: str, phone: str | None = None) -> int:
    """Сразу подтверждённый аккаунт (вход через Google, тесты). Возвращает id."""
    password_hash, salt = hash_password(password)
    clean_name = _clean_text(name)[:NAME_MAX_LENGTH] or TELEGRAM_NAME_FALLBACK
    return database.create_user(clean_name, login, password_hash, salt, time.time(), phone=phone)


def is_blocked_demo_admin(login: str, role: str) -> bool:
    """True — это демо-администратор, а сайт открыт через интернет (run.py --share)."""
    return (config.SHARE_MODE and role == database.ROLE_ADMIN
            and login.lower().endswith("@" + config.DEMO_EMAIL_DOMAIN))


def authenticate(login: str, password: str) -> User | None:
    """Проверяет логин и пароль. Возвращает пользователя или None."""
    row = database.get_user_credentials(normalize_login(login))
    if row is None:
        verify_password(password, "00" * 16, "0" * 64)
        return None
    if not verify_password(password, row["salt"], row["password_hash"]):
        return None
    return User(row["id"], row["name"], row["login"], row["role"], bool(row["email_verified"]),
                language=row["language"])


def login_wait_minutes(login: str, now: float | None = None) -> int:
    """Сколько минут ждать до следующей попытки входа (0 — можно входить)."""
    now = time.time() if now is None else now
    failures = database.login_failures_since(normalize_login(login), now - config.LOGIN_LOCK_SECONDS)
    if len(failures) < config.LOGIN_MAX_FAILURES:
        return 0
    unlock_at = failures[-config.LOGIN_MAX_FAILURES] + config.LOGIN_LOCK_SECONDS
    return max(1, math.ceil((unlock_at - now) / 60))


def note_login(login: str, success: bool, now: float | None = None) -> None:
    """Учитывает результат входа: неудача увеличивает счётчик, успех его сбрасывает."""
    key = normalize_login(login)
    if success:
        database.clear_login_failures(key)
    else:
        database.record_login_failure(key, time.time() if now is None else now, config.LOGIN_LOCK_SECONDS)


WEAK_PASSWORDS = (
    "12345678", "123456789", "1234567890", "87654321", "11111111", "00000000",
    "password", "password1", "qwerty123", "qwertyui", "1q2w3e4r", "iloveyou",
    "admin123", "admin1234", "admin2026", "administrator", "entmaster", "qwerty",
)


def weak_admin_logins(skip_demo: bool = True) -> list[str]:
    """Логины главных администраторов, чей пароль угадывается по списку WEAK_PASSWORDS."""
    weak = []
    for row in database.admin_credentials():
        login = row["login"]
        if skip_demo and login.lower().endswith("@" + config.DEMO_EMAIL_DOMAIN):
            continue
        candidates = (*WEAK_PASSWORDS, login, login.split("@")[0])
        if any(verify_password(c, row["salt"], row["password_hash"]) for c in candidates):
            weak.append(login)
    return weak


VERIFY = "verify"
RESET = "reset"

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
    return hashlib.sha256(f"{purpose}:{user_id}:{code}".encode("utf-8")).hexdigest()


def resend_wait_seconds(user_id: int, purpose: str) -> int:
    """Сколько секунд ждать до следующей отправки кода (0 — можно отправлять)."""
    row = database.get_email_code(user_id, purpose)
    if row is None:
        return 0
    left = row["sent_at"] + config.EMAIL_CODE_RESEND_SECONDS - time.time()
    return max(0, math.ceil(left))


def send_email_code(user_id: int, email: str, purpose: str) -> int:
    """Отправляет на почту новый 6-значный код."""
    wait = resend_wait_seconds(user_id, purpose)
    if wait:
        return wait
    code = f"{secrets.randbelow(10 ** 6):06d}"
    subject, body = _MAIL_TEXTS[purpose]
    minutes = config.EMAIL_CODE_MINUTES
    with i18n.use(database.get_user_language(user_id)):
        subject = t(subject, code=code)
        body = t(body, code=code, minutes=minutes) + f"\n\nENT MASTER: {config.SITE_URL}"
    mailer.send(email, subject, body)
    now = time.time()
    database.save_email_code(user_id, purpose, _code_hash(user_id, purpose, code),
                             now + minutes * 60, now)
    return 0


def check_email_code(user_id: int, purpose: str, code: str) -> str | None:
    """Проверяет код. None — код верный (и больше не действует), иначе текст ошибки."""
    code = re.sub(r"\s", "", code)
    row = database.get_email_code(user_id, purpose)
    if row is None:
        return t(CODE_ERRORS["missing"])
    if row["attempts"] >= config.EMAIL_CODE_MAX_ATTEMPTS:
        return t(CODE_ERRORS["blocked"])
    if row["expires_at"] < time.time():
        return t(CODE_ERRORS["expired"])
    if hmac.compare_digest(_code_hash(user_id, purpose, code), row["code_hash"]):
        database.delete_email_code(user_id, purpose)
        return None
    database.add_email_code_attempt(user_id, purpose)
    left = config.EMAIL_CODE_MAX_ATTEMPTS - row["attempts"] - 1
    if left <= 0:
        return t(CODE_ERRORS["blocked"])
    return t(CODE_ERRORS["wrong"], left=left)


def verify_email(email: str, code: str) -> int:
    """Подтверждает почту кодом из письма и возвращает id пользователя."""
    user = find_email_user(email)
    if user is None or user["email_verified"]:
        raise ValidationError([CODE_ERRORS["missing"]])
    error = check_email_code(user["id"], VERIFY, code)
    if error:
        raise ValidationError([error])
    database.set_email_verified(user["id"])
    return int(user["id"])


def reset_password(email: str, code: str, password: str, password2: str) -> int:
    """Меняет пароль по коду из письма и возвращает id пользователя."""
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


def google_user(email: str, first_name: str, last_name: str) -> int:
    """Аккаунт для входа через Google: найденный по почте или новый. Возвращает id."""
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
        user_id = create_account(name, email, secrets.token_urlsafe(32))
        database.set_user_language(user_id, i18n.get_language())
        return user_id
    except sqlite3.IntegrityError:
        row = find_email_user(email)
        assert row is not None
        return int(row["id"])


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def cookie_header(name: str, value: str, max_age: int, path: str = "/") -> str:
    """Значение Set-Cookie: HttpOnly, SameSite=Lax и Secure, если сайт за HTTPS."""
    cookie = SimpleCookie()
    cookie[name] = value
    morsel = cookie[name]
    morsel["path"] = path
    morsel["max-age"] = max_age
    morsel["httponly"] = True
    morsel["samesite"] = "Lax"
    if config.COOKIE_SECURE:
        morsel["secure"] = True
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
    return cookie_header(config.SESSION_COOKIE_NAME, token, config.SESSION_LIFETIME_SECONDS)


def end_session(request: Request) -> str:
    """Удаляет текущую сессию и возвращает Set-Cookie, стирающий cookie в браузере."""
    if request.session_key:
        database.delete_session(request.session_key)
    return cookie_header(config.SESSION_COOKIE_NAME, "", 0)


def attach_user(request: Request) -> None:
    """Определяет пользователя по cookie и записывает его в request.user."""
    token = request.cookies.get(config.SESSION_COOKIE_NAME, "")
    if not token:
        return
    key = _token_hash(token)
    found = database.get_session_user(key, time.time())
    if found is None:
        return
    user, csrf_token = found
    if is_blocked_demo_admin(user.login, user.role):
        return
    request.user, request.csrf_token = user, csrf_token
    request.session_key = key


def attach_guest_csrf(request: Request) -> None:
    """Гостю — csrf-токен из cookie; если cookie нет, выдаёт новый (сервер запишет его в ответ)."""
    if request.user is not None:
        return
    token = request.cookies.get(config.GUEST_CSRF_COOKIE_NAME, "")
    if not GUEST_TOKEN_RE.fullmatch(token):
        token = secrets.token_urlsafe(32)
        request.new_guest_csrf = token
    request.csrf_token = token


def guest_csrf_cookie(token: str) -> str:
    """Set-Cookie с csrf-токеном гостя (для форм входа, регистрации и восстановления)."""
    return cookie_header(config.GUEST_CSRF_COOKIE_NAME, token, config.SESSION_LIFETIME_SECONDS)


GUEST_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{43}")


def check_csrf(request: Request) -> bool:
    """Проверяет, что форма содержит csrf-токен текущей сессии (защита от подделки запросов)."""
    sent = request.form_value("csrf_token")
    return bool(request.csrf_token) and hmac.compare_digest(sent, request.csrf_token)


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
    """Регистрирует пользователя, который входит только через Telegram."""
    login = f"tg{telegram_id}"
    password_hash, salt = hash_password(secrets.token_urlsafe(32))
    clean_name = " ".join(name.split())[:NAME_MAX_LENGTH] or TELEGRAM_NAME_FALLBACK
    try:
        user_id = database.create_user(clean_name, login, password_hash, salt, time.time())
        database.set_user_language(user_id, i18n.get_language())
    except sqlite3.IntegrityError:
        row = database.get_user_credentials(login)
        assert row is not None
        user_id = row["id"]
    database.bind_telegram(user_id, telegram_id)
    return user_id
