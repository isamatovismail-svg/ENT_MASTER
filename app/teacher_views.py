"""Кабинет учителя (/teacher): ученики школы, заявки, карточка ученика, задания.

Доступ: учитель — только к СВОЕЙ школе, главный администратор — к любой.
Это проверяется в каждом запросе декоратором school_access (как user_id у попыток):
school_id из адреса сверяется со школой учителя в базе, а ученик и задание
дополнительно ищутся только внутри этой школы. Результаты видны только
у подтверждённых учеников.
"""

import sqlite3
import time
from collections.abc import Callable
from datetime import date, datetime
from functools import wraps
from urllib.parse import urlencode

import config
from app import database, ent_logic, notifications, question_form, schools, student_stats, views
from app.templates import SafeHTML, fragment, join, render
from app.web import Request, Response, redirect
from app.i18n import t

View = Callable[..., Response]

FORBIDDEN = "Кабинет учителя доступен только учителю этой школы."


def _teacher_school_id(request: Request) -> int | None:
    """Школа, которой управляет вошедший учитель (None — он не учитель)."""
    assert request.user is not None
    if not request.user.is_teacher:
        return None
    row = database.get_user_school(request.user.id)
    return row["school_id"] if row is not None else None


def school_access(view: View) -> View:
    """Декоратор: вход + csrf (login_required) и доступ к школе school_id из адреса."""

    @wraps(view)
    def wrapper(request: Request, school_id: int, **kwargs: object) -> Response:
        """Пускает учителя этой школы и главного администратора."""
        assert request.user is not None
        if not request.user.is_admin and _teacher_school_id(request) != school_id:
            return views.error_page(request, 403, t(FORBIDDEN))
        school = database.get_school(school_id)
        if school is None:
            return views.not_found(request)
        return view(request, school=school, **kwargs)

    return views.login_required(wrapper)


def _page(request: Request, school, title: str, content: SafeHTML, status: int = 200) -> Response:
    """Страница кабинета учителя: название школы + содержимое.

    Учителю разделы — в главном меню сайта; главному администратору (у него в меню их нет) —
    вкладки школы и ссылка «Все школы».
    """
    is_admin = request.user is not None and request.user.is_admin
    head = fragment(
        '<nav class="admin-menu" aria-label="Кабинет учителя">'
        '<span class="admin-badge">🏫 $school</span>$tabs</nav>$content',
        school=schools.school_title(school["city"], school["name"]),
        tabs=fragment(
            '<a class="admin-tab" href="/teacher/$id">👥 Ученики</a>'
            '<a class="admin-tab" href="/teacher/$id/assignments">📋 Задания</a>'
            '<a class="admin-tab" href="/teacher">🗂 Все школы</a>', id=school["id"],
        ) if is_admin else SafeHTML(""),
        content=content,
    )
    return views.page(request, t("Кабинет учителя — {title}", title=title), head, status)


def _date(timestamp: float | None) -> str:
    """Дата и время или «—»."""
    return views._format_datetime(timestamp)


def _number(value: float | None) -> str:
    """Округлённое число или «—»."""
    return "—" if value is None else str(round(value))


# ── Вход в кабинет ───────────────────────────────────────────────────────────

@views.login_required
def teacher_home(request: Request) -> Response:
    """GET /teacher — учитель попадает в свою школу, администратор выбирает школу."""
    assert request.user is not None
    if request.user.is_admin:
        rows = database.list_schools()
        if not rows:
            table = fragment('<div class="card empty">Школ пока нет.</div>')
        else:
            table = fragment(
                '<div class="table-wrap"><table class="table"><thead><tr><th>Школа</th>'
                "<th>Учеников</th><th>Заявок</th><th>Учителей</th><th></th></tr></thead>"
                "<tbody>$rows</tbody></table></div>",
                rows=join(
                    fragment(
                        "<tr><td><strong>$title</strong></td><td>$students</td><td>$pending</td>"
                        '<td>$teachers</td><td><a class="link" href="/teacher/$id">Открыть →</a>'
                        "</td></tr>",
                        title=schools.school_title(row["city"], row["name"]),
                        students=row["students"] or 0, pending=row["pending"] or 0,
                        teachers=row["teachers"] or 0, id=row["id"],
                    )
                    for row in rows
                ),
            )
        content = fragment(
            '<section class="page-head"><span class="eyebrow">Кабинет учителя</span>'
            "<h1>🗂 Все школы: $count</h1><p class=\"muted\">Назначить учителя: "
            "<code>python manage_admin.py &lt;логин&gt; --teacher &lt;город&gt; &lt;школа&gt;</code>"
            "</p></section>$table",
            count=len(rows), table=table,
        )
        return views.page(request, t("Школы"), content)
    school_id = _teacher_school_id(request)
    if school_id is None:
        return views.error_page(request, 403, t(FORBIDDEN))
    return redirect(f"/teacher/{school_id}")


