"""Тесты страниц на живом сервере: полный путь пользователя через urllib.

Сервер запускается в отдельном потоке на свободном порту с временной базой,
в которую загружен настоящий банк вопросов из data/questions.
"""

import http.cookiejar
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

import config
import seed
from app import database
from app.server import create_server
from tests.base import DatabaseTestCase

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
        _, errors = seed.seed()
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

    # ── помощники ────────────────────────────────────────────────────────────

    def register_and_login(self, browser: Browser, login: str, name: str = "Айгерим") -> None:
        """Регистрирует пользователя через форму и входит."""
        status, path, _, _ = browser.post("/register", {
            "name": name, "login": login, "password": "password123", "password2": "password123",
        })
        self.assertEqual(status, 200)
        self.assertTrue(path.startswith("/login?"), path)
        status, path, html, _ = browser.post("/login", {"login": login, "password": "password123"})
        self.assertEqual((status, path), (200, "/dashboard"))
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

    # ── тесты ────────────────────────────────────────────────────────────────

    def test_public_pages_static_and_404(self) -> None:
        """Главная, регистрация, вход, CSS и 404 работают без входа; скриптов на страницах нет."""
        browser = Browser(self.base_url)
        status, _, html, headers = browser.get("/")
        self.assertEqual(status, 200)
        self.assertIn("Попробовать бесплатно", html)
        self.assertNotIn("<script", html.lower())
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])

        status, _, html, _ = browser.get("/register")
        self.assertEqual(status, 200)
        self.assertIn("Войти через Google", html)
        self.assertRegex(html, r"<button[^>]*disabled>\s*<span class=\"google-mark\">")

        self.assertEqual(browser.get("/login")[0], 200)
        status, _, css, headers = browser.get("/static/style.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", headers["Content-Type"])
        self.assertIn("--color-primary", css)

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
            "name": "Али", "login": "8701", "password": "123", "password2": "456",
        })
        self.assertEqual(status, 400)
        self.assertIn("+7XXXXXXXXXX", html)
        self.assertIn("не короче 8", html)
        self.assertIn('value="Али"', html)

        status, _, html, _ = browser.post("/login", {"login": "x@y.kz", "password": "wrong-pass"})
        self.assertEqual(status, 400)
        self.assertIn("Неверная почта/телефон или пароль", html)

    def test_full_user_journey(self) -> None:
        """Регистрация → вход → пробный ЕНТ → переходы → завершение → результат → история."""
        browser = Browser(self.base_url)
        self.register_and_login(browser, "+77011234567", name="Данияр")

        # Выбор пары: честно показано, что банк неполный.
        status, _, html, _ = browser.get("/mock")
        self.assertEqual(status, 200)
        self.assertIn("Математика + Физика", html)
        self.assertIn("тест будет собран из имеющихся", html)

        status, path, html, _ = browser.post(
            "/mock/start", {"pair": "0", "csrf_token": self.csrf(html)}
        )
        self.assertEqual(status, 200)
        match = re.fullmatch(r"/attempt/(\d+)/kz_history", path)
        self.assertIsNotNone(match, path)
        attempt_id = int(match.group(1))
        self.assertIn("Осталось времени", html)
        self.assertIn("Банк вопросов неполный", html)

        # Отвечаем на историю правильно и переходим по вкладке — ответы сохраняются.
        form = self.correct_form(attempt_id, "kz_history")
        form.update({"csrf_token": [self.csrf(html)], "section": ["kz_history"], "goto": ["math"]})
        status, path, html, _ = browser.post(f"/attempt/{attempt_id}/kz_history", form)
        self.assertEqual((status, path), (200, f"/attempt/{attempt_id}/math"))
        self.assertIn("16/16", html)  # вкладка истории: отвечено 16 из 16

        # Отвечаем на математику и нажимаем «Завершить» — ответы раздела тоже сохраняются.
        form = self.correct_form(attempt_id, "math")
        form.update({"csrf_token": [self.csrf(html)], "section": ["math"], "finish": ["1"]})
        status, path, html, _ = browser.post(f"/attempt/{attempt_id}/math", form)
        self.assertEqual((status, path), (200, f"/attempt/{attempt_id}/finish"))
        self.assertIn("Завершить тест?", html)
        self.assertIn("Без ответа осталось заданий", html)

        # Возврат к разделу: ранее выбранные ответы отмечены.
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
        self.assertIn("Правильный ответ", html)
        # История Казахстана: 16 верных из 16; математика: 9 + 2 + 2·2 + 2·2 = 19.
        self.assertRegex(html, r"История Казахстана</td><td><strong>16</strong> из 16")
        self.assertRegex(html, r"Математика</td><td><strong>19</strong> из 19")
        self.assertIn("Официальный максимум ЕНТ — 140 баллов", html)

        # Завершённый тест нельзя изменить: раздел перенаправляет на результат.
        status, path, _, _ = browser.get(f"/attempt/{attempt_id}/math")
        self.assertEqual(path, f"/result/{attempt_id}")

        status, _, html, _ = browser.get("/history")
        self.assertEqual(status, 200)
        self.assertIn("Пробный ЕНТ", html)
        self.assertIn("Математика + Физика", html)
        self.assertIn("<strong>35</strong> /", html)

        status, _, html, _ = browser.get("/dashboard")
        self.assertIn("Лучший пробный ЕНТ", html)
        self.assertIn("35 <span>из", html)

        # Выход: после него кабинет снова закрыт.
        status, path, html, _ = browser.post("/logout", {"csrf_token": self.csrf(html)})
        self.assertEqual(path, "/?msg=logged_out")
        self.assertIn("Вы вышли из аккаунта", html)
        status, path, _, _ = browser.get("/dashboard")
        self.assertTrue(path.startswith("/login"), path)

    def test_practice_shows_result_immediately(self) -> None:
        """Тренировка: 10 заданий, «Проверить ответы» сразу ведёт к результату."""
        browser = Browser(self.base_url)
        self.register_and_login(browser, "practice@mail.kz")
        status, _, html, _ = browser.get("/practice")
        self.assertEqual(status, 200)
        status, path, html, _ = browser.post(
            "/practice/start", {"subject": "chemistry", "csrf_token": self.csrf(html)}
        )
        match = re.fullmatch(r"/attempt/(\d+)/chemistry", path)
        self.assertIsNotNone(match, path)
        attempt_id = int(match.group(1))
        self.assertEqual(html.count('class="card question"'), config.PRACTICE_QUESTION_COUNT)
        self.assertIn("без ограничения по времени", html)

        form = self.correct_form(attempt_id, "chemistry")
        form.update({"csrf_token": [self.csrf(html)], "section": ["chemistry"], "finish": ["1"]})
        status, path, html, _ = browser.post(f"/attempt/{attempt_id}/chemistry", form)
        self.assertEqual(path, f"/result/{attempt_id}")
        attempt = database.get_attempt(attempt_id, 1)
        assert attempt is not None
        self.assertEqual(attempt.score, attempt.max_score)
        self.assertIn("100%", html)

    def test_expired_test_finishes_on_next_request(self) -> None:
        """Если время вышло, следующий запрос завершает тест и показывает результат."""
        browser = Browser(self.base_url)
        self.register_and_login(browser, "late@mail.kz")
        _, _, html, _ = browser.get("/mock")
        _, path, html, _ = browser.post(
            "/mock/start", {"pair": "3", "csrf_token": self.csrf(html)}
        )
        attempt_id = int(path.split("/")[2])

        # «Перематываем время»: дедлайн попытки уже в прошлом.
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

        # Повторный «старт» при незавершённом тесте ведёт к уже начатому тесту.
        _, _, html, _ = alice.get("/mock")
        self.assertIn("Незавершённый пробный ЕНТ", html)
        _, path, _, _ = alice.post("/mock/start", {"pair": "5", "csrf_token": self.csrf(html)})
        self.assertEqual(path, f"/attempt/{attempt_id}/kz_history?msg=resume")

        # Открытое перенаправление после входа невозможно.
        evil = Browser(self.base_url, follow_redirects=False)
        status, _, _, headers = evil.post(
            "/login", {"login": "bob@mail.kz", "password": "password123", "next": "//evil.example"}
        )
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "/dashboard")
