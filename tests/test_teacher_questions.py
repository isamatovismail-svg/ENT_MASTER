"""Тесты этапа 4: вопросы учителей с проверкой главным администратором."""

import threading
import time

import config
from app import auth, database, ent_logic, schools
from app.database import Question
from app.server import create_server
from tests import test_pages
from tests.base import DatabaseTestCase
from tests.test_pages import Browser


def sample(text: str = "Сколько будет 2 + 2?", subject: str = "math") -> Question:
    """Простой вопрос с одним верным ответом."""
    return Question(id=0, subject=subject, qtype=config.SINGLE, text=text, context="",
                    options=["4", "5", "6", "7"], left=[], correct=["A"],
                    explanation="2 + 2 = 4.")


def form_fields(text: str, explanation: str = "Потому что 2 + 2 = 4.") -> dict:
    """Поля формы вопроса (один верный ответ)."""
    return {"type": "single", "subject": "math", "text": text, "opt_A": "4", "opt_B": "5",
            "opt_C": "6", "opt_D": "7", "correct": "A", "explanation": explanation}


class TeacherQuestionDatabaseTests(DatabaseTestCase):
    """Статусы вопросов и выборки банка."""

    def setUp(self) -> None:
        """Учитель и вопрос на проверке."""
        super().setUp()
        self.teacher = auth.create_account("Учитель", "t@mail.kz", "password1")
        self.question_id = database.insert_teacher_question(sample(), self.teacher, time.time())

    def bank_ids(self) -> set[int]:
        """id вопросов, видимых во всех выборках банка."""
        listed = {q.id for q in database.list_questions()} | {q.id for q in database.list_questions("math")}
        drawn = {ref.id for ref in database.random_questions("math", None, 100)}
        drawn |= {ref.id for ref in database.random_questions("math", config.SINGLE, 100, user_id=1)}
        return listed | drawn

    def test_pending_and_rejected_are_not_in_bank(self) -> None:
        """На проверке и отклонённый — нигде в банке; одобренный — везде."""
        self.assertNotIn(self.question_id, self.bank_ids())
        self.assertEqual(database.question_counts(), {})
        self.assertIsNone(database.get_question(self.question_id))
        with self.assertRaises(ent_logic.TestBuildError):
            ent_logic.build_practice(self.teacher, "math")

        self.assertTrue(database.review_question(self.question_id, database.Q_REJECTED,
                                                 "Неточная формулировка", time.time()))
        self.assertNotIn(self.question_id, self.bank_ids())
        question = database.get_author_question(self.question_id, self.teacher)
        self.assertEqual((question.status, question.review_comment),
                         ("rejected", "Неточная формулировка"))
        # Повторно проверить уже проверенный вопрос нельзя.
        self.assertFalse(database.review_question(self.question_id, database.Q_APPROVED, "",
                                                  time.time()))

        # Учитель исправляет — вопрос снова на проверке, комментарий сброшен.
        edited = sample("Сколько будет 2 + 3?")
        edited.id = self.question_id
        self.assertTrue(database.resubmit_author_question(edited, self.teacher, time.time()))
        question = database.get_author_question(self.question_id, self.teacher)
        self.assertEqual((question.status, question.review_comment, question.text),
                         ("pending", "", "Сколько будет 2 + 3?"))

        self.assertTrue(database.review_question(self.question_id, database.Q_APPROVED, "",
                                                 time.time()))
        self.assertIn(self.question_id, self.bank_ids())
        self.assertEqual(database.question_counts(), {("math", config.SINGLE): 1})
        self.assertIsNotNone(database.get_question(self.question_id))

    def test_approved_question_is_locked_for_teacher(self) -> None:
        """Одобренный вопрос учитель не меняет и не удаляет; чужой — не видит."""
        database.review_question(self.question_id, database.Q_APPROVED, "", time.time())
        edited = sample("Другой текст")
        edited.id = self.question_id
        self.assertFalse(database.resubmit_author_question(edited, self.teacher, time.time()))
        self.assertFalse(database.delete_author_question(self.question_id, self.teacher))
        other = auth.create_account("Чужой", "o@mail.kz", "password1")
        self.assertIsNone(database.get_author_question(self.question_id, other))
        self.assertEqual(database.list_author_questions(other), [])

    def test_seed_does_not_touch_teacher_questions(self) -> None:
        """seed.py с тем же текстом не перезаписывает и не одобряет вопрос учителя."""
        database.upsert_questions("math", [{
            "type": "single", "text": sample().text, "options": ["1", "2"],
            "correct": ["B"], "explanation": "Из файла.",
        }])
        question = database.get_author_question(self.question_id, self.teacher)
        self.assertEqual((question.status, question.options, question.explanation),
                         ("pending", ["4", "5", "6", "7"], "2 + 2 = 4."))

    def test_approve_with_changes(self) -> None:
        """Исправить и одобрить: вопрос в банке, помечен правкой админа, учитель видит пометку."""
        fixed = sample("Сколько будет 2 + 2? (исправлено)")
        fixed.id = self.question_id
        self.assertTrue(database.approve_with_changes(fixed, "Одобрено с исправлениями.", time.time()))
        question = database.get_question(self.question_id)
        self.assertEqual(question.text, "Сколько будет 2 + 2? (исправлено)")
        self.assertEqual(question.review_comment, "Одобрено с исправлениями.")
        with database.connect() as connection:
            edited = connection.execute("SELECT edited_by_admin FROM questions").fetchone()[0]
        self.assertEqual(edited, 1)
        self.assertFalse(database.approve_with_changes(fixed, "", time.time()))


