"""Обработчики страниц: каждая функция получает Request и возвращает Response.

Страницы собираются из шаблонов (templates/*.html). Мелкие повторяющиеся
куски HTML (строки таблиц, карточки, задания) собираются здесь функцией
fragment(), которая экранирует все подставляемые значения.
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


def _nav(request: Request) -> SafeHTML:
    """Меню в шапке: разное для гостя и для вошедшего пользователя."""
    if request.user is None:
        return SafeHTML(
            '<a href="/login">Войти</a>'
            '<a class="btn btn-primary btn-sm" href="/register">Регистрация</a>'
        )
    return fragment(
        '<a href="/dashboard">Кабинет</a>'
        '<a href="/mock">Пробный ЕНТ</a>'
        '<a href="/practice">Тренировка</a>'
        '<a href="/history">История</a>'
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
    """Главная страница с описанием платформы и структурой ЕНТ."""
    rows = []
    for code in config.COMPULSORY_CODES:
        subject = config.SUBJECTS[code]
        rows.append(fragment(
            "<tr><td>$name</td><td>Обязательный</td><td>$count</td><td>$score</td></tr>",
            name=subject.name, count=subject.question_count, score=subject.max_score,
        ))
    profile = config.SUBJECTS[config.PROFILE_PAIRS[0][0]]
    for number in (1, 2):
        rows.append(fragment(
            "<tr><td>Профильный предмет $number</td><td>Профильный</td>"
            "<td>$count</td><td>$score</td></tr>",
            number=number, count=profile.question_count, score=profile.max_score,
        ))
    logged_in = request.user is not None
    content = render(
        "landing.html",
        cta_href="/dashboard" if logged_in else "/register",
        cta_label="Перейти в кабинет" if logged_in else "Попробовать бесплатно",
        structure_rows=join(rows),
        total_questions=config.MOCK_TOTAL_QUESTIONS,
        max_score=config.MOCK_MAX_SCORE,
        duration_hours=config.MOCK_DURATION_MINUTES // 60,
        pairs_count=len(config.PROFILE_PAIRS),
        subjects_count=len(config.SUBJECTS),
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


def _result_card(title: str, attempt: Attempt | None, empty_text: str) -> SafeHTML:
    """Карточка результата для кабинета (лучший / последний)."""
    if attempt is None:
        return fragment(
            '<div class="card stat-card"><h3>$title</h3><p class="muted">$empty</p></div>',
            title=title, empty=empty_text,
        )
    return fragment(
        '<div class="card stat-card"><h3>$title</h3>'
        '<p class="stat-value">$score <span>из $max</span></p>'
        '<p class="muted">$what · $date</p>'
        '<a class="link" href="/result/$id">Смотреть разбор →</a></div>',
        title=title,
        score=attempt.score,
        max=attempt.max_score,
        what=_attempt_title(attempt),
        date=_format_datetime(attempt.finished_at),
        id=attempt.id,
    )


@login_required
def dashboard(request: Request) -> Response:
    """GET /dashboard — личный кабинет."""
    user_id = _user_id(request)
    ent_logic.finish_expired_attempts(user_id)

    in_progress = database.get_in_progress_attempt(user_id, ent_logic.MOCK)
    continue_block = SafeHTML("")
    if in_progress is not None:
        continue_block = fragment(
            '<div class="notice notice-warning continue">'
            "<div><strong>У вас есть незавершённый пробный ЕНТ.</strong> "
            "Осталось времени: $left.</div>"
            '<a class="btn btn-primary" href="/attempt/$id/$subject">Продолжить</a></div>',
            left=_format_duration(ent_logic.remaining_seconds(in_progress)),
            id=in_progress.id,
            subject=in_progress.subjects[0],
        )

    assert request.user is not None
    content = render(
        "dashboard.html",
        name=request.user.name,
        continue_block=continue_block,
        best_card=_result_card(
            "Лучший пробный ЕНТ",
            database.get_best_attempt(user_id, ent_logic.MOCK),
            "Вы ещё не проходили пробный ЕНТ.",
        ),
        last_card=_result_card(
            "Последний результат",
            database.get_last_attempt(user_id),
            "Здесь появится ваш последний тест.",
        ),
        attempts_count=len(database.get_finished_attempts(user_id)),
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


@login_required
def choose_pair(request: Request) -> Response:
    """GET /mock — выбор пары профильных предметов с честным отчётом о банке вопросов."""
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
            '<a class="btn btn-primary" href="/attempt/$id/$subject">Продолжить</a></div>',
            title=_attempt_title(in_progress),
            id=in_progress.id,
            subject=in_progress.subjects[0],
        )

    compulsory_have = 0
    compulsory_rows = []
    for code in config.COMPULSORY_CODES:
        info = ent_logic.availability(code, counts)
        compulsory_have += info.have
        compulsory_rows.append(fragment(
            "<li><span>$name</span>$badge</li>",
            name=info.name, badge=_availability_badge(info.have, info.need),
        ))

    cards = []
    for index, pair in enumerate(config.PROFILE_PAIRS):
        infos = [ent_logic.availability(code, counts) for code in pair]
        total_have = compulsory_have + sum(info.have for info in infos)
        complete = total_have >= config.MOCK_TOTAL_QUESTIONS
        status = (
            fragment('<p class="pair-status ok">Полный тест: $n заданий</p>', n=total_have)
            if complete else
            fragment(
                '<p class="pair-status warn">В банке пока $have из $need заданий — '
                "тест будет собран из имеющихся.</p>",
                have=total_have, need=config.MOCK_TOTAL_QUESTIONS,
            )
        )
        subjects = join(
            fragment("<li><span>$name</span>$badge</li>", name=info.name,
                     badge=_availability_badge(info.have, info.need))
            for info in infos
        )
        cards.append(fragment(
            '<form class="card pair-card" method="post" action="/mock/start">$csrf'
            '<input type="hidden" name="pair" value="$index">'
            "<h3>$title</h3><ul class=\"avail-list\">$subjects</ul>$status"
            '<button type="submit" class="btn btn-primary btn-block" $disabled>'
            "Начать тест</button>"
            "</form>",
            csrf=_csrf_field(request),
            index=index,
            title=" + ".join(info.name for info in infos),
            subjects=subjects,
            status=status,
            disabled=SafeHTML("disabled" if in_progress is not None else ""),
        ))

    content = render(
        "choose_pair.html",
        resume_block=resume_block,
        compulsory_rows=join(compulsory_rows),
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
        return redirect(f"/attempt/{existing.id}/{existing.subjects[0]}?msg=resume")

    try:
        pair_index = int(request.form_value("pair", "-1"))
        attempt_id = ent_logic.build_mock(user_id, pair_index)
    except ValueError:
        return redirect("/mock?msg=bad_pair")
    except ent_logic.TestBuildError:
        return redirect("/mock?msg=no_questions")
    attempt = database.get_attempt(attempt_id, user_id)
    assert attempt is not None
    return redirect(f"/attempt/{attempt.id}/{attempt.subjects[0]}")


# ── Тренировка ───────────────────────────────────────────────────────────────

@login_required
def choose_practice(request: Request) -> Response:
    """GET /practice — выбор предмета для тренировки."""
    counts = database.question_counts()
    cards = []
    for subject in config.SUBJECTS.values():
        total = sum(counts.get((subject.code, qtype), 0) for qtype in config.QUESTION_TYPES)
        cards.append(fragment(
            '<form class="card subject-card" method="post" action="/practice/start">$csrf'
            '<input type="hidden" name="subject" value="$code">'
            '<span class="tag">$kind</span><h3>$name</h3>'
            '<p class="muted">В банке: $total заданий</p>'
            '<button type="submit" class="btn btn-secondary btn-block" $disabled>Начать</button>'
            "</form>",
            csrf=_csrf_field(request),
            code=subject.code,
            kind="Обязательный" if subject.compulsory else "Профильный",
            name=subject.name,
            total=total,
            disabled=SafeHTML("" if total else "disabled"),
        ))
    content = render(
        "practice.html", subject_cards=join(cards), count=config.PRACTICE_QUESTION_COUNT
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
    return redirect(f"/attempt/{attempt_id}/{subject}")


# ── Прохождение теста ────────────────────────────────────────────────────────

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
    total = config.MOCK_DURATION_MINUTES * 60
    kind = " timer-low" if left < 15 * 60 else ""
    return fragment(
        '<div class="timer$kind">'
        '<div class="timer-row"><span>Осталось времени</span><strong>$left</strong></div>'
        '<progress max="$total" value="$used"></progress>'
        '<p class="timer-hint">Время считает сервер и обновляется при каждом переходе. '
        "Тест завершится автоматически в $end.</p></div>",
        kind=SafeHTML(kind),
        left=_format_duration(left),
        total=total,
        used=total - left,
        end=datetime.fromtimestamp(attempt.deadline).strftime("%H:%M"),
    )


def _option_inputs(aq: AttemptQuestion, input_type: str) -> SafeHTML:
    """Варианты ответа в виде radio или checkbox с отметкой уже сохранённого ответа."""
    chosen = set(aq.answer or [])
    items = []
    for letter, text in zip(config.OPTION_LETTERS, aq.options):
        items.append(fragment(
            '<label class="option"><input type="$type" name="$name" value="$letter" $checked>'
            '<span class="letter">$letter</span><span class="option-text">$text</span></label>',
            type=input_type,
            name=ent_logic.field_name(aq),
            letter=letter,
            checked=SafeHTML("checked" if letter in chosen else ""),
            text=text,
        ))
    if input_type == "radio":
        # Без JavaScript отметку radio снять нельзя — поэтому есть вариант «без ответа».
        items.append(fragment(
            '<label class="option option-skip"><input type="radio" name="$name" value="" $checked>'
            '<span class="option-text">Без ответа</span></label>',
            name=ent_logic.field_name(aq),
            checked=SafeHTML("" if chosen else "checked"),
        ))
    return join(items)


def _matching_inputs(aq: AttemptQuestion) -> SafeHTML:
    """Задание на соответствие: список вариантов и выпадающий список для каждой строки."""
    answer = aq.answer or []
    options_list = join(
        fragment('<li><span class="letter">$letter</span>$text</li>', letter=letter, text=text)
        for letter, text in zip(config.OPTION_LETTERS, aq.options)
    )
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
            '<select name="$name">$choices</select></label>',
            number=index + 1,
            left=left_item,
            name=f"{ent_logic.field_name(aq)}_{index}",
            choices=join(choices),
        ))
    return fragment(
        '<ul class="match-options">$options</ul><div class="match-rows">$rows</div>',
        options=options_list,
        rows=join(rows),
    )


def _question_header(aq: AttemptQuestion) -> SafeHTML:
    """Шапка задания: номер, тип и максимальный балл."""
    return fragment(
        '<header class="question-head"><span class="q-number">Задание $number</span>'
        '<span class="badge">$type · $points б.</span></header>',
        number=aq.position,
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


def _question_form_block(aq: AttemptQuestion) -> SafeHTML:
    """Одно задание внутри формы раздела."""
    if aq.qtype == config.MATCHING:
        inputs = _matching_inputs(aq)
        hint = "Сопоставьте каждую строку с вариантом."
    elif aq.qtype == config.MULTIPLE:
        inputs = _option_inputs(aq, "checkbox")
        hint = "Выберите все верные варианты."
    else:
        inputs = _option_inputs(aq, "radio")
        hint = "Выберите один вариант."
    return fragment(
        '<article class="card question" id="q$number">$head$body'
        '<p class="q-hint">$hint</p><div class="options">$inputs</div></article>',
        number=aq.position,
        head=_question_header(aq),
        body=_question_body(aq),
        hint=hint,
        inputs=inputs,
    )


def _section_tabs(attempt: Attempt, questions: list[AttemptQuestion], current: str) -> SafeHTML:
    """Вкладки разделов — это кнопки формы: переход сначала сохраняет ответы."""
    tabs = []
    for code in attempt.subjects:
        subject_questions = [aq for aq in questions if aq.subject == code]
        answered = sum(1 for aq in subject_questions if aq.answer)
        tabs.append(fragment(
            '<button type="submit" name="goto" value="$code" class="tab$active" $aria>'
            '<span>$name</span><small>$answered/$total</small></button>',
            code=code,
            active=SafeHTML(" tab-active" if code == current else ""),
            aria=SafeHTML('aria-current="step"' if code == current else ""),
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
    if attempt.mode == ent_logic.MOCK:
        buttons.append(fragment(
            '<button type="submit" name="goto" value="$code" class="btn btn-secondary">'
            "Сохранить ответы</button>",
            code=current,
        ))
    if index < len(attempt.subjects) - 1:
        following = attempt.subjects[index + 1]
        buttons.append(fragment(
            '<button type="submit" name="goto" value="$code" class="btn btn-primary">'
            "$name →</button>",
            code=following, name=config.SUBJECTS[following].name,
        ))
    finish_label = "Завершить тест" if attempt.mode == ent_logic.MOCK else "Проверить ответы"
    buttons.append(fragment(
        '<button type="submit" name="finish" value="1" class="btn btn-danger">$label</button>',
        label=finish_label,
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
    """GET /attempt/<id>/<предмет> — раздел теста в виде одной HTML-формы."""
    attempt, early = _load_active_attempt(request, attempt_id)
    if attempt is None:
        assert early is not None
        return early
    if subject not in attempt.subjects:
        return not_found(request)

    questions = database.get_attempt_questions(attempt.id)
    section = [aq for aq in questions if aq.subject == subject]
    if section:
        blocks = join(_question_form_block(aq) for aq in section)
    else:
        blocks = SafeHTML(
            '<div class="card empty">В банке пока нет заданий по этому предмету. '
            "Переходите к следующему разделу.</div>"
        )

    answered = sum(1 for aq in questions if aq.answer)
    content = render(
        "test.html",
        mode_label=MODE_NAMES[attempt.mode],
        heading=config.SUBJECTS[subject].name,
        progress=f"Отвечено {answered} из {len(questions)}",
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
    if subject not in attempt.subjects:
        return not_found(request)

    # Поле section подтверждает, что форма относится именно к этому разделу.
    if request.form_value("section") == subject:
        questions = database.get_attempt_questions(attempt.id)
        section = [aq for aq in questions if aq.subject == subject]
        database.save_answers(attempt.id, ent_logic.parse_section_answers(section, request.form))

    if request.form_value("finish"):
        if attempt.mode == ent_logic.PRACTICE:
            ent_logic.finish_attempt(attempt)
            return redirect(f"/result/{attempt.id}")
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

    questions = database.get_attempt_questions(attempt.id)
    rows = []
    unanswered_total = 0
    for code in attempt.subjects:
        subject_questions = [aq for aq in questions if aq.subject == code]
        answered = sum(1 for aq in subject_questions if aq.answer)
        unanswered_total += len(subject_questions) - answered
        rows.append(fragment(
            '<tr><td><a href="/attempt/$id/$code">$name</a></td>'
            "<td>$answered из $total</td></tr>",
            id=attempt.id, code=code, name=config.SUBJECTS[code].name,
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
        back_href=f"/attempt/{attempt.id}/{attempt.subjects[0]}",
    )
    return page(request, "Завершить тест?", content)


@login_required
def finish_submit(request: Request, attempt_id: int) -> Response:
    """POST /attempt/<id>/finish — окончательно завершает и оценивает тест."""
    attempt, early = _load_active_attempt(request, attempt_id)
    if attempt is None:
        assert early is not None
        return early
    ent_logic.finish_attempt(attempt)
    return redirect(f"/result/{attempt.id}")


# ── Результат и история ──────────────────────────────────────────────────────

def _review_item(aq: AttemptQuestion) -> SafeHTML:
    """Разбор одного задания: мой ответ и правильный ответ."""
    max_points = ent_logic.question_max_points(aq.qtype)
    if aq.points == max_points:
        state = "ok"
    elif aq.points > 0:
        state = "partial"
    else:
        state = "wrong"
    left = SafeHTML("")
    if aq.qtype == config.MATCHING:
        left = fragment(
            '<ul class="match-options">$items</ul>',
            items=join(
                fragment(
                    '<li><span class="letter">$letter</span>$text</li>', letter=letter, text=text
                )
                for letter, text in zip(config.OPTION_LETTERS, aq.options)
            ),
        )
    return fragment(
        '<article class="review-item review-$state">'
        '<header class="question-head"><span class="q-number">Задание $number</span>'
        '<span class="badge badge-$state">$points из $max б.</span></header>'
        "$body$left"
        '<dl class="answers"><dt>Ваш ответ</dt><dd>$mine</dd>'
        "<dt>Правильный ответ</dt><dd>$right</dd></dl></article>",
        state=state,
        number=aq.position,
        points=aq.points,
        max=max_points,
        body=_question_body(aq),
        left=left,
        mine=ent_logic.format_answer(aq, aq.answer),
        right=ent_logic.format_answer(aq, aq.correct),
    )


@login_required
def result_page(request: Request, attempt_id: int) -> Response:
    """GET /result/<id> — баллы по предметам, итог и разбор ответов."""
    attempt = database.get_attempt(attempt_id, _user_id(request))
    if attempt is None:
        return not_found(request)
    if not attempt.is_finished:
        if ent_logic.is_expired(attempt):
            ent_logic.finish_attempt(attempt)
            attempt = database.get_attempt(attempt_id, _user_id(request))
            assert attempt is not None
        else:
            return redirect(f"/attempt/{attempt.id}/{attempt.subjects[0]}")

    questions = database.get_attempt_questions(attempt.id)
    scores = ent_logic.subject_scores(attempt, questions)
    is_mock = attempt.mode == ent_logic.MOCK

    score_rows = join(
        fragment(
            "<tr><td>$name</td><td><strong>$score</strong> из $max</td>"
            '<td><progress max="$max_bar" value="$score"></progress></td></tr>',
            name=item.name, score=item.score, max=item.max_score,
            max_bar=max(item.max_score, 1),
        )
        for item in scores
    )

    review_sections = []
    for item in scores:
        subject_questions = [aq for aq in questions if aq.subject == item.code]
        review_sections.append(fragment(
            '<details class="card review-section"><summary>$name — $score из $max</summary>'
            "$items</details>",
            name=item.name, score=item.score, max=item.max_score,
            items=join(_review_item(aq) for aq in subject_questions)
            or SafeHTML('<p class="muted">Заданий не было.</p>'),
        ))

    official_note = SafeHTML("")
    if is_mock and attempt.max_score < config.MOCK_MAX_SCORE:
        official_note = fragment(
            '<p class="muted">В этом тесте можно было набрать $max баллов: '
            "банк вопросов неполный. "
            "Официальный максимум ЕНТ — $official баллов.</p>",
            max=attempt.max_score, official=config.MOCK_MAX_SCORE,
        )

    duration = int((attempt.finished_at or attempt.started_at) - attempt.started_at)
    content = render(
        "result.html",
        mode_label=MODE_NAMES[attempt.mode],
        heading=_attempt_title(attempt),
        date=_format_datetime(attempt.finished_at),
        duration=_format_duration(duration),
        score=attempt.score,
        max_score=attempt.max_score,
        percent=_percent(attempt.score, attempt.max_score),
        official_note=official_note,
        score_rows=score_rows,
        review=join(review_sections),
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
                "<tr><td>$date</td><td>$mode</td><td>$what</td>"
                "<td><strong>$score</strong> / $max</td><td>$percent%</td>"
                '<td><a class="link" href="/result/$id">Разбор</a></td></tr>',
                date=_format_datetime(attempt.finished_at),
                mode=MODE_NAMES[attempt.mode],
                what=_attempt_title(attempt).split(": ", 1)[1],
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
