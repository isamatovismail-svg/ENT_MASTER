"""Обработчики страниц: каждая функция получает Request и возвращает Response.

Страницы собираются из шаблонов (templates/*.html). Мелкие повторяющиеся
куски HTML (строки таблиц, карточки, задания) собираются здесь функцией
fragment(), которая экранирует все подставляемые значения.

Важно: Content-Security-Policy запрещает атрибут style, поэтому цвета и ширины
задаются только классами (subj-<код предмета>, p-<процент>) и элементом <progress>.
"""

import time
from collections.abc import Callable
from datetime import datetime
from functools import wraps
from urllib.parse import quote, urlencode

import config
from app import ads, auth, database, ent_logic, google_auth, i18n, mailer, notifications, schools
from app.database import Attempt, AttemptQuestion
from app.templates import SafeHTML, fragment, join, render
from app.web import Request, Response, html_response, redirect
from app.i18n import t

# Сообщения, которые можно показать через параметр ?msg=код.
# В URL передаётся только код, поэтому подставить свой текст через ссылку нельзя.
MESSAGES: dict[str, tuple[str, str]] = {
    "code_sent": ("success", "Мы отправили 6-значный код на вашу почту. Проверьте и папку «Спам»."),
    "verify_needed": (
        "info", "Почта ещё не подтверждена. Введите код из письма — мы отправили его на вашу почту.",
    ),
    "verified": ("success", "Почта подтверждена. Добро пожаловать в ENT MASTER!"),
    "already_verified": ("info", "Почта уже подтверждена — войдите в аккаунт."),
    "reset_sent": (
        "info",
        "Если аккаунт с такой почтой есть, мы отправили на неё код для смены пароля.",
    ),
    "password_changed": ("success", "Пароль изменён. Вы вошли в аккаунт."),
    "google_off": ("info", "Вход через Google пока не настроен."),
    "google_failed": ("error", "Не удалось войти через Google. Попробуйте ещё раз."),
    "school_requested": (
        "success", "Заявка отправлена. Учитель школы увидит ваши результаты после подтверждения.",
    ),
    "school_same": ("info", "Вы уже в этой школе."),
    "school_left": ("info", "Вы вышли из школы."),
    "member_approved": ("success", "Ученик подтверждён — теперь видны его результаты."),
    "member_rejected": ("info", "Заявка отклонена."),
    "member_removed": ("info", "Ученик исключён из школы."),
    "assignment_created": ("success", "Задание выдано."),
    "assignment_deleted": ("info", "Задание удалено."),
    "banner_saved": ("success", "Баннер сохранён."),
    "banner_deleted": ("info", "Баннер удалён."),
    "review_approved": ("success", "Вопрос одобрен и добавлен в общий банк."),
    "review_rejected": ("info", "Вопрос отклонён, учитель увидит ваш комментарий."),
    "review_comment_needed": ("error", "Чтобы отклонить вопрос, напишите комментарий для учителя."),
    "review_missing": ("error", "Этого вопроса уже нет в очереди — возможно, его уже проверили."),
    "tq_submitted": ("success", "Вопрос отправлен на проверку. Пока его не одобрят, в тесты он не попадает."),
    "tq_resubmitted": ("success", "Исправленный вопрос снова отправлен на проверку."),
    "tq_deleted": ("info", "Вопрос удалён."),
    "tq_locked": ("error", "Одобренный вопрос изменить или удалить нельзя — он уже в общем банке."),
    "logged_out": ("info", "Вы вышли из аккаунта."),
    "language_saved": ("success", "Язык сохранён: интерфейс и вопросы теперь на выбранном языке."),
    "login_required": ("info", "Войдите, чтобы открыть эту страницу."),
    "saved": ("success", "Ответы сохранены."),
    "resume": ("info", "У вас уже есть незавершённый пробный ЕНТ — продолжайте его."),
    "time_up": (
        "warning",
        "Время вышло — тест завершён автоматически. "
        "Засчитаны ответы, сохранённые до окончания времени.",
    ),
    "bad_pair": ("error", "Выберите пару профильных предметов из списка."),
    "bad_subject": ("error", "Выберите предмет из списка."),
    "no_questions": ("error", "В банке нет вопросов для этого теста. Запустите python seed.py."),
    "csrf": ("error", "Форма устарела. Обновите страницу и попробуйте ещё раз."),
    "tg_linked": ("success", "Готово! Telegram привязан — результаты из бота сохраняются в этот аккаунт."),
    "q_created": ("success", "Вопрос добавлен в банк и уже участвует в случайной выборке тестов."),
    "q_updated": ("success", "Изменения вопроса сохранены."),
    "q_deleted": ("success", "Вопрос удалён из банка."),
    "q_archived": (
        "success",
        "Вопрос убран из банка. Он был в попытках учеников, поэтому его разбор в старых "
        "попытках сохранён.",
    ),
    "q_missing": ("error", "Такого вопроса нет — возможно, его уже удалили."),
}

DEMO_ADMIN_BLOCKED = ("Демо-администратор не может войти, пока сайт открыт через интернет "
                      "(режим показа). Войдите как демо-учитель или демо-ученик.")

MAIL_FAILED = "Не удалось отправить письмо с кодом. Попробуйте ещё раз через минуту."

MODE_NAMES = i18n.Translated({ent_logic.MOCK: "Пробный ЕНТ", ent_logic.PRACTICE: "Тренировка"})

# Порог «сильного» предмета в кабинете: от 70% баллов.
STRONG_PERCENT = 70

View = Callable[..., Response]


# ── Общие помощники ──────────────────────────────────────────────────────────

def _format_datetime(timestamp: float | None) -> str:
    """Дата и время в формате «25.11.2026 14:30» (местное время)."""
    if timestamp is None:
        return "—"
    return datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y %H:%M")


def _format_duration(seconds: int) -> str:
    """Длительность в виде «3 ч 05 мин» или «12 мин»."""
    minutes_total = seconds // 60
    hours, minutes = divmod(minutes_total, 60)
    if hours:
        return t("{hours} ч {minutes} мин", hours=hours, minutes=f"{minutes:02d}")
    if minutes_total:
        return t("{minutes} мин", minutes=minutes)
    return t("меньше минуты")


def _percent(score: int, max_score: int) -> int:
    """Процент набранных баллов (целое число)."""
    return round(score * 100 / max_score) if max_score else 0


def _percent_class(percent: int) -> str:
    """Класс p-0 … p-100 с шагом 5 — для кольца с процентом (стили без атрибута style)."""
    return f"p-{min(100, max(0, round(percent / 5) * 5))}"


def _safe_next(value: str) -> str:
    """Разрешает перенаправление только на страницы этого же сайта."""
    if value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return "/dashboard"


def _csrf_field(request: Request) -> SafeHTML:
    """Скрытое поле с csrf-токеном для POST-форм."""
    return fragment(
        '<input type="hidden" name="csrf_token" value="$token">', token=request.csrf_token
    )


def _notice(kind: str, text: str) -> SafeHTML:
    """Цветное уведомление (success, info, warning, error)."""
    return fragment('<div class="notice notice-$kind">$text</div>', kind=kind, text=text)


def _errors_block(errors: list[str]) -> SafeHTML:
    """Список ошибок формы."""
    if not errors:
        return SafeHTML("")
    items = join(fragment("<li>$error</li>", error=error) for error in errors)
    return fragment(
        '<div class="notice notice-error"><ul class="error-list">$items</ul></div>', items=items
    )


def _icon(code: str, extra: str = "") -> SafeHTML:
    """Цветной значок предмета с эмодзи."""
    return fragment(
        '<span class="subj-icon subj-$code$extra" aria-hidden="true">$icon</span>',
        code=code,
        extra=SafeHTML(f" {extra}" if extra else ""),
        icon=config.SUBJECTS[code].icon,
    )


def _bell(request: Request) -> SafeHTML:
    """Колокольчик со счётчиком непрочитанных уведомлений."""
    assert request.user is not None
    unread = database.unread_notifications(request.user.id)
    return fragment(
        '<a class="bell$cls" href="/notifications" aria-label="Уведомления: $count">🔔$badge</a>',
        cls=" bell-unread" if unread else "", count=unread,
        badge=fragment('<span class="bell-count">$n</span>', n=unread if unread < 100 else "99+")
        if unread else SafeHTML(""),
    )


def _nav(request: Request) -> SafeHTML:
    """Меню в шапке: у гостя, ученика, учителя и главного администратора — своё."""
    if request.user is None:
        return fragment('<a href="/login">Войти</a>'
            '<a class="btn btn-primary btn-sm" href="/register">Регистрация</a>')
    logout = fragment(
        '<form method="post" action="/logout" class="nav-form">$csrf'
        '<button type="submit" class="btn btn-ghost btn-sm">Выйти</button></form>',
        csrf=_csrf_field(request),
    )
    if request.user.is_teacher:
        # Учителю — только его работа: ученики, задания, свои вопросы.
        return fragment(
            '<a href="/teacher">👥 Ученики</a>'
            '<a href="/teacher/assignments">📋 Задания</a>'
            '<a href="/teacher/questions">📝 Мои вопросы</a>'
            "$bell"
            '<a href="/profile">👤 Профиль</a>$logout',
            bell=_bell(request), logout=logout,
        )
    return fragment(
        '<a href="/dashboard">🏠 Кабинет</a>'
        '<a href="/mock">📝 Пробный ЕНТ</a>'
        '<a href="/practice">🎯 Тренировка</a>'
        '<a href="/history">📈 История</a>'
        "$bell"
        '<a href="/profile">👤 Профиль</a>'
        "$admin$logout",
        bell=_bell(request),
        admin=(fragment('<a class="nav-admin" href="/admin">⚙️ Админка</a>') if request.user.is_admin else SafeHTML("")),
        logout=logout,
    )


def request_language(request: Request, accept_language: str = "") -> str:
    """Язык страницы: у вошедшего — из профиля, у гостя — из cookie, иначе по браузеру (kk/ru)."""
    if request.user is not None:
        return i18n.normalize(request.user.language)
    chosen = request.cookies.get(i18n.COOKIE_NAME, "")
    if chosen in i18n.LANGUAGES:
        return chosen
    return i18n.KK if accept_language.lower().startswith("kk") else i18n.DEFAULT


