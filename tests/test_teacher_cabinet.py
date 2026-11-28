"""Этап 8: задания доходят до ученика, кабинет учителя, таблица результатов, уведомления, реклама."""

import threading
import time
from datetime import date, datetime, timedelta

from app import config
from app.core import auth, database, ent_logic, notifications, schools, student_stats
from app.web.server import create_server
from tests.base import DatabaseTestCase
from tests.test_deploy import PNG
from tests.test_pages import CSRF_RE, Browser

PASSWORD = "password1"
TODAY = date.today().isoformat()
NEXT_WEEK = (date.today() + timedelta(days=7)).isoformat()
MATH_INFORMATICS = ("math", "informatics")


def csrf(html: str) -> str:
    match = CSRF_RE.search(html)
    assert match is not None, "csrf-токен не найден"
    return match.group(1)


class CabinetServerTestCase(DatabaseTestCase):
    """Сервер, школа, учитель, два подтверждённых ученика и главный админ."""

    def setUp(self) -> None:
        super().setUp()
        self.server = create_server("127.0.0.1", 0)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.school = schools.find_or_create_school("Шымкент", "1")
        self.teacher_id = auth.create_account("Учитель Демо", "teacher@mail.kz", PASSWORD)
        database.make_teacher("teacher@mail.kz", self.school)
        self.student_id = auth.create_account("Ученик Демо", "student@mail.kz", PASSWORD)
        database.set_user_school(self.student_id, self.school, database.SCHOOL_APPROVED)
        self.other_id = auth.create_account("Арман Другой", "other@mail.kz", PASSWORD)
        database.set_user_school(self.other_id, self.school, database.SCHOOL_APPROVED)
        auth.create_account("Админ", "admin@mail.kz", PASSWORD)
        database.set_user_role("admin@mail.kz", database.ROLE_ADMIN)

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def login(self, email: str) -> tuple[Browser, str]:
        browser = Browser(self.base_url)
        _, path, html, _ = browser.post("/login", {"login": email, "password": PASSWORD})
        return browser, html


class AssignmentReachesStudentTests(CabinetServerTestCase):
    """Ученик получает выданное задание по паре «математика и информатика» и оно засчитывается."""

    def test_mock_math_informatics_assignment_end_to_end(self) -> None:
        self.fill_full_bank([*config.COMPULSORY_CODES, *MATH_INFORMATICS])
        teacher, _ = self.login("teacher@mail.kz")
        _, _, html, _ = teacher.get(f"/teacher/{self.school}/assignments/new")
        status, path, html, _ = teacher.post(f"/teacher/{self.school}/assignments/new", {
            "csrf_token": csrf(html), "mode": "mock", "pair": "math,informatics", "subject": "",
            "count": "2", "deadline": NEXT_WEEK, "for_all": "0", "students": [str(self.student_id)],
        })
        self.assertEqual(status, 200, html)
        self.assertIn("Задание выдано", html)
        assignment_id = int(path.split("/assignments/")[1].split("?")[0])

        student, html = self.login("student@mail.kz")
        self.assertIn('class="bell-count">1<', html)
        top = html.index("Задания учителя")
        self.assertLess(top, html.index("Пробный ЕНТ</b>"))
        self.assertIn("Пройдите пробный ЕНТ (Математика + Информатика)", html)
        self.assertIn("0 из 2", html)
        _, _, page, _ = student.get("/notifications")
        self.assertIn("Новое задание: Пробный ЕНТ × 2: Математика + Информатика", page)
        self.assertEqual(database.unread_notifications(self.other_id), 0)

        status, path, _, _ = student.post(f"/assignments/{assignment_id}/start", {"csrf_token": csrf(html)})
        self.assertEqual(status, 200)
        attempt = database.get_in_progress_attempt(self.student_id, ent_logic.MOCK)
        self.assertEqual(attempt.subjects[-2:], list(MATH_INFORMATICS))
        self.assertIn(f"/attempt/{attempt.id}", path)
        ent_logic.finish_attempt(attempt)
        _, _, html, _ = student.get("/dashboard")
        self.assertIn("1 из 2", html)

        student.post(f"/assignments/{assignment_id}/start", {"csrf_token": csrf(html)})
        ent_logic.finish_attempt(database.get_in_progress_attempt(self.student_id, ent_logic.MOCK))
        _, _, html, _ = teacher.get(f"/teacher/{self.school}/assignments/{assignment_id}")
        self.assertIn("выполнено", html)
        _, _, html, _ = teacher.get("/notifications")
        self.assertIn("Ученик Демо выполнил(а) задание «Пробный ЕНТ × 2: Математика + Информатика»", html)
        notifications.attempt_finished(self.student_id)
        self.assertEqual(database.unread_notifications(self.teacher_id), 1)

    def test_cannot_start_foreign_assignment(self) -> None:
        assignment_id = schools.create_assignment(
            self.school, self.teacher_id, "practice", "math", "", "1", NEXT_WEEK, False, [self.other_id])
        student, html = self.login("student@mail.kz")
        status, _, _, _ = student.post(f"/assignments/{assignment_id}/start", {"csrf_token": csrf(html)})
        self.assertEqual(status, 404)

    def test_practice_assignment_starts_its_subject(self) -> None:
        self.add_questions("informatics", config.SINGLE, 12)
        assignment_id = schools.create_assignment(
            self.school, self.teacher_id, "practice", "informatics", "", "1", NEXT_WEEK, True, [])
        student, html = self.login("student@mail.kz")
        status, path, _, _ = student.post(f"/assignments/{assignment_id}/start", {"csrf_token": csrf(html)})
        attempt = database.get_in_progress_attempt(self.student_id, ent_logic.PRACTICE)
        self.assertEqual(attempt.subjects, ["informatics"])
        self.assertEqual(path, f"/practice/{attempt.id}")


