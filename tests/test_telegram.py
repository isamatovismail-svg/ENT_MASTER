"""Тесты Telegram-бота и входа на сайт по одноразовой ссылке. Сеть не используется."""

import io
import json
import re
import sqlite3
import threading
import time
import urllib.error
from pathlib import Path
from urllib.parse import urlsplit

from app import config
from app.core import auth, database, ent_logic
from app.web.server import create_server
from app.telegram_bot import Bot, TelegramAPI, TelegramError, run_polling
from tests import test_pages
from tests.base import DatabaseTestCase
from tests.test_pages import Browser

TG_ID = 777000111


class FakeAPI:
    """Заглушка Bot API: записывает вызовы вместо отправки в Telegram."""

    def __init__(self) -> None:
        """Пустой журнал вызовов."""
        self.calls: list[tuple[str, dict]] = []

    def call(self, method: str, **params):
        """Записывает вызов и возвращает правдоподобный результат."""
        self.calls.append((method, params))
        return [] if method == "getUpdates" else True

    def sent(self) -> list[dict]:
        """Все отправленные сообщения."""
        return [params for method, params in self.calls if method == "sendMessage"]

    def last(self) -> dict:
        """Последнее отправленное сообщение."""
        return self.sent()[-1]

    def edits(self, method: str) -> list[dict]:
        """Вызовы редактирования сообщения данного типа."""
        return [params for name, params in self.calls if name == method]


def buttons(message: dict) -> list[dict]:
    """Все inline-кнопки сообщения одним списком."""
    rows = (message.get("reply_markup") or {}).get("inline_keyboard", [])
    return [button for row in rows for button in row]


def message_update(text: str, chat_type: str = "private") -> dict:
    """Обновление с текстовым сообщением от тестового пользователя."""
    return {"update_id": 1, "message": {
        "message_id": 1, "text": text,
        "chat": {"id": TG_ID, "type": chat_type},
        "from": {"id": TG_ID, "first_name": "Аружан", "last_name": "Т."},
    }}


def callback_update(data: str, telegram_id: int = TG_ID) -> dict:
    """Обновление с нажатием inline-кнопки."""
    return {"update_id": 2, "callback_query": {
        "id": "cb1", "data": data,
        "from": {"id": telegram_id, "first_name": "Аружан"},
        "message": {"message_id": 55, "chat": {"id": telegram_id, "type": "private"}},
    }}


class EnvTests(DatabaseTestCase):
    """Чтение файла .env."""

    def test_load_env(self) -> None:
        """Комментарии и пустые строки пропускаются, кавычки и export снимаются."""
        path = Path(self._tmp.name) / ".env"
        path.write_text(
            "# комментарий\n\nTELEGRAM_BOT_TOKEN='123:abc'\nexport SITE_URL=\"https://x.kz/\"\n"
            "BROKEN LINE\nEMPTY=\n", encoding="utf-8",
        )
        self.assertEqual(config.load_env(path), {
            "TELEGRAM_BOT_TOKEN": "123:abc", "SITE_URL": "https://x.kz/", "EMPTY": "",
        })
        self.assertEqual(config.load_env(Path(self._tmp.name) / "missing.env"), {})

    def test_env_is_gitignored(self) -> None:
        """Файл .env с токеном не попадает в git."""
        lines = (config.BASE_DIR / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".env", lines)


