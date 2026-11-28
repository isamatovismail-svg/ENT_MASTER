"""Страницы аккаунта: подтверждение почты кодом, восстановление пароля, вход через Google.

Все формы здесь — для гостей (как вход и регистрация), поэтому csrf-токена сессии
у них нет. Подобрать код нельзя: после EMAIL_CODE_MAX_ATTEMPTS неверных вводов код
перестаёт действовать, а новый можно запросить не чаще раза в минуту.
"""

import hmac
import logging
import secrets
from http.cookies import SimpleCookie
from urllib.parse import urlencode

from app import config
from app.core import auth, database, google_auth, mailer
from app.web import views
from app.web.render import render
from app.web.http import Request, Response, redirect
from app.i18n import t

logger = logging.getLogger(__name__)


def _wait_error(seconds: int) -> str:
    """Сообщение «код можно запросить через N секунд»."""
    return t("Новый код можно запросить через {seconds} с. Пока используйте код из последнего письма.", seconds=seconds)


def _login_now(request: Request, user_id: int, location: str) -> Response:
    """Создаёт новую сессию (старая, если была, удаляется) и перенаправляет."""
    if request.session_key:
        database.delete_session(request.session_key)
    return redirect(location, cookies=[auth.start_session(user_id)])


# ── Подтверждение почты ──────────────────────────────────────────────────────

def _verify_form(request: Request, email: str, errors: list[str], status: int = 200) -> Response:
    """Страница ввода кода из письма."""
    content = render(
        "verify.html",
        errors=views._errors_block(errors),
        email=email,
        minutes=config.EMAIL_CODE_MINUTES,
    )
    return views.page(request, t("Подтверждение почты"), content, status)


def verify_page(request: Request) -> Response:
    """GET /verify?email=… — форма ввода кода подтверждения."""
    email = auth.normalize_email(request.query_value("email"))
    if not email:
        return redirect("/register")
    return _verify_form(request, email, [])


def verify_submit(request: Request) -> Response:
    """POST /verify — проверка кода; при успехе аккаунт активен и пользователь входит."""
    email = auth.normalize_email(request.form_value("email"))
    user = auth.find_email_user(email)
    if user is not None and user["email_verified"]:
        return redirect("/login?" + urlencode({"msg": "already_verified", "login": email}))
    try:
        user_id = auth.verify_email(email, request.form_value("code"))
    except auth.ValidationError as error:
        return _verify_form(request, email, error.errors, 400)
    return _login_now(request, user_id, "/dashboard?msg=verified")


def verify_resend(request: Request) -> Response:
    """POST /verify/resend — «Отправить код ещё раз» (не чаще раза в минуту)."""
    email = auth.normalize_email(request.form_value("email"))
    user = auth.find_email_user(email)
    if user is None:
        return redirect("/register")
    if user["email_verified"]:
        return redirect("/login?" + urlencode({"msg": "already_verified", "login": email}))
    try:
        wait = auth.send_email_code(user["id"], email, auth.VERIFY)
    except mailer.MailError:
        return _verify_form(request, email, [views.MAIL_FAILED], 503)
    if wait:
        return _verify_form(request, email, [_wait_error(wait)], 429)
    return redirect(views.verify_url(email, "code_sent"))


# ── Восстановление пароля ────────────────────────────────────────────────────

def _forgot_form(request: Request, email: str, errors: list[str], status: int = 200) -> Response:
    """Страница «Забыли пароль?»: ввод почты."""
    content = render("forgot.html", errors=views._errors_block(errors), email=email)
    return views.page(request, t("Восстановление пароля"), content, status)


def forgot_page(request: Request) -> Response:
    """GET /forgot — форма запроса кода для смены пароля."""
    return _forgot_form(request, request.query_value("email"), [])


