"""Этап 15: CSRF всех форм, лимит входа, граничные случаи и чужие данные."""

import re
import threading
import time

import seed
from app import config
from app.core import auth, database
from app.web import router
from app.web.server import create_server
from tests.base import DatabaseTestCase
from tests import test_pages
from tests.test_pages import Browser

GUEST_FORMS = ("/login", "/register", "/verify", "/verify/resend", "/forgot", "/reset", "/tg/login")


class ServerCase(DatabaseTestCase):
    """Сервер на свободном порту и помощники для входа; seed_bank — загрузить банк вопросов."""

    seed_bank = True
    csrf = staticmethod(test_pages.PagesTests.csrf)
    correct_form = staticmethod(test_pages.PagesTests.correct_form)
    answer_form = staticmethod(test_pages.PagesTests.answer_form)

    def setUp(self) -> None:
        """Загружает банк вопросов и запускает сервер на свободном порту."""
        super().setUp()
        if self.seed_bank:
            seed.seed(with_generated=False)
        self.server = create_server("127.0.0.1", 0)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        """Останавливает сервер."""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def register_and_login(self, browser: Browser, email: str) -> None:
        """Регистрация через форму и вход по коду из письма."""
        test_pages.PagesTests().register_and_login(browser, email)

    def student(self, email: str = "student@mail.kz") -> Browser:
        """Зарегистрированный и вошедший ученик."""
        browser = Browser(self.base_url)
        self.register_and_login(browser, email)
        return browser

    @staticmethod
    def user_id(browser: Browser) -> int:
        """Id пользователя по его cookie сессии."""
        key = auth._token_hash(browser.cookie(config.SESSION_COOKIE_NAME))
        found = database.get_session_user(key, time.time())
        assert found is not None
        return found[0].id