def _language_cookie(lang: str) -> str:
    """Set-Cookie с выбранным языком (для гостя; год, только этот сайт)."""
    return (f"{i18n.COOKIE_NAME}={lang}; Path=/; Max-Age={i18n.COOKIE_MAX_AGE}; SameSite=Lax"
            + ("; Secure" if config.COOKIE_SECURE else ""))


def _current_url(request: Request) -> str:
    """Адрес текущей страницы (для возврата после смены языка)."""
    query = {key: value for key, value in request.query.items() if key != "msg"}
    return request.path + ("?" + urlencode(query, doseq=True) if query else "")


def _language_switch(request: Request) -> SafeHTML:
    """Переключатель РУС / ҚАЗ в шапке."""
    current = i18n.get_language()
    back = quote(_current_url(request), safe="")
    return fragment(
        '<nav class="lang-switch" aria-label="Тіл / Язык">$links</nav>',
        links=join(
            fragment('<a class="lang$cls" href="/lang/$code?next=$back" hreflang="$code" lang="$code">$label</a>',
                     cls=" lang-active" if code == current else "", code=code, back=SafeHTML(back),
                     label=i18n.SWITCH_LABELS[code])
            for code in i18n.LANGUAGES
        ),
    )


def language_options(selected: str) -> SafeHTML:
    """Радиокнопки «Язык обучения» (регистрация и профиль)."""
    return join(
        fragment('<label class="check"><input type="radio" name="language" value="$code"$checked> $name</label>',
                 code=code, checked=SafeHTML(" checked" if code == selected else ""),
                 name=i18n.LANGUAGE_NAMES[code])
        for code in i18n.LANGUAGES
    )


def page(
    request: Request | None,
    title: str,
    content: SafeHTML,
    status: int = 200,
    notice: SafeHTML | None = None,
) -> Response:
    """Оборачивает содержимое страницы в общий макет base.html."""
    if notice is None:
        notice = SafeHTML("")
        if request is not None:
            message = MESSAGES.get(request.query_value("msg"))
            if message:
                notice = _notice(message[0], t(message[1]))
    request = request if request is not None else Request("GET", "/")
    body = render("base.html", title=title, nav=_nav(request), notice=notice, content=content,
                  html_lang=i18n.get_language(), lang_switch=_language_switch(request))
    return html_response(body, status)


def login_required(view: View) -> View:
    """Декоратор: пускает на страницу только вошедших пользователей.

    Для POST-запросов дополнительно проверяет csrf-токен формы.
    """

    @wraps(view)
    def wrapper(request: Request, **kwargs: object) -> Response:
        """Проверяет вход и csrf, затем вызывает исходный обработчик."""
        if request.user is None:
            query = urlencode({"next": request.path, "msg": "login_required"})
            return redirect(f"/login?{query}")
        if request.method == "POST" and not auth.check_csrf(request):
            return error_page(request, 403, t(MESSAGES["csrf"][1]))
        return view(request, **kwargs)

    return wrapper


def student_area(view: View) -> View:
    """Декоратор для страниц ученика (кабинет, тесты, история): учителя отправляет в его кабинет."""

    @wraps(view)
    def wrapper(request: Request, **kwargs: object) -> Response:
        """Учитель видит только свою работу — учеников, задания и вопросы."""
        if request.user is not None and request.user.is_teacher:
            return redirect("/teacher")
        return view(request, **kwargs)

    return login_required(wrapper)


def _user_id(request: Request) -> int:
    """id вошедшего пользователя (вызывается только после login_required)."""
    assert request.user is not None
    return request.user.id


def switch_language(request: Request, code: str) -> Response:
    """GET /lang/<код> — сменить язык: гостю — cookie, вошедшему — ещё и в профиле."""
    if code not in i18n.LANGUAGES:
        return not_found(request)
    if request.user is not None:
        database.set_user_language(request.user.id, code)
    return redirect(_safe_next(request.query_value("next") or "/"), cookies=[_language_cookie(code)])


@login_required
def profile_language(request: Request) -> Response:
    """POST /profile/language — язык обучения из профиля."""
    code = request.form_value("language")
    if code not in i18n.LANGUAGES:
        return error_page(request, 400, t("Выберите язык из списка."))
    database.set_user_language(_user_id(request), code)
    return redirect("/profile?msg=language_saved", cookies=[_language_cookie(code)])


# ── Ошибки ───────────────────────────────────────────────────────────────────

def error_page(request: Request | None, status: int, message: str) -> Response:
    """Страница ошибки с понятным текстом."""
    content = render("error.html", code=status, message=message)
    return page(request, t("Ошибка {status}", status=status), content, status, notice=SafeHTML(""))


def not_found(request: Request | None = None) -> Response:
    """Страница 404."""
    return page(request, t("Страница не найдена"), render("404.html"), 404, notice=SafeHTML(""))


def method_not_allowed(request: Request) -> Response:
    """Ответ 405: страница существует, но не поддерживает этот метод."""
    return error_page(request, 405, t("Этот адрес не поддерживает такой запрос."))


def server_error() -> Response:
    """Страница 500 без технических подробностей (они записаны в лог сервера)."""
    return error_page(None, 500, t("Что-то пошло не так. Попробуйте обновить страницу чуть позже."))


# ── Главная, регистрация, вход, выход ───────────────────────────────────────

def landing(request: Request) -> Response:
    """Главная: первый экран, устройство ЕНТ и объяснение профильной пары."""
    compulsory_cards = join(
        fragment(
            '<article class="exam-card subj-$code">$icon<span class="tag">Обязательный</span>'
            "<h3>$name</h3><p><b>$count</b> заданий · <b>$score</b> баллов</p></article>",
            code=code,
            icon=_icon(code),
            name=config.SUBJECTS[code].name,
            count=config.SUBJECTS[code].question_count,
            score=config.SUBJECTS[code].max_score,
        )
        for code in config.COMPULSORY_CODES
    )
    profile = config.SUBJECTS[config.PROFILE_PAIRS[0][0]]
    profile_cards = join(
        fragment(
            '<article class="exam-card exam-card-profile">'
            '<span class="subj-icon subj-profile" aria-hidden="true">⭐</span>'
            '<span class="tag">Профильный</span><h3>Профильный предмет $number</h3>'
            "<p><b>$count</b> заданий · <b>$score</b> баллов</p></article>",
            number=number, count=profile.question_count, score=profile.max_score,
        )
        for number in (1, 2)
    )
    pair_chips = join(
        fragment(
            '<li class="pair-chip">$icon1<span>$name1</span><b>+</b>$icon2<span>$name2</span></li>',
            icon1=_icon(first), name1=config.SUBJECTS[first].name,
            icon2=_icon(second), name2=config.SUBJECTS[second].name,
        )
        for index, (first, second) in enumerate(config.PROFILE_PAIRS)
        if index in config.pairs_for(i18n.get_language())
    )
    logged_in = request.user is not None
    content = render(
        "landing.html",
        cta_href="/dashboard" if logged_in else "/register",
        cta_label=t("Перейти в кабинет") if logged_in else t("Попробовать бесплатно"),
        compulsory_cards=compulsory_cards,
        profile_cards=profile_cards,
        pair_chips=pair_chips,
        total_questions=config.MOCK_TOTAL_QUESTIONS,
        max_score=config.MOCK_MAX_SCORE,
        duration_hours=config.MOCK_DURATION_MINUTES // 60,
        pairs_count=len(config.pairs_for(i18n.get_language())),
        subjects_count=len(config.SUBJECTS),
        profile_questions=profile.question_count,
        profile_score=profile.max_score,
        ad=ads.banner_block("landing", request.user),
    )
    return page(request, t("Подготовка к ЕНТ"), content)


def google_button() -> SafeHTML:
    """Кнопка «Войти через Google»: ссылка, если ключи заданы в .env, иначе неактивна."""
    if google_auth.enabled():
        return fragment('<a class="btn btn-google btn-block" href="/auth/google">'
            '<span class="google-mark">G</span> Войти через Google</a>')
    return fragment('<button type="button" class="btn btn-google btn-block" disabled>'
        '<span class="google-mark">G</span> Войти через Google <span class="soon">скоро</span>'
        "</button>")


def _register_form(request: Request, errors: list[str]) -> Response:
    """Отрисовывает страницу регистрации; введённые значения (кроме паролей) сохраняются."""
    content = render(
        "register.html",
        errors=_errors_block(errors),
        first_name=request.form_value("first_name"),
        last_name=request.form_value("last_name"),
        email=request.form_value("email"),
        phone=request.form_value("phone"),
        school_city=request.form_value("school_city"),
        school_name=request.form_value("school_name"),
        min_length=config.PASSWORD_MIN_LENGTH,
        google=google_button(),
        language_options=language_options(i18n.normalize(request.form_value("language") or i18n.get_language())),
    )
    return page(request, t("Регистрация"), content, 400 if errors else 200)


def verify_url(email: str, msg: str = "") -> str:
    """Адрес страницы ввода кода подтверждения."""
    query = {"email": email, **({"msg": msg} if msg else {})}
    return "/verify?" + urlencode(query)


def register_page(request: Request) -> Response:
    """GET /register — форма регистрации."""
    if request.user is not None:
        return redirect("/dashboard")
    return _register_form(request, [])


def register_submit(request: Request) -> Response:
    """POST /register — проверка полей и создание аккаунта."""
    if request.user is not None:
        return redirect("/dashboard")
    try:
        user_id = auth.register_user(
            request.form_value("first_name"), request.form_value("last_name"),
            request.form_value("email"), request.form_value("phone"),
            request.form_value("password"), request.form_value("password2"),
            school_city=request.form_value("school_city"),
            school_name=request.form_value("school_name"),
            language=request.form_value("language") or i18n.get_language(),
        )
    except auth.ValidationError as error:
        return _register_form(request, error.errors)
    email = auth.normalize_email(request.form_value("email"))
    try:
        auth.send_email_code(user_id, email, auth.VERIFY)
    except mailer.MailError:
        return _register_form(request, [t(MAIL_FAILED)])
    # Если код уже отправляли меньше минуты назад, действует прежний код.
    return redirect(verify_url(email, "code_sent"))