class TeacherSeesOnlyHisWorkTests(CabinetServerTestCase):
    """Учитель видит заявки, учеников, задания и свои вопросы; админка и тесты ему не нужны."""

    def test_menu_and_access(self) -> None:
        teacher, html = self.login("teacher@mail.kz")
        nav = html[html.index('<nav class="nav"'):html.index("</nav>")]
        for link in ('href="/teacher"', 'href="/teacher/assignments"', 'href="/teacher/questions"',
                     'href="/notifications"', 'href="/profile"'):
            self.assertIn(link, nav)
        for link in ('href="/mock"', 'href="/practice"', 'href="/history"', 'href="/admin"',
                     'href="/dashboard"'):
            self.assertNotIn(link, nav)
        for page in ("/dashboard", "/mock", "/practice", "/history"):
            self.assertEqual(teacher.get(page)[1], f"/teacher/{self.school}", page)
        for page in ("/admin", "/admin/users", "/admin/review", "/admin/banners"):
            self.assertEqual(teacher.get(page)[0], 403, page)
        self.assertEqual(teacher.get("/teacher/assignments")[1], f"/teacher/{self.school}/assignments")

    def test_requests_accept_reject_with_notifications(self) -> None:
        newbie = auth.create_account("Новый Ученик", "new@mail.kz", PASSWORD)
        schools.join_school(newbie, "Шымкент", "школа №1")
        self.assertEqual(database.unread_notifications(self.teacher_id), 1)
        teacher, html = self.login("teacher@mail.kz")
        self.assertIn('class="bell-count">1<', html)
        self.assertIn("Заявки в школу: 1", html)
        self.assertIn("Новый Ученик", html)
        teacher.post(f"/teacher/{self.school}/members/{newbie}", {"action": "approve", "csrf_token": csrf(html)})
        texts = [n.text for n in notifications.for_user(newbie)]
        self.assertTrue(texts[0].startswith("Учитель подтвердил вашу заявку: Шымкент, школа №1"))

        rejected = auth.create_account("Отказ", "no@mail.kz", PASSWORD)
        schools.join_school(rejected, "Шымкент", "1")
        _, _, html, _ = teacher.get(f"/teacher/{self.school}")
        teacher.post(f"/teacher/{self.school}/members/{rejected}", {"action": "reject", "csrf_token": csrf(html)})
        self.assertIn("отклонена", notifications.for_user(rejected)[0].text)


