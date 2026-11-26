"""Админ-панель: статистика, банк вопросов (добавить / изменить / удалить) и пользователи.

Все страницы доступны только пользователям с ролью admin (см. manage_admin.py).
Все POST-формы проверяют csrf-токен (декоратор views.login_required).
Без JavaScript: тип вопроса выбирается ссылкой, форма для каждого типа своя.
"""

import sqlite3
import time
from datetime import date, timedelta
from collections.abc import Callable
from functools import wraps
from urllib.parse import urlencode

import config
from app import ads, auth, database, ent_logic, question_form, schools, topics, views
from app.database import Question
from app.templates import SafeHTML, fragment, join, render
from app.web import Request, Response, redirect

View = Callable[..., Response]

PAGE_SIZE = 30            # вопросов на странице списка


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
    pending = database.count_pending_questions()
    links = (("/admin", "📊 Обзор", "home"), ("/admin/questions", "📚 Вопросы", "questions"),
             ("/admin/review", f"🔎 Проверка ({pending})" if pending else "🔎 Проверка", "review"),
             ("/admin/topics", "🧭 Темы НЦТ", "topics"),
             ("/admin/banners", "📢 Реклама", "banners"),
             ("/admin/users", "👥 Пользователи", "users"), ("/teacher", "🏫 Школы", "schools"))
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


def _form_page(request: Request, form: question_form.QuestionForm, action: str, base_url: str, title: str,
               errors: list[str], status: int = 200, note: SafeHTML | None = None,
               back_url: str = "/admin/questions", submit: str = "💾 Сохранить вопрос") -> Response:
    """Отрисовывает страницу формы вопроса в админке."""
    content = question_form.form_content(
        request, form, action, base_url, title, errors, note,
        back_url=back_url, back_label="← К списку вопросов", submit_label=submit,
    )
    return _admin_page(request, title, "questions", content, status)


def _back_to_list(subject: str, message: str) -> Response:
    """Перенаправление к списку вопросов предмета с сообщением."""
    return redirect("/admin/questions?" + urlencode({"subject": subject, "msg": message}))


@admin_required
def question_new(request: Request) -> Response:
    """GET/POST /admin/questions/new — добавление вопроса."""
    if request.method == "POST":
        form = question_form.form_from_request(request)
        question, errors = question_form.build_question(form)
        if question is not None:
            try:
                database.insert_question(question)
            except sqlite3.IntegrityError:
                errors = question_form.duplicate_error()
            else:
                return _back_to_list(question.subject, "q_created")
        return _form_page(request, form, "/admin/questions/new", "/admin/questions/new",
                          "Новый вопрос", errors, 400)

    form = question_form.QuestionForm(qtype=question_form.requested_type(request, config.SINGLE))
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
        form = question_form.form_from_request(request)
        question, errors = question_form.build_question(form, question_id)
        if question is not None:
            try:
                updated = database.update_question(question)
            except sqlite3.IntegrityError:
                errors = question_form.duplicate_error()
            else:
                if not updated:
                    return redirect("/admin/questions?msg=q_missing")
                return _back_to_list(question.subject, "q_updated")
        return _form_page(request, form, url, url, title, errors, 400, note)

    form = question_form.form_from_question(existing, question_form.requested_type(request, existing.qtype))
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


# ── Покрытие тем спецификации НЦТ ────────────────────────────────────────────

