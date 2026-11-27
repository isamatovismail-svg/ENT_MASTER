"""Вход на сайт по одноразовой ссылке из Telegram-бота: /tg/login?token=…

GET только показывает страницу и НЕ тратит токен: ссылки заранее открывают
сервисы превью и браузеры. Вход выполняется кнопкой (POST):
- Telegram уже привязан → «Войти»;
- не привязан → «Создать аккаунт и войти» в один клик, «Привязать к текущему аккаунту»
  (если на сайте уже выполнен вход) или привязка по логину и паролю.
"""

from app import auth, database, views
from app.templates import SafeHTML, fragment, render
from app.web import Request, Response, redirect
from app.i18n import t

INVALID_LINK = (
    "Ссылка для входа недействительна: она одноразовая и действует "
    "10 минут. Получите новую в боте — команда /start, кнопка «Войти на сайт»."
)


def _page(request: Request, token: str, info, errors: list[str], login: str = "",
          status: int = 200) -> Response:
    """Страница подтверждения входа через Telegram."""
    linked = database.get_user_by_telegram(info["telegram_id"])
    current = SafeHTML("")
    if request.user is not None and (linked is None or linked.id != request.user.id):
        current = fragment(
            '<form method="post" action="/tg/login" class="tg-option">$csrf'
            '<input type="hidden" name="token" value="$token">'
            '<button type="submit" name="action" value="current" class="btn btn-secondary btn-block">'
            "Привязать к моему аккаунту «$name»</button></form>",
            csrf=views._csrf_field(request), token=token, name=request.user.name,
        )
    if linked is not None:
        main = fragment(
            '<p>Этот Telegram привязан к аккаунту <strong>$name</strong>.</p>'
            '<form method="post" action="/tg/login"><input type="hidden" name="token" value="$token">'
            '<button type="submit" name="action" value="login" class="btn btn-primary btn-block btn-lg">'
            "Войти</button></form>",
            name=linked.name, token=token,
        )
        divider = t("привязать к другому аккаунту?")
    else:
        main = fragment(
            '<form method="post" action="/tg/login" class="tg-option">'
            '<input type="hidden" name="token" value="$token">'
            '<button type="submit" name="action" value="new" class="btn btn-primary btn-block btn-lg">'
            "🚀 Создать аккаунт и войти</button>"
            '<p class="muted small">Новый аккаунт, вход в него — через бота.</p></form>',
            token=token,
        )
        divider = t("уже есть аккаунт на сайте?")
    actions = render(
        "tg_link_options.html", main=main, current=current, divider=divider, token=token,
        login=login, errors=views._errors_block(errors),
    )
    content = render("tg_login.html", telegram_name=info["telegram_name"], actions=actions)
    return views.page(request, t("Вход через Telegram"), content, status)


def tg_login_page(request: Request) -> Response:
    """GET /tg/login?token=… — подтверждение входа (токен ещё не тратится)."""
    token = request.query_value("token")
    info = auth.peek_telegram_token(token)
    if info is None:
        return views.error_page(request, 400, t(INVALID_LINK))
    return _page(request, token, info, [])


def tg_login_submit(request: Request) -> Response:
    """POST /tg/login — вход, регистрация или привязка Telegram к аккаунту."""
    token = request.form_value("token")
    info = auth.peek_telegram_token(token)
    if info is None:
        return views.error_page(request, 400, t(INVALID_LINK))
    telegram_id = info["telegram_id"]
    action = request.form_value("action")
    linked = database.get_user_by_telegram(telegram_id)

    if action == "link":
        login = request.form_value("login")
        user = auth.authenticate(login, request.form_value("password"))
        if user is None:
            return _page(request, token, info, [t("Неверная почта/телефон или пароль.")], login, 400)
        if not user.email_verified:
            return _page(request, token, info,
                         [t("Сначала подтвердите почту: войдите на сайт и введите код из письма.")],
                         login, 400)
        user_id = user.id
    elif action == "current":
        if request.user is None or not auth.check_csrf(request):
            return views.error_page(request, 403, views.MESSAGES["csrf"][1])
        user_id = request.user.id
    elif action == "login" and linked is None:
        return _page(request, token, info, [], status=400)
    elif action in ("login", "new"):
        user_id = linked.id if linked is not None else 0
    else:
        return _page(request, token, info, [], status=400)

    target = database.get_user(user_id) if user_id else None
    if target is not None and auth.is_blocked_demo_admin(target["login"], target["role"]):
        return views.error_page(request, 403, views.DEMO_ADMIN_BLOCKED)

    # Токен тратится только здесь — один раз, даже если форму отправят дважды.
    if not auth.use_telegram_token(token):
        return views.error_page(request, 400, t(INVALID_LINK))
    if action == "new" and not user_id:
        user_id = auth.create_telegram_user(telegram_id, info["telegram_name"])
    elif action in ("link", "current"):
        database.bind_telegram(user_id, telegram_id)

    if request.session_key:
        database.delete_session(request.session_key)
    return redirect("/dashboard?msg=tg_linked", cookies=[auth.start_session(user_id)])