class ApiTests(DatabaseTestCase):
    """Клиент Bot API и цикл long polling."""

    def test_call_success_and_errors(self) -> None:
        """Успешный ответ → result; ok=false и HTTP-ошибка → TelegramError с кодом."""
        requests = []

        def opener(request, timeout):
            """Возвращает заранее заданный ответ вместо сети."""
            requests.append((request, timeout))
            body = json.loads(request.data)
            if body.get("fail"):
                raise urllib.error.HTTPError(
                    request.full_url, 400, "Bad Request", {},
                    io.BytesIO(b'{"ok": false, "error_code": 400, "description": "chat not found"}'),
                )
            return io.BytesIO(json.dumps({"ok": True, "result": {"echo": body}}).encode())

        api = TelegramAPI("TOKEN", opener=opener)
        self.assertEqual(api.call("sendMessage", chat_id=1, text="Привет"),
                         {"echo": {"chat_id": 1, "text": "Привет"}})
        request, timeout = requests[0]
        self.assertEqual(request.full_url, "https://api.telegram.org/botTOKEN/sendMessage")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        api.call("getUpdates", timeout=30)
        self.assertEqual(requests[-1][1], 45)  # long polling ждёт дольше обычного
        with self.assertRaises(TelegramError) as caught:
            api.call("sendMessage", fail=True)
        self.assertEqual((str(caught.exception), caught.exception.code), ("chat not found", 400))

    def test_polling_survives_errors(self) -> None:
        """Сетевая ошибка → пауза и повтор; offset растёт; 401 останавливает бота."""
        script = [urllib.error.URLError("нет сети"),
                  [message_update("/start") | {"update_id": 10}],
                  [{"update_id": 11, "edited_message": {}}],
                  TelegramError("Unauthorized", 401)]
        calls = []

        class ScriptedAPI(FakeAPI):
            def call(self, method, **params):
                calls.append((method, params))
                if method != "getUpdates":
                    return True
                step = script.pop(0)
                if isinstance(step, Exception):
                    raise step
                return step

        pauses = []
        with self.assertRaises(TelegramError):
            run_polling(ScriptedAPI(), sleep=pauses.append)
        polls = [params for method, params in calls if method == "getUpdates"]
        self.assertEqual(pauses, [1.0])
        self.assertNotIn("offset", polls[0])
        self.assertEqual(polls[2]["offset"], 11)
        self.assertEqual(polls[3]["offset"], 12)
        self.assertIn("sendMessage", [method for method, _ in calls])