@views.login_required
def teacher_assignments_home(request: Request) -> Response:
    """GET /teacher/assignments — пункт меню «Задания»: задания школы учителя."""
    school_id = _teacher_school_id(request)
    if school_id is None:
        return redirect("/teacher")
    return redirect(f"/teacher/{school_id}/assignments")


# ── Ученики и заявки ─────────────────────────────────────────────────────────

def _requests_block(request: Request, school_id: int) -> SafeHTML:
    """Заявки учеников в школу: подтвердить или отклонить."""
    pending = database.list_school_members(school_id, database.SCHOOL_PENDING)
    if not pending:
        return SafeHTML("")
    csrf = views._csrf_field(request)
    return fragment(
        '<section class="card requests-card"><h2>🙋 Заявки в школу: $count</h2>'
        '<ul class="member-list">$rows</ul></section>',
        count=len(pending),
        rows=join(
            fragment(
                '<li><div><strong>$name</strong><small class="muted">$login · '
                "заявка от $created</small></div>"
                '<form method="post" action="/teacher/$sid/members/$uid" class="inline-form">$csrf'
                '<button type="submit" name="action" value="approve" class="btn btn-primary btn-sm">'
                "Принять</button>"
                '<button type="submit" name="action" value="reject" class="btn btn-ghost btn-sm">'
                "Отклонить</button></form></li>",
                name=row["name"], login=row["login"], created=_date(row["created_at"]),
                sid=school_id, uid=row["id"], csrf=csrf,
            )
            for row in pending
        ),
    )


def _activity_text(timestamp: float | None, now: float) -> str:
    """«сегодня 14:30», «вчера», «5 дн. назад» или «не заходил»."""
    if timestamp is None:
        return t("не заходил")
    moment = datetime.fromtimestamp(timestamp)
    today = datetime.fromtimestamp(now).date()
    days = (today - moment.date()).days
    if days <= 0:
        return t("сегодня {time}", time=f"{moment:%H:%M}")
    if days == 1:
        return t("вчера {time}", time=f"{moment:%H:%M}")
    return t("{days} дн. назад", days=days)


def _counts_cell(counts: tuple[int, int]) -> SafeHTML:
    """«📝 1 · 🎯 3» — пробные ЕНТ и тренировки."""
    mocks, practices = counts
    if not mocks and not practices:
        return SafeHTML('<span class="muted">—</span>')
    return fragment('<span class="counts" title="пробных ЕНТ / тренировок">$m / $p</span>', m=mocks, p=practices)


def _percent_cell(value: int | None, extra: str = "") -> SafeHTML:
    if value is None:
        return SafeHTML('<span class="muted">—</span>')
    return fragment("<strong>$value%</strong>$extra", value=value,
                    extra=fragment('<br><small class="muted">$t</small>', t=extra) if extra else SafeHTML(""))


def _trend_cell(trend: int | None) -> SafeHTML:
    if trend is None:
        return SafeHTML('<span class="muted">—</span>')
    if trend >= student_stats.TREND_MIN_CHANGE:
        return fragment('<span class="delta delta-up">▲ +$t%</span>', t=trend)
    if trend <= -student_stats.TREND_MIN_CHANGE:
        return fragment('<span class="delta delta-down">▼ $t%</span>', t=trend)
    return SafeHTML('<span class="delta delta-same">≈ 0</span>')


