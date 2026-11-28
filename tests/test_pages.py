"""Тесты страниц на живом сервере: полный путь пользователя через urllib."""

import http.cookiejar
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

from html import escape as html_escape

from app import config
import seed
from app.core import database, ent_logic
from app.web.server import create_server
from tests.base import DatabaseTestCase, FakeMailer

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Обработчик, который не следует за перенаправлениями (чтобы их проверить)."""

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        """Отключает автоматический переход по Location."""
        return None


class Browser:
    """Мини-«браузер» на urllib: хранит cookie, умеет GET и POST форм."""

    def __init__(self, base_url: str, follow_redirects: bool = True) -> None:
        """Создаёт клиента с собственным хранилищем cookie."""
        self.base_url = base_url
        self.cookies = http.cookiejar.CookieJar()
        handlers: list[urllib.request.BaseHandler] = [
            urllib.request.HTTPCookieProcessor(self.cookies)
        ]
        if not follow_redirects:
            handlers.append(NoRedirect())
        self.opener = urllib.request.build_opener(*handlers)

    def request(self, path: str, data: dict | list | None = None) -> tuple[int, str, str, dict]:
        """Выполняет запрос. Возвращает (статус, итоговый путь, HTML, заголовки)."""
        body = urllib.parse.urlencode(data, doseq=True).encode() if data is not None else None
        try:
            with self.opener.open(self.base_url + path, data=body, timeout=10) as response:
                final_path = response.geturl().removeprefix(self.base_url)
                html = response.read().decode("utf-8")
                return response.status, final_path, html, dict(response.headers)
        except urllib.error.HTTPError as error:
            with error:
                return error.code, path, error.read().decode("utf-8"), dict(error.headers)

    def get(self, path: str) -> tuple[int, str, str, dict]:
        """GET-запрос."""
        return self.request(path)

    def post(self, path: str, data: dict | list) -> tuple[int, str, str, dict]:
        """POST-запрос с данными формы."""
        return self.request(path, data)


class PagesTests(DatabaseTestCase):
    """Основные страницы и сценарии на работающем сервере."""

    def setUp(self) -> None:
        """Загружает банк вопросов и запускает сервер на свободном порту."""
        super().setUp()
        _, errors = seed.seed(with_generated=False)
        self.assertEqual(errors, [])
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


    def register_and_login(
        self, browser: Browser, email: str, name: str = "Айгерим", phone: str = ""
    ) -> None:
        """Регистрирует пользователя через форму и входит, введя код из письма."""
        status, path, html, _ = browser.post("/register", {
            "first_name": name, "last_name": "Тестова", "email": email, "phone": phone,
            "password": "password123", "password2": "password123",
        })
        self.assertEqual(status, 200, html)
        self.assertTrue(path.startswith("/verify?"), path)
        mail = FakeMailer.active
        assert mail is not None
        status, path, html, _ = browser.post(
            "/verify", {"email": email, "code": mail.last_code(email)}
        )
        self.assertEqual((status, path), (200, "/dashboard?msg=verified"))
        self.assertIn("Личный кабинет", html)

    @staticmethod
    def csrf(html: str) -> str:
        """Достаёт csrf-токен из HTML страницы."""
        match = CSRF_RE.search(html)
        assert match is not None, "csrf-токен не найден"
        return match.group(1)

    @staticmethod
    def correct_form(attempt_id: int, subject: str) -> dict[str, list[str]]:
        """Форма раздела, заполненная правильными ответами из базы."""
        form: dict[str, list[str]] = {}
        for aq in database.get_attempt_questions(attempt_id):
            if aq.subject != subject:
                continue
            if aq.qtype == config.MATCHING:
                for index, letter in enumerate(aq.correct):
                    form[f"q{aq.id}_{index}"] = [letter]
            else:
                form[f"q{aq.id}"] = list(aq.correct)
        return form

    @staticmethod
    def answer_form(aq: database.AttemptQuestion, right: bool) -> dict[str, list[str]]:
        """Форма ответа на одно задание: правильный или заведомо неверный ответ."""
        letters = config.OPTION_LETTERS[: len(aq.options)]
        if aq.qtype == config.MATCHING:
            return {
                f"q{aq.id}_{index}": [letter if right else next(x for x in letters if x != letter)]
                for index, letter in enumerate(aq.correct)
            }
        if right:
            return {f"q{aq.id}": list(aq.correct)}
        return {f"q{aq.id}": [next(x for x in letters if x not in aq.correct)]}


    def test_public_pages_static_and_404(self) -> None:
        """Главная, регистрация, вход, CSS и 404 работают без входа; скриптов на страницах нет."""
        browser = Browser(self.base_url)
        status, _, html, headers = browser.get("/")
        self.assertEqual(status, 200)
        self.assertIn("Попробовать бесплатно", html)
        self.assertIn("Как устроен ЕНТ", html)
        self.assertIn("Что такое профильная пара?", html)
        self.assertIn("Математика</span><b>+</b>", html)
        self.assertNotIn(' style="', html)
        self.assertNotIn("<script", html.lower())
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])

        status, _, html, _ = browser.get("/register")
        self.assertEqual(status, 200)
        self.assertIn("Войти через Google", html)

        self.assertEqual(browser.get("/login")[0], 200)
        status, _, css, headers = browser.get("/static/style.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", headers["Content-Type"])
        self.assertIn("--accent", css)
        self.assertIn("prefers-color-scheme: dark", css)

        self.assertEqual(browser.get("/static/../config.py")[0], 404)
        self.assertEqual(browser.get("/static/%2e%2e/config.py")[0], 404)
        status, _, html, _ = browser.get("/no-such-page")
        self.assertEqual(status, 404)
        self.assertIn("Страница не найдена", html)
        self.assertEqual(browser.get("/attempt/abc/math")[0], 404)

    def test_private_pages_redirect_to_login(self) -> None:
        """Закрытые страницы без входа перенаправляют на /login с параметром next."""
        browser = Browser(self.base_url, follow_redirects=False)
        private = ("/dashboard", "/mock", "/practice", "/history", "/result/1", "/attempt/1/math")
        for path in private:
            status, _, _, headers = browser.get(path)
            self.assertEqual(status, 303, path)
            location = headers["Location"]
            self.assertTrue(location.startswith("/login?"), location)
            self.assertIn(urllib.parse.quote(path, safe=""), location)

    def test_registration_errors_are_shown(self) -> None:
        """Ошибки формы регистрации показываются на странице, введённые данные сохраняются."""
        browser = Browser(self.base_url)
        status, _, html, _ = browser.post("/register", {
            "first_name": "Али", "last_name": "", "email": "ali@mail", "phone": "8701",
            "password": "123", "password2": "456",
        })
        self.assertEqual(status, 400)
        self.assertIn("Введите фамилию", html)
        self.assertIn("Почта указана неверно", html)
        self.assertIn("должно быть 10 цифр", html)
        self.assertIn("не короче 8", html)
        self.assertIn('value="Али"', html)
        self.assertIn('value="8701"', html)
        self.assertEqual(self.mail.messages, [])

        status, _, html, _ = browser.post("/login", {"login": "x@y.kz", "password": "wrong-pass"})
        self.assertEqual(status, 400)
        self.assertIn("Неверная почта/телефон или пароль", html)

    def test_full_user_journey(self) -> None:
        """Регистрация → вход → пробный ЕНТ → переходы → завершение → результат → история."""
        browser = Browser(self.base_url)
        self.register_and_login(browser, "daniyar@mail.kz", name="Данияр", phone="8 701 123 45 67")

        status, _, html, _ = browser.get("/mock")
        self.assertEqual(status, 200)
        self.assertIn("Математика + Физика", html)
        self.assertIn("тест будет собран из имеющихся", html)
        self.assertIn("<b>66</b> заданий", html)
        self.assertIn("2 ч 12 мин", html)
        self.assertIn("Как считается время", html)

        status, path, html, _ = browser.post(
            "/mock/start", {"pair": "0", "csrf_token": self.csrf(html)}
        )
        self.assertEqual(status, 200)
        match = re.fullmatch(r"/attempt/(\d+)/kz_history", path)
        self.assertIsNotNone(match, path)
        attempt_id = int(match.group(1))
        self.assertIn("Осталось времени", html)
        self.assertIn("Банк вопросов неполный", html)
        self.assertNotIn("Почему так", html)
        self.assertNotIn("ro-correct", html)
        attempt = database.get_attempt(attempt_id, 1)
        assert attempt is not None
        self.assertAlmostEqual(attempt.deadline - attempt.started_at, 132 * 60)

        form = self.correct_form(attempt_id, "kz_history")
        form.update({"csrf_token": [self.csrf(html)], "section": ["kz_history"], "goto": ["math"]})
        status, path, html, _ = browser.post(f"/attempt/{attempt_id}/kz_history", form)
        self.assertEqual((status, path), (200, f"/attempt/{attempt_id}/math"))
        self.assertIn("16/16", html)

        form = self.correct_form(attempt_id, "math")
        form.update({"csrf_token": [self.csrf(html)], "section": ["math"], "finish": ["1"]})
        status, path, html, _ = browser.post(f"/attempt/{attempt_id}/math", form)
        self.assertEqual((status, path), (200, f"/attempt/{attempt_id}/finish"))
        self.assertIn("Завершить тест?", html)
        self.assertIn("Без ответа осталось заданий", html)

        status, _, section_html, _ = browser.get(f"/attempt/{attempt_id}/math")
        self.assertEqual(status, 200)
        self.assertIn("checked", section_html)
        self.assertIn("selected", section_html)

        status, path, html, _ = browser.post(
            f"/attempt/{attempt_id}/finish", {"csrf_token": self.csrf(html)}
        )
        self.assertEqual((status, path), (200, f"/result/{attempt_id}"))
        self.assertIn("Итоговый балл", html)
        self.assertIn("Разбор ответов", html)
        self.assertIn("✓ ваш ответ — верно", html)
        self.assertIn("Почему так", html)
        self.assertIn("Вы не ответили на это задание", html)
        self.assertIn('id="only-mistakes"', html)
        score_re = r"<span>{}</span><span class=\"subject-score\"><strong>{}</strong> из {}"
        self.assertRegex(html, score_re.format("История Казахстана", 16, 16))
        self.assertRegex(html, score_re.format("Математика", 19, 19))
        self.assertIn("Официальный максимум ЕНТ — 140 баллов", html)

        status, path, _, _ = browser.get(f"/attempt/{attempt_id}/math")
        self.assertEqual(path, f"/result/{attempt_id}")

        status, _, html, _ = browser.get("/history")
        self.assertEqual(status, 200)
        self.assertIn("Пробный ЕНТ", html)
        self.assertIn("Математика + Физика", html)
        self.assertIn("<strong>35</strong> /", html)

        status, _, html, _ = browser.get("/dashboard")
        self.assertIn("Лучший балл", html)
        self.assertIn("35 <span>из 140</span>", html)
        self.assertIn("пробных: 1 · тренировок: 0", html)
        self.assertIn("До максимума осталось 105 баллов", html)
        strong = html.split("Сильные предметы", 1)[1].split("Что подтянуть", 1)[0]
        self.assertIn("История Казахстана", strong)
        self.assertIn("<b>100%</b>", strong)
        self.assertIn("Последние попытки", html)

        status, path, html, _ = browser.post("/logout", {"csrf_token": self.csrf(html)})
        self.assertEqual(path, "/?msg=logged_out")
        self.assertIn("Вы вышли из аккаунта", html)
        status, path, _, _ = browser.get("/dashboard")
        self.assertTrue(path.startswith("/login"), path)

    def test_practice_one_question_at_a_time(self) -> None:
        """Тренировка: вопрос → проверка с подсветкой и объяснением → следующий → итог."""
        browser = Browser(self.base_url)
        self.register_and_login(browser, "practice@mail.kz")
        status, _, html, _ = browser.get("/practice")
        self.assertEqual(status, 200)
        self.assertIn("Химия", html)
        status, path, html, _ = browser.post(
            "/practice/start", {"subject": "chemistry", "csrf_token": self.csrf(html)}
        )
        match = re.fullmatch(r"/practice/(\d+)", path)
        self.assertIsNotNone(match, path)
        attempt_id = int(match.group(1))
        self.assertEqual(html.count('class="card question"'), 1)
        self.assertIn("Вопрос <b>1</b> из 10", html)
        self.assertIn("Проверить ответ", html)
        self.assertNotIn("Почему так", html)
        questions = database.get_attempt_questions(attempt_id)
        self.assertEqual(len(questions), config.PRACTICE_QUESTION_COUNT)

        form = self.answer_form(questions[0], right=True)
        form.update({"csrf_token": [self.csrf(html)], "question": [str(questions[0].id)]})
        status, path, html, _ = browser.post(f"/practice/{attempt_id}", form)
        self.assertEqual(path, f"/practice/{attempt_id}/review/1")
        self.assertIn("Верно!", html)
        self.assertIn("Почему так", html)
        self.assertIn(html_escape(questions[0].explanation), html)
        self.assertIn("Следующий вопрос", html)

        bad = self.answer_form(questions[0], right=False)
        bad.update({"csrf_token": [self.csrf(html)], "question": [str(questions[0].id)]})
        browser.post(f"/practice/{attempt_id}", bad)
        self.assertEqual(
            database.get_attempt_questions(attempt_id)[0].points,
            ent_logic.question_max_points(questions[0].qtype),
        )

        status, path, html, _ = browser.get(f"/practice/{attempt_id}")
        self.assertIn("Вопрос <b>2</b> из 10", html)
        self.assertIn("step-ok", html)
        form = self.answer_form(questions[1], right=False)
        form.update({"csrf_token": [self.csrf(html)], "question": [str(questions[1].id)]})
        status, path, html, _ = browser.post(f"/practice/{attempt_id}", form)
        self.assertEqual(path, f"/practice/{attempt_id}/review/2")
        self.assertIn("Неверно", html)
        self.assertRegex(html, r"ro-wrong|mr-wrong")
        self.assertRegex(html, r"ro-correct|mr-right")

        for number in range(3, config.PRACTICE_QUESTION_COUNT + 1):
            status, path, html, _ = browser.get(f"/practice/{attempt_id}")
            self.assertIn(f"Вопрос <b>{number}</b>", html)
            aq = questions[number - 1]
            status, path, html, _ = browser.post(f"/practice/{attempt_id}", {
                "csrf_token": self.csrf(html), "question": str(aq.id), "skip": "1",
            })
            self.assertEqual(path, f"/practice/{attempt_id}/review/{number}")
            self.assertIn("Без ответа", html)
        self.assertIn("Посмотреть итог", html)
        self.assertNotIn("Следующий вопрос", html)

        _, path, _, _ = browser.get(f"/attempt/{attempt_id}/chemistry")
        self.assertTrue(path.startswith(f"/practice/{attempt_id}"), path)

        status, path, html, _ = browser.post(
            f"/attempt/{attempt_id}/finish", {"csrf_token": self.csrf(html)}
        )
        self.assertEqual(path, f"/result/{attempt_id}")
        attempt = database.get_attempt(attempt_id, 1)
        assert attempt is not None
        self.assertEqual(attempt.score, ent_logic.question_max_points(questions[0].qtype))
        self.assertIn("Итоговый балл", html)
        self.assertIn("Почему так", html)
        self.assertIn("Ещё 10 вопросов", html)

        _, path, _, _ = browser.get(f"/practice/{attempt_id}")
        self.assertEqual(path, f"/result/{attempt_id}")

    def test_expired_test_finishes_on_next_request(self) -> None:
        """Если время вышло, следующий запрос завершает тест и показывает результат."""
        browser = Browser(self.base_url)
        self.register_and_login(browser, "late@mail.kz")
        _, _, html, _ = browser.get("/mock")
        _, path, html, _ = browser.post(
            "/mock/start", {"pair": "3", "csrf_token": self.csrf(html)}
        )
        attempt_id = int(path.split("/")[2])

        with database.connect() as connection:
            connection.execute("UPDATE attempts SET deadline = 1 WHERE id = ?", (attempt_id,))

        form = {"csrf_token": self.csrf(html), "section": "kz_history", "goto": "math_literacy"}
        status, path, html, _ = browser.post(f"/attempt/{attempt_id}/kz_history", form)
        self.assertEqual(path, f"/result/{attempt_id}?msg=time_up")
        self.assertIn("Время вышло", html)

    def test_security_checks(self) -> None:
        """XSS экранируется, без csrf-токена POST отклоняется, чужую попытку не видно."""
        alice = Browser(self.base_url)
        self.register_and_login(alice, "alice@mail.kz", name="<script>alert(1)</script>")
        status, _, html, _ = alice.get("/dashboard")
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

        status, _, html, _ = alice.post("/mock/start", {"pair": "0"})
        self.assertEqual(status, 403)
        self.assertIn("Форма устарела", html)

        _, _, html, _ = alice.get("/mock")
        _, path, _, _ = alice.post("/mock/start", {"pair": "0", "csrf_token": self.csrf(html)})
        attempt_id = int(path.split("/")[2])

        bob = Browser(self.base_url)
        self.register_and_login(bob, "bob@mail.kz", name="Bob")
        self.assertEqual(bob.get(f"/attempt/{attempt_id}/kz_history")[0], 404)
        self.assertEqual(bob.get(f"/result/{attempt_id}")[0], 404)

        _, _, html, _ = alice.get("/mock")
        self.assertIn("Незавершённый пробный ЕНТ", html)
        _, path, _, _ = alice.post("/mock/start", {"pair": "5", "csrf_token": self.csrf(html)})
        self.assertEqual(path, f"/attempt/{attempt_id}/kz_history?msg=resume")

        evil = Browser(self.base_url, follow_redirects=False)
        status, _, _, headers = evil.post(
            "/login", {"login": "bob@mail.kz", "password": "password123", "next": "//evil.example"}
        )
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "/dashboard")