class StudentsTableTests(CabinetServerTestCase):
    """Таблица учеников: активность, сегодня/вчера/7 дней, баллы, изменение, слабые предметы."""

    def finished(self, user_id: int, subject: str, correct: int, when: float) -> int:
        """Тренировка из 10 заданий с correct верными ответами, завершённая в момент when."""
        attempt_id = ent_logic.build_practice(user_id, subject, now=when - 600)
        questions = database.get_attempt_questions(attempt_id)
        database.save_answers(attempt_id, {
            aq.id: (aq.correct if index < correct else ["D" if aq.correct != ["D"] else "C"])
            for index, aq in enumerate(questions)})
        ent_logic.finish_attempt(database.get_attempt(attempt_id, user_id), now=when)
        return attempt_id

    def test_overview_counts_trend_weak_and_help_order(self) -> None:
        self.add_questions("math", config.SINGLE, 15)
        self.add_questions("physics", config.SINGLE, 15)
        now = time.time()
        today_noon = datetime.combine(date.today(), datetime.min.time()).timestamp() + 1
        self.finished(self.student_id, "math", 9, today_noon - 86400 + 3600)
        self.finished(self.student_id, "math", 8, min(now - 60, today_noon + 120))
        self.finished(self.student_id, "physics", 2, min(now - 30, today_noon + 240))
        self.finished(self.other_id, "math", 10, now - 40 * 86400)

        rows = {r.user_id: r for r in student_stats.school_overview(self.school, "all", now)}
        demo = rows[self.student_id]
        self.assertEqual(demo.today, (0, 2))
        self.assertEqual(demo.yesterday, (0, 1))
        self.assertEqual(demo.week, (0, 3))
        self.assertEqual((demo.last, demo.best), (20, 90))
        self.assertLess(demo.trend, 0)
        self.assertEqual([w.code for w in demo.weak], ["physics"])
        self.assertTrue(rows[self.other_id].needs_help)

        week = {r.user_id: r for r in student_stats.school_overview(self.school, "7d", now)}
        self.assertIsNone(week[self.other_id].average)
        self.assertEqual(student_stats.school_overview(self.school, "yesterday", now)[0].attempts
                         + student_stats.school_overview(self.school, "yesterday", now)[1].attempts, 1)

        teacher, html = self.login("teacher@mail.kz")
        self.assertLess(html.index("Арман Другой"), html.index("Ученик Демо"))
        self.assertIn("нужна помощь", html)
        self.assertIn("Физика 20%", html)
        _, _, html, _ = teacher.get(f"/teacher/{self.school}?period=all&sort=name&dir=desc")
        self.assertLess(html.index("Ученик Демо"), html.index("Арман Другой"))
        _, _, html, _ = teacher.get(f"/teacher/{self.school}?period=today&sort=best&dir=desc")
        self.assertIn('chip chip-active" href="?period=today', html)

        _, _, html, _ = teacher.get(f"/teacher/{self.school}/students/{self.student_id}")
        self.assertIn("Лента по дням", html)
        self.assertIn("Сегодня", html)
        self.assertIn("Вчера", html)
        self.assertIn("Физика: 2 / 10", html)

    def test_sort_rows_by_any_column(self) -> None:
        for code, _ in __import__("app.web.teacher_views", fromlist=["x"]).STUDENT_COLUMNS:
            self.assertIn(code, student_stats.SORT_KEYS)
            student_stats.sort_rows(student_stats.school_overview(self.school), code, True)


