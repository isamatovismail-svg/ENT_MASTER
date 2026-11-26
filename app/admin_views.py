"""Админ-панель: статистика, банк вопросов (добавить / изменить / удалить) и пользователи.

Все страницы доступны только пользователям с ролью admin (см. manage_admin.py).
Все POST-формы проверяют csrf-токен (декоратор views.login_required).
Без JavaScript: тип вопроса выбирается ссылкой, форма для каждого типа своя.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from urllib.parse import urlencode

import config
from app import auth, database, ent_logic, views
from app.database import Question
from app.question_bank import validate_question
from app.templates import SafeHTML, fragment, join, render
from app.web import Request, Response, redirect

View = Callable[..., Response]

PAGE_SIZE = 30            # вопросов на странице списка
LEFT_ROWS = 6             # строк «слева» в форме задания на соответствие
TEXT_MAX_LENGTH = 4000    # ограничение длины текстовых полей формы
OPTION_MAX_LENGTH = 500


def admin_required(view: View) -> View:
    """Декоратор: только для администратора (гостя — на вход, остальным — 403)."""

    @wraps(view)
    def wrapper(request: Request, **kwargs: object) -> Response:
        """Проверяет роль после проверки входа и csrf."""
        assert request.user is not None
        if not request.user.is_admin:
            return views.error_page(request, 403, "Эта страница доступна только администраторам.")
        return view(request, **kwargs)

    return views.login_required(wrapper)


def _admin_page(request: Request, title: str, current: str, content: SafeHTML,
                status: int = 200) -> Response:
    """Страница админки: подменю разделов + содержимое."""
    links = (("/admin", "📊 Обзор", "home"), ("/admin/questions", "📚 Вопросы", "questions"),
             ("/admin/users", "👥 Пользователи", "users"))
    menu = join(
        fragment('<a href="$href" class="admin-tab$active">$label</a>', href=href, label=label,
                 active=SafeHTML(" admin-tab-active" if key == current else ""))
        for href, label, key in links
    )
    body = fragment(
        '<nav class="admin-menu" aria-label="Разделы админки">'
        '<span class="admin-badge">⚙️ Админка</span>$menu</nav>$content',
        menu=menu, content=content,
    )
    return views.page(request, f"Админка — {title}", body, status)


# ── Обзор ────────────────────────────────────────────────────────────────────

def _bank_rows(counts: dict[tuple[str, str], int]) -> tuple[SafeHTML, int]:
    """Строки таблицы «вопросов по предметам» и число предметов ниже нормы ЕНТ."""
    rows = []
    below = 0
    for subject in config.SUBJECTS.values():
        quota = dict(subject.quota)
        cells = []
        missing = 0
        for qtype in config.QUESTION_TYPES:
            have = counts.get((subject.code, qtype), 0)
            need = quota.get(qtype, 0)
            missing += max(0, need - have)
            if need:
                kind = "ok" if have >= need else "warn"
                cells.append(fragment(
                    '<td><span class="badge badge-$kind">$have / $need</span></td>',
                    kind=kind, have=have, need=need,
                ))
            else:
                cells.append(fragment('<td class="muted">$have</td>', have=have))
        total = sum(counts.get((subject.code, qtype), 0) for qtype in config.QUESTION_TYPES)
        if missing:
            below += 1
            status = fragment(
                '<span class="badge badge-warn">⚠ меньше нормы</span>'
                '<small class="status-note">не хватает $n</small>', n=missing
            )
        else:
            status = SafeHTML('<span class="badge badge-ok">✅ норма ЕНТ</span>')
        rows.append(fragment(
            '<tr><td><a class="subject-link" href="/admin/questions?$query">$icon $name</a></td>'
            "$cells<td><strong>$total</strong> / $norm</td><td>$status</td></tr>",
            query=urlencode({"subject": subject.code}),
            icon=views._icon(subject.code),
            name=subject.name,
            cells=join(cells),
            total=total,
            norm=subject.question_count,
            status=status,
        ))
    return join(rows), below


@admin_required
def dashboard(request: Request) -> Response:
    """GET /admin — общая статистика и наполненность банка вопросов."""
    stats = database.site_stats()
    counts = database.question_counts()
    rows, below = _bank_rows(counts)
    avg_mock = round(stats["avg_mock_score"]) if stats["avg_mock_score"] is not None else "—"
    avg_percent = round(stats["avg_percent"]) if stats["avg_percent"] is not None else "—"
    cards = join((
        views._stat_card("👥", "total", "Пользователи", stats["users"], "",
                         f"администраторов: {stats['admins']}"),
        views._stat_card("📝", "last", "Завершённых попыток", stats["attempts"], "",
                         f"пробных: {stats['mocks']} · тренировок: {stats['practices']}"),
        views._stat_card("⭐", "best", "Средний балл", avg_mock, f"из {config.MOCK_MAX_SCORE}",
                         "по всем пробным ЕНТ"),
        views._stat_card("🎯", "avg", "Средний результат", avg_percent,
                         "%" if stats["avg_percent"] is not None else "",
                         "доля баллов во всех попытках"),
    ))
    content = render(
        "admin_dashboard.html",
        cards=cards,
        bank_rows=rows,
        total_questions=sum(counts.values()),
        below=below,
        type_headers=join(
            fragment("<th>$name</th>", name=config.QUESTION_TYPE_NAMES[qtype])
            for qtype in config.QUESTION_TYPES
        ),
    )
    return _admin_page(request, "Обзор", "home", content)


# ── Список вопросов ──────────────────────────────────────────────────────────

def _short(text: str, limit: int = 140) -> str:
    """Обрезает длинный текст для таблицы."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _matches(question: Question, needle: str) -> bool:
    """Поиск без учёта регистра по тексту, контексту, вариантам и объяснению."""
    haystack = " ".join(
        [question.text, question.context, question.explanation, *question.options, *question.left]
    )
    return needle in haystack.casefold()