def _weak_cell(weak: list) -> SafeHTML:
    if not weak:
        return SafeHTML('<span class="muted">—</span>')
    return join(
        fragment('<span class="weak-chip subj-$code">$icon $name $p%</span>', code=item.code,
                 icon=config.SUBJECTS[item.code].icon, name=config.SUBJECTS[item.code].name, p=item.percent)
        for item in weak
    )


# Столбцы таблицы учеников: (код сортировки, заголовок).
STUDENT_COLUMNS = (
    ("name", "Ученик"), ("activity", "Активность"), ("today", "Сегодня"), ("yesterday", "Вчера"),
    ("week", "7 дней"), ("last", "Последний"), ("average", "Средний"), ("best", "Лучший"),
    ("trend", "Изменение"), ("weak", "Слабые предметы"),
)


def _students_table(school_id: int, period: str, sort: str, descending: bool) -> SafeHTML:
    """Таблица всех учеников школы с сортировкой по любому столбцу."""
    now = time.time()
    rows = student_stats.sort_rows(student_stats.school_overview(school_id, period, now), sort, descending)
    if not rows:
        return fragment('<div class="card empty">Подтверждённых учеников пока нет. Ученики указывают школу '
            "при регистрации или в профиле, а вы принимаете заявку.</div>")

    def header(code: str, label: str) -> SafeHTML:
        active = code == sort
        next_desc = (not descending) if active else student_stats.DEFAULT_DESC.get(code, True)
        arrow = (" ▼" if descending else " ▲") if active else ""
        return fragment(
            '<th><a class="sort-link$cls" href="?$query">$label$arrow</a></th>',
            cls=" sort-active" if active else "", label=label, arrow=arrow,
            query=urlencode({"period": period, "sort": code, "dir": "desc" if next_desc else "asc"}),
        )

    body = join(
        fragment(
            '<tr class="$cls"><td><a class="link" href="/teacher/$sid/students/$uid"><strong>$name</strong></a>'
            "$help<br><small class=\"muted\">$login</small></td>"
            "<td>$activity</td><td>$today</td><td>$yesterday</td><td>$week</td>"
            "<td>$last</td><td>$avg</td><td>$best</td><td>$trend</td><td>$weak</td></tr>",
            cls="row-help" if row.needs_help else "", sid=school_id, uid=row.user_id, name=row.name,
            help=(fragment(' <span class="badge badge-wrong">нужна помощь</span>') if row.needs_help else SafeHTML("")),
            login=row.login, activity=_activity_text(row.last_activity, now),
            today=_counts_cell(row.today), yesterday=_counts_cell(row.yesterday), week=_counts_cell(row.week),
            last=_percent_cell(row.last, t("ЕНТ {score}/{max}", score=row.last_mock_score, max=config.MOCK_MAX_SCORE)
                               if row.last_mock_score is not None else ""),
            avg=_percent_cell(row.average), best=_percent_cell(row.best),
            trend=_trend_cell(row.trend), weak=_weak_cell(row.weak),
        )
        for row in rows
    )
    return fragment(
        '<div class="table-wrap"><table class="table students-table"><thead><tr>$head</tr></thead>'
        "<tbody>$body</tbody></table></div>",
        head=join(header(code, t(label)) for code, label in STUDENT_COLUMNS), body=body,
    )


def _period_filter(period: str, sort: str, descending: bool) -> SafeHTML:
    """Переключатель периода: сегодня, вчера, 7 дней, 30 дней, всё время."""
    return fragment(
        '<nav class="period-filter" aria-label="Период">$links</nav>',
        links=join(
            fragment('<a class="chip$cls" href="?$query">$label</a>',
                     cls=" chip-active" if code == period else "", label=label,
                     query=urlencode({"period": code, "sort": sort, "dir": "desc" if descending else "asc"}))
            for code, label in student_stats.PERIODS.items()
        ),
    )