def _login_form(request: Request, errors: list[str], login: str, next_url: str) -> Response:
    """Отрисовывает страницу входа."""
    content = render(
        "login.html", errors=_errors_block(errors), login=login, next=next_url,
        google=google_button(),
    )
    return page(request, t("Вход"), content, 400 if errors else 200)


def login_page(request: Request) -> Response:
    """GET /login — форма входа."""
    if request.user is not None:
        return redirect("/dashboard")
    return _login_form(
        request, [], request.query_value("login"), _safe_next(request.query_value("next"))
    )


def login_submit(request: Request) -> Response:
    """POST /login — проверка пароля и создание сессии."""
    login = request.form_value("login")
    next_url = _safe_next(request.form_value("next"))
    if not login.strip() or not request.form_value("password"):
        return _login_form(request, [t("Введите почту (или телефон) и пароль.")], login, next_url)
    user = auth.authenticate(login, request.form_value("password"))
    if user is None:
        return _login_form(request, [t("Неверная почта/телефон или пароль.")], login, next_url)
    if auth.is_blocked_demo_admin(user.login, user.role):
        return _login_form(request, [t(DEMO_ADMIN_BLOCKED)], login, next_url)
    if not user.email_verified:
        # Пароль верный, но почта не подтверждена: отправляем код (если не отправляли
        # только что) и ведём на страницу ввода кода.
        try:
            auth.send_email_code(user.id, user.login, auth.VERIFY)
        except mailer.MailError:
            return _login_form(request, [t(MAIL_FAILED)], login, next_url)
        return redirect(verify_url(user.login, "verify_needed"))
    # При входе всегда создаётся новая сессия, старая (если была) удаляется.
    if request.session_key:
        database.delete_session(request.session_key)
    return redirect(next_url, cookies=[auth.start_session(user.id)])


def logout(request: Request) -> Response:
    """POST /logout — выход из аккаунта."""
    if request.user is None:
        return redirect("/")
    if not auth.check_csrf(request):
        return error_page(request, 403, t(MESSAGES["csrf"][1]))
    return redirect("/?msg=logged_out", cookies=[auth.end_session(request)])


# ── Личный кабинет ───────────────────────────────────────────────────────────

def _attempt_title(attempt: Attempt) -> str:
    """Короткое описание попытки: режим и предметы."""
    if attempt.mode == ent_logic.MOCK:
        profile_codes = attempt.subjects[len(config.COMPULSORY_CODES):]
        profile = [config.SUBJECTS[code].name for code in profile_codes]
        return t("Пробный ЕНТ: ") + " + ".join(profile)
    return t("Тренировка: ") + config.SUBJECTS[attempt.subjects[0]].name


def _attempt_icon(attempt: Attempt) -> SafeHTML:
    """Значок попытки: у тренировки — значок предмета, у пробного ЕНТ — общий."""
    if attempt.mode == ent_logic.PRACTICE:
        return _icon(attempt.subjects[0])
    return SafeHTML('<span class="subj-icon subj-mock" aria-hidden="true">📝</span>')


def _attempt_url(attempt: Attempt) -> str:
    """Куда вести, чтобы продолжить незавершённую попытку."""
    if attempt.mode == ent_logic.PRACTICE:
        return f"/practice/{attempt.id}"
    return f"/attempt/{attempt.id}/{attempt.subjects[0]}"


def _stat_card(icon: str, kind: str, title: str, value: object, unit: str, note: str) -> SafeHTML:
    """Карточка с одним числом для кабинета."""
    return fragment(
        '<article class="stat-card stat-$kind"><span class="stat-icon" aria-hidden="true">$icon</span>'
        '<p class="stat-title">$title</p>'
        '<p class="stat-value">$value <span>$unit</span></p>'
        '<p class="stat-note">$note</p></article>',
        icon=icon, kind=kind, title=title, value=value, unit=unit, note=note,
    )


def _strength_rows(items: list[ent_logic.SubjectStrength], empty: str) -> SafeHTML:
    """Список предметов с полосой процента."""
    if not items:
        return fragment('<p class="muted small">$empty</p>', empty=empty)
    return fragment(
        '<ul class="strength-list">$rows</ul>',
        rows=join(
            fragment(
                '<li class="subj-$code">$icon<div class="strength-body">'
                '<div class="strength-top"><span>$name</span><b>$percent%</b></div>'
                '<progress max="100" value="$percent">$percent%</progress>'
                '<small class="muted">заданий решено: $count</small></div></li>',
                code=item.code, icon=_icon(item.code), name=item.name,
                percent=item.percent, count=item.questions,
            )
            for item in items
        ),
    )


def topic_rows(items: list[ent_logic.TopicStrength], empty: str) -> SafeHTML:
    """Список тем спецификации с процентом (слабые темы ученика)."""
    if not items:
        return fragment('<p class="muted small">$empty</p>', empty=empty)
    return fragment(
        '<ul class="strength-list">$rows</ul>',
        rows=join(
            fragment(
                '<li class="subj-$code">$icon<div class="strength-body">'
                '<div class="strength-top"><span>$label <small class="muted">· $subject</small></span>'
                "<b>$percent%</b></div>"
                '<progress max="100" value="$percent">$percent%</progress>'
                '<small class="muted">заданий по теме: $count</small></div></li>',
                code=item.subject, icon=_icon(item.subject), label=item.label,
                subject=config.SUBJECTS[item.subject].name, percent=item.percent, count=item.questions,
            )
            for item in items
        ),
    )


def _attempt_rows(attempts: list[Attempt]) -> SafeHTML:
    """Компактный список попыток (кабинет)."""
    return join(
        fragment(
            '<li><a class="recent-item" href="/result/$id">$icon'
            '<span class="recent-text"><b>$what</b><small>$date</small></span>'
            '<span class="score-pill $grade">$score / $max</span></a></li>',
            id=attempt.id,
            icon=_attempt_icon(attempt),
            what=_attempt_title(attempt),
            date=_format_datetime(attempt.finished_at),
            grade=_grade_class(_percent(attempt.score, attempt.max_score)),
            score=attempt.score,
            max=attempt.max_score,
        )
        for attempt in attempts
    )


def _grade_class(percent: int) -> str:
    """Цвет плашки с результатом: зелёный, жёлтый или красный."""
    if percent >= STRONG_PERCENT:
        return "grade-good"
    if percent >= 40:
        return "grade-mid"
    return "grade-low"


def _continue_blocks(user_id: int) -> SafeHTML:
    """Напоминания о незавершённом пробном ЕНТ и тренировке."""
    blocks = []
    mock = database.get_in_progress_attempt(user_id, ent_logic.MOCK)
    if mock is not None:
        blocks.append(fragment(
            '<div class="notice notice-warning continue">'
            "<div><strong>📝 У вас есть незавершённый пробный ЕНТ.</strong> "
            "Осталось времени: $left.</div>"
            '<a class="btn btn-primary" href="$href">Продолжить</a></div>',
            left=_format_duration(ent_logic.remaining_seconds(mock)),
            href=_attempt_url(mock),
        ))
    practice = database.get_in_progress_attempt(user_id, ent_logic.PRACTICE)
    if practice is not None:
        blocks.append(fragment(
            '<div class="notice notice-info continue">'
            "<div><strong>🎯 Незавершённая тренировка:</strong> $name.</div>"
            '<a class="btn btn-secondary" href="$href">Продолжить</a></div>',
            name=config.SUBJECTS[practice.subjects[0]].name,
            href=_attempt_url(practice),
        ))
    return join(blocks)


def school_status_text(row) -> SafeHTML:
    """Школа пользователя и статус заявки — для кабинета и профиля."""
    if row is None:
        return fragment('<p class="muted">Вы не состоите в школе.</p>')
    title = schools.school_title(row["city"], row["name"])
    if row["role"] == database.ROLE_TEACHER:
        badge = fragment('<span class="badge badge-partial">учитель</span>')
    else:
        badge = {
            database.SCHOOL_APPROVED: fragment('<span class="badge badge-ok">подтверждено</span>'),
            database.SCHOOL_PENDING: fragment('<span class="badge badge-warn">ждёт подтверждения учителя</span>'),
            database.SCHOOL_REJECTED: fragment('<span class="badge badge-wrong">заявка отклонена</span>'),
        }.get(row["school_status"], "")
    return fragment("<p><strong>🏫 $title</strong> $badge</p>", title=title, badge=badge or SafeHTML(""))


def _deadline_text(deadline: float) -> str:
    """Срок задания: «до 30.11.2026»."""
    return t("до {date}", date=_date_only(deadline))


def _date_only(timestamp: float) -> str:
    """Дата «30.11.2026»."""
    return datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y")


ASSIGNMENT_STATUS = {
    "done": ('<span class="badge badge-ok">✅ выполнено</span>'),
    "overdue": ('<span class="badge badge-wrong">не выполнено</span>'),
    "active": ('<span class="badge badge-warn">в процессе</span>'),
}


def _assignment_action(request: Request, assignment) -> str:
    """Что сделать: «Пройдите пробный ЕНТ (Математика + Информатика)» и т. п."""
    if assignment["mode"] == "mock":
        pair = schools.pair_codes(assignment["target"])
        what = " + ".join(config.SUBJECTS[c].name for c in pair) if pair else t("любая пара на ваш выбор")
        return t("Пройдите пробный ЕНТ ({what})", what=what)
    subject = config.SUBJECTS.get(assignment["target"])
    return t("Пройдите тренировку: {subject}", subject=subject.name if subject else assignment["target"])


