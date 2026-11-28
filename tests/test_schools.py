"""Тесты этапа 3: школы, роли, кабинет учителя и задания."""

import contextlib
import io
import threading
import time
from datetime import date, timedelta

from app import config
import manage_admin
from app.core import auth, database, ent_logic, schools
from app.web.server import create_server
from tests import test_pages
from tests.base import DatabaseTestCase
from tests.test_pages import Browser

TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def approved_student(school_id: int, name: str, email: str) -> int:
    """Готовый подтверждённый ученик школы."""
    user_id = auth.create_account(name, email, "password1")
    database.set_user_school(user_id, school_id, database.SCHOOL_APPROVED)
    return user_id


class SchoolTests(DatabaseTestCase):
    """Школы без дубликатов, заявки, статусы."""

    def test_school_key_merges_spellings(self) -> None:
        """«Школа №12», «СОШ 12» и «12» в одном городе — одна школа."""
        key = schools.school_key("Алматы", "12")
        for city, name in (("г. Алматы", "Школа №12"), ("АЛМАТЫ", "СОШ 12"), (" алматы ", "№ 12")):
            self.assertEqual(schools.school_key(city, name), key, (city, name))
        self.assertNotEqual(schools.school_key("Алматы", "Гимназия 12"), key)
        self.assertNotEqual(schools.school_key("Астана", "12"), key)

        first = schools.find_or_create_school(*schools.validate_school("Алматы", "Школа №12"))
        second = schools.find_or_create_school(*schools.validate_school("г. алматы", "12"))
        self.assertEqual(first, second)
        self.assertEqual(len(database.list_schools()), 1)
        school = database.get_school(first)
        self.assertEqual(schools.school_title(school["city"], school["name"]), "Алматы, школа №12")

    def test_validate_school(self) -> None:
        """Пустые поля — без школы; заполнено одно поле — ошибка."""
        self.assertIsNone(schools.validate_school(" ", ""))
        self.assertEqual(schools.validate_school("Астана", " НИШ "), ("Астана", "НИШ"))
        for city, name, fragment in (("Алматы", "", "номер"), ("", "12", "город"),
                                     ("Алматы", "№", "неверно")):
            with self.assertRaises(schools.SchoolError) as context:
                schools.validate_school(city, name)
            self.assertIn(fragment, " ".join(context.exception.errors))

    def test_registration_with_school_is_pending(self) -> None:
        """Школа при регистрации: заявка ждёт подтверждения; неполная школа — ошибка."""
        user_id = auth.register_user("Али", "Ахметов", "ali@mail.kz", "", "password1", "password1",
                                     school_city="Алматы", school_name="12")
        row = database.get_user_school(user_id)
        self.assertEqual((row["city"], row["name"], row["school_status"]),
                         ("Алматы", "12", database.SCHOOL_PENDING))
        with self.assertRaises(auth.ValidationError) as context:
            auth.register_user("Бек", "Ахметов", "bek@mail.kz", "", "password1", "password1",
                               school_city="Алматы")
        self.assertIn("номер или название школы", " ".join(context.exception.errors))

    def test_join_change_and_leave(self) -> None:
        """Смена школы снова требует подтверждения; та же школа статус не сбрасывает."""
        user_id = auth.create_account("Али", "ali@mail.kz", "password1")
        first = schools.join_school(user_id, "Алматы", "12")
        database.set_member_status(first, user_id, database.SCHOOL_APPROVED)
        self.assertEqual(schools.join_school(user_id, "Алматы", "Школа №12"), first)
        self.assertEqual(database.get_user_school(user_id)["school_status"], "approved")

        second = schools.join_school(user_id, "Астана", "5")
        self.assertNotEqual(first, second)
        self.assertEqual(database.get_user_school(user_id)["school_status"], "pending")
        self.assertIsNone(schools.join_school(user_id, "", ""))
        self.assertIsNone(database.get_user_school(user_id))

    def test_teacher_manages_only_own_school(self) -> None:
        """Подтвердить/исключить можно только ученика своей школы."""
        mine = schools.find_or_create_school("Алматы", "12")
        other = schools.find_or_create_school("Астана", "5")
        student = auth.create_account("Али", "ali@mail.kz", "password1")
        database.set_user_school(student, other, database.SCHOOL_PENDING)
        self.assertFalse(database.set_member_status(mine, student, database.SCHOOL_APPROVED))
        self.assertTrue(database.set_member_status(other, student, database.SCHOOL_APPROVED))
        self.assertEqual(len(database.list_school_members(other, "approved")), 1)
        self.assertEqual(database.list_school_members(mine, "approved"), [])

    def test_last_login_is_saved(self) -> None:
        """Время последнего входа записывается при создании сессии."""
        user_id = auth.create_account("Али", "ali@mail.kz", "password1")
        before = time.time()
        auth.start_session(user_id)
        with database.connect() as connection:
            last = connection.execute("SELECT last_login_at FROM users").fetchone()[0]
        self.assertGreaterEqual(last, before)