@school_access
def school_page(request: Request, school) -> Response:
    """GET /teacher/<id> — заявки и таблица всех учеников школы."""
    school_id = school["id"]
    period = request.query_value("period")
    period = period if period in student_stats.PERIODS else student_stats.DEFAULT_PERIOD
    sort = request.query_value("sort")
    sort = sort if sort in student_stats.SORT_KEYS else student_stats.DEFAULT_SORT
    descending = request.query_value("dir", "desc") != "asc"
    students = database.list_school_members(school_id, database.SCHOOL_APPROVED)
    content = render(
        "teacher_school.html",
        title=schools.school_title(school["city"], school["name"]),
        count=len(students), requests=_requests_block(request, school_id),
        period_label=student_stats.PERIODS[period].lower(),
        periods=_period_filter(period, sort, descending),
        students=_students_table(school_id, period, sort, descending), sid=school_id,
    )
    return _page(request, school, t("Ученики"), content)


@school_access
def assignments_page(request: Request, school) -> Response:
    """GET /teacher/<id>/assignments — все задания школы и кто их выполнил."""
    school_id = school["id"]
    assignments = database.list_assignments(school_id)
    if assignments:
        rows = []
        for assignment in assignments:
            progress = schools.assignment_progress(assignment)
            done = sum(item.status == "done" for item in progress)
            rows.append(fragment(
                "<tr><td><strong>$title</strong><br><small class=\"muted\">$who</small></td>"
                "<td>$created</td><td>$deadline</td>"
                '<td><progress max="$total" value="$done">$done</progress> $done из $total</td>'
                '<td><a class="link" href="/teacher/$sid/assignments/$aid">Кто выполнил →</a></td></tr>',
                title=schools.assignment_title(assignment["mode"], assignment["target"],
                                               assignment["count"]),
                who=t("всем ученикам") if assignment["for_all"] else t("выбранным ученикам"),
                created=_date(assignment["created_at"]),
                deadline=views._deadline_text(assignment["deadline"]),
                done=done, total=len(progress) or 1, sid=school_id, aid=assignment["id"],
            ))
        table = fragment(
            '<div class="table-wrap"><table class="table"><thead><tr><th>Задание</th>'
            "<th>Выдано</th><th>Срок</th><th>Выполнили</th><th></th></tr></thead>"
            "<tbody>$rows</tbody></table></div>",
            rows=join(rows),
        )
    else:
        table = fragment('<div class="card empty">Заданий пока нет. Нажмите «Выдать задание».</div>')
    content = fragment(
        '<section class="page-head admin-head"><div><span class="eyebrow">Задания</span>'
        "<h1>📋 Задания школы: $count</h1>"
        '<p class="muted">Ученик получает уведомление о новом задании и напоминание за сутки до срока. '
        "Засчитываются попытки, завершённые после выдачи задания и до конца дня срока.</p></div>"
        '<a class="btn btn-primary" href="/teacher/$sid/assignments/new">＋ Выдать задание</a></section>$table',
        count=len(assignments), sid=school_id, table=table,
    )
    return _page(request, school, t("Задания"), content)


@school_access
def member_action(request: Request, school, user_id: int) -> Response:
    """POST /teacher/<id>/members/<uid> — подтвердить, отклонить заявку или исключить ученика."""
    statuses = {
        "approve": (database.SCHOOL_APPROVED, "member_approved"),
        "reject": (database.SCHOOL_REJECTED, "member_rejected"),
        "remove": (None, "member_removed"),
    }
    action = statuses.get(request.form_value("action"))
    if action is None:
        return views.error_page(request, 400, t("Неизвестное действие."))
    status, message = action
    if not database.set_member_status(school["id"], user_id, status):
        return views.not_found(request)
    if status is not None:
        notifications.request_decided(school["id"], user_id, status == database.SCHOOL_APPROVED)
    return redirect(f"/teacher/{school['id']}?msg={message}")


# ── Карточка ученика ─────────────────────────────────────────────────────────

WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")


def _day_title(day: date, today: date) -> str:
    """«Сегодня», «Вчера» или «25.11.2026, среда»."""
    if day == today:
        return t("Сегодня")
    if (today - day).days == 1:
        return t("Вчера")
    return f"{day:%d.%m.%Y}, {t(WEEKDAYS[day.weekday()])}"