def _assignments_block(request: Request, user_id: int) -> SafeHTML:
    """Активные задания учителя — наверху кабинета: что сделать, прогресс X из N, срок, кнопка."""
    items = []
    for assignment in database.list_student_assignments(user_id):
        progress = schools.student_progress(assignment, user_id)
        if progress is None or progress.status != "active":
            continue
        left = assignment["deadline"] - time.time()
        urgent = left < notifications.DUE_SOON_SECONDS
        items.append(fragment(
            '<li class="task$cls"><div class="task-main"><strong>$action</strong>'
            '<small class="muted">$title · срок $deadline$urgent</small>'
            '<div class="task-progress"><progress max="$count" value="$done">$done / $count</progress>'
            " <b>$done из $count</b></div></div>"
            '<form method="post" action="/assignments/$aid/start">$csrf'
            '<button type="submit" class="btn btn-primary">Начать →</button></form></li>',
            cls=" task-urgent" if urgent else "", action=_assignment_action(request, assignment),
            title=schools.assignment_title(assignment["mode"], assignment["target"], assignment["count"]),
            deadline=_date_only(assignment["deadline"]),
            urgent=(fragment(' · <span class="badge badge-wrong">меньше суток</span>') if urgent else SafeHTML("")),
            count=assignment["count"], done=progress.done, aid=assignment["id"], csrf=_csrf_field(request),
        ))
    if not items:
        return SafeHTML("")
    return fragment(
        '<section class="card tasks-card"><h2>📋 Задания учителя: $n</h2><ul class="task-list">$items</ul>'
        "</section>",
        n=len(items), items=join(items),
    )


def _school_block(user_id: int) -> SafeHTML:
    """Кабинет ученика: его школа и уже выполненные или просроченные задания."""
    row = database.get_user_school(user_id)
    assignments = database.list_student_assignments(user_id)
    if row is None and not assignments:
        return fragment('<section class="card school-card"><div class="card-title-row"><h2>🏫 Школа</h2>'
            '<a class="link" href="/profile">Указать школу →</a></div>'
            '<p class="muted">Укажите школу — учитель сможет давать задания и видеть ваш прогресс.'
            "</p></section>")
    items = []
    for assignment in assignments:
        progress = schools.student_progress(assignment, user_id)
        if progress is None or progress.status == "active":
            continue  # активные задания — в отдельном блоке наверху
        items.append(fragment(
            '<li class="assignment-item"><div><strong>$title</strong>'
            '<small class="muted">$deadline · сделано $done из $count</small></div>'
            '<progress max="$count" value="$done">$done / $count</progress>$status</li>',
            title=schools.assignment_title(assignment["mode"], assignment["target"],
                                           assignment["count"]),
            deadline=_deadline_text(assignment["deadline"]), done=progress.done,
            count=assignment["count"], status=fragment(ASSIGNMENT_STATUS[progress.status]),
        ))
    tasks = (
        fragment('<h3>Прошлые задания</h3><ul class="assignment-list">$items</ul>',
                 items=join(items[-5:]))
        if items else SafeHTML("")
    )
    return fragment(
        '<section class="card school-card"><div class="card-title-row"><h2>🏫 Школа</h2>'
        '<a class="link" href="/profile">Изменить →</a></div>$status$tasks</section>',
        status=school_status_text(row), tasks=tasks,
    )


@student_area
def assignment_start(request: Request, assignment_id: int) -> Response:
    """POST /assignments/<id>/start — сразу начать именно то, что задал учитель."""
    user_id = _user_id(request)
    assignment = next((a for a in database.list_student_assignments(user_id)
                       if a["id"] == assignment_id), None)
    if assignment is None:
        return not_found(request)
    ent_logic.finish_expired_attempts(user_id)
    if assignment["mode"] == ent_logic.PRACTICE:
        try:
            attempt_id = ent_logic.build_practice(user_id, assignment["target"])
        except (ValueError, ent_logic.TestBuildError):
            return redirect("/practice?msg=no_questions")
        return redirect(f"/practice/{attempt_id}")
    existing = database.get_in_progress_attempt(user_id, ent_logic.MOCK)
    if existing is not None:
        return redirect(f"{_attempt_url(existing)}?msg=resume")
    pair = schools.pair_codes(assignment["target"])
    if pair is None or pair not in config.PROFILE_PAIRS:
        return redirect("/mock")  # любая пара — ученик выбирает сам
    if config.PROFILE_PAIRS.index(pair) not in config.pairs_for(database.get_user_language(user_id)):
        return redirect("/mock?msg=bad_pair")
    try:
        attempt_id = ent_logic.build_mock(user_id, config.PROFILE_PAIRS.index(pair))
    except ent_logic.TestBuildError:
        return redirect("/mock?msg=no_questions")
    attempt = database.get_attempt(attempt_id, user_id)
    assert attempt is not None
    return redirect(_attempt_url(attempt))


# ── Уведомления ──────────────────────────────────────────────────────────────

@login_required
def notifications_page(request: Request) -> Response:
    """GET /notifications — все уведомления, непрочитанные выделены."""
    user_id = _user_id(request)
    notifications.check_due(user_id=user_id)
    items = notifications.for_user(user_id)
    unread = sum(not item.read for item in items)
    rows = join(
        fragment(
            '<li class="notification$cls"><span class="notification-icon" aria-hidden="true">$icon</span>'
            '<div><a class="link" href="/notifications/$id">$text</a>'
            '<small class="muted">$date$status</small></div></li>',
            cls="" if item.read else " notification-unread", icon=item.icon, id=item.id, text=item.text,
            date=_format_datetime(item.created_at), status=t(" · новое") if not item.read else "",
        )
        for item in items
    )
    mark_all = fragment(
        '<form method="post" action="/notifications/read">$csrf'
        '<button type="submit" class="btn btn-ghost btn-sm">✓ Отметить все прочитанными</button></form>',
        csrf=_csrf_field(request),
    ) if unread else SafeHTML("")
    content = fragment(
        '<section class="page-head admin-head"><div><span class="eyebrow">Уведомления</span>'
        "<h1>🔔 Уведомления</h1><p class=\"muted\">Непрочитанных: $unread. Если к аккаунту привязан "
        "Telegram-бот, уведомления приходят и туда.</p></div>$mark_all</section>$list",
        unread=unread, mark_all=mark_all,
        list=fragment('<ul class="notification-list card">$rows</ul>', rows=rows) if items
        else fragment('<div class="card empty">Уведомлений пока нет.</div>'),
    )
    return page(request, t("Уведомления"), content)


@login_required
def notifications_read(request: Request) -> Response:
    """POST /notifications/read — отметить все уведомления прочитанными."""
    database.mark_notifications_read(_user_id(request), time.time())
    return redirect("/notifications")


@login_required
def notification_open(request: Request, notification_id: int) -> Response:
    """GET /notifications/<id> — отметить прочитанным и открыть страницу, о которой уведомление."""
    user_id = _user_id(request)
    row = database.get_notification(notification_id, user_id)
    if row is None:
        return not_found(request)
    database.mark_notifications_read(user_id, time.time(), notification_id)
    return redirect(_safe_next(row["link"]) if row["link"] else "/notifications")


@student_area
def dashboard(request: Request) -> Response:
    """GET /dashboard — личный кабинет со статистикой и последними попытками."""
    user_id = _user_id(request)
    ent_logic.finish_expired_attempts(user_id)
    notifications.check_due(user_id=user_id)

    attempts = database.get_finished_attempts(user_id)
    mocks = [attempt for attempt in attempts if attempt.mode == ent_logic.MOCK]
    practices = len(attempts) - len(mocks)
    best = max(mocks, key=lambda a: (a.score, a.id)) if mocks else None
    last = attempts[0] if attempts else None

    best_card = _stat_card(
        "🏆", "best", t("Лучший балл"),
        best.score if best else "—", t("из {n}", n=config.MOCK_MAX_SCORE),
        t("лучший пробный ЕНТ") if best else t("пройдите пробный ЕНТ"),
    )
    last_card = _stat_card(
        "🕒", "last", t("Последний балл"),
        last.score if last else "—", t("из {n}", n=last.max_score) if last else "",
        _attempt_title(last) if last else t("здесь появится последний тест"),
    )
    total_card = _stat_card(
        "📊", "total", t("Всего попыток"), len(attempts), "",
        t("пробных: {mocks} · тренировок: {practices}", mocks=len(mocks), practices=practices),
    )
    if mocks:
        average = round(sum(a.score for a in mocks) / len(mocks))
        average_card = _stat_card(
            "⭐", "avg", t("Средний балл"), average, t("из {n}", n=config.MOCK_MAX_SCORE),
            t("среднее по пробным ЕНТ"),
        )
    elif attempts:
        average = round(sum(_percent(a.score, a.max_score) for a in attempts) / len(attempts))
        average_card = _stat_card("⭐", "avg", t("Средний балл"), average, "%", t("среднее по тренировкам"))
    else:
        average_card = _stat_card("⭐", "avg", t("Средний балл"), "—", "", t("пока нет попыток"))

    best_score = best.score if best else 0
    left = config.MOCK_MAX_SCORE - best_score
    if best is None:
        goal_text = t("Пройдите пробный ЕНТ — и здесь будет видно, сколько осталось до 140.")
    elif left == 0:
        goal_text = t("Максимальный балл! Так держать 🎉")
    else:
        goal_text = t("До максимума осталось {left} баллов.", left=left)
    if best is not None and best.max_score < config.MOCK_MAX_SCORE:
        goal_text += (
            " " + t("В вашем лучшем тесте можно было набрать {n}: банк вопросов пока неполный.", n=best.max_score)
        )

    strengths = ent_logic.subject_strengths(user_id)
    strong = [item for item in strengths if item.percent >= STRONG_PERCENT][:3]
    weak = [item for item in reversed(strengths) if item.percent < STRONG_PERCENT][:3]

    recent = (
        fragment('<ul class="recent-list">$rows</ul>', rows=_attempt_rows(attempts[:5]))
        if attempts else
        fragment('<p class="muted">Пока пусто. Начните с тренировки — это 10 минут.</p>')
    )

    assert request.user is not None
    content = render(
        "dashboard.html",
        name=request.user.name,
        tasks_block=_assignments_block(request, user_id),
        continue_block=_continue_blocks(user_id),
        school_block=_school_block(user_id),
        best_card=best_card,
        last_card=last_card,
        total_card=total_card,
        average_card=average_card,
        best_score=best_score,
        max_score=config.MOCK_MAX_SCORE,
        goal_percent=_percent(best_score, config.MOCK_MAX_SCORE),
        goal_text=goal_text,
        strong=_strength_rows(strong, t("Пока нет предметов с результатом от {n}%.", n=STRONG_PERCENT)),
        weak=_strength_rows(weak, t("Слабых предметов не найдено — или ещё мало попыток.")),
        weak_topics=topic_rows(ent_logic.weak_topics(user_id, 3),
                               t("Слабых тем пока нет — или по темам ещё мало заданий.")),
        recent=recent,
        total_questions=config.MOCK_TOTAL_QUESTIONS,
        duration_hours=config.MOCK_DURATION_MINUTES // 60,
        practice_count=config.PRACTICE_QUESTION_COUNT,
        ad=ads.banner_block("dashboard", request.user),
    )
    return page(request, t("Личный кабинет"), content)