@admin_required
def topics_report(request: Request) -> Response:
    """GET /admin/topics?subject=… — темы спецификации и сколько вопросов банка на каждую."""
    counts = database.topic_counts()
    subject = request.query_value("subject")
    if subject not in config.SUBJECTS:
        subject = ""

    summary_rows = []
    for code, info in config.SUBJECTS.items():
        items = topics.topics_for(code)
        covered = sum(1 for item in items if counts.get((code, item.code), 0))
        untagged = counts.get((code, ""), 0)
        summary_rows.append(fragment(
            '<tr><td><a class="subject-link" href="/admin/topics?subject=$code">$icon $name</a></td>'
            '<td>$covered из $total</td><td><progress max="$total" value="$covered">$covered</progress></td>'
            "<td>$untagged</td></tr>",
            code=code, icon=views._icon(code), name=info.name, covered=covered, total=len(items),
            untagged=untagged or "—",
        ))
    summary = fragment(
        '<div class="table-wrap"><table class="table"><thead><tr><th>Предмет</th>'
        "<th>Тем с вопросами</th><th></th><th>Вопросов без темы</th></tr></thead>"
        "<tbody>$rows</tbody></table></div>",
        rows=join(summary_rows),
    )

    details = SafeHTML("")
    if subject:
        items = topics.topics_for(subject)
        total = sum(counts.get((subject, item.code), 0) for item in items) or 1
        rows = []
        section = None
        for item in items:
            if item.section != section:
                section = item.section
                rows.append(fragment('<tr class="section-row"><th colspan="4">$s</th></tr>', s=section))
            n = counts.get((subject, item.code), 0)
            rows.append(fragment(
                '<tr class="$cls"><td>$code</td><td>$name</td><td>$n</td><td>$share</td></tr>',
                cls="topic-empty" if not n else "", code=item.code, name=item.name, n=n or "нет",
                share=f"{round(n * 100 / total, 1):g}%".replace(".", ",") if n else "—",
            ))
        details = fragment(
            '<section class="section"><h2>$icon $name: темы спецификации</h2>'
            '<div class="table-wrap"><table class="table"><thead><tr><th>№</th><th>Тема</th>'
            "<th>Вопросов в банке</th><th>Доля в банке</th></tr></thead><tbody>$rows</tbody>"
            "</table></div></section>",
            icon=views._icon(subject), name=config.SUBJECTS[subject].name, rows=join(rows),
        )

    content = fragment(
        '<section class="page-head"><span class="eyebrow">Спецификация НЦТ</span>'
        "<h1>🧭 Темы ЕНТ и покрытие банка</h1>"
        '<p class="muted">Разделы и темы — из официальных спецификаций НЦТ «для использования '
        'с $year года» (<a class="link" href="$source">testcenter.kz</a>). НЦТ не указывает, сколько '
        "заданий приходится на каждую тему, поэтому здесь показана доля темы в нашем банке. "
        "Темы без вопросов выделены — их нужно пополнить (шаблонами генераторов, JSON или вопросами "
        "учителей).</p></section>$summary$details",
        year=topics.SPEC_YEAR, source=topics.SPEC_SOURCE, summary=summary, details=details,
    )
    return _admin_page(request, "Темы НЦТ", "topics", content)


# ── Рекламные баннеры ────────────────────────────────────────────────────────

BANNER_STATUS_BADGE = {"показывается": "badge-ok", "запланирован": "badge-warn",
                       "закончился": "badge", "выключен": "badge-wrong"}