def _timeline_block(school_id: int, user_id: int) -> SafeHTML:
    """Лента ученика по дням: что делал, баллы, по каким предметам."""
    days = student_stats.timeline(user_id)
    if not days:
        return fragment('<div class="card empty">Ученик ещё не завершил ни одного теста.</div>')
    today = date.today()
    blocks = []
    for day, items in days:
        entries = join(
            fragment(
                '<li class="timeline-item"><span class="timeline-time">$time</span>'
                '<div class="timeline-body"><strong>$mode</strong> · <strong>$score</strong> / $max '
                '($percent%)<div class="timeline-subjects">$subjects</div></div>'
                '<a class="link" href="/teacher/$sid/students/$uid/attempts/$aid">Разбор →</a></li>',
                time=datetime.fromtimestamp(item.attempt.finished_at or 0).strftime("%H:%M"),
                mode=views.MODE_NAMES[item.attempt.mode], score=item.attempt.score,
                max=item.attempt.max_score, percent=item.percent,
                subjects=join(
                    fragment('<span class="weak-chip subj-$code">$icon $name: $p / $m</span>', code=code,
                             icon=config.SUBJECTS[code].icon, name=config.SUBJECTS[code].name, p=points, m=most)
                    for code, points, most in item.subjects
                ),
                sid=school_id, uid=user_id, aid=item.attempt.id,
            )
            for item in items
        )
        mocks = sum(item.attempt.mode == ent_logic.MOCK for item in items)
        blocks.append(fragment(
            '<section class="timeline-day"><h3>$title <small class="muted">пробных ЕНТ: $mocks · '
            "тренировок: $practices</small></h3><ul class=\"timeline\">$entries</ul></section>",
            title=_day_title(day, today), mocks=mocks, practices=len(items) - mocks, entries=entries,
        ))
    return join(blocks)


@school_access
def student_card(request: Request, school, user_id: int) -> Response:
    """GET /teacher/<id>/students/<uid> — сводка, слабые места и лента по дням."""
    student = database.get_school_student(school["id"], user_id)
    if student is None:
        return views.not_found(request)
    attempts = database.get_finished_attempts(user_id)
    mocks = [a for a in attempts if a.mode == ent_logic.MOCK]
    strengths = ent_logic.subject_strengths(user_id)
    weak = [item for item in reversed(strengths) if item.percent < views.STRONG_PERCENT][:3]
    content = render(
        "teacher_student.html",
        name=student["name"], login=student["login"],
        last=_date(student["last_login_at"]), sid=school["id"],
        csrf=views._csrf_field(request), uid=user_id,
        mocks=len(mocks), practices=len(attempts) - len(mocks),
        best=max((a.score for a in mocks), default="—"),
        average=round(sum(a.score for a in mocks) / len(mocks)) if mocks else "—",
        max_score=config.MOCK_MAX_SCORE,
        weak=views._strength_rows(weak, t("Слабых предметов не найдено — или ещё мало попыток.")),
        weak_topics=views.topic_rows(
            ent_logic.weak_topics(user_id, 6),
            t("Слабых тем нет: по всем темам с {n}+ заданиями результат не ниже {p}% — или заданий пока мало.",
              n=ent_logic.MIN_TOPIC_QUESTIONS, p=ent_logic.WEAK_TOPIC_PERCENT)),
        timeline=_timeline_block(school["id"], user_id),
    )
    return _page(request, school, student["name"], content)


@school_access
def student_attempt(request: Request, school, user_id: int, attempt_id: int) -> Response:
    """GET /teacher/<id>/students/<uid>/attempts/<aid> — разбор попытки ученика."""
    student = database.get_school_student(school["id"], user_id)
    attempt = database.get_attempt(attempt_id, user_id)
    if student is None or attempt is None or not attempt.is_finished:
        return views.not_found(request)
    actions = fragment(
        '<a class="btn btn-primary" href="/teacher/$sid/students/$uid">← К ученику $name</a>',
        sid=school["id"], uid=user_id, name=student["name"],
    )
    return _page(request, school, t("Разбор попытки"), views.result_content(attempt, actions))


# ── Задания ──────────────────────────────────────────────────────────────────