class TeacherQuestionPagesTests(DatabaseTestCase):
    """Вопросы учителя и очередь проверки на работающем сервере."""

    def setUp(self) -> None:
        """Сервер, учитель школы, второй учитель, ученик и администратор."""
        super().setUp()
        self.server = create_server("127.0.0.1", 0)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        school = schools.find_or_create_school("Алматы", "12")
        for name, email in (("Учитель Айгуль", "teacher@mail.kz"), ("Другой", "other@mail.kz")):
            auth.create_account(name, email, "password1")
            database.make_teacher(email, school)
        auth.create_account("Ученик", "student@mail.kz", "password1")
        auth.create_account("Админ", "admin@mail.kz", "password1")
        database.set_user_role("admin@mail.kz", database.ROLE_ADMIN)

    def tearDown(self) -> None:
        """Останавливает сервер."""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    csrf = staticmethod(test_pages.PagesTests.csrf)

    def login(self, email: str) -> Browser:
        """Браузер, вошедший в аккаунт."""
        browser = Browser(self.base_url)
        _, path, _, _ = browser.post("/login", {"login": email, "password": "password1"})
        self.assertEqual(path, "/dashboard")
        return browser

    def post_form(self, browser: Browser, url: str, fields: dict):
        """POST формы с csrf-токеном со страницы этой формы."""
        _, _, html, _ = browser.get(url)
        return browser.post(url, {"csrf_token": self.csrf(html), **fields})

    def test_review_cycle(self) -> None:
        """Учитель предлагает → админ отклоняет с комментарием → учитель исправляет →
        админ исправляет и одобряет → вопрос в банке и в тестах."""
        teacher = self.login("teacher@mail.kz")
        _, _, html, _ = teacher.get("/teacher/questions")
        self.assertIn("Вы ещё не предлагали вопросов", html)

        # Та же форма и та же проверка, что в админке.
        status, _, html, _ = self.post_form(teacher, "/teacher/questions/new",
                                            form_fields("Вопрос без объяснения", explanation=""))
        self.assertEqual(status, 400)
        self.assertIn("Вопрос без объяснения", html)
        status, path, html, _ = self.post_form(teacher, "/teacher/questions/new",
                                               form_fields("Сколько будет 2 + 2?"))
        self.assertEqual(path, "/teacher/questions?msg=tq_submitted")
        self.assertIn("на проверке", html)
        question_id = database.list_author_questions(
            database.get_user_credentials("teacher@mail.kz")["id"])[0].id
        self.assertEqual(database.question_counts(), {})

        # Чужой учитель вопрос не видит и не меняет.
        other = self.login("other@mail.kz")
        self.assertEqual(other.get(f"/teacher/questions/{question_id}/edit")[0], 404)
        self.assertNotIn("Сколько будет 2 + 2?", other.get("/teacher/questions")[2])

        # Админ: очередь, отклонение только с комментарием.
        admin = self.login("admin@mail.kz")
        _, _, html, _ = admin.get("/admin/review")
        self.assertIn("🔎 Проверка (1)", html)
        self.assertIn("Вопросы учителей на проверке: 1", html)
        self.assertIn("Учитель Айгуль", html)
        self.assertIn("Алматы, школа №12", html)
        self.assertIn("✅", html)  # верный вариант отмечен
        review_url = f"/admin/review/{question_id}"
        self.assertEqual(admin.post(review_url, {"action": "reject"})[0], 403)  # нет csrf
        _, path, _, _ = admin.post(review_url, {"action": "reject", "comment": " ",
                                                "csrf_token": self.csrf(html)})
        self.assertEqual(path, "/admin/review?msg=review_comment_needed")
        _, path, html, _ = admin.post(review_url, {
            "action": "reject", "comment": "Добавьте единицы измерения",
            "csrf_token": self.csrf(html)})
        self.assertIn("Очередь пуста", html)

        _, _, html, _ = teacher.get("/teacher/questions")
        self.assertIn("отклонён", html)
        self.assertIn("Добавьте единицы измерения", html)
        _, _, html, _ = teacher.get(f"/teacher/questions/{question_id}/edit")
        self.assertIn("Комментарий администратора: Добавьте единицы измерения", html)
        _, path, _, _ = self.post_form(teacher, f"/teacher/questions/{question_id}/edit",
                                       form_fields("Сколько будет 2 + 2 яблока?"))
        self.assertEqual(path, "/teacher/questions?msg=tq_resubmitted")

        # Админ исправляет и одобряет.
        edit_url = f"/admin/review/{question_id}/edit"
        _, _, html, _ = admin.get(edit_url)
        self.assertIn("Сколько будет 2 + 2 яблока?", html)
        _, path, html, _ = self.post_form(admin, edit_url,
                                          form_fields("Сколько будет 2 + 2 яблока? Ответ в штуках."))
        self.assertEqual(path, "/admin/review?msg=review_approved")
        self.assertEqual(database.question_counts(), {("math", config.SINGLE): 1})
        self.assertIn("Ответ в штуках", admin.get("/admin/questions?subject=math")[2])

        _, _, html, _ = teacher.get("/teacher/questions")
        self.assertIn("одобрен", html)
        self.assertIn("Одобрено с исправлениями администратора", html)
        self.assertEqual(teacher.get(f"/teacher/questions/{question_id}/edit")[1],
                         "/teacher/questions?msg=tq_locked")

        # Одобренный вопрос попадает в тренировку любого ученика.
        student_id = database.get_user_credentials("student@mail.kz")["id"]
        attempt_id = ent_logic.build_practice(student_id, "math")
        self.assertEqual([aq.question_id for aq in database.get_attempt_questions(attempt_id)],
                         [question_id])

    def test_quick_approve_and_delete(self) -> None:
        """«Одобрить» одной кнопкой; учитель может удалить вопрос, пока он не одобрен."""
        teacher = self.login("teacher@mail.kz")
        self.post_form(teacher, "/teacher/questions/new", form_fields("Первый вопрос"))
        self.post_form(teacher, "/teacher/questions/new", form_fields("Второй вопрос"))
        first, second = sorted(q.id for q in database.list_author_questions(
            database.get_user_credentials("teacher@mail.kz")["id"]))

        _, _, html, _ = teacher.get("/teacher/questions")
        _, path, html, _ = teacher.post(f"/teacher/questions/{second}/delete",
                                        {"csrf_token": self.csrf(html)})
        self.assertEqual(path, "/teacher/questions?msg=tq_deleted")
        self.assertNotIn("Второй вопрос", html)

        admin = self.login("admin@mail.kz")
        _, _, html, _ = admin.get("/admin/review")
        _, path, _, _ = admin.post(f"/admin/review/{first}",
                                   {"action": "approve", "csrf_token": self.csrf(html)})
        self.assertEqual(path, "/admin/review?msg=review_approved")
        self.assertIsNotNone(database.get_question(first))
        _, _, html, _ = teacher.get("/teacher/questions")
        _, path, _, _ = teacher.post(f"/teacher/questions/{first}/delete",
                                     {"csrf_token": self.csrf(html)})
        self.assertEqual(path, "/teacher/questions?msg=tq_locked")
        self.assertEqual(admin.get("/admin/review/999/edit")[1], "/admin/review?msg=review_missing")

    def test_access(self) -> None:
        """«Мои вопросы» — только учителям, очередь проверки — только администратору."""
        student = self.login("student@mail.kz")
        self.assertEqual(student.get("/teacher/questions")[0], 403)
        self.assertEqual(student.get("/teacher/questions/new")[0], 403)
        self.assertEqual(student.get("/admin/review")[0], 403)
        teacher = self.login("teacher@mail.kz")
        self.assertEqual(teacher.get("/admin/review")[0], 403)
        self.assertIn('href="/teacher/questions"', teacher.get("/teacher")[2])
        admin = self.login("admin@mail.kz")
        self.assertEqual(admin.get("/teacher/questions")[0], 403)
        self.assertTrue(Browser(self.base_url).get("/teacher/questions")[1].startswith("/login?"))
