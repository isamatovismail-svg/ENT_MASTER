"""Обработчики страниц: каждая функция получает Request и возвращает Response.

Страницы собираются из шаблонов (templates/*.html). Мелкие повторяющиеся
куски HTML (строки таблиц, карточки, задания) собираются здесь функцией
fragment(), которая экранирует все подставляемые значения.

Важно: Content-Security-Policy запрещает атрибут style, поэтому цвета и ширины
задаются только классами (subj-<код предмета>, p-<процент>) и элементом <progress>.
"""

from collections.abc import Callable
from datetime import datetime
from functools import wraps
from urllib.parse import quote, urlencode

import config
from app import auth, database, ent_logic
from app.database import Attempt, AttemptQuestion
from app.templates import SafeHTML, fragment, join, render
from app.web import Request, Response, html_response, redirect

# Сообщения, которые можно показать через параметр ?msg=код.
# В URL передаётся только код, поэтому подставить свой текст через ссылку нельзя.
MESSAGES: dict[str, tuple[str, str]] = {
    "registered": ("success", "Регистрация прошла успешно. Теперь войдите в аккаунт."),
    "logged_out": ("info", "Вы вышли из аккаунта."),
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
}

MODE_NAMES = {ent_logic.MOCK: "Пробный ЕНТ", ent_logic.PRACTICE: "Тренировка"}

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
        return f"{hours} ч {minutes:02d} мин"
    if minutes_total:
        return f"{minutes} мин"
    return "меньше минуты"


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


def _nav(request: Request) -> SafeHTML:
    """Меню в шапке: разное для гостя и для вошедшего пользователя."""
    if request.user is None:
        return SafeHTML(
            '<a href="/login">Войти</a>'
            '<a class="btn btn-primary btn-sm" href="/register">Регистрация</a>'
        )
    return fragment(
        '<a href="/dashboard">🏠 Кабинет</a>'
        '<a href="/mock">📝 Пробный ЕНТ</a>'
        '<a href="/practice">🎯 Тренировка</a>'
        '<a href="/history">📈 История</a>'
        '<form method="post" action="/logout" class="nav-form">$csrf'
        '<button type="submit" class="btn btn-ghost btn-sm">Выйти</button></form>',
        csrf=_csrf_field(request),
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
                notice = _notice(*message)
    nav = _nav(request) if request is not None else _nav(Request("GET", "/"))
    body = render("base.html", title=title, nav=nav, notice=notice, content=content)
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
            return error_page(request, 403, MESSAGES["csrf"][1])
        return view(request, **kwargs)

    return wrapper


def _user_id(request: Request) -> int:
    """id вошедшего пользователя (вызывается только после login_required)."""
    assert request.user is not None
    return request.user.id


# ── Ошибки ───────────────────────────────────────────────────────────────────

def error_page(request: Request | None, status: int, message: str) -> Response:
    """Страница ошибки с понятным текстом."""
    content = render("error.html", code=status, message=message)
    return page(request, f"Ошибка {status}", content, status, notice=SafeHTML(""))


def not_found(request: Request | None = None) -> Response:
    """Страница 404."""
    return page(request, "Страница не найдена", render("404.html"), 404, notice=SafeHTML(""))


def method_not_allowed(request: Request) -> Response:
    """Ответ 405: страница существует, но не поддерживает этот метод."""
    return error_page(request, 405, "Этот адрес не поддерживает такой запрос.")


def server_error() -> Response:
    """Страница 500 без технических подробностей (они записаны в лог сервера)."""
    return error_page(None, 500, "Что-то пошло не так. Попробуйте обновить страницу чуть позже.")


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
        for first, second in config.PROFILE_PAIRS
    )
    logged_in = request.user is not None
    content = render(
        "landing.html",
        cta_href="/dashboard" if logged_in else "/register",
        cta_label="Перейти в кабинет" if logged_in else "Попробовать бесплатно",
        compulsory_cards=compulsory_cards,
        profile_cards=profile_cards,
        pair_chips=pair_chips,
        total_questions=config.MOCK_TOTAL_QUESTIONS,
        max_score=config.MOCK_MAX_SCORE,
        duration_hours=config.MOCK_DURATION_MINUTES // 60,
        pairs_count=len(config.PROFILE_PAIRS),
        subjects_count=len(config.SUBJECTS),
        profile_questions=profile.question_count,
        profile_score=profile.max_score,
    )
    return page(request, "Подготовка к ЕНТ", content)


