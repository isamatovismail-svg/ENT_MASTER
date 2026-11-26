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
from datetime import date
from functools import wraps

import config
from app import database, ent_logic, question_form, schools, views
from app.templates import SafeHTML, fragment, join, render
from app.web import Request, Response, redirect

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
            return views.error_page(request, 403, FORBIDDEN)
        school = database.get_school(school_id)
        if school is None:
            return views.not_found(request)
        return view(request, school=school, **kwargs)

    return views.login_required(wrapper)


def _page(request: Request, school, title: str, content: SafeHTML, status: int = 200) -> Response:
    """Страница кабинета учителя: заголовок школы + содержимое."""
    head = fragment(
        '<nav class="admin-menu" aria-label="Кабинет учителя">'
        '<span class="admin-badge">🏫 $school</span>'
        '<a class="admin-tab" href="/teacher/$id">👥 Ученики и задания</a>'
        '<a class="admin-tab" href="/teacher/$id/assignments/new">＋ Новое задание</a>'
        "$questions$all</nav>$content",
        school=schools.school_title(school["city"], school["name"]), id=school["id"],
        all=SafeHTML('<a class="admin-tab" href="/teacher">🗂 Все школы</a>'
                     if request.user is not None and request.user.is_admin else ""),
        questions=SafeHTML('<a class="admin-tab" href="/teacher/questions">📝 Мои вопросы</a>'
                           if request.user is not None and request.user.is_teacher else ""),
        content=content,
    )
    return views.page(request, f"Кабинет учителя — {title}", head, status)


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
            table = SafeHTML('<div class="card empty">Школ пока нет.</div>')
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
        return views.page(request, "Школы", content)
    school_id = _teacher_school_id(request)
    if school_id is None:
        return views.error_page(request, 403, FORBIDDEN)
    return redirect(f"/teacher/{school_id}")


# ── Ученики и заявки ─────────────────────────────────────────────────────────

@school_access
def school_page(request: Request, school) -> Response:
    """GET /teacher/<id> — заявки, ученики со сводкой, задания."""
    school_id = school["id"]
    csrf = views._csrf_field(request)

    pending = database.list_school_members(school_id, database.SCHOOL_PENDING)
    if pending:
        requests_block = fragment(
            '<section class="card"><h2>🔔 Заявки: $count</h2><ul class="member-list">$rows</ul>'
            "</section>",
            count=len(pending),
            rows=join(
                fragment(
                    '<li><div><strong>$name</strong><small class="muted">$login · '
                    "зарегистрирован $created</small></div>"
                    '<form method="post" action="/teacher/$sid/members/$uid" class="inline-form">$csrf'
                    '<button type="submit" name="action" value="approve" class="btn btn-primary btn-sm">'
                    "Подтвердить</button>"
                    '<button type="submit" name="action" value="reject" class="btn btn-ghost btn-sm">'
                    "Отклонить</button></form></li>",
                    name=row["name"], login=row["login"], created=_date(row["created_at"]),
                    sid=school_id, uid=row["id"], csrf=csrf,
                )
                for row in pending
            ),
        )
    else:
        requests_block = SafeHTML("")

    students = database.list_school_members(school_id, database.SCHOOL_APPROVED)
    if students:
        students_block = fragment(
            '<div class="table-wrap"><table class="table"><thead><tr>'
            "<th>Ученик</th><th>Последний вход</th><th>Пробных ЕНТ</th><th>Тренировок</th>"
            "<th>Средний балл ЕНТ</th><th>Лучший балл ЕНТ</th><th>Средний %</th><th></th>"
            "</tr></thead><tbody>$rows</tbody></table></div>",
            rows=join(
                fragment(
                    "<tr><td><strong>$name</strong><br><small class=\"muted\">$login</small></td>"
                    "<td>$last</td><td>$mocks</td><td>$practices</td><td>$avg</td><td>$best</td>"
                    "<td>$percent</td>"
                    '<td><a class="link" href="/teacher/$sid/students/$uid">Карточка →</a></td></tr>',
                    name=row["name"], login=row["login"], last=_date(row["last_login_at"]),
                    mocks=row["mocks"], practices=row["practices"], avg=_number(row["avg_mock"]),
                    best=_number(row["best_mock"]),
                    percent=_number(row["avg_percent"]) + ("%" if row["avg_percent"] is not None else ""),
                    sid=school_id, uid=row["id"],
                )
                for row in students
            ),
        )
    else:
        students_block = SafeHTML(
            '<div class="card empty">Подтверждённых учеников пока нет. Ученики указывают школу '
            "при регистрации или в профиле, а вы подтверждаете заявку.</div>"
        )

    assignments = database.list_assignments(school_id)
    if assignments:
        rows = []
        for assignment in assignments:
            progress = schools.assignment_progress(assignment)
            done = sum(item.status == "done" for item in progress)
            rows.append(fragment(
                "<tr><td><strong>$title</strong><br><small class=\"muted\">$who</small></td>"
                "<td>$created</td><td>$deadline</td><td>$done из $total</td>"
                '<td><a class="link" href="/teacher/$sid/assignments/$aid">Таблица →</a></td></tr>',
                title=schools.assignment_title(assignment["mode"], assignment["target"],
                                               assignment["count"]),
                who="всем ученикам" if assignment["for_all"] else "выбранным ученикам",
                created=_date(assignment["created_at"]),
                deadline=views._deadline_text(assignment["deadline"]),
                done=done, total=len(progress), sid=school_id, aid=assignment["id"],
            ))
        assignments_block = fragment(
            '<div class="table-wrap"><table class="table"><thead><tr><th>Задание</th>'
            "<th>Выдано</th><th>Срок</th><th>Выполнили</th><th></th></tr></thead>"
            "<tbody>$rows</tbody></table></div>",
            rows=join(rows),
        )
    else:
        assignments_block = SafeHTML('<div class="card empty">Заданий пока нет.</div>')

    content = render(
        "teacher_school.html",
        title=schools.school_title(school["city"], school["name"]),
        count=len(students), requests=requests_block, students=students_block,
        assignments=assignments_block, sid=school_id,
    )
    return _page(request, school, "Ученики", content)


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
        return views.error_page(request, 400, "Неизвестное действие.")
    status, message = action
    if not database.set_member_status(school["id"], user_id, status):
        return views.not_found(request)
    return redirect(f"/teacher/{school['id']}?msg={message}")