@admin_required
def banners(request: Request) -> Response:
    """GET /admin/banners — баннеры, места показа, сроки, показы и клики."""
    rows = database.list_banners()
    if rows:
        items = join(
            fragment(
                '<tr><td><img class="ad-thumb" src="/ad/$id/image" alt="$title"></td>'
                '<td><strong>$title</strong><br><a class="link small" href="$link" rel="noopener">$link</a></td>'
                "<td>$places</td><td>$start — $end</td>"
                '<td><span class="badge $badge">$status</span></td>'
                "<td>$shows</td><td>$clicks</td><td>$ctr</td>"
                '<td><a class="link" href="/admin/banners/$id/edit">Изменить →</a></td></tr>',
                id=row["id"], title=row["title"], link=row["link_url"],
                places=", ".join(ads.PLACEMENTS.get(p, p) for p in row["placements"].split(",")),
                start=row["starts_on"], end=row["ends_on"],
                badge=BANNER_STATUS_BADGE[ads.status(row)], status=ads.status(row),
                shows=row["impressions"], clicks=row["clicks"],
                ctr=f"{row['clicks'] * 100 / row['impressions']:.1f}%".replace(".", ",")
                if row["impressions"] else "—",
            )
            for row in rows
        )
        table = fragment(
            '<div class="table-wrap"><table class="table"><thead><tr><th></th><th>Баннер</th>'
            "<th>Места показа</th><th>Сроки</th><th>Статус</th><th>Показы</th><th>Клики</th>"
            "<th>CTR</th><th></th></tr></thead><tbody>$items</tbody></table></div>",
            items=items,
        )
    else:
        table = SafeHTML('<div class="card empty">Баннеров пока нет.</div>')
    content = fragment(
        '<section class="page-head admin-head"><div><span class="eyebrow">Монетизация</span>'
        "<h1>📢 Рекламные баннеры</h1>"
        '<p class="muted">Свои баннеры без JavaScript: картинка и ссылка. Показы считаются при выводе '
        "баннера, клики — при переходе. На страницах теста реклама не показывается.</p></div>"
        '<a class="btn btn-primary" href="/admin/banners/new">＋ Добавить баннер</a></section>$table',
        table=table,
    )
    return _admin_page(request, "Реклама", "banners", content)


def _banner_form(request: Request, url: str, title: str, values: dict, errors: list[str],
                 banner_id: int = 0, status: int = 200) -> Response:
    """Форма баннера (новый или изменение)."""
    chosen = set(values.get("placements", []))
    boxes = join(
        fragment('<label class="check"><input type="checkbox" name="placements" value="$code"$c> $name</label>',
                 code=code, name=name, c=SafeHTML(" checked" if code in chosen else ""))
        for code, name in ads.PLACEMENTS.items()
    )
    preview = (fragment('<p><img class="ad-thumb ad-thumb-big" src="/ad/$id/image" alt="текущая картинка"></p>'
                        '<p class="muted small">Загрузите новый файл, только если хотите заменить картинку.</p>',
                        id=banner_id)
               if banner_id else SafeHTML(""))
    delete = (fragment('<form method="post" action="/admin/banners/$id/delete" class="section">$csrf'
                       '<button type="submit" class="btn btn-link">Удалить баннер</button></form>',
                       id=banner_id, csrf=views._csrf_field(request))
              if banner_id else SafeHTML(""))
    content = render(
        "admin_banner_form.html", title=title, url=url, csrf=views._csrf_field(request),
        errors=views._errors_block(errors), name=values.get("title", ""), link=values.get("link_url", ""),
        placements=boxes, starts_on=values.get("starts_on", ""), ends_on=values.get("ends_on", ""),
        active=SafeHTML(" checked" if values.get("active") else ""), preview=preview,
        max_mb=config.BANNER_MAX_BYTES // 1_000_000, delete=delete,
    )
    return _admin_page(request, title, "banners", content, status)


def _banner_values(request: Request) -> dict:
    """Значения формы баннера из запроса."""
    return {"title": request.form_value("title"), "link_url": request.form_value("link_url"),
            "placements": request.form.get("placements", []), "starts_on": request.form_value("starts_on"),
            "ends_on": request.form_value("ends_on"), "active": request.form_value("active") == "1"}


@admin_required
def banner_new(request: Request) -> Response:
    """GET/POST /admin/banners/new — новый баннер (форма с загрузкой картинки)."""
    url = "/admin/banners/new"
    if request.method == "GET":
        today = date.today()
        return _banner_form(request, url, "Новый баннер", {
            "placements": ["landing", "dashboard"], "active": True, "starts_on": today.isoformat(),
            "ends_on": (today + timedelta(days=30)).isoformat()}, [])
    values = _banner_values(request)
    upload = request.files.get("image")
    try:
        form = ads.validate(values["title"], values["link_url"], values["placements"], values["starts_on"],
                            values["ends_on"], values["active"], upload.data if upload else None, True)
    except ads.BannerError as error:
        return _banner_form(request, url, "Новый баннер", values, error.errors, status=400)
    assert form.image is not None
    database.create_banner(form.title, form.link_url, form.image, form.image_type, form.placements,
                           form.starts_on, form.ends_on, form.active, time.time())
    return redirect("/admin/banners?msg=banner_saved")