@admin_required
def questions(request: Request) -> Response:
    """GET /admin/questions — список вопросов с фильтром по предмету и поиском."""
    subject = request.query_value("subject")
    if subject not in config.SUBJECTS:
        subject = ""
    search = request.query_value("q").strip()[:200]
    try:
        page_number = max(1, int(request.query_value("page", "1")))
    except ValueError:
        page_number = 1

    found = database.list_questions(subject or None)
    if search:
        needle = search.casefold()
        found = [question for question in found if _matches(question, needle)]
    pages = max(1, -(-len(found) // PAGE_SIZE))
    page_number = min(page_number, pages)
    shown = found[(page_number - 1) * PAGE_SIZE: page_number * PAGE_SIZE]

    rows = join(
        fragment(
            "<tr><td class=\"muted\">#$id</td>"
            '<td><span class="subject-link">$icon $subject</span></td>'
            '<td><span class="tag">$type</span></td>'
            '<td class="q-cell">$text</td><td>$used</td>'
            '<td class="row-actions"><a class="btn btn-secondary btn-sm" href="/admin/questions/$id/edit">'
            "Изменить</a>"
            '<a class="btn btn-ghost btn-sm" href="/admin/questions/$id/delete">Удалить</a></td></tr>',
            id=question.id,
            icon=views._icon(question.subject),
            subject=config.SUBJECTS[question.subject].name if question.subject in config.SUBJECTS
            else question.subject,
            type=config.QUESTION_TYPE_NAMES.get(question.qtype, question.qtype),
            text=_short(question.text),
            used=question.used,
        )
        for question in shown
    )
    if not shown:
        table = SafeHTML('<div class="card empty">Ничего не найдено. Измените фильтр или поиск.</div>')
    else:
        table = fragment(
            '<div class="table-wrap"><table class="table admin-table"><thead><tr>'
            "<th>№</th><th>Предмет</th><th>Тип</th><th>Вопрос</th><th>В попытках</th><th></th>"
            "</tr></thead><tbody>$rows</tbody></table></div>",
            rows=rows,
        )

    def page_link(number: int, label: str) -> SafeHTML:
        """Ссылка на страницу списка с теми же фильтрами."""
        query = urlencode({key: value for key, value in
                           (("subject", subject), ("q", search), ("page", number)) if value})
        return fragment('<a class="btn btn-ghost btn-sm" href="/admin/questions?$q">$label</a>',
                        q=query, label=label)

    pager = SafeHTML("")
    if pages > 1:
        pager = fragment(
            '<nav class="pager" aria-label="Страницы">$prev<span>Страница $n из $total</span>$next</nav>',
            prev=page_link(page_number - 1, "← Назад") if page_number > 1 else SafeHTML(""),
            next=page_link(page_number + 1, "Далее →") if page_number < pages else SafeHTML(""),
            n=page_number, total=pages,
        )

    subject_options = join(
        [fragment('<option value="">Все предметы</option>')] + [
            fragment('<option value="$code" $sel>$icon $name</option>', code=code,
                     sel=SafeHTML("selected" if code == subject else ""),
                     icon=info.icon, name=info.name)
            for code, info in config.SUBJECTS.items()
        ]
    )
    content = render(
        "admin_questions.html",
        subject_options=subject_options,
        search=search,
        count=len(found),
        table=table,
        pager=pager,
        new_query=urlencode({"subject": subject}) if subject else "",
    )
    return _admin_page(request, "Вопросы", "questions", content)


# ── Форма вопроса ────────────────────────────────────────────────────────────

@dataclass
class QuestionForm:
    """Значения полей формы вопроса (в том числе после ошибки — чтобы не вводить заново)."""

    subject: str = ""
    qtype: str = config.SINGLE
    context: str = ""
    text: str = ""
    options: list[str] = field(default_factory=lambda: [""] * len(config.OPTION_LETTERS))
    correct: set[str] = field(default_factory=set)
    left: list[str] = field(default_factory=lambda: [""] * LEFT_ROWS)
    match: list[str] = field(default_factory=lambda: [""] * LEFT_ROWS)
    explanation: str = ""


def _form_from_question(question: Question, qtype: str) -> QuestionForm:
    """Заполняет форму данными вопроса (qtype может отличаться — смена типа)."""
    form = QuestionForm(
        subject=question.subject, qtype=qtype, context=question.context,
        text=question.text, explanation=question.explanation,
    )
    for index, option in enumerate(question.options[: len(form.options)]):
        form.options[index] = option
    same_kind = (qtype == config.MATCHING) == (question.qtype == config.MATCHING)
    if same_kind and qtype == config.MATCHING:
        for index, (left, letter) in enumerate(list(zip(question.left, question.correct))[:LEFT_ROWS]):
            form.left[index] = left
            form.match[index] = letter
    elif same_kind:
        form.correct = set(question.correct)
    return form


def _form_from_request(request: Request) -> QuestionForm:
    """Читает поля формы из POST-запроса."""
    qtype = request.form_value("type")
    form = QuestionForm(
        subject=request.form_value("subject"),
        qtype=qtype if qtype in config.QUESTION_TYPES else config.SINGLE,
        context=request.form_value("context").strip(),
        text=request.form_value("text").strip(),
        explanation=request.form_value("explanation").strip(),
    )
    letters = config.OPTION_LETTERS
    form.options = [request.form_value(f"opt_{letter}").strip() for letter in letters]
    form.correct = {value for value in request.form.get("correct", []) if value in letters}
    form.left = [request.form_value(f"left_{index}").strip() for index in range(LEFT_ROWS)]
    form.match = [
        value if value in letters else ""
        for value in (request.form_value(f"match_{index}") for index in range(LEFT_ROWS))
    ]
    return form


def _trim(values: list[str]) -> list[str]:
    """Убирает пустые значения в конце списка."""
    values = list(values)
    while values and not values[-1]:
        values.pop()
    return values


def _build_question(form: QuestionForm, question_id: int = 0) -> tuple[Question | None, list[str]]:
    """Проверяет форму и собирает из неё вопрос. Возвращает (вопрос или None, ошибки)."""
    errors: list[str] = []
    if form.subject not in config.SUBJECTS:
        errors.append("Выберите предмет.")
    for name, value, limit in (("Текст вопроса", form.text, TEXT_MAX_LENGTH),
                               ("Контекст", form.context, TEXT_MAX_LENGTH),
                               ("Объяснение", form.explanation, TEXT_MAX_LENGTH)):
        if len(value) > limit:
            errors.append(f"{name}: не длиннее {limit} символов.")
    if any(len(option) > OPTION_MAX_LENGTH for option in form.options + form.left):
        errors.append(f"Варианты и строки — не длиннее {OPTION_MAX_LENGTH} символов.")

    options = _trim(form.options)
    if "" in options:
        errors.append("Варианты ответа заполняйте подряд: A, B, C… без пропусков.")
    letters = config.OPTION_LETTERS[: len(options)]

    left: list[str] = []
    if form.qtype == config.MATCHING:
        rows = list(zip(form.left, form.match))
        while rows and not rows[-1][0] and not rows[-1][1]:
            rows.pop()
        left = [row[0] for row in rows]
        correct = [row[1] for row in rows]
        if any(not item for item in left):
            errors.append("Строки соответствия заполняйте подряд, без пропусков.")
        if any(not letter for letter in correct):
            errors.append("Для каждой строки соответствия выберите правильную букву.")
    else:
        correct = sorted(letter for letter in form.correct if letter in letters)
        if not correct:
            errors.append("Отметьте правильный ответ.")

    data = {
        "type": form.qtype,
        "text": form.text,
        "context": form.context if form.qtype == config.CONTEXT else "",
        "options": options,
        "left": left,
        "correct": correct,
        "explanation": form.explanation,
    }
    if not errors:
        errors.extend(problem[:1].upper() + problem[1:] + "." for problem in validate_question(data))
    if errors:
        return None, errors
    return Question(
        id=question_id, subject=form.subject, qtype=form.qtype, text=data["text"],
        context=data["context"], options=options, left=left, correct=correct,
        explanation=form.explanation,
    ), []


def _type_switch(base_url: str, current: str, subject: str) -> SafeHTML:
    """Ссылки выбора типа вопроса (без JavaScript форма перезагружается)."""
    return join(
        fragment(
            '<a class="type-chip$active" href="$href">$name</a>',
            active=SafeHTML(" type-chip-active" if qtype == current else ""),
            href=f"{base_url}?{urlencode({'type': qtype, 'subject': subject} if subject else {'type': qtype})}",
            name=config.QUESTION_TYPE_NAMES[qtype],
        )
        for qtype in config.QUESTION_TYPES
    )


def _option_rows(form: QuestionForm) -> SafeHTML:
    """Поля вариантов ответа; рядом — отметка правильного (кроме соответствия)."""
    input_type = {config.MULTIPLE: "checkbox", config.MATCHING: ""}.get(form.qtype, "radio")
    rows = []
    for index, letter in enumerate(config.OPTION_LETTERS):
        mark = SafeHTML("")
        if input_type:
            mark = fragment(
                '<label class="correct-mark"><input type="$type" name="correct" value="$letter" $checked>'
                "<span>верный</span></label>",
                type=input_type, letter=letter,
                checked=SafeHTML("checked" if letter in form.correct else ""),
            )
        rows.append(fragment(
            '<div class="option-edit"><span class="letter">$letter</span>'
            '<input type="text" name="opt_$letter" value="$value" maxlength="$max" '
            'aria-label="Вариант $letter" placeholder="$placeholder">$mark</div>',
            letter=letter, value=form.options[index], max=OPTION_MAX_LENGTH, mark=mark,
            placeholder="обязательно" if index < 2 else "необязательно",
        ))
    return join(rows)


def _matching_rows(form: QuestionForm) -> SafeHTML:
    """Строки «слева» для соответствия и выбор правильной буквы для каждой."""
    if form.qtype != config.MATCHING:
        return SafeHTML("")
    rows = []
    for index in range(LEFT_ROWS):
        choices = join(
            [fragment('<option value="">— буква —</option>')] + [
                fragment('<option value="$l" $sel>$l</option>', l=letter,
                         sel=SafeHTML("selected" if form.match[index] == letter else ""))
                for letter in config.OPTION_LETTERS
            ]
        )
        rows.append(fragment(
            '<div class="option-edit"><span class="letter">$n</span>'
            '<input type="text" name="left_$i" value="$value" maxlength="$max" '
            'aria-label="Строка $n" placeholder="$placeholder">'
            '<select name="match_$i" aria-label="Правильная буква для строки $n">$choices</select></div>',
            n=index + 1, i=index, value=form.left[index], max=OPTION_MAX_LENGTH, choices=choices,
            placeholder="обязательно" if index < 2 else "необязательно",
        ))
    return fragment(
        '<fieldset class="admin-fieldset"><legend>Строки слева — что сопоставляем</legend>'
        '<p class="muted small">Для каждой строки выберите букву правильного варианта справа.</p>'
        "$rows</fieldset>",
        rows=join(rows),
    )


def _form_page(request: Request, form: QuestionForm, action: str, base_url: str, title: str,
               errors: list[str], status: int = 200, note: SafeHTML | None = None) -> Response:
    """Отрисовывает страницу формы вопроса."""
    subject_options = join(
        [fragment('<option value="">— выберите предмет —</option>')] + [
            fragment('<option value="$code" $sel>$icon $name</option>', code=code, icon=info.icon,
                     name=info.name, sel=SafeHTML("selected" if code == form.subject else ""))
            for code, info in config.SUBJECTS.items()
        ]
    )
    context_field = SafeHTML("")
    if form.qtype == config.CONTEXT:
        context_field = fragment(
            '<label class="field"><span>Контекст — текст, таблица или данные к заданию</span>'
            '<textarea name="context" rows="5" maxlength="$max" required>$value</textarea></label>',
            max=TEXT_MAX_LENGTH, value=form.context,
        )
    hints = {
        config.SINGLE: "Заполните от 2 до 8 вариантов и отметьте один верный.",
        config.CONTEXT: "Заполните контекст, от 2 до 8 вариантов и отметьте один верный.",
        config.MULTIPLE: "Заполните от 2 до 8 вариантов и отметьте все верные.",
        config.MATCHING: "Справа — варианты (A, B, C…), слева — строки. Вариантов может быть больше, "
                         "чем строк.",
    }
    content = render(
        "admin_question_form.html",
        title=title,
        note=note or SafeHTML(""),
        type_switch=_type_switch(base_url, form.qtype, form.subject),
        errors=views._errors_block(errors),
        action=action,
        csrf=views._csrf_field(request),
        qtype=form.qtype,
        subject_options=subject_options,
        context_field=context_field,
        text=form.text,
        text_max=TEXT_MAX_LENGTH,
        matching_rows=_matching_rows(form),
        options_legend="Варианты справа" if form.qtype == config.MATCHING else "Варианты ответа",
        option_hint=hints[form.qtype],
        option_rows=_option_rows(form),
        explanation=form.explanation,
    )
    return _admin_page(request, title, "questions", content, status)


def _requested_type(request: Request, default: str) -> str:
    """Тип вопроса из ?type= (или default)."""
    qtype = request.query_value("type")
    return qtype if qtype in config.QUESTION_TYPES else default


def _duplicate_error() -> list[str]:
    """Сообщение о дубликате текста (UNIQUE subject + text)."""
    return ["У этого предмета уже есть вопрос с таким текстом (возможно, удалённый). "
            "Измените формулировку."]


def _back_to_list(subject: str, message: str) -> Response:
    """Перенаправление к списку вопросов предмета с сообщением."""
    return redirect("/admin/questions?" + urlencode({"subject": subject, "msg": message}))


@admin_required
def question_new(request: Request) -> Response:
    """GET/POST /admin/questions/new — добавление вопроса."""
    if request.method == "POST":
        form = _form_from_request(request)
        question, errors = _build_question(form)
        if question is not None:
            try:
                database.insert_question(question)
            except sqlite3.IntegrityError:
                errors = _duplicate_error()
            else:
                return _back_to_list(question.subject, "q_created")
        return _form_page(request, form, "/admin/questions/new", "/admin/questions/new",
                          "Новый вопрос", errors, 400)

    form = QuestionForm(qtype=_requested_type(request, config.SINGLE))
    subject = request.query_value("subject")
    form.subject = subject if subject in config.SUBJECTS else ""
    return _form_page(request, form, "/admin/questions/new", "/admin/questions/new",
                      "Новый вопрос", [])


@admin_required
def question_edit(request: Request, question_id: int) -> Response:
    """GET/POST /admin/questions/<id>/edit — изменение вопроса."""
    existing = database.get_question(question_id)
    if existing is None:
        return redirect("/admin/questions?msg=q_missing")
    url = f"/admin/questions/{question_id}/edit"
    title = f"Вопрос #{question_id}"
    note = None
    if existing.used:
        note = views._notice(
            "info",
            f"Этот вопрос уже встречался в попытках учеников ({existing.used}). "
            "Изменения будут видны и в разборе старых попыток, а баллы в них не пересчитываются.",
        )

    if request.method == "POST":
        form = _form_from_request(request)
        question, errors = _build_question(form, question_id)
        if question is not None:
            try:
                updated = database.update_question(question)
            except sqlite3.IntegrityError:
                errors = _duplicate_error()
            else:
                if not updated:
                    return redirect("/admin/questions?msg=q_missing")
                return _back_to_list(question.subject, "q_updated")
        return _form_page(request, form, url, url, title, errors, 400, note)

    form = _form_from_question(existing, _requested_type(request, existing.qtype))
    return _form_page(request, form, url, url, title, [], note=note)


@admin_required
def question_delete(request: Request, question_id: int) -> Response:
    """GET/POST /admin/questions/<id>/delete — подтверждение и удаление вопроса."""
    question = database.get_question(question_id)
    if question is None:
        return redirect("/admin/questions?msg=q_missing")
    if request.method == "POST":
        result = database.delete_question(question_id)
        message = {"deleted": "q_deleted", "archived": "q_archived"}.get(result, "q_missing")
        return _back_to_list(question.subject, message)

    used_note = (
        f"Вопрос встречался в попытках учеников ({question.used}) — он исчезнет из банка и "
        "новых тестов, но разбор старых попыток сохранится."
        if question.used else
        "Вопрос ещё не встречался в попытках — он будет удалён полностью."
    )
    content = render(
        "admin_question_delete.html",
        id=question.id,
        icon=views._icon(question.subject),
        subject=config.SUBJECTS[question.subject].name,
        type=config.QUESTION_TYPE_NAMES[question.qtype],
        text=question.text,
        used_note=used_note,
        csrf=views._csrf_field(request),
        cancel=f"/admin/questions?{urlencode({'subject': question.subject})}",
    )
    return _admin_page(request, "Удалить вопрос", "questions", content)


# ── Пользователи ─────────────────────────────────────────────────────────────

def _role_badge(role: str) -> SafeHTML:
    """Плашка роли пользователя."""
    if role == database.ROLE_ADMIN:
        return SafeHTML('<span class="badge badge-partial">⚙️ админ</span>')
    return SafeHTML('<span class="badge">ученик</span>')


@admin_required
def users(request: Request) -> Response:
    """GET /admin/users — все пользователи со сводкой попыток и поиском по имени или логину.

    Телефон в поиске можно набрать в любом виде («8 705 …», «+7 (705) …»):
    он приводится к +7XXXXXXXXXX так же, как при входе.
    """
    search = request.query_value("q").strip()[:200]
    rows = database.list_users_with_stats()
    if search:
        login = auth.normalize_login(search)
        needle = search.casefold()
        rows = [
            row for row in rows
            if row["login"] == login or needle in row["name"].casefold()
            or needle in row["login"].casefold()
        ]
    table_rows = join(
        fragment(
            "<tr><td><strong>$name</strong></td><td>$login</td><td>$role</td><td>$created</td>"
            "<td>$attempts <span class=\"muted\">(пробных: $mocks)</span></td>"
            "<td>$best</td><td>$last</td>"
            '<td><a class="link" href="/admin/users/$id">Попытки →</a></td></tr>',
            name=row["name"], login=row["login"], role=_role_badge(row["role"]),
            created=views._format_datetime(row["created_at"]),
            attempts=row["attempts"], mocks=row["mocks"] or 0,
            best=row["best_mock"] if row["best_mock"] is not None else "—",
            last=views._format_datetime(row["last_finished"]),
            id=row["id"],
        )
        for row in rows
    )
    content = render("admin_users.html", rows=table_rows, count=len(rows), search=search)
    return _admin_page(request, "Пользователи", "users", content)


@admin_required
def user_detail(request: Request, user_id: int) -> Response:
    """GET /admin/users/<id> — пользователь, его попытки и результаты."""
    user = database.get_user(user_id)
    if user is None:
        return views.not_found(request)
    attempts = database.get_finished_attempts(user_id)
    in_progress = [
        attempt for mode in (ent_logic.MOCK, ent_logic.PRACTICE)
        if (attempt := database.get_in_progress_attempt(user_id, mode)) is not None
    ]
    if attempts:
        rows = join(
            fragment(
                "<tr><td>$date</td><td>$mode</td>"
                '<td><span class="subject-link">$icon $what</span></td>'
                '<td><span class="score-pill $grade"><strong>$score</strong> / $max</span></td>'
                "<td>$percent%</td>"
                '<td><a class="link" href="/admin/users/$uid/attempts/$id">Разбор →</a></td></tr>',
                date=views._format_datetime(attempt.finished_at),
                mode=views.MODE_NAMES[attempt.mode],
                icon=views._attempt_icon(attempt),
                what=views._attempt_title(attempt).split(": ", 1)[1],
                grade=views._grade_class(views._percent(attempt.score, attempt.max_score)),
                score=attempt.score, max=attempt.max_score,
                percent=views._percent(attempt.score, attempt.max_score),
                uid=user_id, id=attempt.id,
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
        table = SafeHTML('<div class="card empty">Завершённых попыток пока нет.</div>')

    mocks = [attempt for attempt in attempts if attempt.mode == ent_logic.MOCK]
    strengths = ent_logic.subject_strengths(user_id)
    content = render(
        "admin_user.html",
        name=user["name"],
        login=user["login"],
        role=_role_badge(user["role"]),
        created=views._format_datetime(user["created_at"]),
        attempts=len(attempts),
        in_progress=len(in_progress),
        best=max((a.score for a in mocks), default="—"),
        average=round(sum(a.score for a in mocks) / len(mocks)) if mocks else "—",
        max_score=config.MOCK_MAX_SCORE,
        strengths=views._strength_rows(strengths, "Пока нет решённых заданий."),
        table=table,
    )
    return _admin_page(request, f"Пользователь {user['name']}", "users", content)


@admin_required
def user_attempt(request: Request, user_id: int, attempt_id: int) -> Response:
    """GET /admin/users/<id>/attempts/<id> — разбор попытки ученика глазами администратора."""
    user = database.get_user(user_id)
    attempt = database.get_attempt(attempt_id, user_id)
    if user is None or attempt is None or not attempt.is_finished:
        return views.not_found(request)
    actions = fragment(
        '<a class="btn btn-primary" href="/admin/users/$uid">← К пользователю $name</a>',
        uid=user_id, name=user["name"],
    )
    return _admin_page(request, "Разбор попытки", "users", views.result_content(attempt, actions))