def _register_form(
    request: Request, errors: list[str], name: str = "", login: str = ""
) -> Response:
    """Отрисовывает страницу регистрации (с ошибками, если они есть)."""
    content = render(
        "register.html",
        errors=_errors_block(errors),
        name=name,
        login=login,
        min_length=config.PASSWORD_MIN_LENGTH,
    )
    return page(request, "Регистрация", content, 400 if errors else 200)


def register_page(request: Request) -> Response:
    """GET /register — форма регистрации."""
    if request.user is not None:
        return redirect("/dashboard")
    return _register_form(request, [])


def register_submit(request: Request) -> Response:
    """POST /register — проверка полей и создание аккаунта."""
    if request.user is not None:
        return redirect("/dashboard")
    name = request.form_value("name")
    login = request.form_value("login")
    try:
        auth.register_user(
            name, login, request.form_value("password"), request.form_value("password2")
        )
    except auth.ValidationError as error:
        return _register_form(request, error.errors, name, login)
    query = urlencode({"msg": "registered", "login": auth.normalize_login(login)})
    return redirect(f"/login?{query}")


def _login_form(request: Request, errors: list[str], login: str, next_url: str) -> Response:
    """Отрисовывает страницу входа."""
    content = render(
        "login.html", errors=_errors_block(errors), login=login, next=next_url
    )
    return page(request, "Вход", content, 400 if errors else 200)


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
        return _login_form(request, ["Введите почту (или телефон) и пароль."], login, next_url)
    user = auth.authenticate(login, request.form_value("password"))
    if user is None:
        return _login_form(request, ["Неверная почта/телефон или пароль."], login, next_url)
    # При входе всегда создаётся новая сессия, старая (если была) удаляется.
    if request.session_key:
        database.delete_session(request.session_key)
    return redirect(next_url, cookies=[auth.start_session(user.id)])


def logout(request: Request) -> Response:
    """POST /logout — выход из аккаунта."""
    if request.user is None:
        return redirect("/")
    if not auth.check_csrf(request):
        return error_page(request, 403, MESSAGES["csrf"][1])
    return redirect("/?msg=logged_out", cookies=[auth.end_session(request)])


# ── Личный кабинет ───────────────────────────────────────────────────────────

def _attempt_title(attempt: Attempt) -> str:
    """Короткое описание попытки: режим и предметы."""
    if attempt.mode == ent_logic.MOCK:
        profile_codes = attempt.subjects[len(config.COMPULSORY_CODES):]
        profile = [config.SUBJECTS[code].name for code in profile_codes]
        return "Пробный ЕНТ: " + " + ".join(profile)
    return "Тренировка: " + config.SUBJECTS[attempt.subjects[0]].name


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