class ManageTeacherTests(DatabaseTestCase):
    """python manage_admin.py <логин> --teacher <город> <школа>."""

    def run_command(self, *args: str) -> tuple[int, str]:
        """Запускает команду и возвращает (код, вывод)."""
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = manage_admin.main(list(args))
        return code, output.getvalue()

    def test_teacher_and_revoke(self) -> None:
        """Назначение учителя создаёт школу; снятие роли убирает учителя из школы."""
        auth.create_account("Учитель", "teacher@mail.kz", "password1")
        code, text = self.run_command("Teacher@mail.kz", "--teacher", "Алматы", "Школа №12")
        self.assertEqual(code, 0, text)
        self.assertIn("учитель школы «Алматы, школа №12»", text)
        row = database.get_user_credentials("teacher@mail.kz")
        self.assertEqual(row["role"], database.ROLE_TEACHER)
        school = database.get_user_school(row["id"])
        self.assertEqual((school["city"], school["name"]), ("Алматы", "12"))

        code, _ = self.run_command("teacher@mail.kz", "--revoke")
        self.assertEqual(code, 0)
        self.assertEqual(database.get_user_credentials("teacher@mail.kz")["role"], "user")
        self.assertIsNone(database.get_user_school(row["id"]))

        self.assertEqual(self.run_command("teacher@mail.kz", "--teacher", "Алматы", "")[0], 1)
        self.assertEqual(self.run_command("nobody@mail.kz", "--teacher", "Алматы", "1")[0], 1)
        self.assertEqual(self.run_command("teacher@mail.kz", "--teacher")[0], 1)