class BotTests(DatabaseTestCase):
    """Обработчики бота на заглушке API и временной базе."""

    def setUp(self) -> None:
        """Банк из трёх вопросов разных типов и бот с заглушкой API."""
        super().setUp()
        self.add_questions("math", config.SINGLE, 1)
        self.add_questions("math", config.MULTIPLE, 1)
        self.add_questions("math", config.MATCHING, 1)
        self.api = FakeAPI()
        self.bot = Bot(self.api)

    def link(self) -> int:
        """Создаёт пользователя сайта, привязанного к тестовому Telegram."""
        return auth.create_telegram_user(TG_ID, "Аружан")

    def press(self, data: str) -> None:
        """Нажимает inline-кнопку."""
        self.bot.handle_update(callback_update(data))

    def callback_notice(self) -> str:
        """Текст последнего ответа на нажатие кнопки."""
        return self.api.edits("answerCallbackQuery")[-1].get("text", "")

    def test_start_menu_and_login_link(self) -> None:
        """/start — приветствие и три кнопки; «Войти» — одноразовая ссылка."""
        self.bot.handle_update(message_update("/start"))
        menu = self.api.last()
        self.assertEqual(menu["chat_id"], TG_ID)
        self.assertIn("Привет, Аружан", menu["text"])
        self.assertEqual([b["text"] for b in buttons(menu)],
                         ["🔐 Войти на сайт", "🎯 Тренировка", "📊 Мои результаты"])

        # В группах бот молчит.
        before = len(self.api.calls)
        self.bot.handle_update(message_update("/start", chat_type="group"))
        self.assertEqual(len(self.api.calls), before)

        self.press("login")
        text = self.api.last()["text"]
        match = re.search(r"(http\S+/tg/login\?token=(\S+))", text)
        self.assertIsNotNone(match, text)
        self.assertIsNotNone(auth.peek_telegram_token(match.group(2)))
        # localhost Telegram в кнопках не принимает — ссылка только в тексте.
        self.assertEqual(buttons(self.api.last()), [])
        self.assertEqual(self.api.last()["link_preview_options"], {"is_disabled": True})

        original = config.SITE_URL
        config.SITE_URL = "https://ent-master.example.kz"
        try:
            self.press("login")
        finally:
            config.SITE_URL = original
        self.assertTrue(buttons(self.api.last())[0]["url"].startswith(
            "https://ent-master.example.kz/tg/login?token="))
        self.assertEqual(self.api.edits("answerCallbackQuery")[-1]["callback_query_id"], "cb1")

    def test_training_requires_link(self) -> None:
        """Без привязки тренировка и результаты просят войти."""
        for data in ("train", "results", "subj:math", "next:1"):
            self.press(data)
            if data in ("train", "results"):
                self.assertIn("войдите на сайт", self.api.last()["text"])
        self.assertEqual(database.list_questions("math")[0].used, 0)

    def test_full_training(self) -> None:
        """Выбор предмета → вопросы всех типов → разбор с объяснением → итог → результаты."""
        user_id = self.link()
        self.press("train")
        subject_buttons = [b["callback_data"] for b in buttons(self.api.last())]
        self.assertIn("subj:math", subject_buttons)
        self.assertNotIn("subj:physics", subject_buttons)  # по физике вопросов нет

        self.press("subj:math")
        attempt = database.get_in_progress_attempt(user_id, ent_logic.PRACTICE)
        assert attempt is not None
        questions = database.get_attempt_questions(attempt.id)
        self.assertEqual(len(questions), 3)
        self.assertIn("вопрос 1 из 3", self.api.last()["text"])

        for number, aq in enumerate(questions, start=1):
            prefix = f"{attempt.id}:{aq.id}"
            if number > 1:
                self.press(f"next:{attempt.id}")
                self.assertIn(f"вопрос {number} из 3", self.api.last()["text"])
            question_message = self.api.last()
            self.assertIn(aq.text, question_message["text"])
            if aq.qtype == config.SINGLE:
                self.assertIn(f"a:{prefix}:{aq.correct[0]}",
                              [b["callback_data"] for b in buttons(question_message)])
                self.press(f"a:{prefix}:{aq.correct[0]}")
                feedback = self.api.last()["text"]
                self.assertIn("✅ Верно!", feedback)
            elif aq.qtype == config.MULTIPLE:
                # Отмечаем один вариант — клавиатура обновляется с ✅.
                first = aq.correct[0]
                self.press(f"t:{prefix}:{first}")
                markup = self.api.edits("editMessageReplyMarkup")[-1]["reply_markup"]
                texts = [b["text"] for row in markup["inline_keyboard"] for b in row]
                self.assertIn(f"✅ {first}", texts)
                self.press(f"a:{prefix}:{first}")  # пропущены два верных → 0 баллов
                feedback = self.api.last()["text"]
                self.assertIn("❌ Неверно", feedback)
                self.assertIn("Правильный ответ", feedback)
            else:
                self.press(f"m:{prefix}:{aq.correct[0]}")
                edit = self.api.edits("editMessageText")[-1]
                self.assertIn("строки 2", edit["text"])
                self.press(f"m:{prefix}:{''.join(aq.correct)}")
                self.assertIn("✅ Верно!", self.api.last()["text"])
            self.assertIn("💡 Почему так: Объяснение к заданию", self.api.last()["text"])
            # Кнопки у вопроса убираются после ответа.
            self.assertEqual(self.api.edits("editMessageReplyMarkup")[-1]["reply_markup"],
                             {"inline_keyboard": []})
            # Повторное нажатие ничего не меняет.
            self.press(f"a:{prefix}:-")
            self.assertEqual(self.callback_notice(), "Вы уже ответили на этот вопрос")

        last_buttons = [b["callback_data"] for b in buttons(self.api.last())]
        self.assertEqual(last_buttons, [f"fin:{attempt.id}"])
        self.press(f"fin:{attempt.id}")
        summary = self.api.last()["text"]
        finished = database.get_attempt(attempt.id, user_id)
        assert finished is not None
        self.assertTrue(finished.is_finished)
        self.assertEqual(finished.score, 1 + 0 + 2)
        self.assertIn(f"Результат: 3 из {finished.max_score} баллов", summary)
        self.assertIn(f"/result/{attempt.id}", summary)

        self.press("results")
        results = self.api.last()["text"]
        self.assertIn("Тренировок: 1", results)
        self.assertIn(f"3/{finished.max_score}", results)
        self.assertIn("Пробный ЕНТ ещё не проходили", results)

        # Ответ в завершённой тренировке не принимается.
        self.press(f"a:{attempt.id}:{questions[0].id}:A")
        self.assertEqual(self.callback_notice(), "Тренировка уже завершена")

    def test_skip_continue_and_foreign_attempt(self) -> None:
        """Пропуск вопроса, «Продолжить» в меню тренировки и чужая попытка."""
        user_id = self.link()
        self.press("subj:math")
        attempt = database.get_in_progress_attempt(user_id, ent_logic.PRACTICE)
        assert attempt is not None
        first = database.get_attempt_questions(attempt.id)[0]
        self.press(f"a:{attempt.id}:{first.id}:-")
        self.assertIn("⏭ Пропущено", self.api.last()["text"])

        self.press("train")
        self.assertIn("▶️ Продолжить: Математика (1/3)",
                      [b["text"] for b in buttons(self.api.last())])

        # Другой пользователь Telegram не может отвечать в чужой тренировке.
        stranger = 555
        auth.create_telegram_user(stranger, "Чужой")
        self.bot.handle_update(callback_update(f"next:{attempt.id}", telegram_id=stranger))
        self.assertEqual(self.callback_notice(), "Эта тренировка не найдена")
        # Подделанные кнопки не ломают бота.
        for data in ("a:x:y:z", f"a:{attempt.id}:999:A", f"a:{attempt.id}:{first.id}:Z", "zzz"):
            self.press(data)
            self.assertIn(self.callback_notice(), ("Кнопка устарела", "Вы уже ответили на этот вопрос"))


