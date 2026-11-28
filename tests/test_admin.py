"""Тесты админ-панели: доступ, csrf, вопросы (добавить/изменить/удалить), пользователи."""

import contextlib
import io
import re
import threading
from urllib.parse import urlencode

from app import config
import manage_admin
from app.core import database, ent_logic
from app.web.server import create_server
from tests.base import DatabaseTestCase
from tests import test_pages
from tests.test_pages import Browser

ADMIN_PAGES = ("/admin", "/admin/questions", "/admin/questions/new", "/admin/users")


class ManageAdminTests(DatabaseTestCase):
    """Команда python manage_admin.py <логин>."""

    def run_command(self, *args: str) -> tuple[int, str]:
        """Запускает команду и возвращает (код возврата, вывод)."""
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = manage_admin.main(list(args))
        return code, output.getvalue()

    def test_grant_and_revoke(self) -> None:
        """Назначение и снятие роли; логин нормализуется как при входе."""
        from app.core import auth
        auth.create_account("Админ", "boss@mail.kz", "password1")
        code, text = self.run_command("boss@mail.KZ")
        self.assertEqual(code, 0, text)
        self.assertEqual(database.get_user_credentials("boss@mail.kz")["role"], "admin")
        code, _ = self.run_command("boss@mail.kz", "--revoke")
        self.assertEqual(code, 0)
        self.assertEqual(database.get_user_credentials("boss@mail.kz")["role"], "user")

    def test_unknown_login_and_usage(self) -> None:
        """Неизвестный логин и запуск без аргументов — код 1 и понятное сообщение."""
        code, text = self.run_command("nobody@mail.kz")
        self.assertEqual(code, 1)
        self.assertIn("не найден", text)
        code, text = self.run_command()
        self.assertEqual(code, 1)
        self.assertIn("manage_admin.py", text)