def _assignment_form(request: Request, school, errors: list[str], status: int = 200) -> Response:
    """Форма нового задания (значения сохраняются при ошибке)."""
    form = request.form_value
    mode = form("mode", "mock")
    chosen = set(request.form.get("students", []))
    for_all = form("for_all", "1") == "1"
    pair_value = form("pair")
    subject_value = form("subject")
    students = database.list_school_members(school["id"], database.SCHOOL_APPROVED)

    def checked(flag: bool) -> SafeHTML:
        return SafeHTML(" checked" if flag else "")

    def selected(flag: bool) -> SafeHTML:
        return SafeHTML(" selected" if flag else "")

    pairs = join(
        fragment('<option value="$value"$sel>$label</option>', value=f"{a},{b}",
                 sel=selected(pair_value == f"{a},{b}"),
                 label=f"{config.SUBJECTS[a].name} + {config.SUBJECTS[b].name}")
        for a, b in config.PROFILE_PAIRS
    )
    subjects = join(
        fragment('<option value="$code"$sel>$name</option>', code=code,
                 sel=selected(subject_value == code), name=info.name)
        for code, info in config.SUBJECTS.items()
    )
    student_boxes = join(
        fragment('<label class="check"><input type="checkbox" name="students" value="$id"$c> $name'
                 "</label>", id=row["id"], c=checked(str(row["id"]) in chosen), name=row["name"])
        for row in students
    ) if students else fragment('<p class="muted small">Подтверждённых учеников пока нет.</p>')
    content = render(
        "teacher_assignment_form.html",
        errors=views._errors_block(errors), csrf=views._csrf_field(request), sid=school["id"],
        mock_checked=checked(mode == "mock"), practice_checked=checked(mode == "practice"),
        any_pair=selected(not pair_value), pairs=pairs,
        no_subject=selected(not subject_value), subjects=subjects,
        count=form("count", "1"), max_count=schools.ASSIGNMENT_MAX_COUNT,
        deadline=form("deadline"), today=date.today().isoformat(),
        all_checked=checked(for_all), some_checked=checked(not for_all),
        students=student_boxes,
    )
    return _page(request, school, t("Новое задание"), content, status)


@school_access
def assignment_new(request: Request, school) -> Response:
    """GET/POST /teacher/<id>/assignments/new — выдать задание."""
    if request.method == "GET":
        return _assignment_form(request, school, [])
    assert request.user is not None
    ids = [int(value) for value in request.form.get("students", []) if value.isdigit()]
    try:
        assignment_id = schools.create_assignment(
            school["id"], request.user.id, request.form_value("mode"),
            request.form_value("subject"), request.form_value("pair"),
            request.form_value("count"), request.form_value("deadline"),
            request.form_value("for_all", "1") == "1", ids,
        )
    except schools.SchoolError as error:
        return _assignment_form(request, school, error.errors, 400)
    return redirect(f"/teacher/{school['id']}/assignments/{assignment_id}?msg=assignment_created")


@school_access
def assignment_page(request: Request, school, assignment_id: int) -> Response:
    """GET /teacher/<id>/assignments/<aid> — кто выполнил, кто нет, баллы."""
    assignment = database.get_assignment(assignment_id, school["id"])
    if assignment is None:
        return views.not_found(request)
    progress = schools.assignment_progress(assignment)
    if progress:
        table = fragment(
            '<div class="table-wrap"><table class="table"><thead><tr><th>Ученик</th>'
            "<th>Сделано</th><th>Баллы засчитанных попыток</th><th>Статус</th></tr></thead>"
            "<tbody>$rows</tbody></table></div>",
            rows=join(
                fragment(
                    '<tr><td><a class="link" href="/teacher/$sid/students/$uid">$name</a></td>'
                    "<td>$done из $count</td><td>$scores</td><td>$status</td></tr>",
                    sid=school["id"], uid=item.user_id, name=item.name, done=item.done,
                    count=assignment["count"], scores=", ".join(item.scores) or "—",
                    status=fragment(views.ASSIGNMENT_STATUS[item.status]),
                )
                for item in progress
            ),
        )
    else:
        table = fragment('<div class="card empty">Задание пока некому выполнять.</div>')
    done = sum(item.status == "done" for item in progress)
    content = fragment(
        '<section class="page-head"><span class="eyebrow">Задание</span><h1>📋 $title</h1>'
        '<p class="muted">Выдано $created · срок $deadline · $who · выполнили $done из $total. '
        "Засчитываются попытки, завершённые после выдачи задания и до конца дня срока.</p>"
        "</section>$table"
        '<form method="post" action="/teacher/$sid/assignments/$aid/delete" class="section">'
        '$csrf<button type="submit" class="btn btn-link">Удалить задание</button></form>',
        title=schools.assignment_title(assignment["mode"], assignment["target"], assignment["count"]),
        created=_date(assignment["created_at"]),
        deadline=views._date_only(assignment["deadline"]),
        who=t("всем ученикам школы") if assignment["for_all"] else t("выбранным ученикам"),
        done=done, total=len(progress), table=table, sid=school["id"], aid=assignment_id,
        csrf=views._csrf_field(request),
    )
    return _page(request, school, t("Задание"), content)