@admin_required
def banner_edit(request: Request, banner_id: int) -> Response:
    """GET/POST /admin/banners/<id>/edit — изменить баннер (картинку — по желанию)."""
    row = database.get_banner(banner_id)
    if row is None:
        return views.not_found(request)
    url = f"/admin/banners/{banner_id}/edit"
    title = f"Баннер #{banner_id}"
    if request.method == "GET":
        return _banner_form(request, url, title, {
            "title": row["title"], "link_url": row["link_url"], "placements": row["placements"].split(","),
            "starts_on": row["starts_on"], "ends_on": row["ends_on"], "active": bool(row["active"])},
            [], banner_id)
    values = _banner_values(request)
    upload = request.files.get("image")
    try:
        form = ads.validate(values["title"], values["link_url"], values["placements"], values["starts_on"],
                            values["ends_on"], values["active"], upload.data if upload else None, False)
    except ads.BannerError as error:
        return _banner_form(request, url, title, values, error.errors, banner_id, 400)
    database.update_banner(banner_id, form.title, form.link_url, form.placements, form.starts_on,
                           form.ends_on, form.active, form.image, form.image_type)
    return redirect("/admin/banners?msg=banner_saved")


@admin_required
def banner_delete(request: Request, banner_id: int) -> Response:
    """POST /admin/banners/<id>/delete — удалить баннер."""
    if not database.delete_banner(banner_id):
        return views.not_found(request)
    return redirect("/admin/banners?msg=banner_deleted")


# ── Проверка вопросов учителей ───────────────────────────────────────────────

REVIEW_EDITED_COMMENT = "Одобрено с исправлениями администратора."


@admin_required
def review_queue(request: Request) -> Response:
    """GET /admin/review — очередь вопросов учителей на проверке (старые сверху)."""
    items = database.list_pending_questions()
    csrf = views._csrf_field(request)
    if items:
        cards = join(
            fragment(
                '<article class="card review-card"><header class="review-head">'
                "<strong>Вопрос #$id</strong><span class=\"muted small\">$author · $school · "
                "отправлен $date</span></header>$preview"
                '<div class="review-actions">'
                '<form method="post" action="/admin/review/$id" class="inline-form">$csrf'
                '<button type="submit" name="action" value="approve" class="btn btn-primary btn-sm">'
                "✅ Одобрить</button></form>"
                '<a class="btn btn-secondary btn-sm" href="/admin/review/$id/edit">✏️ Исправить и одобрить</a>'
                "</div>"
                '<form method="post" action="/admin/review/$id" class="form review-reject">$csrf'
                '<label class="field"><span>Комментарий для учителя (обязателен при отклонении)</span>'
                '<textarea name="comment" rows="2" maxlength="1000"></textarea></label>'
                '<button type="submit" name="action" value="reject" class="btn btn-ghost btn-sm">'
                "❌ Отклонить</button></form></article>",
                id=question.id, preview=question_form.preview(question), csrf=csrf,
                author=row["author_name"] or "автор удалён",
                school=(schools.school_title(row["school_city"], row["school_name"])
                        if row["school_city"] else "без школы"),
                date=views._format_datetime(question.submitted_at),
            )
            for question, row in items
        )
    else:
        cards = SafeHTML('<div class="card empty">Очередь пуста — все вопросы проверены. 🎉</div>')
    content = fragment(
        '<section class="page-head"><span class="eyebrow">Проверка</span>'
        "<h1>🔎 Вопросы учителей на проверке: $count</h1>"
        '<p class="muted">Одобренный вопрос сразу попадает в общий банк (для всех школ). '
        "Отклонённый возвращается учителю с вашим комментарием.</p></section>$cards",
        count=len(items), cards=cards,
    )
    return _admin_page(request, "Проверка вопросов", "review", content)