# ── Карточка ученика ─────────────────────────────────────────────────────────

def _growth_rows(mocks: list) -> SafeHTML:
    """Рост результата: пробные ЕНТ по датам, процент и изменение к предыдущему."""
    if not mocks:
        return SafeHTML('<p class="muted">Пробных ЕНТ пока нет.</p>')
    rows = []
    previous = None
    for attempt in mocks:
        percent = views._percent(attempt.score, attempt.max_score)
        if previous is None:
            delta = SafeHTML('<span class="muted">—</span>')
        else:
            change = percent - previous
            kind = "up" if change > 0 else "down" if change < 0 else "same"
            delta = fragment('<span class="delta delta-$kind">$sign$change%</span>',
                             kind=kind, sign="+" if change > 0 else "", change=change)
        previous = percent
        rows.append(fragment(
            "<tr><td>$date</td><td><strong>$score</strong> / $max</td>"
            '<td><progress max="100" value="$percent">$percent%</progress> $percent%</td>'
            "<td>$delta</td></tr>",
            date=_date(attempt.finished_at), score=attempt.score, max=attempt.max_score,
            percent=percent, delta=delta,
        ))
    return fragment(
        '<div class="table-wrap"><table class="table growth-table"><thead><tr><th>Дата</th>'
        "<th>Баллы</th><th>Результат</th><th>Изменение</th></tr></thead><tbody>$rows</tbody>"
        "</table></div>",
        rows=join(rows),
    )