class AuditTests(ServerCase):
    """Проверки безопасности и устойчивости на работающем сервере."""

    def test_guest_forms_require_csrf(self) -> None:
        """Формы гостя без токена отклоняются, токен выдаётся в HttpOnly-cookie и в форме."""
        browser = Browser(self.base_url)
        for path in GUEST_FORMS:
            status, _, html, _ = browser.request(path, {"login": "a@b.kz", "email": "a@b.kz", "password": "x"})
            self.assertEqual(status, 403, path)
            self.assertIn("Форма устарела", html)
        self.assertIsNone(database.get_user_credentials("a@b.kz"))

        _, _, html, headers = Browser(self.base_url).get("/login")
        cookie = headers["Set-Cookie"]
        self.assertIn("ent_csrf=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        token = re.search(r"ent_csrf=([\w-]+)", cookie).group(1)
        self.assertEqual(self.csrf(html), token)

    def test_login_is_locked_after_many_failures(self) -> None:
        """После LOGIN_MAX_FAILURES неудач вход закрыт даже с верным паролем, затем снова открыт."""
        self.student()
        browser = Browser(self.base_url)
        for _ in range(config.LOGIN_MAX_FAILURES):
            status, _, _, _ = browser.post("/login", {"login": "student@mail.kz", "password": "wrong-pass"})
            self.assertEqual(status, 400)
        status, _, html, _ = browser.post("/login", {"login": " Student@Mail.kz ", "password": "password123"})
        self.assertEqual(status, 429)
        self.assertIn("Слишком много неудачных попыток входа", html)

        with database.connect() as connection:
            connection.execute("UPDATE login_failures SET failed_at = failed_at - ?",
                               (config.LOGIN_LOCK_SECONDS + 1,))
        status, path, _, _ = browser.post("/login", {"login": "student@mail.kz", "password": "password123"})
        self.assertEqual((status, path), (200, "/dashboard"))
        self.assertEqual(database.login_failures_since(auth.normalize_login("student@mail.kz"), 0), [])

    def test_every_post_route_checks_csrf(self) -> None:
        """Каждый POST-маршрут вошедшего пользователя без токена отвечает 403 и ничего не меняет."""
        admin = self.student("admin@mail.kz")
        database.set_user_role("admin@mail.kz", database.ROLE_ADMIN)
        for method, pattern, _ in router.ROUTES:
            if method != "POST":
                continue
            path = re.sub(r"<int:\w+>", "1", re.sub(r"<(?!int:)\w+>", "math", pattern))
            status, _, _, _ = admin.request(path, {"x": "1"})
            self.assertEqual(status, 403, path)

    def test_hostile_and_long_input(self) -> None:
        """Очень длинные строки и разметка в полях не ломают страницы и экранируются."""
        browser = Browser(self.base_url)
        status, _, html, _ = browser.post("/register", {
            "first_name": "Я" * 5000, "last_name": "Т" * 5000, "email": "long@mail.kz",
            "password": "password123", "password2": "password123",
        })
        self.assertEqual(status, 400)
        self.assertIsNone(database.get_user_credentials("long@mail.kz"))

        student = self.student()
        _, _, html, _ = student.get("/profile")
        status, _, html, _ = student.post("/profile/school", {
            "csrf_token": self.csrf(html), "city": '"><img src=x>', "school": "<b>12</b>" + "№" * 3000,
        })
        self.assertLess(status, 500)
        self.assertNotIn("<img src=x>", html)
        self.assertNotIn("<b>12</b>", student.get("/profile")[2])

        for path in ("/result/99999999999999999999", "/practice/-1", "/attempt/1/%00",
                     "/teacher/99999999999999999999", "/notifications/18446744073709551616"):
            self.assertIn(student.get(path)[0], (403, 404), path)

    def test_answers_after_deadline_are_ignored(self) -> None:
        """Ответы, присланные после окончания времени, не сохраняются и не дают баллов."""
        browser = self.student()
        _, _, html, _ = browser.get("/mock")
        _, path, html, _ = browser.post("/mock/start", {"pair": "0", "csrf_token": self.csrf(html)})
        attempt_id = int(path.split("/")[2])
        with database.connect() as connection:
            connection.execute("UPDATE attempts SET deadline = ? WHERE id = ?", (time.time() - 1, attempt_id))
        form = self.correct_form(attempt_id, "kz_history")
        form.update({"csrf_token": [self.csrf(html)], "section": ["kz_history"], "finish": ["1"]})
        _, path, _, _ = browser.post(f"/attempt/{attempt_id}/kz_history", form)
        self.assertEqual(path, f"/result/{attempt_id}?msg=time_up")
        questions = database.get_attempt_questions(attempt_id)
        self.assertTrue(all(aq.answer is None for aq in questions))
        self.assertEqual(database.get_attempt(attempt_id, self.user_id(browser)).score, 0)

    def test_repeated_submissions(self) -> None:
        """Повторная отправка ответа и двойное завершение не меняют баллы и не дублируют попытки."""
        browser = self.student()
        _, _, html, _ = browser.get("/practice")
        csrf = self.csrf(html)
        _, path, _, _ = browser.post("/practice/start", {"subject": "kz_history", "csrf_token": csrf})
        attempt_id = int(path.split("/")[2])
        aq = database.get_attempt_questions(attempt_id)[0]
        answer = {"question": str(aq.id), "csrf_token": csrf, **self.answer_form(aq, True)}
        browser.post(f"/practice/{attempt_id}", answer)
        browser.post(f"/practice/{attempt_id}", {**answer, **self.answer_form(aq, False)})
        self.assertEqual(database.get_attempt_questions(attempt_id)[0].answer, list(aq.correct))

        for _ in range(2):
            _, path, _, _ = browser.post(f"/attempt/{attempt_id}/finish", {"csrf_token": csrf})
            self.assertTrue(path.startswith(f"/result/{attempt_id}"), path)
        user_id = self.user_id(browser)
        self.assertEqual(len(database.get_finished_attempts(user_id)), 1)
        self.assertEqual(database.get_attempt(attempt_id, user_id).score, 1)

    def test_access_rules_for_every_route(self) -> None:
        """Гость попадает на вход, ученик не открывает админку и кабинет учителя."""
        public = {"/", "/register", "/login", "/verify", "/forgot", "/reset", "/auth/google",
                  "/auth/google/callback", "/tg/login", "/lang/<code>", "/ad/<int:banner_id>",
                  "/ad/<int:banner_id>/image"}
        guest = Browser(self.base_url, follow_redirects=False)
        student = self.student()
        for method, pattern, _ in router.ROUTES:
            if method != "GET" or pattern in public:
                continue
            path = re.sub(r"<int:\w+>", "1", re.sub(r"<(?!int:)\w+>", "math", pattern))
            status, _, _, headers = guest.get(path)
            self.assertEqual(status, 303, path)
            self.assertTrue(headers["Location"].startswith("/login?next="), path)
            if pattern.startswith(("/admin", "/teacher/")):
                self.assertEqual(student.get(path)[0], 403, path)

    def test_double_click_starts_one_practice(self) -> None:
        """Повторное нажатие «Начать» открывает ту же тренировку, а не создаёт вторую."""
        browser = self.student()
        csrf = self.csrf(browser.get("/practice")[2])
        paths = [browser.post("/practice/start", {"subject": "math", "csrf_token": csrf})[1] for _ in range(2)]
        self.assertEqual(paths[0], paths[1])
        _, other, _, _ = browser.post("/practice/start", {"subject": "physics", "csrf_token": csrf})
        self.assertNotEqual(other, paths[0])

    def test_other_users_data_is_hidden(self) -> None:
        """Ученик не видит чужую тренировку, разбор и уведомления."""
        alice = self.student("alice@mail.kz")
        _, _, html, _ = alice.get("/practice")
        _, path, _, _ = alice.post("/practice/start", {"subject": "kz_history", "csrf_token": self.csrf(html)})
        attempt_id = int(path.split("/")[2])
        bob = self.student("bob@mail.kz")
        for url in (f"/practice/{attempt_id}", f"/practice/{attempt_id}/review/1",
                    f"/attempt/{attempt_id}/finish", f"/result/{attempt_id}"):
            self.assertEqual(bob.get(url)[0], 404, url)
        _, _, html, _ = bob.get("/profile")
        status, _, _, _ = bob.post(f"/practice/{attempt_id}", {"csrf_token": self.csrf(html), "question": "1"})
        self.assertEqual(status, 404)
        self.assertEqual(bob.get("/admin")[0], 403)
        self.assertEqual(bob.get("/teacher/1")[0], 403)


class EmptyBankTests(ServerCase):
    """Пустой банк вопросов: страницы и кнопки теста не падают, а объясняют, что вопросов нет."""

    seed_bank = False

    def test_empty_bank_pages(self) -> None:
        """Кабинет, выбор пары и предмета, старт теста и тренировки — без ошибок сервера."""
        browser = self.student()
        for path in ("/dashboard", "/mock", "/practice", "/history", "/profile", "/notifications"):
            self.assertEqual(browser.get(path)[0], 200, path)
        csrf = self.csrf(browser.get("/mock")[2])
        _, path, html, _ = browser.post("/mock/start", {"pair": "0", "csrf_token": csrf})
        self.assertEqual(path, "/mock?msg=no_questions")
        _, path, _, _ = browser.post("/practice/start", {"subject": "math", "csrf_token": csrf})
        self.assertEqual(path, "/practice?msg=no_questions")