@admin_required
def review_action(request: Request, question_id: int) -> Response:
    """POST /admin/review/<id> — одобрить или отклонить (с комментарием) вопрос."""
    action = request.form_value("action")
    comment = " ".join(request.form_value("comment").split())[:1000]
    if action == "approve":
        status, message = database.Q_APPROVED, "review_approved"
    elif action == "reject":
        if not comment:
            return redirect("/admin/review?msg=review_comment_needed")
        status, message = database.Q_REJECTED, "review_rejected"
    else:
        return views.error_page(request, 400, "Неизвестное действие.")
    if not database.review_question(question_id, status, comment, time.time()):
        return redirect("/admin/review?msg=review_missing")
    return redirect(f"/admin/review?msg={message}")


@admin_required
def review_edit(request: Request, question_id: int) -> Response:
    """GET/POST /admin/review/<id>/edit — исправить вопрос учителя и сразу одобрить."""
    existing = database.get_pending_question(question_id)
    if existing is None:
        return redirect("/admin/review?msg=review_missing")
    url = f"/admin/review/{question_id}/edit"
    title = f"Исправить и одобрить вопрос #{question_id}"
    if request.method == "POST":
        form = question_form.form_from_request(request)
        question, errors = question_form.build_question(form, question_id)
        if question is not None:
            try:
                saved = database.approve_with_changes(question, REVIEW_EDITED_COMMENT, time.time())
            except sqlite3.IntegrityError:
                errors = question_form.duplicate_error()
            else:
                if not saved:
                    return redirect("/admin/review?msg=review_missing")
                return redirect("/admin/review?msg=review_approved")
        return _review_form(request, form, url, title, errors, 400)
    form = question_form.form_from_question(
        existing, question_form.requested_type(request, existing.qtype))
    return _review_form(request, form, url, title, [])


def _review_form(request: Request, form, url: str, title: str, errors: list[str],
                 status: int = 200) -> Response:
    """Форма «Исправить и одобрить» в разделе проверки."""
    content = question_form.form_content(
        request, form, url, url, title, errors,
        views._notice("info", "После сохранения вопрос будет одобрен и попадёт в общий банк. "
                              "Учитель увидит пометку «одобрено с исправлениями»."),
        back_url="/admin/review", back_label="← К очереди проверки",
        submit_label="✅ Сохранить и одобрить",
    )
    return _admin_page(request, title, "review", content, status)


# ── Пользователи ─────────────────────────────────────────────────────────────

def _role_badge(role: str) -> SafeHTML:
    """Плашка роли пользователя."""
    if role == database.ROLE_ADMIN:
        return SafeHTML('<span class="badge badge-partial">⚙️ админ</span>')
    if role == database.ROLE_TEACHER:
        return SafeHTML('<span class="badge badge-ok">🏫 учитель</span>')
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
            if login in (row["login"], row["phone"]) or needle in row["name"].casefold()
            or needle in row["login"].casefold()
        ]
    table_rows = join(
        fragment(
            "<tr><td><strong>$name</strong></td><td>$login$phone$unverified</td><td>$role</td>"
            "<td>$created</td>"
            "<td>$attempts <span class=\"muted\">(пробных: $mocks)</span></td>"
            "<td>$best</td><td>$last</td>"
            '<td><a class="link" href="/admin/users/$id">Попытки →</a></td></tr>',
            name=row["name"], login=row["login"], role=_role_badge(row["role"]),
            phone=fragment('<br><small class="muted">$phone</small>', phone=row["phone"])
            if row["phone"] else SafeHTML(""),
            unverified=SafeHTML(' <span class="badge badge-warn">почта не подтверждена</span>')
            if not row["email_verified"] else SafeHTML(""),
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