@school_access
def student_card(request: Request, school, user_id: int) -> Response:
    """GET /teacher/<id>/students/<uid> — история, предметы, слабые места, рост результата."""
    student = database.get_school_student(school["id"], user_id)
    if student is None:
        return views.not_found(request)
    attempts = database.get_finished_attempts(user_id)
    mocks = sorted((a for a in attempts if a.mode == ent_logic.MOCK),
                   key=lambda a: (a.finished_at or 0, a.id))
    strengths = ent_logic.subject_strengths(user_id)
    weak = [item for item in reversed(strengths) if item.percent < views.STRONG_PERCENT][:3]

    if attempts:
        history = fragment(
            '<div class="table-wrap"><table class="table"><thead><tr><th>Дата</th><th>Режим</th>'
            "<th>Предметы</th><th>Баллы</th><th>%</th><th></th></tr></thead><tbody>$rows</tbody>"
            "</table></div>",
            rows=join(
                fragment(
                    "<tr><td>$date</td><td>$mode</td><td>$what</td>"
                    "<td><strong>$score</strong> / $max</td><td>$percent%</td>"
                    '<td><a class="link" href="/teacher/$sid/students/$uid/attempts/$aid">Разбор →</a>'
                    "</td></tr>",
                    date=_date(a.finished_at), mode=views.MODE_NAMES[a.mode],
                    what=views._attempt_title(a).split(": ", 1)[1], score=a.score,
                    max=a.max_score, percent=views._percent(a.score, a.max_score),
                    sid=school["id"], uid=user_id, aid=a.id,
                )
                for a in attempts
            ),
        )
    else:
        history = SafeHTML('<div class="card empty">Завершённых попыток пока нет.</div>')

    content = render(
        "teacher_student.html",
        name=student["name"], login=student["login"],
        last=_date(student["last_login_at"]), sid=school["id"],
        csrf=views._csrf_field(request), uid=user_id,
        mocks=len(mocks), practices=len(attempts) - len(mocks),
        best=max((a.score for a in mocks), default="—"),
        average=round(sum(a.score for a in mocks) / len(mocks)) if mocks else "—",
        max_score=config.MOCK_MAX_SCORE,
        strengths=views._strength_rows(strengths, "Пока нет решённых заданий."),
        weak=views._strength_rows(weak, "Слабых предметов не найдено — или ещё мало попыток."),
        weak_topics=views.topic_rows(
            ent_logic.weak_topics(user_id, 8),
            f"Слабых тем нет: по всем темам с {ent_logic.MIN_TOPIC_QUESTIONS}+ заданиями результат "
            f"не ниже {ent_logic.WEAK_TOPIC_PERCENT}% — или заданий пока мало."),
        growth=_growth_rows(mocks),
        history=history,
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
    return _page(request, school, "Разбор попытки", views.result_content(attempt, actions))


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
    ) if students else SafeHTML('<p class="muted small">Подтверждённых учеников пока нет.</p>')
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
    return _page(request, school, "Новое задание", content, status)


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
                    status=SafeHTML(views.ASSIGNMENT_STATUS[item.status]),
                )
                for item in progress
            ),
        )
    else:
        table = SafeHTML('<div class="card empty">Задание пока некому выполнять.</div>')
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
        deadline=views._deadline_text(assignment["deadline"]).removeprefix("до "),
        who="всем ученикам школы" if assignment["for_all"] else "выбранным ученикам",
        done=done, total=len(progress), table=table, sid=school["id"], aid=assignment_id,
        csrf=views._csrf_field(request),
    )
    return _page(request, school, "Задание", content)


@school_access
def assignment_delete(request: Request, school, assignment_id: int) -> Response:
    """POST /teacher/<id>/assignments/<aid>/delete — удалить задание своей школы."""
    if not database.delete_assignment(assignment_id, school["id"]):
        return views.not_found(request)
    return redirect(f"/teacher/{school['id']}?msg=assignment_deleted")




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
                request, 403, "Раздел «Мои вопросы» доступен только учителям. "
                "Администратор проверяет вопросы в админке → «Проверка».")
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
        comment = (fragment('<p class="review-comment">💬 $comment</p>', comment=question.review_comment)
                   if question.review_comment else SafeHTML(""))
        if question.status == database.Q_APPROVED:
            actions = SafeHTML('<span class="muted small">в общем банке</span>')
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
            status=SafeHTML(QUESTION_STATUS.get(question.status, "")), id=question.id,
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
        list=join(rows) if rows else SafeHTML(
            '<div class="card empty">Вы ещё не предлагали вопросов.</div>'),
    )
    return _page(request, school, "Мои вопросы", content)


def _question_page(request: Request, school, form, url: str, title: str, errors: list[str],
                   status: int = 200, note: SafeHTML | None = None) -> Response:
    """Форма вопроса учителя (та же, что в админке)."""
    content = question_form.form_content(
        request, form, url, url, title, errors, note,
        back_url="/teacher/questions", back_label="← К моим вопросам",
        submit_label="📨 Отправить на проверку",
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
        return _question_page(request, school, form, url, "Новый вопрос", errors, 400)
    form = question_form.QuestionForm(qtype=question_form.requested_type(request, config.SINGLE))
    subject = request.query_value("subject")
    form.subject = subject if subject in config.SUBJECTS else ""
    return _question_page(request, school, form, url, "Новый вопрос", [])


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
    title = f"Вопрос #{question_id}"
    note = (views._notice("warning", f"Комментарий администратора: {existing.review_comment}")
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