class AssignmentTests(DatabaseTestCase):
    """Задания: какие попытки засчитываются."""

    def setUp(self) -> None:
        """Школа, учитель, два подтверждённых ученика и банк вопросов."""
        super().setUp()
        self.school = schools.find_or_create_school("Алматы", "12")
        self.teacher = auth.create_account("Учитель", "t@mail.kz", "password1")
        self.alice = approved_student(self.school, "Алия", "alice@mail.kz")
        self.bob = approved_student(self.school, "Бекзат", "bob@mail.kz")
        for code in ("math", "physics", "chemistry", *config.COMPULSORY_CODES):
            self.add_questions(code, config.SINGLE, 12)

    def practice(self, user_id: int, subject: str, finished_at: float) -> None:
        """Завершённая тренировка в заданное время."""
        attempt_id = ent_logic.build_practice(user_id, subject, now=finished_at - 60)
        attempt = database.get_attempt(attempt_id, user_id)
        ent_logic.finish_attempt(attempt, now=finished_at)

    def mock(self, user_id: int, pair_index: int, finished_at: float) -> None:
        """Завершённый пробный ЕНТ в заданное время."""
        attempt_id = ent_logic.build_mock(user_id, pair_index, now=finished_at - 60)
        attempt = database.get_attempt(attempt_id, user_id)
        ent_logic.finish_attempt(attempt, now=finished_at)

    def test_only_attempts_between_issue_and_deadline_count(self) -> None:
        """Засчитываются попытки по предмету задания, завершённые после выдачи и до срока."""
        assignment_id = schools.create_assignment(
            self.school, self.teacher, "practice", "math", "", "2", TOMORROW, True, [])
        assignment = database.get_assignment(assignment_id, self.school)
        created, deadline = assignment["created_at"], assignment["deadline"]
        self.practice(self.alice, "math", created - 10)
        self.practice(self.alice, "physics", created + 10)
        self.practice(self.alice, "math", created + 20)
        self.practice(self.alice, "math", created + 30)
        self.practice(self.alice, "math", created + 40)
        self.practice(self.bob, "math", deadline + 10)

        progress = {item.user_id: item for item in schools.assignment_progress(assignment)}
        self.assertEqual((progress[self.alice].done, progress[self.alice].status), (2, "done"))
        self.assertEqual(len(progress[self.alice].scores), 2)
        self.assertEqual((progress[self.bob].done, progress[self.bob].status), (0, "active"))
        later = schools.assignment_progress(assignment, now=deadline + 100)
        self.assertEqual({item.user_id: item.status for item in later}[self.bob], "overdue")

    def test_mock_pair_and_selected_students(self) -> None:
        """Конкретная пара засчитывается только для неё; «выбранным» — только им."""
        pair = ",".join(config.PROFILE_PAIRS[0])
        assignment_id = schools.create_assignment(
            self.school, self.teacher, "mock", "", pair, "1", TOMORROW, False, [self.alice, 999])
        assignment = database.get_assignment(assignment_id, self.school)
        self.assertEqual([row["id"] for row in database.assignment_students(assignment)],
                         [self.alice])
        chemistry_pair = config.PROFILE_PAIRS.index(("chemistry", "physics"))
        self.mock(self.alice, chemistry_pair, assignment["created_at"] + 10)
        self.assertEqual(schools.assignment_progress(assignment)[0].done, 0)
        self.mock(self.alice, 0, assignment["created_at"] + 20)
        self.assertEqual(schools.assignment_progress(assignment)[0].done, 1)

        self.assertEqual(len(database.list_student_assignments(self.alice)), 1)
        self.assertEqual(database.list_student_assignments(self.bob), [])
        database.set_user_school(self.alice, None, None)
        self.assertEqual(database.list_student_assignments(self.alice), [])

    def test_any_pair_counts_every_mock(self) -> None:
        """«Любая пара» засчитывает любой пробный ЕНТ."""
        assignment_id = schools.create_assignment(
            self.school, self.teacher, "mock", "", "", "1", TOMORROW, True, [])
        assignment = database.get_assignment(assignment_id, self.school)
        self.mock(self.bob, config.PROFILE_PAIRS.index(("chemistry", "physics")),
                  assignment["created_at"] + 10)
        progress = {item.user_id: item.done for item in schools.assignment_progress(assignment)}
        self.assertEqual(progress, {self.alice: 0, self.bob: 1})

    def test_assignment_form_errors(self) -> None:
        """Неверная форма задания — список понятных ошибок."""
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        cases = (
            (("practice", "", "", "1", TOMORROW, True, []), "предмет"),
            (("mock", "", "math,law", "1", TOMORROW, True, []), "пару"),
            (("exam", "", "", "1", TOMORROW, True, []), "вид задания"),
            (("practice", "math", "", "0", TOMORROW, True, []), "от 1 до 20"),
            (("practice", "math", "", "1", yesterday, True, []), "в прошлом"),
            (("practice", "math", "", "1", "", True, []), "срок"),
            (("practice", "math", "", "1", TOMORROW, False, [12345]), "хотя бы одного"),
        )
        for args, fragment in cases:
            with self.assertRaises(schools.SchoolError, msg=args) as context:
                schools.create_assignment(self.school, self.teacher, *args)
            self.assertIn(fragment, " ".join(context.exception.errors), args)

    def test_deadline_is_end_of_day(self) -> None:
        """Срок — конец выбранного дня; сегодняшний день допустим."""
        today = date.today()
        end = schools.parse_deadline(today.isoformat())
        self.assertEqual(time.localtime(end)[3:6], (23, 59, 59))