@school_access
def assignment_delete(request: Request, school, assignment_id: int) -> Response:
    """POST /teacher/<id>/assignments/<aid>/delete — удалить задание своей школы."""
    if not database.delete_assignment(assignment_id, school["id"]):
        return views.not_found(request)
    return redirect(f"/teacher/{school['id']}/assignments?msg=assignment_deleted")




# ── Мои вопросы: учитель предлагает вопросы в общий банк ─────────────────────

QUESTION_STATUS = {
    database.Q_PENDING: '<span class="badge badge-warn">⏳ на проверке</span>',
    database.Q_APPROVED: '<span class="badge badge-ok">✅ одобрен</span>',
    database.Q_REJECTED: '<span class="badge badge-wrong">❌ отклонён</span>',
}


def teacher_only(view: View) -> View:
    """Декоратор: вход + csrf и роль учителя (вопросы учителя привязаны к нему самому)."""

    @wraps(view)
    def wrapper(request: Request, **kwargs: object) -> Response:
        """Пускает только учителя со школой."""
        school_id = _teacher_school_id(request)
        school = database.get_school(school_id) if school_id is not None else None
        if school is None:
            return views.error_page(
                request, 403, t("Раздел «Мои вопросы» доступен только учителям. "
                "Администратор проверяет вопросы в админке → «Проверка»."))
        return view(request, school=school, **kwargs)

    return views.login_required(wrapper)


@teacher_only
def my_questions(request: Request, school) -> Response:
    """GET /teacher/questions — вопросы учителя, их статусы и комментарии администратора."""
    assert request.user is not None
    items = database.list_author_questions(request.user.id)
    csrf = views._csrf_field(request)
    rows = []
    for question in items:
        comment = (fragment('<p class="review-comment">💬 $comment</p>', comment=t(question.review_comment))
                   if question.review_comment else SafeHTML(""))
        if question.status == database.Q_APPROVED:
            actions = fragment('<span class="muted small">в общем банке</span>')
        else:
            actions = fragment(
                '<a class="link" href="/teacher/questions/$id/edit">Изменить</a>'
                '<form method="post" action="/teacher/questions/$id/delete" class="inline-form">$csrf'
                '<button type="submit" class="btn btn-link">Удалить</button></form>',
                id=question.id, csrf=csrf,
            )
        rows.append(fragment(
            '<article class="card my-question"><header class="review-head">$status'
            '<span class="muted small">#$id · $icon $subject · $type · отправлен $date</span></header>'
            '<p><strong>$text</strong></p>$comment<div class="review-actions">$actions</div></article>',
            status=fragment(QUESTION_STATUS.get(question.status, "")), id=question.id,
            icon=views._icon(question.subject), subject=config.SUBJECTS[question.subject].name,
            type=config.QUESTION_TYPE_NAMES[question.qtype],
            date=_date(question.submitted_at), text=question.text, comment=comment,
            actions=actions,
        ))
    counts = {status: sum(q.status == status for q in items) for status in QUESTION_STATUS}
    content = fragment(
        '<section class="page-head admin-head"><div><span class="eyebrow">Мои вопросы</span>'
        "<h1>📝 Вопросы для общего банка</h1>"
        '<p class="muted">На проверке: $pending · одобрено: $approved · отклонено: $rejected. '
        "Новый вопрос попадает в тесты только после одобрения администратором — тогда он "
        "доступен ученикам всех школ. Отклонённый вопрос можно исправить и отправить снова.</p>"
        '</div><a class="btn btn-primary" href="/teacher/questions/new">＋ Предложить вопрос</a>'
        "</section>$list",
        pending=counts[database.Q_PENDING], approved=counts[database.Q_APPROVED],
        rejected=counts[database.Q_REJECTED],
        list=join(rows) if rows else fragment('<div class="card empty">Вы ещё не предлагали вопросов.</div>'),
    )
    return _page(request, school, t("Мои вопросы"), content)