# ── Рекламные баннеры ────────────────────────────────────────────────────────

def ad_click(request: Request, banner_id: int) -> Response:
    """GET /ad/<id> — переход по баннеру: учитываем клик и ведём на сайт рекламодателя."""
    link = database.count_banner_click(banner_id)
    if link is None:
        return not_found(request)
    return redirect(link)


def ad_image(request: Request, banner_id: int) -> Response:
    """GET /ad/<id>/image — картинка баннера (кэшируется браузером на сутки)."""
    found = database.get_banner_image(banner_id)
    if found is None:
        return not_found(request)
    data, mime = found
    return Response(body=data, content_type=mime,
                    headers=[("Cache-Control", "public, max-age=86400")])


# ── Профиль: школа ───────────────────────────────────────────────────────────

def _profile_page(request: Request, errors: list[str], city: str = "", name: str = "",
                  status: int = 200) -> Response:
    """Профиль: данные аккаунта и выбор школы."""
    assert request.user is not None
    row = database.get_user_school(request.user.id)
    if row is not None and row["role"] == database.ROLE_TEACHER:
        school_form = fragment('<p class="muted">Школу учителя назначает главный администратор.</p>')
    else:
        leave = (
            fragment(
                '<form method="post" action="/profile/school" class="inline-form">$csrf'
                '<button type="submit" name="action" value="leave" class="btn btn-link">'
                "Выйти из школы</button></form>",
                csrf=_csrf_field(request),
            )
            if row is not None else SafeHTML("")
        )
        school_form = render(
            "profile_school_form.html",
            csrf=_csrf_field(request),
            city=city if errors else (row["city"] if row else ""),
            name=name if errors else (row["name"] if row else ""),
            button=t("Сменить школу") if row is not None else t("Отправить заявку"),
            leave=leave,
        )
    content = render(
        "profile.html",
        name=request.user.name,
        login=request.user.login,
        errors=_errors_block(errors),
        school_status=school_status_text(row),
        school_form=school_form,
        csrf=_csrf_field(request),
        language_options=language_options(i18n.get_language()),
    )
    return page(request, t("Профиль"), content, status)


@login_required
def profile(request: Request) -> Response:
    """GET /profile — профиль ученика и его школа."""
    return _profile_page(request, [])


@login_required
def profile_school(request: Request) -> Response:
    """POST /profile/school — выбрать/сменить школу (нужно подтверждение) или выйти из неё."""
    user_id = _user_id(request)
    current = database.get_user_school(user_id)
    if current is not None and current["role"] == database.ROLE_TEACHER:
        return error_page(request, 403, t("Школу учителя назначает главный администратор."))
    if request.form_value("action") == "leave":
        database.set_user_school(user_id, None, None)
        return redirect("/profile?msg=school_left")
    city, name = request.form_value("city"), request.form_value("name")
    try:
        if schools.validate_school(city, name) is None:
            return _profile_page(
                request, [t("Укажите город и номер (или название) школы.")], city, name, 400
            )
        school_id = schools.join_school(user_id, city, name)
    except schools.SchoolError as error:
        return _profile_page(request, error.errors, city, name, 400)
    same = (current is not None and current["school_id"] == school_id
            and current["school_status"] != database.SCHOOL_REJECTED)
    return redirect("/profile?msg=" + ("school_same" if same else "school_requested"))


# ── Пробный ЕНТ: выбор пары и старт ─────────────────────────────────────────

def _availability_badge(have: int, need: int) -> SafeHTML:
    """Плашка «есть N из M заданий» — зелёная, если хватает, иначе жёлтая."""
    kind = "ok" if have >= need else "warn"
    return fragment(
        '<span class="badge badge-$kind">$have из $need</span>', kind=kind, have=have, need=need
    )


def _avail_row(info: ent_logic.SubjectAvailability) -> SafeHTML:
    """Строка «значок, предмет, N из M» в списке доступности банка."""
    return fragment(
        "<li>$icon<span>$name</span>$badge</li>",
        icon=_icon(info.code), name=info.name, badge=_availability_badge(info.have, info.need),
    )


@student_area
def choose_pair(request: Request) -> Response:
    """GET /mock — выбор пары профильных предметов с честным отчётом о банке и времени."""
    user_id = _user_id(request)
    ent_logic.finish_expired_attempts(user_id)
    language = database.get_user_language(user_id)
    counts = database.question_counts(language)
    allowed = config.pairs_for(language)

    resume_block = SafeHTML("")
    in_progress = database.get_in_progress_attempt(user_id, ent_logic.MOCK)
    if in_progress is not None:
        resume_block = fragment(
            '<div class="notice notice-warning continue">'
            "<div><strong>Незавершённый пробный ЕНТ:</strong> $title. "
            "Новый тест можно начать после его завершения.</div>"
            '<a class="btn btn-primary" href="$href">Продолжить</a></div>',
            title=_attempt_title(in_progress),
            href=_attempt_url(in_progress),
        )

    compulsory_rows = join(
        _avail_row(ent_logic.availability(code, counts)) for code in config.COMPULSORY_CODES
    )

    any_incomplete = False
    cards = []
    for index, pair in enumerate(config.PROFILE_PAIRS):
        if index not in allowed:
            continue  # пара «язык обучения и литература» другого языка обучения
        infos = [ent_logic.availability(code, counts) for code in pair]
        total = ent_logic.pair_question_count(index, counts)
        minutes = ent_logic.mock_duration_minutes(total)
        complete = total >= config.MOCK_TOTAL_QUESTIONS
        any_incomplete = any_incomplete or not complete
        status = (
            fragment('<p class="pair-status ok">✅ Полный тест, как на ЕНТ</p>')
            if complete else
            fragment(
                '<p class="pair-status warn">В банке пока $have из $need заданий — '
                "тест будет собран из имеющихся.</p>",
                have=total, need=config.MOCK_TOTAL_QUESTIONS,
            )
        )
        cards.append(fragment(
            '<form class="pair-card" method="post" action="/mock/start">$csrf'
            '<input type="hidden" name="pair" value="$index">'
            '<div class="pair-icons">$icon1$icon2</div>'
            "<h3>$title</h3><ul class=\"avail-list\">$subjects</ul>"
            '<p class="pair-facts"><span>📝 <b>$total</b> заданий</span>'
            "<span>⏱ <b>$time</b></span></p>$status"
            '<button type="submit" class="btn btn-primary btn-block" $disabled>'
            "Начать тест</button>"
            "</form>",
            csrf=_csrf_field(request),
            index=index,
            icon1=_icon(pair[0], "big"),
            icon2=_icon(pair[1], "big"),
            title=" + ".join(info.name for info in infos),
            subjects=join(_avail_row(info) for info in infos),
            total=total,
            time=_format_duration(minutes * 60),
            status=status,
            disabled=SafeHTML("disabled" if in_progress is not None else ""),
        ))

    time_note = (
        fragment(
            '<div class="notice notice-info"><strong>⏱ Как считается время.</strong> '
            "Полный тест — $full_q заданий за $full_min минут. Если в банке заданий меньше, "
            "время сокращается пропорционально: $full_min мин × (заданий в тесте / $full_q), "
            "с округлением вверх до минуты.</div>",
            full_q=config.MOCK_TOTAL_QUESTIONS, full_min=config.MOCK_DURATION_MINUTES,
        )
        if any_incomplete else SafeHTML("")
    )

    content = render(
        "choose_pair.html",
        resume_block=resume_block,
        time_note=time_note,
        compulsory_rows=compulsory_rows,
        pair_cards=join(cards),
        total_questions=config.MOCK_TOTAL_QUESTIONS,
        max_score=config.MOCK_MAX_SCORE,
        duration_hours=config.MOCK_DURATION_MINUTES // 60,
    )
    return page(request, t("Пробный ЕНТ"), content)


@student_area
def start_mock(request: Request) -> Response:
    """POST /mock/start — собирает пробный ЕНТ по выбранной паре."""
    user_id = _user_id(request)
    ent_logic.finish_expired_attempts(user_id)
    existing = database.get_in_progress_attempt(user_id, ent_logic.MOCK)
    if existing is not None:
        return redirect(f"{_attempt_url(existing)}?msg=resume")

    try:
        pair_index = int(request.form_value("pair", "-1"))
        if pair_index not in config.pairs_for(database.get_user_language(user_id)):
            return redirect("/mock?msg=bad_pair")
        attempt_id = ent_logic.build_mock(user_id, pair_index)
    except ValueError:
        return redirect("/mock?msg=bad_pair")
    except ent_logic.TestBuildError:
        return redirect("/mock?msg=no_questions")
    attempt = database.get_attempt(attempt_id, user_id)
    assert attempt is not None
    return redirect(_attempt_url(attempt))


# ── Вопрос: форма ответа и разбор ────────────────────────────────────────────

def _option_inputs(aq: AttemptQuestion, input_type: str, allow_skip: bool) -> SafeHTML:
    """Варианты ответа в виде radio или checkbox с отметкой уже сохранённого ответа."""
    chosen = set(aq.answer or [])
    # В тренировке radio обязателен (пропустить можно отдельной кнопкой).
    required = SafeHTML("required" if input_type == "radio" and not allow_skip else "")
    items = []
    for letter, text in zip(config.OPTION_LETTERS, aq.options):
        items.append(fragment(
            '<label class="option"><input type="$type" name="$name" value="$letter" $checked $required>'
            '<span class="letter">$letter</span><span class="option-text">$text</span></label>',
            type=input_type,
            name=ent_logic.field_name(aq),
            letter=letter,
            checked=SafeHTML("checked" if letter in chosen else ""),
            required=required,
            text=text,
        ))
    if input_type == "radio" and allow_skip:
        # Без JavaScript отметку radio снять нельзя — поэтому есть вариант «без ответа».
        items.append(fragment(
            '<label class="option option-skip"><input type="radio" name="$name" value="" $checked>'
            '<span class="option-text">Без ответа</span></label>',
            name=ent_logic.field_name(aq),
            checked=SafeHTML("" if chosen else "checked"),
        ))
    return join(items)