class TeacherPagesTests(DatabaseTestCase):
    """Кабинет учителя и профиль ученика на работающем сервере."""

    def setUp(self) -> None:
        """Сервер, школа с учителем, второй учитель другой школы, администратор."""
        super().setUp()
        self.add_questions("math", config.SINGLE, 12)
        self.server = create_server("127.0.0.1", 0)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.school = schools.find_or_create_school("Алматы", "12")
        self.other_school = schools.find_or_create_school("Астана", "5")
        auth.create_account("Учитель", "teacher@mail.kz", "password1")
        database.make_teacher("teacher@mail.kz", self.school)
        auth.create_account("Чужой учитель", "other@mail.kz", "password1")
        database.make_teacher("other@mail.kz", self.other_school)
        auth.create_account("Админ", "admin@mail.kz", "password1")
        database.set_user_role("admin@mail.kz", database.ROLE_ADMIN)

    def tearDown(self) -> None:
        """Останавливает сервер."""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def login(self, email: str) -> Browser:
        """Браузер, вошедший в аккаунт."""
        browser = Browser(self.base_url)
        status, path, _, _ = browser.post("/login", {"login": email, "password": "password1"})
        self.assertTrue(path == "/dashboard" or path.startswith("/teacher"), path)
        return browser

    csrf = staticmethod(test_pages.PagesTests.csrf)

    def test_full_school_flow(self) -> None:
        """Заявка при регистрации → подтверждение → карточка → задание → ученик его видит."""
        student = Browser(self.base_url)
        status, path, html, _ = student.post("/register", {
            "first_name": "Алия", "last_name": "Серикова", "email": "aliya@mail.kz",
            "school_city": "г. Алматы", "school_name": "Школа №12",
            "password": "password123", "password2": "password123",
        })
        student.post("/verify", {"email": "aliya@mail.kz",
                                 "code": self.mail.last_code("aliya@mail.kz")})
        _, _, html, _ = student.get("/dashboard")
        self.assertIn("Алматы, школа №12", html)
        self.assertIn("ждёт подтверждения учителя", html)
        student_id = database.get_user_credentials("aliya@mail.kz")["id"]

        teacher = self.login("teacher@mail.kz")
        self.assertEqual(teacher.get("/dashboard")[1], f"/teacher/{self.school}")
        status, path, html, _ = teacher.get("/teacher")
        self.assertEqual(path, f"/teacher/{self.school}")
        self.assertIn("Заявки в школу: 1", html)
        self.assertIn("Алия Серикова", html)
        card = f"/teacher/{self.school}/students/{student_id}"
        self.assertEqual(teacher.get(card)[0], 404)

        member_url = f"/teacher/{self.school}/members/{student_id}"
        self.assertEqual(teacher.post(member_url, {"action": "approve"})[0], 403)
        status, path, html, _ = teacher.post(
            member_url, {"action": "approve", "csrf_token": self.csrf(html)})
        self.assertIn("Ученик подтверждён", html)
        self.assertIn(card, html)

        _, _, html, _ = student.get("/practice")
        student.post("/practice/start", {"subject": "math", "csrf_token": self.csrf(html)})
        attempt = database.get_in_progress_attempt(student_id, ent_logic.PRACTICE)
        ent_logic.finish_attempt(attempt)
        status, _, html, _ = teacher.get(card)
        self.assertEqual(status, 200)
        self.assertIn("Лента по дням", html)
        self.assertIn("Сегодня", html)
        self.assertIn("Математика", html)
        self.assertIn(f"{card}/attempts/{attempt.id}", html)
        self.assertEqual(teacher.get(f"{card}/attempts/{attempt.id}")[0], 200)

        _, _, html, _ = teacher.get(f"/teacher/{self.school}/assignments/new")
        self.assertIn("Алия Серикова", html)
        status, _, html, _ = teacher.post(f"/teacher/{self.school}/assignments/new", {
            "csrf_token": self.csrf(html), "mode": "practice", "subject": "", "count": "2",
            "deadline": TOMORROW, "for_all": "1",
        })
        self.assertEqual(status, 400)
        self.assertIn("Выберите предмет", html)
        self.assertIn('value="2"', html)
        status, path, html, _ = teacher.post(f"/teacher/{self.school}/assignments/new", {
            "csrf_token": self.csrf(html), "mode": "practice", "subject": "math", "count": "2",
            "deadline": TOMORROW, "for_all": "0", "students": [str(student_id)],
        })
        self.assertIn("Задание выдано", html)
        self.assertIn("Тренировка × 2: Математика", html)
        self.assertIn("0 из 2", html)
        assignment_path = path.split("?")[0]

        _, _, html, _ = student.get("/dashboard")
        self.assertIn("Задания учителя", html)
        self.assertIn("Тренировка × 2: Математика", html)
        self.assertIn("0 из 2", html)
        self.assertIn("Пройдите тренировку: Математика", html)

        _, _, html, _ = teacher.get(assignment_path)
        status, path, html, _ = teacher.post(f"{assignment_path}/delete",
                                             {"csrf_token": self.csrf(html)})
        self.assertIn("Задание удалено", html)
        self.assertTrue(path.startswith(f"/teacher/{self.school}/assignments"))
        self.assertEqual(teacher.get(assignment_path)[0], 404)

    def test_access_is_limited_to_own_school(self) -> None:
        """Учитель чужой школы, ученик и гость в кабинет не попадают; админ — во все школы."""
        student_id = auth.create_account("Ученик", "student@mail.kz", "password1")
        database.set_user_school(student_id, self.school, database.SCHOOL_APPROVED)
        assignment_id = schools.create_assignment(
            self.school, 1, "practice", "math", "", "1", TOMORROW, True, [])
        pages = (
            f"/teacher/{self.school}",
            f"/teacher/{self.school}/students/{student_id}",
            f"/teacher/{self.school}/assignments/new",
            f"/teacher/{self.school}/assignments/{assignment_id}",
        )
        other = self.login("other@mail.kz")
        self.assertEqual(other.get("/teacher")[1], f"/teacher/{self.other_school}")
        for page in pages:
            self.assertEqual(other.get(page)[0], 403, page)
        _, _, html, _ = other.get(f"/teacher/{self.other_school}")
        status, _, _, _ = other.post(f"/teacher/{self.school}/members/{student_id}",
                                     {"action": "remove", "csrf_token": self.csrf(html)})
        self.assertEqual(status, 403)
        self.assertEqual(
            other.get(f"/teacher/{self.other_school}/students/{student_id}")[0], 404)
        self.assertEqual(
            other.get(f"/teacher/{self.other_school}/assignments/{assignment_id}")[0], 404)

        student = self.login("student@mail.kz")
        self.assertEqual(student.get("/teacher")[0], 403)
        self.assertEqual(student.get(pages[0])[0], 403)
        self.assertTrue(Browser(self.base_url).get(pages[0])[1].startswith("/login?"))

        admin = self.login("admin@mail.kz")
        status, _, html, _ = admin.get("/teacher")
        self.assertIn("Все школы: 2", html)
        self.assertIn("Астана, школа №5", html)
        for page in pages:
            self.assertEqual(admin.get(page)[0], 200, page)
        self.assertIn("🏫 учитель", admin.get("/admin/users")[2])

    def test_profile_change_and_leave_school(self) -> None:
        """В профиле ученик выбирает школу, меняет её (нужно подтверждение) и выходит."""
        student_id = auth.create_account("Ученик", "student@mail.kz", "password1")
        database.set_user_school(student_id, self.school, database.SCHOOL_APPROVED)
        browser = self.login("student@mail.kz")
        _, _, html, _ = browser.get("/profile")
        self.assertIn("подтверждено", html)
        self.assertIn("Сменить школу", html)

        status, _, html, _ = browser.post("/profile/school", {
            "csrf_token": self.csrf(html), "city": "Астана", "name": ""})
        self.assertEqual(status, 400)
        self.assertIn("номер или название", html)
        status, _, html, _ = browser.post("/profile/school", {
            "csrf_token": self.csrf(html), "city": "Астана", "name": "5"})
        self.assertIn("Заявка отправлена", html)
        self.assertIn("Астана, школа №5", html)
        self.assertIn("ждёт подтверждения", html)

        status, _, html, _ = browser.post("/profile/school", {
            "csrf_token": self.csrf(html), "action": "leave"})
        self.assertIn("Вы вышли из школы", html)
        self.assertIsNone(database.get_user_school(student_id))

        teacher = self.login("teacher@mail.kz")
        _, _, html, _ = teacher.get("/profile")
        self.assertIn("назначает главный администратор", html)
        status, _, _, _ = teacher.post("/profile/school", {
            "csrf_token": self.csrf(html), "city": "Астана", "name": "5"})
        self.assertEqual(status, 403)