class AdminPagesTests(DatabaseTestCase):
    """Админка на работающем сервере с пустым банком вопросов."""

    def setUp(self) -> None:
        """Запускает сервер, создаёт администратора и обычного ученика."""
        super().setUp()
        self.server = create_server("127.0.0.1", 0)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        helper = test_pages.PagesTests()
        self.admin = Browser(self.base_url)
        helper.register_and_login(self.admin, "admin@mail.kz", name="Админ")
        database.set_user_role("admin@mail.kz", database.ROLE_ADMIN)
        self.student = Browser(self.base_url)
        helper.register_and_login(self.student, "student@mail.kz", name="Ученик")

    def tearDown(self) -> None:
        """Останавливает сервер."""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    csrf = staticmethod(test_pages.PagesTests.csrf)

    def post_question(self, url: str, fields: dict, browser: Browser | None = None):
        """Отправляет форму вопроса с csrf-токеном со страницы формы."""
        browser = browser or self.admin
        _, _, html, _ = browser.get(url)
        data = {"csrf_token": self.csrf(html), **fields}
        return browser.post(url, data)


    def test_access_only_for_admin(self) -> None:
        """Гость → вход, ученик → 403, админ → 200; ссылка «Админка» только у админа."""
        guest = Browser(self.base_url, follow_redirects=False)
        for path in ADMIN_PAGES:
            status, _, _, headers = guest.get(path)
            self.assertEqual(status, 303, path)
            self.assertTrue(headers["Location"].startswith("/login?"), path)
            status, _, html, _ = self.student.get(path)
            self.assertEqual(status, 403, path)
            self.assertIn("только администраторам", html)
            status, _, html, _ = self.admin.get(path)
            self.assertEqual(status, 200, path)
        self.assertNotIn('href="/admin"', self.student.get("/dashboard")[2])
        self.assertIn('href="/admin"', self.admin.get("/dashboard")[2])

        _, _, html, _ = self.student.get("/dashboard")
        status, _, _, _ = self.student.post("/admin/questions/new", {
            "csrf_token": self.csrf(html), "type": "single", "subject": "math", "topic": "05", "text": "x",
            "opt_A": "1", "opt_B": "2", "correct": "A", "explanation": "y",
        })
        self.assertEqual(status, 403)
        self.assertEqual(database.list_questions(), [])

    def test_csrf_required(self) -> None:
        """POST админки без csrf-токена отклоняется."""
        status, _, html, _ = self.admin.post("/admin/questions/new", {
            "type": "single", "subject": "math", "topic": "05", "text": "x", "opt_A": "1", "opt_B": "2",
            "correct": "A", "explanation": "y",
        })
        self.assertEqual(status, 403)
        self.assertIn("Форма устарела", html)
        self.assertEqual(database.list_questions(), [])
        self.assertIn('name="csrf_token"', self.admin.get("/admin/questions/new")[2])


    def test_create_all_types_and_use_in_tests(self) -> None:
        """Вопросы всех четырёх типов добавляются через форму и сразу попадают в тесты."""
        cases = {
            config.SINGLE: {"opt_A": "4", "opt_B": "5", "opt_C": "6", "correct": "B"},
            config.CONTEXT: {"context": "Цена 100 тг, скидка 10%.", "opt_A": "90 тг",
                             "opt_B": "110 тг", "correct": "A"},
            config.MULTIPLE: {"opt_A": "2", "opt_B": "4", "opt_C": "5", "opt_D": "7",
                              "correct": ["A", "C", "D"]},
            config.MATCHING: {"left_0": "x²", "left_1": "sin x", "match_0": "B", "match_1": "A",
                              "opt_A": "cos x", "opt_B": "2x", "opt_C": "−sin x"},
        }
        for qtype, fields in cases.items():
            status, _, html, _ = self.admin.get(f"/admin/questions/new?type={qtype}")
            self.assertEqual(status, 200)
            if qtype == config.CONTEXT:
                self.assertIn('name="context"', html)
            if qtype == config.MATCHING:
                self.assertIn('name="left_0"', html)
                self.assertNotIn('name="correct"', html)
            if qtype == config.MULTIPLE:
                self.assertIn('type="checkbox" name="correct"', html)
            status, path, html, _ = self.post_question("/admin/questions/new", {
                "type": qtype, "subject": "law", "topic": "01", "text": f"Вопрос типа {qtype}",
                "explanation": f"Объяснение для {qtype}.", **fields,
            })
            self.assertEqual(status, 200, html[-2000:])
            self.assertEqual(path, "/admin/questions?subject=law&msg=q_created")
            self.assertIn("Вопрос добавлен", html)
            self.assertIn(f"Вопрос типа {qtype}", html)

        saved = {question.qtype: question for question in database.list_questions("law")}
        self.assertEqual(saved[config.SINGLE].correct, ["B"])
        self.assertEqual(saved[config.SINGLE].options, ["4", "5", "6"])
        self.assertEqual(saved[config.CONTEXT].context, "Цена 100 тг, скидка 10%.")
        self.assertEqual(saved[config.MULTIPLE].correct, ["A", "C", "D"])
        self.assertEqual(saved[config.MATCHING].left, ["x²", "sin x"])
        self.assertEqual(saved[config.MATCHING].correct, ["B", "A"])
        self.assertEqual(saved[config.MATCHING].explanation, "Объяснение для matching.")

        counts = database.question_counts()
        self.assertEqual(counts[("law", config.SINGLE)], 1)
        attempt_id = ent_logic.build_practice(1, "law")
        texts = {aq.text for aq in database.get_attempt_questions(attempt_id)}
        self.assertEqual(texts, {f"Вопрос типа {qtype}" for qtype in cases})

    def test_form_errors_keep_values(self) -> None:
        """Ошибки формы показываются, введённое не теряется, в базу ничего не пишется."""
        status, _, html, _ = self.post_question("/admin/questions/new", {
            "type": "single", "subject": "math", "topic": "05", "text": "Сколько будет 2 + 2?",
            "opt_A": "3", "opt_C": "4", "explanation": "",
        })
        self.assertEqual(status, 400)
        self.assertIn("заполняйте подряд", html)
        self.assertIn("Отметьте правильный ответ", html)
        self.assertIn("Сколько будет 2 + 2?", html)
        self.assertIn('value="4"', html)

        status, _, html, _ = self.post_question("/admin/questions/new", {
            "type": "matching", "subject": "math", "topic": "05", "text": "Сопоставьте",
            "left_0": "a", "left_1": "b", "match_0": "A", "opt_A": "1", "opt_B": "2",
            "explanation": "Потому что.",
        })
        self.assertEqual(status, 400)
        self.assertIn("выберите правильную букву", html)

        status, _, html, _ = self.post_question("/admin/questions/new", {
            "type": "single", "subject": "math", "topic": "05", "text": "Без объяснения",
            "opt_A": "1", "opt_B": "2", "correct": "A", "explanation": "  ",
        })
        self.assertEqual(status, 400)
        self.assertIn("Нет объяснения", html)

        status, _, html, _ = self.post_question("/admin/questions/new", {
            "type": "single", "subject": "nope", "text": "x", "opt_A": "1", "opt_B": "2",
            "correct": "Z", "explanation": "y",
        })
        self.assertEqual(status, 400)
        self.assertIn("Выберите предмет", html)
        self.assertEqual(database.list_questions(), [])

    def test_edit_search_and_duplicates(self) -> None:
        """Изменение вопроса, смена типа, поиск, фильтр и защита от дубликатов."""
        self.add_questions("math", config.SINGLE, 2)
        self.add_questions("physics", config.SINGLE, 1)
        first = next(q for q in database.list_questions("math") if q.text.endswith("№0"))

        status, _, html, _ = self.admin.get(f"/admin/questions/{first.id}/edit")
        self.assertEqual(status, 200)
        self.assertIn(first.text, html)
        self.assertRegex(html, r'value="A" checked')

        status, _, html, _ = self.admin.get(f"/admin/questions/{first.id}/edit?type=multiple")
        self.assertIn('type="checkbox" name="correct" value="A" checked', html)

        status, path, html, _ = self.post_question(f"/admin/questions/{first.id}/edit", {
            "type": "multiple", "subject": "math", "topic": "05", "text": "Обновлённый вопрос про корни",
            "opt_A": "верно", "opt_B": "тоже верно", "opt_C": "нет",
            "correct": ["A", "B"], "explanation": "Новое объяснение.",
        })
        self.assertEqual(path, "/admin/questions?subject=math&msg=q_updated")
        updated = database.get_question(first.id)
        assert updated is not None
        self.assertEqual((updated.qtype, updated.correct), ("multiple", ["A", "B"]))
        self.assertEqual(updated.explanation, "Новое объяснение.")

        other = next(q for q in database.list_questions("math") if q.id != first.id)
        status, _, html, _ = self.post_question(f"/admin/questions/{other.id}/edit", {
            "type": "single", "subject": "math", "topic": "05", "text": "Обновлённый вопрос про корни",
            "opt_A": "1", "opt_B": "2", "correct": "A", "explanation": "x",
        })
        self.assertEqual(status, 400)
        self.assertIn("уже есть вопрос с таким текстом", html)

        _, _, html, _ = self.admin.get("/admin/questions?" + urlencode({"q": "КОРНИ"}))
        self.assertIn("Найдено: 1", html)
        _, _, html, _ = self.admin.get("/admin/questions?subject=physics")
        self.assertIn("Найдено: 1", html)
        self.assertIn("physics single №0", html)
        _, _, html, _ = self.admin.get("/admin/questions?" + urlencode({"subject": "physics", "q": "корни"}))
        self.assertIn("Ничего не найдено", html)

        self.post_question("/admin/questions/new", {
            "type": "single", "subject": "math", "topic": "05", "text": "<script>alert(1)</script>",
            "opt_A": "1", "opt_B": "2", "correct": "A", "explanation": "x",
        })
        _, _, html, _ = self.admin.get("/admin/questions")
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_seed_keeps_admin_edits(self) -> None:
        """Вопрос, изменённый или созданный в админке, seed.py больше не перезаписывает."""
        original = {"type": "single", "text": "Сколько будет 2 + 2?", "options": ["4", "5"],
                    "correct": ["A"], "explanation": "Из файла."}
        other = {**original, "text": "Сколько будет 3 + 3?", "options": ["6", "7"]}
        database.upsert_questions("math", [original, other])
        edited = next(q for q in database.list_questions("math") if q.text == original["text"])
        status, _, _, _ = self.post_question(f"/admin/questions/{edited.id}/edit", {
            "type": "single", "subject": "math", "topic": "05", "text": original["text"],
            "opt_A": "4", "opt_B": "22", "correct": "A", "explanation": "Правка админа.",
        })
        self.assertEqual(status, 200)
        self.post_question("/admin/questions/new", {
            "type": "single", "subject": "math", "topic": "05", "text": "Новый вопрос админа",
            "opt_A": "1", "opt_B": "2", "correct": "B", "explanation": "Своё.",
        })

        database.upsert_questions("math", [
            {**original, "explanation": "Новая версия файла."},
            {**other, "explanation": "Новая версия файла."},
            {**original, "text": "Новый вопрос админа", "explanation": "Из файла."},
        ])
        by_text = {q.text: q for q in database.list_questions("math")}
        self.assertEqual(by_text[original["text"]].explanation, "Правка админа.")
        self.assertEqual(by_text[original["text"]].options, ["4", "22"])
        self.assertEqual(by_text["Новый вопрос админа"].explanation, "Своё.")
        self.assertEqual(by_text[other["text"]].explanation, "Новая версия файла.")

    def test_delete_unused_and_used(self) -> None:
        """Неиспользованный вопрос удаляется, использованный — скрывается, разбор цел."""
        self.add_questions("chemistry", config.SINGLE, 2)
        unused, used = database.list_questions("chemistry")
        attempt_id = database.create_attempt(1, "practice", ["chemistry"], 0.0, None, 1, [],
                                             [(used.id, "chemistry", [0, 1, 2, 3])])
        attempt = database.get_attempt(attempt_id, 1)
        assert attempt is not None
        ent_logic.finish_attempt(attempt)

        status, _, html, _ = self.admin.get(f"/admin/questions/{unused.id}/delete")
        self.assertIn("будет удалён полностью", html)
        status, path, html, _ = self.admin.post(
            f"/admin/questions/{unused.id}/delete", {"csrf_token": self.csrf(html)}
        )
        self.assertIn("msg=q_deleted", path)
        with database.connect() as connection:
            self.assertIsNone(connection.execute(
                "SELECT id FROM questions WHERE id = ?", (unused.id,)).fetchone())

        _, _, html, _ = self.admin.get(f"/admin/questions/{used.id}/delete")
        self.assertIn("разбор старых попыток сохранится", html)
        _, path, html, _ = self.admin.post(
            f"/admin/questions/{used.id}/delete", {"csrf_token": self.csrf(html)}
        )
        self.assertIn("msg=q_archived", path)
        self.assertEqual(database.list_questions("chemistry"), [])
        self.assertEqual(database.question_counts(), {})
        with self.assertRaises(ent_logic.TestBuildError):
            ent_logic.build_practice(1, "chemistry")
        self.assertEqual(len(database.get_attempt_questions(attempt_id)), 1)
        status, _, html, _ = self.admin.get(f"/admin/users/1/attempts/{attempt_id}")
        self.assertEqual(status, 200)
        self.assertIn(used.text, html)
        _, path, _, _ = self.admin.get(f"/admin/questions/{used.id}/edit")
        self.assertIn("msg=q_missing", path)


    def test_dashboard_and_users(self) -> None:
        """Статистика, нехватка по норме ЕНТ, список пользователей и их попытки."""
        self.add_questions("kz_history", config.SINGLE, 20)
        self.add_questions("math", config.SINGLE, 3)
        attempt_id = ent_logic.build_practice(2, "math")
        questions = database.get_attempt_questions(attempt_id)
        database.save_answers(attempt_id, {aq.id: aq.correct for aq in questions})
        attempt = database.get_attempt(attempt_id, 2)
        assert attempt is not None
        ent_logic.finish_attempt(attempt)

        _, _, html, _ = self.admin.get("/admin")
        self.assertIn("Пользователи", html)
        self.assertIn("администраторов: 1", html)
        self.assertIn("тренировок: 1", html)
        self.assertIn("100 <span>%</span>", html)
        history_row = html.split("История Казахстана", 1)[1].split("</tr>", 1)[0]
        self.assertIn("норма ЕНТ", history_row)
        math_row = html.split("Математика</a>", 1)[1].split("</tr>", 1)[0]
        self.assertIn("меньше нормы", math_row)
        self.assertIn("не хватает 37", math_row)

        _, _, html, _ = self.admin.get("/admin/users")
        self.assertIn("student@mail.kz", html)
        self.assertIn("⚙️ админ", html)

        test_pages.PagesTests().register_and_login(
            Browser(self.base_url), "phone@mail.kz", name="Телефон", phone="8 705 967 84 20")
        _, _, html, _ = self.admin.get("/admin/users?" + urlencode({"q": "STUDENT"}))
        self.assertIn("Пользователи: 1", html)
        self.assertIn("student@mail.kz", html)
        _, _, html, _ = self.admin.get("/admin/users?" + urlencode({"q": "+7 (705) 967-84-20"}))
        self.assertIn("Пользователи: 1", html)
        self.assertIn("phone@mail.kz", html)
        self.assertIn("+77059678420", html)
        status, _, html, _ = self.admin.get("/admin/users/2")
        self.assertEqual(status, 200)
        self.assertIn("Ученик", html)
        self.assertIn("Тренировка", html)
        self.assertIn(f"/admin/users/2/attempts/{attempt_id}", html)

        status, _, html, _ = self.admin.get(f"/admin/users/2/attempts/{attempt_id}")
        self.assertEqual(status, 200)
        self.assertIn("Итоговый балл", html)
        self.assertIn("К пользователю Ученик", html)
        self.assertEqual(self.admin.get(f"/admin/users/1/attempts/{attempt_id}")[0], 404)
        self.assertEqual(self.admin.get("/admin/users/999")[0], 404)
        self.assertIsNotNone(re.search(r"Пользователи: 3", self.admin.get("/admin/users")[2]))