class TelegramLoginPagesTests(DatabaseTestCase):
    """Вход на сайт по одноразовой ссылке из бота."""

    def setUp(self) -> None:
        """Запускает сервер на свободном порту."""
        super().setUp()
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

    @staticmethod
    def token(telegram_id: int = TG_ID) -> str:
        """Новый токен входа для Telegram-пользователя."""
        url = auth.telegram_login_url(telegram_id, "Аружан Т.")
        return urlsplit(url).query.removeprefix("token=")

    def test_new_account_and_one_time_token(self) -> None:
        """GET не тратит токен; «Создать аккаунт» входит; токен второй раз не работает."""
        browser = Browser(self.base_url)
        token = self.token()
        for _ in range(2):  # превью ссылок и повторное открытие не тратят токен
            status, _, html, _ = browser.get(f"/tg/login?token={token}")
            self.assertEqual(status, 200)
        self.assertIn("Аружан Т.", html)
        self.assertIn("Создать аккаунт и войти", html)

        status, path, html, _ = browser.post("/tg/login", {"token": token, "action": "new"})
        self.assertEqual((status, path), (200, "/dashboard?msg=tg_linked"))
        self.assertIn("Telegram привязан", html)
        self.assertIn("Привет, Аружан Т.!", html)
        user = database.get_user_by_telegram(TG_ID)
        assert user is not None
        self.assertEqual(user.login, f"tg{TG_ID}")

        other = Browser(self.base_url)
        status, _, html, _ = other.post("/tg/login", {"token": token, "action": "new"})
        self.assertEqual(status, 400)
        self.assertIn("недействительна", html)
        self.assertEqual(other.get(f"/tg/login?token={token}")[0], 400)
        self.assertEqual(other.get("/tg/login?token=garbage")[0], 400)

        # Следующая ссылка для того же Telegram — просто «Войти» в тот же аккаунт.
        token = self.token()
        _, _, html, _ = other.get(f"/tg/login?token={token}")
        self.assertIn("привязан к аккаунту", html)
        status, path, _, _ = other.post("/tg/login", {"token": token, "action": "login"})
        self.assertEqual(path, "/dashboard?msg=tg_linked")
        with database.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)

    def test_link_existing_account_with_password(self) -> None:
        """Привязка к существующему аккаунту: неверный пароль не тратит токен."""
        auth.create_account("Аружан", "aru@mail.kz", "password123")
        browser = Browser(self.base_url)
        token = self.token()
        status, _, html, _ = browser.post("/tg/login", {
            "token": token, "action": "link", "login": "aru@mail.kz", "password": "wrong-pass",
        })
        self.assertEqual(status, 400)
        self.assertIn("Неверная почта/телефон или пароль", html)
        self.assertIn('value="aru@mail.kz"', html)

        # Аккаунт с неподтверждённой почтой привязать нельзя.
        auth.register_user("Боря", "Новый", "new@mail.kz", "", "password123", "password123")
        status, _, html, _ = browser.post("/tg/login", {
            "token": token, "action": "link", "login": "new@mail.kz", "password": "password123",
        })
        self.assertEqual(status, 400)
        self.assertIn("Сначала подтвердите почту", html)

        status, path, _, _ = browser.post("/tg/login", {
            "token": token, "action": "link", "login": "aru@mail.kz", "password": "password123",
        })
        self.assertEqual(path, "/dashboard?msg=tg_linked")
        user = database.get_user_by_telegram(TG_ID)
        assert user is not None
        self.assertEqual(user.login, "aru@mail.kz")

    def test_telegram_moves_from_auto_account(self) -> None:
        """Telegram, привязанный к авто-аккаунту, можно перенести на свой аккаунт."""
        auto_id = auth.create_telegram_user(TG_ID, "Авто")
        auth.create_account("Аружан", "aru@mail.kz", "password123")
        browser = Browser(self.base_url)
        browser.post("/login", {"login": "aru@mail.kz", "password": "password123"})
        token = self.token()
        _, _, html, _ = browser.get(f"/tg/login?token={token}")
        self.assertIn("привязан к аккаунту <strong>Авто</strong>", html)
        self.assertIn("Привязать к моему аккаунту «Аружан»", html)
        self.assertNotIn("Создать аккаунт и войти", html)
        status, path, _, _ = browser.post("/tg/login", {
            "token": token, "action": "current", "csrf_token": test_pages.PagesTests.csrf(html),
        })
        self.assertEqual(path, "/dashboard?msg=tg_linked")
        self.assertEqual(database.get_user_by_telegram(TG_ID).login, "aru@mail.kz")
        with database.connect() as connection:
            row = connection.execute("SELECT telegram_id FROM users WHERE id = ?", (auto_id,))
            self.assertIsNone(row.fetchone()["telegram_id"])

        # Авто-аккаунт не потерян: новый вход «Создать аккаунт» вернётся к нему, а не упадёт.
        database.bind_telegram(database.get_user_credentials("aru@mail.kz")["id"], 999)
        self.assertEqual(auth.create_telegram_user(TG_ID, "Авто"), auto_id)

    def test_link_current_session_needs_csrf_and_expiry(self) -> None:
        """«Привязать к моему аккаунту» требует csrf; просроченная ссылка не работает."""
        browser = Browser(self.base_url)
        test_pages.PagesTests().register_and_login(browser, "me@mail.kz", name="Мадина")
        token = self.token()
        _, _, html, _ = browser.get(f"/tg/login?token={token}")
        self.assertIn("Привязать к моему аккаунту «Мадина Тестова»", html)
        status, _, _, _ = browser.post("/tg/login", {"token": token, "action": "current"})
        self.assertEqual(status, 403)
        status, path, _, _ = browser.post("/tg/login", {
            "token": token, "action": "current",
            "csrf_token": test_pages.PagesTests.csrf(html),
        })
        self.assertEqual(path, "/dashboard?msg=tg_linked")
        self.assertEqual(database.get_user_by_telegram(TG_ID).login, "me@mail.kz")

        token = self.token(42)
        with database.connect() as connection:
            connection.execute("UPDATE telegram_login_tokens SET expires_at = ?", (time.time() - 1,))
        self.assertEqual(browser.get(f"/tg/login?token={token}")[0], 400)
        self.assertEqual(browser.post("/tg/login", {"token": token, "action": "new"})[0], 400)
        self.assertIsNone(database.get_user_by_telegram(42))


class TelegramMigrationTests(DatabaseTestCase):
    """init_db добавляет telegram_id и уникальный индекс в старую базу."""

    def test_unique_telegram_id(self) -> None:
        """Один Telegram нельзя записать двум пользователям напрямую."""
        first = auth.create_account("Асан", "a@mail.kz", "password1")
        second = auth.create_account("Берик", "b@mail.kz", "password1")
        database.bind_telegram(first, 1)
        with self.assertRaises(sqlite3.IntegrityError), database.connect() as connection:
            connection.execute("UPDATE users SET telegram_id = 1 WHERE id = ?", (second,))