def _options_legend(aq: AttemptQuestion) -> SafeHTML:
    """Список вариантов справа для задания на соответствие."""
    return fragment(
        '<ul class="match-options">$items</ul>',
        items=join(
            fragment('<li><span class="letter">$letter</span>$text</li>', letter=letter, text=text)
            for letter, text in zip(config.OPTION_LETTERS, aq.options)
        ),
    )


def _matching_inputs(aq: AttemptQuestion, allow_skip: bool) -> SafeHTML:
    """Задание на соответствие: список вариантов и выпадающий список для каждой строки."""
    answer = aq.answer or []
    rows = []
    for index, left_item in enumerate(aq.left):
        current = answer[index] if index < len(answer) else ""
        choices = [fragment('<option value="">— выберите —</option>')]
        for letter in config.OPTION_LETTERS[: len(aq.options)]:
            choices.append(fragment(
                '<option value="$letter" $selected>$letter</option>',
                letter=letter,
                selected=SafeHTML("selected" if letter == current else ""),
            ))
        rows.append(fragment(
            '<label class="match-row"><span>$number) $left</span>'
            '<select name="$name" $required>$choices</select></label>',
            number=index + 1,
            left=left_item,
            name=f"{ent_logic.field_name(aq)}_{index}",
            required=SafeHTML("" if allow_skip else "required"),
            choices=join(choices),
        ))
    return fragment(
        '$options<div class="match-rows">$rows</div>',
        options=_options_legend(aq),
        rows=join(rows),
    )


def _question_header(aq: AttemptQuestion, label: str) -> SafeHTML:
    """Шапка задания: номер, тип и максимальный балл."""
    return fragment(
        '<header class="question-head"><span class="q-number">$label</span>'
        '<span class="badge">$type · $points б.</span></header>',
        label=label,
        type=config.QUESTION_TYPE_NAMES[aq.qtype],
        points=ent_logic.question_max_points(aq.qtype),
    )


def _question_body(aq: AttemptQuestion) -> SafeHTML:
    """Контекст (если есть) и текст задания."""
    context = (
        fragment('<div class="q-context">$context</div>', context=aq.context)
        if aq.context else SafeHTML("")
    )
    return fragment('$context<p class="q-text">$text</p>', context=context, text=aq.text)


def _question_form_block(aq: AttemptQuestion, label: str, allow_skip: bool = True) -> SafeHTML:
    """Одно задание внутри формы (без подсветки правильного ответа)."""
    if aq.qtype == config.MATCHING:
        inputs = _matching_inputs(aq, allow_skip)
        hint = t("Сопоставьте каждую строку с вариантом.")
    elif aq.qtype == config.MULTIPLE:
        inputs = _option_inputs(aq, "checkbox", allow_skip)
        hint = t("Выберите все верные варианты.")
    else:
        inputs = _option_inputs(aq, "radio", allow_skip)
        hint = t("Выберите один вариант.")
    return fragment(
        '<article class="card question" id="q$number">$head$body'
        '<p class="q-hint">$hint</p><div class="options">$inputs</div></article>',
        number=aq.position,
        head=_question_header(aq, label),
        body=_question_body(aq),
        hint=hint,
        inputs=inputs,
    )


def _option_label(aq: AttemptQuestion, letter: str) -> str:
    """«B) текст варианта» по букве."""
    index = config.OPTION_LETTERS.find(letter)
    if letter and 0 <= index < len(aq.options):
        return f"{letter}) {aq.options[index]}"
    return "—"


def _review_options(aq: AttemptQuestion) -> SafeHTML:
    """Варианты с подсветкой: правильные зелёным, ошибочно выбранные красным."""
    chosen = set(aq.answer or [])
    correct = set(aq.correct)
    items = []
    for letter, text in zip(config.OPTION_LETTERS, aq.options):
        if letter in correct and letter in chosen:
            kind, tag = "ro-correct ro-chosen", t("✓ ваш ответ — верно")
        elif letter in correct:
            kind, tag = "ro-correct", t("✓ правильный ответ")
        elif letter in chosen:
            kind, tag = "ro-wrong ro-chosen", t("✗ ваш ответ")
        else:
            kind, tag = "", ""
        items.append(fragment(
            '<li class="ro $kind"><span class="letter">$letter</span>'
            '<span class="ro-text">$text</span>$tag</li>',
            kind=kind, letter=letter, text=text,
            tag=fragment('<span class="ro-tag">$tag</span>', tag=tag) if tag else SafeHTML(""),
        ))
    return fragment('<ul class="review-options">$items</ul>', items=join(items))


def _review_matching(aq: AttemptQuestion) -> SafeHTML:
    """Соответствие: для каждой строки — мой ответ (зелёный/красный) и правильный."""
    answer = aq.answer or []
    rows = []
    for index, left_item in enumerate(aq.left):
        mine = answer[index] if index < len(answer) else ""
        right = aq.correct[index] if index < len(aq.correct) else ""
        ok = mine == right and mine != ""
        rows.append(fragment(
            '<div class="mr-row $state"><div class="mr-left">$number) $left</div>'
            '<div class="mr-mine"><small>Ваш ответ</small>$mark $mine</div>'
            '<div class="mr-right"><small>Правильно</small>✓ $right</div></div>',
            state="mr-ok" if ok else "mr-wrong",
            number=index + 1,
            left=left_item,
            mark="✓" if ok else "✗",
            mine=_option_label(aq, mine) if mine else t("нет ответа"),
            right=_option_label(aq, right),
        ))
    return fragment(
        '$options<div class="match-review">$rows</div>',
        options=_options_legend(aq),
        rows=join(rows),
    )


def _explanation(aq: AttemptQuestion) -> SafeHTML:
    """Блок «Почему так» с объяснением из банка вопросов."""
    if not aq.explanation:
        return SafeHTML("")
    return fragment(
        '<div class="explain"><p class="explain-title">💡 Почему так</p><p>$text</p></div>',
        text=aq.explanation,
    )


def _review_body(aq: AttemptQuestion) -> SafeHTML:
    """Задание с подсветкой ответов и объяснением (тренировка и разбор результата)."""
    marks = _review_matching(aq) if aq.qtype == config.MATCHING else _review_options(aq)
    empty = (
        fragment('<p class="no-answer">Вы не ответили на это задание.</p>')
        if not aq.answer else SafeHTML("")
    )
    return fragment(
        "$body$empty$marks$explain",
        body=_question_body(aq), empty=empty, marks=marks, explain=_explanation(aq),
    )


# ── Тренировка ───────────────────────────────────────────────────────────────

@student_area
def choose_practice(request: Request) -> Response:
    """GET /practice — выбор предмета для тренировки."""
    counts = database.question_counts(database.get_user_language(_user_id(request)))
    groups = {True: [], False: []}
    for subject in config.SUBJECTS.values():
        total = sum(counts.get((subject.code, qtype), 0) for qtype in config.QUESTION_TYPES)
        groups[subject.compulsory].append(fragment(
            '<form method="post" action="/practice/start">$csrf'
            '<input type="hidden" name="subject" value="$code">'
            '<button type="submit" class="subject-card subj-$code" $disabled>'
            '<span class="subject-emoji" aria-hidden="true">$icon</span>'
            '<span class="subject-name">$name</span>'
            '<span class="subject-count">$total заданий в банке</span>'
            '<span class="subject-go">Начать →</span></button></form>',
            csrf=_csrf_field(request),
            code=subject.code,
            icon=subject.icon,
            name=subject.name,
            total=total,
            disabled=SafeHTML("" if total else "disabled"),
        ))
    practice = database.get_in_progress_attempt(_user_id(request), ent_logic.PRACTICE)
    resume = (
        fragment(
            '<div class="notice notice-info continue"><div><strong>🎯 Незавершённая тренировка:'
            "</strong> $name.</div>"
            '<a class="btn btn-secondary" href="$href">Продолжить</a></div>',
            name=config.SUBJECTS[practice.subjects[0]].name, href=_attempt_url(practice),
        )
        if practice is not None else SafeHTML("")
    )
    content = render(
        "practice.html",
        resume=resume,
        compulsory_cards=join(groups[True]),
        profile_cards=join(groups[False]),
        count=config.PRACTICE_QUESTION_COUNT,
    )
    return page(request, t("Тренировка"), content)


@student_area
def start_practice(request: Request) -> Response:
    """POST /practice/start — собирает тренировку по одному предмету."""
    subject = request.form_value("subject")
    if subject not in config.SUBJECTS:
        return redirect("/practice?msg=bad_subject")
    try:
        attempt_id = ent_logic.build_practice(_user_id(request), subject)
    except ent_logic.TestBuildError:
        return redirect("/practice?msg=no_questions")
    return redirect(f"/practice/{attempt_id}")


def _practice_attempt(request: Request, attempt_id: int) -> Attempt | None:
    """Тренировка пользователя по id (чужая или пробный ЕНТ — None)."""
    attempt = database.get_attempt(attempt_id, _user_id(request))
    if attempt is None or attempt.mode != ent_logic.PRACTICE:
        return None
    return attempt


def _practice_head(attempt: Attempt, questions: list[AttemptQuestion], current: int) -> SafeHTML:
    """Шапка тренировки: предмет, номер вопроса, баллы и «шаги» с результатами."""
    code = attempt.subjects[0]
    steps = []
    for aq in questions:
        if aq.position == current:
            state = "step-current"
        elif aq.checked:
            state = f"step-{ent_logic.question_state(aq)}"
        else:
            state = "step-todo"
        steps.append(fragment(
            '<li class="step $state" title="Вопрос $number">$number</li>',
            state=state, number=aq.position,
        ))
    checked = [aq for aq in questions if aq.checked]
    return fragment(
        '<section class="practice-head subj-$code">'
        '<div class="practice-title">$icon<div><span class="eyebrow">Тренировка</span>'
        "<h1>$name</h1></div></div>"
        '<div class="practice-meta"><span>Вопрос <b>$current</b> из $total</span>'
        "<span>Баллы: <b>$score</b> из $score_max</span></div>"
        '<ol class="steps" aria-label="Прогресс тренировки">$steps</ol></section>',
        code=code,
        icon=_icon(code, "big"),
        name=config.SUBJECTS[code].name,
        current=current,
        total=len(questions),
        score=sum(aq.points for aq in checked),
        score_max=sum(ent_logic.question_max_points(aq.qtype) for aq in checked),
        steps=join(steps),
    )