def forgot_submit(request: Request) -> Response:
    """POST /forgot — отправка кода на почту.

    Ответ одинаковый, есть ли такой аккаунт или нет: по нему нельзя узнать,
    кто зарегистрирован на сайте.
    """
    email = auth.normalize_email(request.form_value("email"))
    if not auth.EMAIL_RE.match(email):
        return _forgot_form(request, email, [t("Введите почту, указанную при регистрации.")], 400)
    user = auth.find_email_user(email)
    if user is not None:
        try:
            # Если код отправляли меньше минуты назад, действует прежний код
            # (ответ тот же, чтобы не выдавать, что аккаунт существует).
            auth.send_email_code(user["id"], email, auth.RESET)
        except mailer.MailError:
            return _forgot_form(request, email, [views.MAIL_FAILED], 503)
    return redirect("/reset?" + urlencode({"email": email, "msg": "reset_sent"}))


def _reset_form(request: Request, email: str, errors: list[str], status: int = 200) -> Response:
    """Страница ввода кода и нового пароля."""
    content = render(
        "reset.html",
        errors=views._errors_block(errors),
        email=email,
        minutes=config.EMAIL_CODE_MINUTES,
        min_length=config.PASSWORD_MIN_LENGTH,
    )
    return views.page(request, t("Новый пароль"), content, status)


def reset_page(request: Request) -> Response:
    """GET /reset?email=… — ввод кода из письма и нового пароля."""
    email = auth.normalize_email(request.query_value("email"))
    if not email:
        return redirect("/forgot")
    return _reset_form(request, email, [])


def reset_submit(request: Request) -> Response:
    """POST /reset — смена пароля по коду; все старые сессии завершаются, пользователь входит."""
    email = auth.normalize_email(request.form_value("email"))
    try:
        user_id = auth.reset_password(
            email, request.form_value("code"),
            request.form_value("password"), request.form_value("password2"),
        )
    except auth.ValidationError as error:
        return _reset_form(request, email, error.errors, 400)
    return _login_now(request, user_id, "/dashboard?msg=password_changed")


# ── Вход через Google ────────────────────────────────────────────────────────

def _state_cookie(value: str, max_age: int) -> str:
    """Cookie со state для OAuth: HttpOnly, SameSite=Lax (Google возвращает GET-переходом)."""
    cookie = SimpleCookie()
    cookie[config.OAUTH_STATE_COOKIE_NAME] = value
    morsel = cookie[config.OAUTH_STATE_COOKIE_NAME]
    morsel["path"] = "/auth/google"
    morsel["max-age"] = max_age
    morsel["httponly"] = True
    morsel["samesite"] = "Lax"
    if config.COOKIE_SECURE:
        morsel["secure"] = True  # на сервере с HTTPS cookie не уходит по незащищённому http
    return morsel.OutputString()


def google_start(request: Request) -> Response:
    """GET /auth/google — перенаправление на страницу входа Google."""
    if not google_auth.enabled():
        return redirect("/login?msg=google_off")
    state = secrets.token_urlsafe(32)
    return redirect(
        google_auth.authorization_url(state),
        cookies=[_state_cookie(state, config.OAUTH_STATE_LIFETIME_SECONDS)],
    )


def google_callback(request: Request) -> Response:
    """GET /auth/google/callback — Google вернул пользователя: проверка state, обмен code."""
    clear_state = _state_cookie("", 0)
    if not google_auth.enabled():
        return redirect("/login?msg=google_off")
    if request.query_value("error"):
        # Пользователь нажал «Отмена» на странице Google.
        return redirect("/login", cookies=[clear_state])
    expected = request.cookies.get(config.OAUTH_STATE_COOKIE_NAME, "")
    state = request.query_value("state")
    if not expected or not hmac.compare_digest(state, expected):
        return redirect("/login?msg=google_failed", cookies=[clear_state])
    try:
        info = google_auth.exchange_code(request.query_value("code"))
    except google_auth.GoogleAuthError as error:
        logger.warning("Вход через Google не удался: %s", error)
        return redirect("/login?msg=google_failed", cookies=[clear_state])
    user_id = auth.google_user(info.email, info.first_name, info.last_name)
    if request.session_key:
        database.delete_session(request.session_key)
    return redirect("/dashboard", cookies=[clear_state, auth.start_session(user_id)])