def _question_page(request: Request, school, form, url: str, title: str, errors: list[str],
                   status: int = 200, note: SafeHTML | None = None) -> Response:
    """Форма вопроса учителя (та же, что в админке)."""
    content = question_form.form_content(
        request, form, url, url, title, errors, note,
        back_url="/teacher/questions", back_label=t("← К моим вопросам"),
        submit_label=t("📨 Отправить на проверку"),
    )
    return _page(request, school, title, content, status)


@teacher_only
def my_question_new(request: Request, school) -> Response:
    """GET/POST /teacher/questions/new — новый вопрос уходит на проверку."""
    assert request.user is not None
    url = "/teacher/questions/new"
    if request.method == "POST":
        form = question_form.form_from_request(request)
        question, errors = question_form.build_question(form)
        if question is not None:
            try:
                database.insert_teacher_question(question, request.user.id, time.time())
            except sqlite3.IntegrityError:
                errors = question_form.duplicate_error()
            else:
                return redirect("/teacher/questions?msg=tq_submitted")
        return _question_page(request, school, form, url, t("Новый вопрос"), errors, 400)
    form = question_form.QuestionForm(qtype=question_form.requested_type(request, config.SINGLE))
    subject = request.query_value("subject")
    form.subject = subject if subject in config.SUBJECTS else ""
    return _question_page(request, school, form, url, t("Новый вопрос"), [])


@teacher_only
def my_question_edit(request: Request, school, question_id: int) -> Response:
    """GET/POST /teacher/questions/<id>/edit — исправить вопрос на проверке или отклонённый."""
    assert request.user is not None
    existing = database.get_author_question(question_id, request.user.id)
    if existing is None:
        return views.not_found(request)
    if existing.status == database.Q_APPROVED:
        return redirect("/teacher/questions?msg=tq_locked")
    url = f"/teacher/questions/{question_id}/edit"
    title = t("Вопрос #{n}", n=question_id)
    note = (views._notice("warning", t("Комментарий администратора: {c}", c=existing.review_comment))
            if existing.review_comment else None)
    if request.method == "POST":
        form = question_form.form_from_request(request)
        question, errors = question_form.build_question(form, question_id)
        if question is not None:
            try:
                saved = database.resubmit_author_question(question, request.user.id, time.time())
            except sqlite3.IntegrityError:
                errors = question_form.duplicate_error()
            else:
                if not saved:
                    return redirect("/teacher/questions?msg=tq_locked")
                return redirect("/teacher/questions?msg=tq_resubmitted")
        return _question_page(request, school, form, url, title, errors, 400, note)
    form = question_form.form_from_question(
        existing, question_form.requested_type(request, existing.qtype))
    return _question_page(request, school, form, url, title, [], note=note)


@teacher_only
def my_question_delete(request: Request, school, question_id: int) -> Response:
    """POST /teacher/questions/<id>/delete — удалить свой вопрос (если он ещё не одобрен)."""
    assert request.user is not None
    if database.get_author_question(question_id, request.user.id) is None:
        return views.not_found(request)
    if not database.delete_author_question(question_id, request.user.id):
        return redirect("/teacher/questions?msg=tq_locked")
    return redirect("/teacher/questions?msg=tq_deleted")