@login_required
def practice_question(request: Request, attempt_id: int) -> Response:
    """GET /practice/<id> — текущий (первый непроверенный) вопрос тренировки."""
    attempt = _practice_attempt(request, attempt_id)
    if attempt is None:
        return not_found(request)
    if attempt.is_finished:
        return redirect(f"/result/{attempt.id}")
    questions = database.get_attempt_questions(attempt.id)
    current = next((aq for aq in questions if not aq.checked), None)
    if current is None:
        # Все задания проверены — показываем разбор последнего с кнопкой «Итог».
        return redirect(f"/practice/{attempt.id}/review/{questions[-1].position}")

    content = render(
        "practice_question.html",
        head=_practice_head(attempt, questions, current.position),
        action=f"/practice/{attempt.id}",
        csrf=_csrf_field(request),
        question_id=current.id,
        question=_question_form_block(
            current, t("Вопрос {n}", n=current.position), allow_skip=False
        ),
        finish_action=f"/attempt/{attempt.id}/finish",
    )
    return page(request, t("Тренировка — {subject}", subject=config.SUBJECTS[attempt.subjects[0]].name), content)


@login_required
def practice_answer(request: Request, attempt_id: int) -> Response:
    """POST /practice/<id> — проверяет ответ на один вопрос и ведёт к разбору."""
    attempt = _practice_attempt(request, attempt_id)
    if attempt is None:
        return not_found(request)
    if attempt.is_finished:
        return redirect(f"/result/{attempt.id}")
    questions = database.get_attempt_questions(attempt.id)
    try:
        question_id = int(request.form_value("question"))
    except ValueError:
        return redirect(f"/practice/{attempt.id}")
    aq = next((item for item in questions if item.id == question_id), None)
    if aq is None:
        return redirect(f"/practice/{attempt.id}")
    if not aq.checked:
        # «Пропустить» — засчитывается как задание без ответа.
        form = {} if request.form_value("skip") else request.form
        ent_logic.check_practice_answer(attempt, aq, form)
    return redirect(f"/practice/{attempt.id}/review/{aq.position}")


@login_required
def practice_review(request: Request, attempt_id: int, number: int) -> Response:
    """GET /practice/<id>/review/<номер> — разбор отвеченного вопроса и кнопка «Дальше»."""
    attempt = _practice_attempt(request, attempt_id)
    if attempt is None:
        return not_found(request)
    questions = database.get_attempt_questions(attempt.id)
    aq = next((item for item in questions if item.position == number), None)
    if aq is None:
        return not_found(request)
    if not aq.checked:
        return redirect(f"/result/{attempt.id}" if attempt.is_finished else f"/practice/{attempt.id}")

    state = ent_logic.question_state(aq)
    verdicts = {
        "ok": ("✓", t("Верно!")),
        "partial": ("≈", t("Почти! Одна ошибка")),
        "wrong": ("✗", t("Неверно") if aq.answer else t("Без ответа")),
    }
    mark, verdict = verdicts[state]

    remaining = any(not item.checked for item in questions)
    if attempt.is_finished:
        next_block = fragment(
            '<a class="btn btn-primary btn-lg" href="/result/$id">К итогам →</a>', id=attempt.id
        )
    elif remaining:
        next_block = fragment(
            '<a class="btn btn-primary btn-lg" href="/practice/$id">Следующий вопрос →</a>',
            id=attempt.id,
        )
    else:
        next_block = fragment(
            '<form method="post" action="/attempt/$id/finish">$csrf'
            '<button type="submit" class="btn btn-primary btn-lg">Посмотреть итог 🏁</button></form>',
            id=attempt.id, csrf=_csrf_field(request),
        )

    content = render(
        "practice_review.html",
        head=_practice_head(attempt, questions, aq.position),
        state=state,
        mark=mark,
        verdict=verdict,
        points=aq.points,
        max_points=ent_logic.question_max_points(aq.qtype),
        question_head=_question_header(aq, t("Вопрос {n}", n=aq.position)),
        review=_review_body(aq),
        next_block=next_block,
    )
    return page(request, t("Разбор — вопрос {n}", n=aq.position), content)


# ── Прохождение пробного ЕНТ ─────────────────────────────────────────────────

def _load_active_attempt(
    request: Request, attempt_id: int
) -> tuple[Attempt | None, Response | None]:
    """Загружает попытку для прохождения.

    Возвращает (попытка, None) или (None, готовый ответ): 404, если попытка чужая,
    или перенаправление на результат, если тест завершён или время вышло.
    """
    attempt = database.get_attempt(attempt_id, _user_id(request))
    if attempt is None:
        return None, not_found(request)
    if attempt.is_finished:
        return None, redirect(f"/result/{attempt.id}")
    if ent_logic.is_expired(attempt):
        ent_logic.finish_attempt(attempt)
        return None, redirect(f"/result/{attempt.id}?msg=time_up")
    return attempt, None


def _timer(attempt: Attempt) -> SafeHTML:
    """Блок с оставшимся временем (его считает сервер при каждом запросе)."""
    if attempt.deadline is None:
        return fragment('<div class="timer timer-free">Тренировка — без ограничения по времени.</div>')
    left = ent_logic.remaining_seconds(attempt)
    total = max(ent_logic.total_seconds(attempt), 1)
    kind = " timer-low" if left < 15 * 60 else ""
    return fragment(
        '<div class="timer$kind">'
        '<div class="timer-row"><span>⏱ Осталось времени</span><strong>$left</strong></div>'
        '<progress max="$total" value="$used"></progress>'
        '<p class="timer-hint">Время считает сервер и обновляется при каждом переходе. '
        "Тест завершится автоматически в $end.</p></div>",
        kind=SafeHTML(kind),
        left=_format_duration(left),
        total=total,
        used=total - left,
        end=datetime.fromtimestamp(attempt.deadline).strftime("%H:%M"),
    )


def _section_tabs(attempt: Attempt, questions: list[AttemptQuestion], current: str) -> SafeHTML:
    """Вкладки разделов — это кнопки формы: переход сначала сохраняет ответы."""
    tabs = []
    for code in attempt.subjects:
        subject_questions = [aq for aq in questions if aq.subject == code]
        answered = sum(1 for aq in subject_questions if aq.answer)
        tabs.append(fragment(
            '<button type="submit" name="goto" value="$code" class="tab subj-$code$active" $aria>'
            '<span class="tab-icon" aria-hidden="true">$icon</span>'
            '<span>$name</span><small>$answered/$total</small></button>',
            code=code,
            active=SafeHTML(" tab-active" if code == current else ""),
            aria=SafeHTML('aria-current="step"' if code == current else ""),
            icon=config.SUBJECTS[code].icon,
            name=config.SUBJECTS[code].name,
            answered=answered,
            total=len(subject_questions),
        ))
    return join(tabs)


def _section_buttons(attempt: Attempt, current: str) -> SafeHTML:
    """Кнопки внизу раздела: назад, сохранить, далее, завершить."""
    index = attempt.subjects.index(current)
    buttons = []
    if index > 0:
        previous = attempt.subjects[index - 1]
        buttons.append(fragment(
            '<button type="submit" name="goto" value="$code" class="btn btn-ghost">'
            "← $name</button>",
            code=previous, name=config.SUBJECTS[previous].name,
        ))
    buttons.append(fragment(
        '<button type="submit" name="goto" value="$code" class="btn btn-secondary">'
        "💾 Сохранить ответы</button>",
        code=current,
    ))
    if index < len(attempt.subjects) - 1:
        following = attempt.subjects[index + 1]
        buttons.append(fragment(
            '<button type="submit" name="goto" value="$code" class="btn btn-primary">'
            "$name →</button>",
            code=following, name=config.SUBJECTS[following].name,
        ))
    buttons.append(fragment('<button type="submit" name="finish" value="1" class="btn btn-danger">Завершить тест</button>'))
    return join(buttons)


def _shortage_note(attempt: Attempt, subject: str | None = None) -> SafeHTML:
    """Предупреждение, если банк вопросов не позволил собрать полный тест."""
    items = [item for item in attempt.shortage if subject is None or item["subject"] == subject]
    if not items:
        return SafeHTML("")
    parts = [
        t("{subject} — «{qtype}»: {have} из {need}", subject=config.SUBJECTS[item["subject"]].name,
          qtype=config.QUESTION_TYPE_NAMES[item["type"]], have=item["have"], need=item["need"])
        for item in items
    ]
    return _notice(
        "warning",
        t("Банк вопросов неполный, тест собран из имеющихся заданий. ") + "; ".join(parts) + ".",
    )


@login_required
def section_page(request: Request, attempt_id: int, subject: str) -> Response:
    """GET /attempt/<id>/<предмет> — раздел пробного ЕНТ в виде одной HTML-формы."""
    attempt, early = _load_active_attempt(request, attempt_id)
    if attempt is None:
        assert early is not None
        return early
    if attempt.mode == ent_logic.PRACTICE:
        return redirect(_attempt_url(attempt))
    if subject not in attempt.subjects:
        return not_found(request)

    questions = database.get_attempt_questions(attempt.id)
    section = [aq for aq in questions if aq.subject == subject]
    if section:
        blocks = join(_question_form_block(aq, t("Задание {n}", n=aq.position)) for aq in section)
    else:
        blocks = fragment('<div class="card empty">В банке пока нет заданий по этому предмету. '
            "Переходите к следующему разделу.</div>")

    answered = sum(1 for aq in questions if aq.answer)
    content = render(
        "test.html",
        mode_label=MODE_NAMES[attempt.mode],
        icon=_icon(subject, "big"),
        heading=config.SUBJECTS[subject].name,
        progress=t("Отвечено {answered} из {total}", answered=answered, total=len(questions)),
        answered=answered,
        total=max(len(questions), 1),
        timer=_timer(attempt),
        action=f"/attempt/{attempt.id}/{quote(subject)}",
        csrf=_csrf_field(request),
        subject=subject,
        tabs=_section_tabs(attempt, questions, subject),
        shortage=_shortage_note(attempt, subject),
        questions=blocks,
        buttons=_section_buttons(attempt, subject),
    )
    return page(request, f"{MODE_NAMES[attempt.mode]} — {config.SUBJECTS[subject].name}", content)


