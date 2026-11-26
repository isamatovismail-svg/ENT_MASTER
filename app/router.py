"""Таблица маршрутов: какой URL и метод обрабатывает какая функция из views.

Шаблон пути поддерживает параметры:
- <int:name> — целое число (передаётся в функцию как int);
- <name>     — код из латинских букв, цифр и «_» (передаётся как str).
"""

import re
from collections.abc import Callable

from app import account_views, admin_views, teacher_views, telegram_views, views
from app.web import Request, Response

View = Callable[..., Response]

# Порядок важен: более конкретные пути должны идти раньше общих.
ROUTES: list[tuple[str, str, View]] = [
    ("GET", "/", views.landing),
    ("GET", "/register", views.register_page),
    ("POST", "/register", views.register_submit),
    ("GET", "/login", views.login_page),
    ("POST", "/login", views.login_submit),
    ("POST", "/logout", views.logout),
    ("GET", "/verify", account_views.verify_page),
    ("POST", "/verify", account_views.verify_submit),
    ("POST", "/verify/resend", account_views.verify_resend),
    ("GET", "/forgot", account_views.forgot_page),
    ("POST", "/forgot", account_views.forgot_submit),
    ("GET", "/reset", account_views.reset_page),
    ("POST", "/reset", account_views.reset_submit),
    ("GET", "/auth/google", account_views.google_start),
    ("GET", "/auth/google/callback", account_views.google_callback),
    ("GET", "/tg/login", telegram_views.tg_login_page),
    ("POST", "/tg/login", telegram_views.tg_login_submit),
    ("GET", "/dashboard", views.dashboard),
    ("GET", "/mock", views.choose_pair),
    ("POST", "/mock/start", views.start_mock),
    ("GET", "/practice", views.choose_practice),
    ("POST", "/practice/start", views.start_practice),
    ("GET", "/practice/<int:attempt_id>", views.practice_question),
    ("POST", "/practice/<int:attempt_id>", views.practice_answer),
    ("GET", "/practice/<int:attempt_id>/review/<int:number>", views.practice_review),
    ("GET", "/attempt/<int:attempt_id>/finish", views.finish_confirm),
    ("POST", "/attempt/<int:attempt_id>/finish", views.finish_submit),
    ("GET", "/attempt/<int:attempt_id>/<subject>", views.section_page),
    ("POST", "/attempt/<int:attempt_id>/<subject>", views.section_submit),
    ("GET", "/result/<int:attempt_id>", views.result_page),
    ("GET", "/history", views.history),
    ("GET", "/ad/<int:banner_id>", views.ad_click),
    ("GET", "/ad/<int:banner_id>/image", views.ad_image),
    ("GET", "/profile", views.profile),
    ("POST", "/profile/school", views.profile_school),
    # Кабинет учителя (учитель своей школы и главный администратор)
    ("GET", "/teacher", teacher_views.teacher_home),
    ("GET", "/teacher/questions", teacher_views.my_questions),
    ("GET", "/teacher/questions/new", teacher_views.my_question_new),
    ("POST", "/teacher/questions/new", teacher_views.my_question_new),
    ("GET", "/teacher/questions/<int:question_id>/edit", teacher_views.my_question_edit),
    ("POST", "/teacher/questions/<int:question_id>/edit", teacher_views.my_question_edit),
    ("POST", "/teacher/questions/<int:question_id>/delete", teacher_views.my_question_delete),
    ("GET", "/teacher/<int:school_id>", teacher_views.school_page),
    ("POST", "/teacher/<int:school_id>/members/<int:user_id>", teacher_views.member_action),
    ("GET", "/teacher/<int:school_id>/students/<int:user_id>", teacher_views.student_card),
    ("GET", "/teacher/<int:school_id>/students/<int:user_id>/attempts/<int:attempt_id>",
     teacher_views.student_attempt),
    ("GET", "/teacher/<int:school_id>/assignments/new", teacher_views.assignment_new),
    ("POST", "/teacher/<int:school_id>/assignments/new", teacher_views.assignment_new),
    ("GET", "/teacher/<int:school_id>/assignments/<int:assignment_id>", teacher_views.assignment_page),
    ("POST", "/teacher/<int:school_id>/assignments/<int:assignment_id>/delete",
     teacher_views.assignment_delete),
    # Админ-панель (только для роли admin)
    ("GET", "/admin", admin_views.dashboard),
    ("GET", "/admin/questions", admin_views.questions),
    ("GET", "/admin/questions/new", admin_views.question_new),
    ("POST", "/admin/questions/new", admin_views.question_new),
    ("GET", "/admin/questions/<int:question_id>/edit", admin_views.question_edit),
    ("POST", "/admin/questions/<int:question_id>/edit", admin_views.question_edit),
    ("GET", "/admin/questions/<int:question_id>/delete", admin_views.question_delete),
    ("POST", "/admin/questions/<int:question_id>/delete", admin_views.question_delete),
    ("GET", "/admin/topics", admin_views.topics_report),
    ("GET", "/admin/banners", admin_views.banners),
    ("GET", "/admin/banners/new", admin_views.banner_new),
    ("POST", "/admin/banners/new", admin_views.banner_new),
    ("GET", "/admin/banners/<int:banner_id>/edit", admin_views.banner_edit),
    ("POST", "/admin/banners/<int:banner_id>/edit", admin_views.banner_edit),
    ("POST", "/admin/banners/<int:banner_id>/delete", admin_views.banner_delete),
    ("GET", "/admin/review", admin_views.review_queue),
    ("POST", "/admin/review/<int:question_id>", admin_views.review_action),
    ("GET", "/admin/review/<int:question_id>/edit", admin_views.review_edit),
    ("POST", "/admin/review/<int:question_id>/edit", admin_views.review_edit),
    ("GET", "/admin/users", admin_views.users),
    ("GET", "/admin/users/<int:user_id>", admin_views.user_detail),
    ("GET", "/admin/users/<int:user_id>/attempts/<int:attempt_id>", admin_views.user_attempt),
]

_PARAM_RE = re.compile(r"<(?:(int):)?([a-z_]+)>")


def _compile(pattern: str) -> tuple[re.Pattern[str], set[str]]:
    """Превращает шаблон пути в регулярное выражение и список целочисленных параметров."""
    int_params: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        """Заменяет один <параметр> на именованную группу регулярного выражения."""
        converter, name = match.groups()
        if converter == "int":
            int_params.add(name)
            return rf"(?P<{name}>\d{{1,10}})"
        return rf"(?P<{name}>[a-z0-9_]+)"

    # re.escape не трогает символы < > : _ /, поэтому метки параметров остаются на месте.
    regex = _PARAM_RE.sub(replace, re.escape(pattern))
    return re.compile(regex), int_params


_COMPILED = [(method, *_compile(pattern), view) for method, pattern, view in ROUTES]


def dispatch(request: Request) -> Response:
    """Находит обработчик для запроса и вызывает его.

    Путь найден, но метод другой — 405; путь не найден — 404.
    """
    path = request.path.rstrip("/") or "/"
    path_matched = False
    for method, regex, int_params, view in _COMPILED:
        match = regex.fullmatch(path)
        if match is None:
            continue
        path_matched = True
        if method != request.method:
            continue
        kwargs: dict[str, object] = {
            name: int(value) if name in int_params else value
            for name, value in match.groupdict().items()
        }
        return view(request, **kwargs)
    if path_matched:
        return views.method_not_allowed(request)
    return views.not_found(request)