@login_required
def dashboard(request: Request) -> Response:
    """GET /dashboard — личный кабинет со статистикой и последними попытками."""
    user_id = _user_id(request)
    ent_logic.finish_expired_attempts(user_id)

    attempts = database.get_finished_attempts(user_id)
    mocks = [attempt for attempt in attempts if attempt.mode == ent_logic.MOCK]
    practices = len(attempts) - len(mocks)
    best = max(mocks, key=lambda a: (a.score, a.id)) if mocks else None
    last = attempts[0] if attempts else None

    best_card = _stat_card(
        "🏆", "best", "Лучший балл",
        best.score if best else "—", f"из {config.MOCK_MAX_SCORE}",
        "лучший пробный ЕНТ" if best else "пройдите пробный ЕНТ",
    )
    last_card = _stat_card(
        "🕒", "last", "Последний балл",
        last.score if last else "—", f"из {last.max_score}" if last else "",
        _attempt_title(last) if last else "здесь появится последний тест",
    )
    total_card = _stat_card(
        "📊", "total", "Всего попыток", len(attempts), "",
        f"пробных: {len(mocks)} · тренировок: {practices}",
    )
    if mocks:
        average = round(sum(a.score for a in mocks) / len(mocks))
        average_card = _stat_card(
            "⭐", "avg", "Средний балл", average, f"из {config.MOCK_MAX_SCORE}",
            "среднее по пробным ЕНТ",
        )
    elif attempts:
        average = round(sum(_percent(a.score, a.max_score) for a in attempts) / len(attempts))
        average_card = _stat_card("⭐", "avg", "Средний балл", average, "%", "среднее по тренировкам")
    else:
        average_card = _stat_card("⭐", "avg", "Средний балл", "—", "", "пока нет попыток")

    best_score = best.score if best else 0
    left = config.MOCK_MAX_SCORE - best_score
    if best is None:
        goal_text = "Пройдите пробный ЕНТ — и здесь будет видно, сколько осталось до 140."
    elif left == 0:
        goal_text = "Максимальный балл! Так держать 🎉"
    else:
        goal_text = f"До максимума осталось {left} баллов."
    if best is not None and best.max_score < config.MOCK_MAX_SCORE:
        goal_text += (
            f" В вашем лучшем тесте можно было набрать {best.max_score}: банк вопросов пока неполный."
        )

    strengths = ent_logic.subject_strengths(user_id)
    strong = [item for item in strengths if item.percent >= STRONG_PERCENT][:3]
    weak = [item for item in reversed(strengths) if item.percent < STRONG_PERCENT][:3]

    recent = (
        fragment('<ul class="recent-list">$rows</ul>', rows=_attempt_rows(attempts[:5]))
        if attempts else
        SafeHTML('<p class="muted">Пока пусто. Начните с тренировки — это 10 минут.</p>')
    )

    assert request.user is not None
    content = render(
        "dashboard.html",
        name=request.user.name,
        continue_block=_continue_blocks(user_id),
        best_card=best_card,
        last_card=last_card,
        total_card=total_card,
        average_card=average_card,
        best_score=best_score,
        max_score=config.MOCK_MAX_SCORE,
        goal_percent=_percent(best_score, config.MOCK_MAX_SCORE),
        goal_text=goal_text,
        strong=_strength_rows(strong, f"Пока нет предметов с результатом от {STRONG_PERCENT}%."),
        weak=_strength_rows(weak, "Слабых предметов не найдено — или ещё мало попыток."),
        recent=recent,
        total_questions=config.MOCK_TOTAL_QUESTIONS,
        duration_hours=config.MOCK_DURATION_MINUTES // 60,
        practice_count=config.PRACTICE_QUESTION_COUNT,
    )
    return page(request, "Личный кабинет", content)


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


@login_required
def choose_pair(request: Request) -> Response:
    """GET /mock — выбор пары профильных предметов с честным отчётом о банке и времени."""
    user_id = _user_id(request)
    ent_logic.finish_expired_attempts(user_id)
    counts = database.question_counts()

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
        infos = [ent_logic.availability(code, counts) for code in pair]
        total = ent_logic.pair_question_count(index, counts)
        minutes = ent_logic.mock_duration_minutes(total)
        complete = total >= config.MOCK_TOTAL_QUESTIONS
        any_incomplete = any_incomplete or not complete
        status = (
            SafeHTML('<p class="pair-status ok">✅ Полный тест, как на ЕНТ</p>')
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
    return page(request, "Пробный ЕНТ", content)


@login_required
def start_mock(request: Request) -> Response:
    """POST /mock/start — собирает пробный ЕНТ по выбранной паре."""
    user_id = _user_id(request)
    ent_logic.finish_expired_attempts(user_id)
    existing = database.get_in_progress_attempt(user_id, ent_logic.MOCK)
    if existing is not None:
        return redirect(f"{_attempt_url(existing)}?msg=resume")

    try:
        pair_index = int(request.form_value("pair", "-1"))
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
        hint = "Сопоставьте каждую строку с вариантом."
    elif aq.qtype == config.MULTIPLE:
        inputs = _option_inputs(aq, "checkbox", allow_skip)
        hint = "Выберите все верные варианты."
    else:
        inputs = _option_inputs(aq, "radio", allow_skip)
        hint = "Выберите один вариант."
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
            kind, tag = "ro-correct ro-chosen", "✓ ваш ответ — верно"
        elif letter in correct:
            kind, tag = "ro-correct", "✓ правильный ответ"
        elif letter in chosen:
            kind, tag = "ro-wrong ro-chosen", "✗ ваш ответ"
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
            mine=_option_label(aq, mine) if mine else "нет ответа",
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
        SafeHTML('<p class="no-answer">Вы не ответили на это задание.</p>')
        if not aq.answer else SafeHTML("")
    )
    return fragment(
        "$body$empty$marks$explain",
        body=_question_body(aq), empty=empty, marks=marks, explain=_explanation(aq),
    )