@login_required
def section_submit(request: Request, attempt_id: int, subject: str) -> Response:
    """POST /attempt/<id>/<предмет> — сохраняет ответы раздела, затем выполняет действие.

    Ответы сохраняются ВСЕГДА до перехода: по вкладке, «Далее», «Назад» или «Завершить».
    """
    attempt, early = _load_active_attempt(request, attempt_id)
    if attempt is None:
        assert early is not None
        return early
    if attempt.mode == ent_logic.PRACTICE:
        return redirect(_attempt_url(attempt))
    if subject not in attempt.subjects:
        return not_found(request)

    # Поле section подтверждает, что форма относится именно к этому разделу.
    if request.form_value("section") == subject:
        questions = database.get_attempt_questions(attempt.id)
        section = [aq for aq in questions if aq.subject == subject]
        database.save_answers(attempt.id, ent_logic.parse_section_answers(section, request.form))

    if request.form_value("finish"):
        return redirect(f"/attempt/{attempt.id}/finish")

    target = request.form_value("goto")
    if target in attempt.subjects and target != subject:
        return redirect(f"/attempt/{attempt.id}/{target}")
    return redirect(f"/attempt/{attempt.id}/{subject}?msg=saved")


@login_required
def finish_confirm(request: Request, attempt_id: int) -> Response:
    """GET /attempt/<id>/finish — страница подтверждения завершения теста."""
    attempt, early = _load_active_attempt(request, attempt_id)
    if attempt is None:
        assert early is not None
        return early
    if attempt.mode == ent_logic.PRACTICE:
        return redirect(_attempt_url(attempt))

    questions = database.get_attempt_questions(attempt.id)
    rows = []
    unanswered_total = 0
    for code in attempt.subjects:
        subject_questions = [aq for aq in questions if aq.subject == code]
        answered = sum(1 for aq in subject_questions if aq.answer)
        unanswered_total += len(subject_questions) - answered
        rows.append(fragment(
            '<tr><td><a class="subject-link" href="/attempt/$id/$code">$icon $name</a></td>'
            "<td>$answered из $total</td></tr>",
            id=attempt.id, code=code, icon=_icon(code), name=config.SUBJECTS[code].name,
            answered=answered, total=len(subject_questions),
        ))

    warning = (
        _notice("warning", t("Без ответа осталось заданий: {n}. После завершения изменить ответы будет нельзя.",
                             n=unanswered_total))
        if unanswered_total else
        _notice("success", t("Вы ответили на все задания."))
    )
    content = render(
        "finish_confirm.html",
        timer=_timer(attempt),
        warning=warning,
        rows=join(rows),
        action=f"/attempt/{attempt.id}/finish",
        csrf=_csrf_field(request),
        back_href=_attempt_url(attempt),
    )
    return page(request, t("Завершить тест?"), content)


@login_required
def finish_submit(request: Request, attempt_id: int) -> Response:
    """POST /attempt/<id>/finish — окончательно завершает и оценивает тест или тренировку."""
    attempt, early = _load_active_attempt(request, attempt_id)
    if attempt is None:
        assert early is not None
        return early
    ent_logic.finish_attempt(attempt)
    return redirect(f"/result/{attempt.id}")


# ── Результат и история ──────────────────────────────────────────────────────

def _review_item(aq: AttemptQuestion) -> SafeHTML:
    """Разбор одного задания на странице результата."""
    state = ent_logic.question_state(aq)
    return fragment(
        '<article class="review-item review-$state">'
        '<header class="question-head"><span class="q-number">Задание $number</span>'
        '<span class="badge badge-$state">$points из $max б.</span></header>'
        "$body</article>",
        state=state,
        number=aq.position,
        points=aq.points,
        max=ent_logic.question_max_points(aq.qtype),
        body=_review_body(aq),
    )


def result_content(attempt: Attempt, actions: SafeHTML) -> SafeHTML:
    """Страница результата завершённой попытки (общая для ученика и админки).

    actions — кнопки внизу страницы: у ученика свои, у администратора — свои.
    """
    questions = database.get_attempt_questions(attempt.id)
    scores = ent_logic.subject_scores(attempt, questions)
    is_mock = attempt.mode == ent_logic.MOCK
    percent = _percent(attempt.score, attempt.max_score)

    score_rows = join(
        fragment(
            '<li class="subj-$code">$icon<div class="strength-body">'
            '<div class="strength-top"><span>$name</span>'
            '<span class="subject-score"><strong>$score</strong> из $max</span></div>'
            '<progress max="$max_bar" value="$score"></progress></div></li>',
            code=item.code, icon=_icon(item.code), name=item.name,
            score=item.score, max=item.max_score, max_bar=max(item.max_score, 1),
        )
        for item in scores
    )

    review_sections = []
    for item in scores:
        subject_questions = [aq for aq in questions if aq.subject == item.code]
        mistakes = sum(1 for aq in subject_questions if ent_logic.question_state(aq) != "ok")
        review_sections.append(fragment(
            '<details class="review-section subj-$code" $open><summary>$icon'
            '<span class="rs-name">$name</span>'
            '<span class="rs-meta">$score из $max · ошибок: $mistakes</span></summary>'
            '<div class="review-items">$items</div></details>',
            code=item.code,
            open=SafeHTML("" if is_mock else "open"),
            icon=_icon(item.code),
            name=item.name, score=item.score, max=item.max_score, mistakes=mistakes,
            items=join(_review_item(aq) for aq in subject_questions)
            or fragment('<p class="muted">Заданий не было.</p>'),
        ))

    official_note = SafeHTML("")
    if is_mock and attempt.max_score < config.MOCK_MAX_SCORE:
        official_note = fragment(
            '<p class="muted small">В этом тесте можно было набрать $max баллов: '
            "банк вопросов неполный. "
            "Официальный максимум ЕНТ — $official баллов.</p>",
            max=attempt.max_score, official=config.MOCK_MAX_SCORE,
        )

    if percent >= 85:
        cheer = t("Отличный результат! 🎉")
    elif percent >= STRONG_PERCENT:
        cheer = t("Хороший результат — ещё немного до максимума 💪")
    elif percent >= 40:
        cheer = t("Неплохо! Разберите ошибки ниже — это самый быстрый рост 📈")
    else:
        cheer = t("Не сдавайтесь: прочитайте объяснения и попробуйте ещё раз 🌱")

    duration = int((attempt.finished_at or attempt.started_at) - attempt.started_at)
    return render(
        "result.html",
        mode_label=MODE_NAMES[attempt.mode],
        icon=_attempt_icon(attempt),
        heading=_attempt_title(attempt),
        date=_format_datetime(attempt.finished_at),
        duration=_format_duration(duration),
        score=attempt.score,
        max_score=attempt.max_score,
        percent=percent,
        ring_class=_percent_class(percent),
        cheer=cheer,
        official_note=official_note,
        score_rows=score_rows,
        review=join(review_sections),
        actions=actions,
    )


@login_required
def result_page(request: Request, attempt_id: int) -> Response:
    """GET /result/<id> — баллы по предметам, итог и разбор с объяснениями."""
    attempt = database.get_attempt(attempt_id, _user_id(request))
    if attempt is None:
        return not_found(request)
    if not attempt.is_finished:
        if ent_logic.is_expired(attempt):
            ent_logic.finish_attempt(attempt)
            attempt = database.get_attempt(attempt_id, _user_id(request))
            assert attempt is not None
        else:
            return redirect(_attempt_url(attempt))

    again = (
        fragment('<a class="btn btn-secondary" href="/mock">Новый пробный ЕНТ</a>')
        if attempt.mode == ent_logic.MOCK else
        fragment(
            '<form method="post" action="/practice/start">$csrf'
            '<input type="hidden" name="subject" value="$code">'
            '<button type="submit" class="btn btn-secondary">🔁 Ещё 10 вопросов</button></form>',
            csrf=_csrf_field(request), code=attempt.subjects[0],
        )
    )
    actions = fragment(
        '<a class="btn btn-primary" href="/dashboard">В кабинет</a>$again'
        '<a class="btn btn-ghost" href="/history">История попыток</a>',
        again=again,
    )
    content = join([result_content(attempt, actions), ads.banner_block("result", request.user)])
    return page(request, t("Результат"), content)


@student_area
def history(request: Request) -> Response:
    """GET /history — таблица всех завершённых попыток."""
    user_id = _user_id(request)
    ent_logic.finish_expired_attempts(user_id)
    attempts = database.get_finished_attempts(user_id)
    if attempts:
        rows = join(
            fragment(
                "<tr><td>$date</td><td>$mode</td>"
                '<td><span class="subject-link">$icon $what</span></td>'
                '<td><span class="score-pill $grade"><strong>$score</strong> / $max</span></td>'
                "<td>$percent%</td>"
                '<td><a class="link" href="/result/$id">Разбор →</a></td></tr>',
                date=_format_datetime(attempt.finished_at),
                mode=MODE_NAMES[attempt.mode],
                icon=_attempt_icon(attempt),
                what=_attempt_title(attempt).split(": ", 1)[1],
                grade=_grade_class(_percent(attempt.score, attempt.max_score)),
                score=attempt.score,
                max=attempt.max_score,
                percent=_percent(attempt.score, attempt.max_score),
                id=attempt.id,
            )
            for attempt in attempts
        )
        table = fragment(
            '<div class="table-wrap"><table class="table"><thead><tr>'
            "<th>Дата</th><th>Режим</th><th>Предметы</th><th>Баллы</th><th>%</th><th></th>"
            "</tr></thead><tbody>$rows</tbody></table></div>",
            rows=rows,
        )
    else:
        table = fragment('<div class="card empty">Пока нет завершённых попыток. '
            '<a class="link" href="/mock">Начните пробный ЕНТ</a> или '
            '<a class="link" href="/practice">тренировку</a>.</div>')
    content = render("history.html", table=table, count=len(attempts), ad=ads.banner_block("history", request.user))
    return page(request, t("История попыток"), content)