class NotificationTests(CabinetServerTestCase):
    """Колокольчик, страница, «прочитано», Telegram, напоминание о сроке."""

    def test_page_read_open_and_privacy(self) -> None:
        notifications.notify(self.student_id, notifications.REQUEST_APPROVED, {"school": "Шымкент, школа №1"},
                             "/dashboard")
        notifications.notify(self.other_id, notifications.REQUEST_REJECTED, {"school": "X"}, "/profile")
        student, html = self.login("student@mail.kz")
        self.assertIn('aria-label="Уведомления: 1"', html)
        _, _, html, _ = student.get("/notifications")
        self.assertIn("notification-unread", html)
        mine = notifications.for_user(self.student_id)[0]
        foreign = notifications.for_user(self.other_id)[0]
        self.assertEqual(student.get(f"/notifications/{foreign.id}")[0], 404)
        _, path, _, _ = student.get(f"/notifications/{mine.id}")
        self.assertEqual(path, "/dashboard")
        self.assertEqual(database.unread_notifications(self.student_id), 0)
        self.assertEqual(database.unread_notifications(self.other_id), 1)

        notifications.notify(self.student_id, notifications.ASSIGNMENT_NEW,
                             {"mode": "practice", "target": "math", "count": 1, "deadline": time.time()})
        _, _, html, _ = student.get("/notifications")
        self.assertEqual(student.post("/notifications/read", {})[0], 403)
        student.post("/notifications/read", {"csrf_token": csrf(html)})
        self.assertEqual(database.unread_notifications(self.student_id), 0)

    def test_telegram_copy_and_failure_does_not_break(self) -> None:
        database.bind_telegram(self.student_id, 777)
        schools.create_assignment(self.school, self.teacher_id, "practice", "math", "", "1", NEXT_WEEK,
                                  False, [self.student_id])
        self.assertEqual(self.telegram.messages[-1]["chat_id"], 777)
        self.assertIn("Новое задание", self.telegram.messages[-1]["text"])
        self.assertIn(f"{config.SITE_URL}/dashboard", self.telegram.messages[-1]["text"])
        self.telegram.fail = True
        teacher, _ = self.login("teacher@mail.kz")
        _, _, html, _ = teacher.get(f"/teacher/{self.school}/assignments/new")
        with self.assertLogs("app.core.notifications", "WARNING"):
            status, _, html, _ = teacher.post(f"/teacher/{self.school}/assignments/new", {
                "csrf_token": csrf(html), "mode": "practice", "subject": "physics", "count": "1",
                "deadline": NEXT_WEEK, "for_all": "1"})
        self.assertIn("Задание выдано", html)
        self.assertEqual(database.unread_notifications(self.student_id), 2)

    def test_due_soon_once_and_only_if_not_done(self) -> None:
        now = time.time()
        assignment_id = database.create_assignment(
            self.school, self.teacher_id, "practice", "math", 1, now - 3 * 86400, now + 20 * 3600, None)
        self.assertEqual(notifications.check_due(now), 2)
        self.assertEqual(notifications.check_due(now), 0)
        texts = [n.text for n in notifications.for_user(self.student_id)]
        self.assertIn("меньше суток", texts[0])
        self.assertIn("сделано 0 из 1", texts[0])
        database.create_assignment(self.school, self.teacher_id, "practice", "physics", 1, now - 86400,
                                   now + 3 * 86400, None)
        database.create_assignment(self.school, self.teacher_id, "practice", "chemistry", 1, now - 3600,
                                   now + 3600, None)
        self.assertEqual(notifications.check_due(now), 0)
        self.assertIsNotNone(assignment_id)


class AdsTests(CabinetServerTestCase):
    """Реклама — только ученикам и гостям, никогда учителям, админам и во время теста."""

    def test_banner_audience(self) -> None:
        today = date.today()
        database.create_banner("Курсы", "https://e.kz", PNG, "image/png", "landing,dashboard,history",
                               (today - timedelta(days=1)).isoformat(), (today + timedelta(days=1)).isoformat(),
                               True, 0)
        self.assertIn("ad-banner", Browser(self.base_url).get("/")[2])
        student, html = self.login("student@mail.kz")
        self.assertIn("ad-banner", html)
        teacher, _ = self.login("teacher@mail.kz")
        self.assertNotIn("ad-banner", teacher.get("/")[2])
        admin, html = self.login("admin@mail.kz")
        self.assertNotIn("ad-banner", html)
        self.assertNotIn("ad-banner", admin.get("/")[2])
        self.assertNotIn("ad-banner", admin.get("/history")[2])
        self.add_questions("math", config.SINGLE, 12)
        attempt_id = ent_logic.build_practice(self.student_id, "math")
        self.assertNotIn("ad-banner", student.get(f"/practice/{attempt_id}")[2])