# ── Тренировка ───────────────────────────────────────────────────────────────

@login_required
def choose_practice(request: Request) -> Response:
    """GET /practice — выбор предмета для тренировки."""
    counts = database.question_counts()
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
    return page(request, "Тренировка", content)


@login_required
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
            current, f"Вопрос {current.position}", allow_skip=False
        ),
        finish_action=f"/attempt/{attempt.id}/finish",
    )
    return page(request, f"Тренировка — {config.SUBJECTS[attempt.subjects[0]].name}", content)


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
        "ok": ("✓", "Верно!"),
        "partial": ("≈", "Почти! Одна ошибка"),
        "wrong": ("✗", "Неверно" if aq.answer else "Без ответа"),
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
        question_head=_question_header(aq, f"Вопрос {aq.position}"),
        review=_review_body(aq),
        next_block=next_block,
    )
    return page(request, f"Разбор — вопрос {aq.position}", content)


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
        return SafeHTML(
            '<div class="timer timer-free">Тренировка — без ограничения по времени.</div>'
        )
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
    buttons.append(SafeHTML(
        '<button type="submit" name="finish" value="1" class="btn btn-danger">Завершить тест</button>'
    ))
    return join(buttons)


def _shortage_note(attempt: Attempt, subject: str | None = None) -> SafeHTML:
    """Предупреждение, если банк вопросов не позволил собрать полный тест."""
    items = [item for item in attempt.shortage if subject is None or item["subject"] == subject]
    if not items:
        return SafeHTML("")
    parts = [
        f"{config.SUBJECTS[item['subject']].name} — «{config.QUESTION_TYPE_NAMES[item['type']]}»: "
        f"{item['have']} из {item['need']}"
        for item in items
    ]
    return _notice(
        "warning",
        "Банк вопросов неполный, тест собран из имеющихся заданий. " + "; ".join(parts) + ".",
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
        blocks = join(_question_form_block(aq, f"Задание {aq.position}") for aq in section)
    else:
        blocks = SafeHTML(
            '<div class="card empty">В банке пока нет заданий по этому предмету. '
            "Переходите к следующему разделу.</div>"
        )

    answered = sum(1 for aq in questions if aq.answer)
    content = render(
        "test.html",
        mode_label=MODE_NAMES[attempt.mode],
        icon=_icon(subject, "big"),
        heading=config.SUBJECTS[subject].name,
        progress=f"Отвечено {answered} из {len(questions)}",
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
        _notice("warning", f"Без ответа осталось заданий: {unanswered_total}. "
                           "После завершения изменить ответы будет нельзя.")
        if unanswered_total else
        _notice("success", "Вы ответили на все задания.")
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
    return page(request, "Завершить тест?", content)


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
            or SafeHTML('<p class="muted">Заданий не было.</p>'),
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
        cheer = "Отличный результат! 🎉"
    elif percent >= STRONG_PERCENT:
        cheer = "Хороший результат — ещё немного до максимума 💪"
    elif percent >= 40:
        cheer = "Неплохо! Разберите ошибки ниже — это самый быстрый рост 📈"
    else:
        cheer = "Не сдавайтесь: прочитайте объяснения и попробуйте ещё раз 🌱"

    again = (
        SafeHTML('<a class="btn btn-secondary" href="/mock">Новый пробный ЕНТ</a>')
        if is_mock else
        fragment(
            '<form method="post" action="/practice/start">$csrf'
            '<input type="hidden" name="subject" value="$code">'
            '<button type="submit" class="btn btn-secondary">🔁 Ещё 10 вопросов</button></form>',
            csrf=_csrf_field(request), code=attempt.subjects[0],
        )
    )

    duration = int((attempt.finished_at or attempt.started_at) - attempt.started_at)
    content = render(
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
        again=again,
    )
    return page(request, "Результат", content)


@login_required
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
        table = SafeHTML(
            '<div class="card empty">Пока нет завершённых попыток. '
            '<a class="link" href="/mock">Начните пробный ЕНТ</a> или '
            '<a class="link" href="/practice">тренировку</a>.</div>'
        )
    content = render("history.html", table=table, count=len(attempts))
    return page(request, "История попыток", content)
