"""Тесты этапа 2: подтверждение почты кодом, восстановление пароля, вход через Google.

Письма не отправляются: DatabaseTestCase подменяет отправителя на FakeMailer.
В Google тесты тоже не ходят: подменяется google_auth.post_form.
"""

import base64
import json
import threading
import time
import urllib.parse
from unittest import mock

import config
from app import auth, database, google_auth, mailer
from app.server import create_server
from tests import test_pages
from tests.base import DatabaseTestCase
from tests.test_pages import Browser

GOOGLE_SETTINGS = {
    "GOOGLE_CLIENT_ID": "client-123.apps.googleusercontent.com",
    "GOOGLE_CLIENT_SECRET": "secret",
    "GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/google/callback",
}


def google_enabled():
    """Контекст: ключи Google заданы."""
    return mock.patch.multiple(config, **GOOGLE_SETTINGS)


def make_id_token(**claims: object) -> str:
    """id_token в формате JWT (подпись не проверяется — токен получен напрямую от Google)."""
    payload = {
        "aud": GOOGLE_SETTINGS["GOOGLE_CLIENT_ID"], "iss": "https://accounts.google.com",
        "exp": time.time() + 600, "email": "Google.User@Gmail.com", "email_verified": True,
        "given_name": "Айдана", "family_name": "Серикова", **claims,
    }

    def part(data: dict) -> str:
        raw = json.dumps(data).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f"{part({'alg': 'RS256'})}.{part(payload)}.c2lnbmF0dXJl"


class EmailCodeTests(DatabaseTestCase):
    """Коды из писем: отправка, хранение, попытки, срок, повторная отправка."""

    def setUp(self) -> None:
        """Регистрирует неподтверждённого пользователя."""
        super().setUp()
        self.user_id = auth.register_user("Али", "Ахметов", "ali@mail.kz", "",
                                          "password1", "password1")

    def code_row(self, purpose: str = auth.VERIFY):
        """Строка кода из базы."""
        return database.get_email_code(self.user_id, purpose)

    def test_code_is_sent_and_only_hash_is_stored(self) -> None:
        """В письме 6 цифр, в базе — только SHA-256; верный код подтверждает почту один раз."""
        self.assertEqual(auth.send_email_code(self.user_id, "ali@mail.kz", auth.VERIFY), 0)
        code = self.mail.last_code("ali@mail.kz")
        row = self.code_row()
        self.assertNotIn(code, row["code_hash"])
        self.assertEqual(len(row["code_hash"]), 64)
        self.assertAlmostEqual(row["expires_at"] - row["sent_at"], 15 * 60)

        self.assertEqual(auth.verify_email("ALI@mail.kz", f" {code[:3]} {code[3:]} "), self.user_id)
        self.assertEqual(database.get_user_credentials("ali@mail.kz")["email_verified"], 1)
        self.assertIsNone(self.code_row())
        with self.assertRaises(auth.ValidationError):
            auth.verify_email("ali@mail.kz", code)

    def test_resend_not_more_than_once_a_minute(self) -> None:
        """Повторная отправка раньше чем через минуту не делается; новый код отменяет старый."""
        auth.send_email_code(self.user_id, "ali@mail.kz", auth.VERIFY)
        first = self.mail.last_code("ali@mail.kz")
        wait = auth.send_email_code(self.user_id, "ali@mail.kz", auth.VERIFY)
        self.assertTrue(55 <= wait <= 60, wait)
        self.assertEqual(len(self.mail.messages), 1)

        with database.connect() as connection:
            connection.execute("UPDATE email_codes SET sent_at = sent_at - 61")
        self.assertEqual(auth.send_email_code(self.user_id, "ali@mail.kz", auth.VERIFY), 0)
        second = self.mail.last_code("ali@mail.kz")
        if first != second:
            self.assertIsNotNone(auth.check_email_code(self.user_id, auth.VERIFY, first))
        self.assertIsNone(auth.check_email_code(self.user_id, auth.VERIFY, second))

    def test_five_attempts_then_blocked(self) -> None:
        """После 5 неверных вводов код не принимается даже верный."""
        auth.send_email_code(self.user_id, "ali@mail.kz", auth.VERIFY)
        code = self.mail.last_code("ali@mail.kz")
        wrong = "000000" if code != "000000" else "111111"
        for left in (4, 3, 2, 1):
            error = auth.check_email_code(self.user_id, auth.VERIFY, wrong)
            self.assertIn(f"Осталось попыток: {left}", error)
        self.assertIn("Слишком много", auth.check_email_code(self.user_id, auth.VERIFY, wrong))
        self.assertIn("Слишком много", auth.check_email_code(self.user_id, auth.VERIFY, code))

    def test_expired_code(self) -> None:
        """Код старше 15 минут не действует."""
        auth.send_email_code(self.user_id, "ali@mail.kz", auth.VERIFY)
        code = self.mail.last_code("ali@mail.kz")
        with database.connect() as connection:
            connection.execute("UPDATE email_codes SET expires_at = ?", (time.time() - 1,))
        self.assertIn("истёк", auth.check_email_code(self.user_id, auth.VERIFY, code))

    def test_mail_failure_saves_no_code(self) -> None:
        """Если письмо не ушло, код не сохраняется и можно сразу попробовать снова."""
        self.mail.fail = True
        with self.assertRaises(mailer.MailError):
            auth.send_email_code(self.user_id, "ali@mail.kz", auth.VERIFY)
        self.assertIsNone(self.code_row())
        self.mail.fail = False
        self.assertEqual(auth.send_email_code(self.user_id, "ali@mail.kz", auth.VERIFY), 0)

    def test_console_sender_without_smtp(self) -> None:
        """Без настроек SMTP письма печатаются в консоль; с настройками — SMTP_SSL."""
        with mock.patch.multiple(config, SMTP_HOST="", SMTP_USER="", SMTP_PASSWORD=""):
            self.assertIsInstance(mailer._default_sender(), mailer.ConsoleSender)
        with mock.patch.multiple(config, SMTP_HOST="smtp.gmail.com", SMTP_USER="a@gmail.com",
                                 SMTP_PASSWORD="app-pass"):
            sender = mailer._default_sender()
        self.assertIsInstance(sender, mailer.SMTPSender)
        with mock.patch("smtplib.SMTP_SSL") as smtp:
            sender.send("ali@mail.kz", "Тема", "Текст 123456")
        self.assertEqual(smtp.call_args.args[:2], ("smtp.gmail.com", config.SMTP_PORT))
        client = smtp.return_value.__enter__.return_value
        client.login.assert_called_once_with("a@gmail.com", "app-pass")
        self.assertEqual(client.send_message.call_args.args[0]["To"], "ali@mail.kz")


class PasswordResetTests(DatabaseTestCase):
    """Смена пароля по коду из письма."""

    def test_reset_password(self) -> None:
        """Пароль проверяется до кода; верный код меняет пароль и завершает все сессии."""
        user_id = auth.create_account("Мария", "maria@mail.kz", "password1")
        auth.start_session(user_id)
        auth.send_email_code(user_id, "maria@mail.kz", auth.RESET)
        code = self.mail.last_code("maria@mail.kz")

        with self.assertRaises(auth.ValidationError) as context:
            auth.reset_password("maria@mail.kz", code, "short", "short")
        self.assertIn("не короче 8", context.exception.errors[0])
        self.assertEqual(database.get_email_code(user_id, auth.RESET)["attempts"], 0)
        with self.assertRaises(auth.ValidationError):
            auth.reset_password("nobody@mail.kz", code, "newpass99", "newpass99")

        self.assertEqual(auth.reset_password("maria@mail.kz", code, "newpass99", "newpass99"),
                         user_id)
        self.assertIsNone(auth.authenticate("maria@mail.kz", "password1"))
        self.assertIsNotNone(auth.authenticate("maria@mail.kz", "newpass99"))
        with database.connect() as connection:
            sessions = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        self.assertEqual(sessions, 0)


class GoogleTests(DatabaseTestCase):
    """Проверка id_token и выбор аккаунта при входе через Google."""

    def test_enabled_only_with_all_keys(self) -> None:
        """Кнопка активна, только если заданы все три ключа."""
        with google_enabled():
            self.assertTrue(google_auth.enabled())
            with mock.patch.object(config, "GOOGLE_CLIENT_SECRET", ""):
                self.assertFalse(google_auth.enabled())

    def test_parse_id_token_checks_claims(self) -> None:
        """Проверяются aud, iss, exp и подтверждённость почты."""
        with google_enabled():
            user = google_auth.parse_id_token(make_id_token())
            self.assertEqual((user.email, user.first_name, user.last_name),
                             ("google.user@gmail.com", "Айдана", "Серикова"))
            google_auth.parse_id_token(make_id_token(iss="accounts.google.com"))
            bad_tokens = (
                make_id_token(aud="other-app"),
                make_id_token(iss="https://evil.example"),
                make_id_token(exp=time.time() - 1),
                make_id_token(email_verified=False),
                make_id_token(email=None),
                "not-a-jwt",
                "a.!!!.c",
            )
            for token in bad_tokens:
                with self.assertRaises(google_auth.GoogleAuthError, msg=token):
                    google_auth.parse_id_token(token)

    def test_exchange_code_posts_to_google(self) -> None:
        """code меняется на токены POST-запросом на oauth2.googleapis.com/token."""
        with google_enabled(), mock.patch.object(
            google_auth, "post_form", return_value={"id_token": make_id_token()}
        ) as post:
            user = google_auth.exchange_code("auth-code")
        url, fields = post.call_args.args
        self.assertEqual(url, "https://oauth2.googleapis.com/token")
        self.assertEqual((fields["code"], fields["grant_type"]), ("auth-code", "authorization_code"))
        self.assertEqual(user.email, "google.user@gmail.com")
        with google_enabled(), mock.patch.object(google_auth, "post_form", return_value={}):
            with self.assertRaises(google_auth.GoogleAuthError):
                google_auth.exchange_code("auth-code")

    def test_google_user_accounts(self) -> None:
        """Новый пользователь создаётся, существующий находится по почте.

        Неподтверждённая регистрация на ту же почту получает случайный пароль:
        его мог задать чужой человек.
        """
        new_id = auth.google_user("new@gmail.com", "Айдана", "Серикова")
        self.assertEqual(database.get_user(new_id)["name"], "Айдана Серикова")
        self.assertEqual(auth.google_user("NEW@gmail.com", "", ""), new_id)

        verified = auth.create_account("Мария", "maria@gmail.com", "password1")
        self.assertEqual(auth.google_user("maria@gmail.com", "Мария", ""), verified)
        self.assertIsNotNone(auth.authenticate("maria@gmail.com", "password1"))

        pending = auth.register_user("Чужой", "Человек", "victim@gmail.com", "",
                                     "attacker1", "attacker1")
        self.assertEqual(auth.google_user("victim@gmail.com", "Жертва", ""), pending)
        self.assertEqual(database.get_user_credentials("victim@gmail.com")["email_verified"], 1)
        self.assertIsNone(auth.authenticate("victim@gmail.com", "attacker1"))


class AccountPagesTests(DatabaseTestCase):
    """Страницы подтверждения почты, восстановления пароля и входа через Google на сервере."""

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

    def register_and_login(self, browser: Browser, email: str, name: str) -> None:
        """Регистрация через форму с вводом кода (общий помощник из test_pages)."""
        test_pages.PagesTests().register_and_login(browser, email, name=name)

    def test_register_verify_flow(self) -> None:
        """Регистрация → код на почту → неверный код → повтор раньше минуты → вход по коду."""
        browser = Browser(self.base_url)
        status, path, html, _ = browser.post("/register", {
            "first_name": "Ерлан", "last_name": "Абаев", "email": "Erlan@Mail.kz",
            "phone": "8 701 555 44 33", "password": "password123", "password2": "password123",
        })
        self.assertEqual(path, "/verify?email=erlan%40mail.kz&msg=code_sent")
        self.assertIn("erlan@mail.kz", html)
        self.assertIn("Отправить код ещё раз", html)
        code = self.mail.last_code("erlan@mail.kz")

        # Без подтверждения войти нельзя — ведём на ввод кода.
        status, path, html, _ = browser.post(
            "/login", {"login": "87015554433", "password": "password123"}
        )
        self.assertTrue(path.startswith("/verify?email=erlan%40mail.kz&msg=verify_needed"), path)
        self.assertTrue(browser.get("/dashboard")[1].startswith("/login?next=%2Fdashboard"))

        wrong = "000000" if code != "000000" else "111111"
        status, _, html, _ = browser.post("/verify", {"email": "erlan@mail.kz", "code": wrong})
        self.assertEqual(status, 400)
        self.assertIn("Осталось попыток: 4", html)

        status, _, html, _ = browser.post("/verify/resend", {"email": "erlan@mail.kz"})
        self.assertEqual(status, 429)
        self.assertIn("Новый код можно запросить через", html)
        self.assertEqual(len(self.mail.messages), 1)

        status, path, html, _ = browser.post("/verify", {"email": "erlan@mail.kz", "code": code})
        self.assertEqual(path, "/dashboard?msg=verified")
        self.assertIn("Почта подтверждена", html)
        self.assertIn("Ерлан Абаев", html)

        # Повторное подтверждение и повторная регистрация на ту же почту.
        status, path, _, _ = Browser(self.base_url).post(
            "/verify", {"email": "erlan@mail.kz", "code": code}
        )
        self.assertTrue(path.startswith("/login?msg=already_verified"), path)
        status, _, html, _ = Browser(self.base_url).post("/register", {
            "first_name": "Ерлан", "last_name": "Абаев", "email": "erlan@mail.kz",
            "password": "password123", "password2": "password123",
        })
        self.assertEqual(status, 400)
        self.assertIn("уже зарегистрирован", html)

        # Вход по телефону после подтверждения.
        status, path, _, _ = Browser(self.base_url).post(
            "/login", {"login": "+7 (701) 555-44-33", "password": "password123"}
        )
        self.assertEqual(path, "/dashboard")

    def test_mail_failure_is_reported(self) -> None:
        """Если SMTP не отвечает, пользователь видит понятную ошибку."""
        self.mail.fail = True
        status, _, html, _ = Browser(self.base_url).post("/register", {
            "first_name": "Ерлан", "last_name": "Абаев", "email": "erlan@mail.kz",
            "password": "password123", "password2": "password123",
        })
        self.assertEqual(status, 400)
        self.assertIn("Не удалось отправить письмо", html)

    def test_forgot_and_reset_password(self) -> None:
        """«Забыли пароль?» → код → новый пароль; старые сессии завершены."""
        old_device = Browser(self.base_url)
        self.register_and_login(old_device, "maria@mail.kz", name="Мария")
        browser = Browser(self.base_url)
        self.assertIn('href="/forgot"', browser.get("/login")[2])

        # Неизвестная почта — тот же ответ, но письма нет.
        status, path, html, _ = browser.post("/forgot", {"email": "nobody@mail.kz"})
        self.assertEqual(path, "/reset?email=nobody%40mail.kz&msg=reset_sent")
        sent_before = len(self.mail.messages)
        status, path, html, _ = browser.post("/forgot", {"email": "Maria@mail.kz"})
        self.assertEqual(path, "/reset?email=maria%40mail.kz&msg=reset_sent")
        self.assertIn("Если аккаунт с такой почтой есть", html)
        self.assertEqual(len(self.mail.messages), sent_before + 1)
        code = self.mail.last_code("maria@mail.kz")

        status, _, html, _ = browser.post("/reset", {
            "email": "maria@mail.kz", "code": code, "password": "newpass99", "password2": "other",
        })
        self.assertEqual(status, 400)
        self.assertIn("не совпадают", html)
        status, path, html, _ = browser.post("/reset", {
            "email": "maria@mail.kz", "code": code, "password": "newpass99", "password2": "newpass99",
        })
        self.assertEqual(path, "/dashboard?msg=password_changed")
        self.assertIn("Пароль изменён", html)

        self.assertTrue(old_device.get("/dashboard")[1].startswith("/login?"))
        status, path, _, _ = Browser(self.base_url).post(
            "/login", {"login": "maria@mail.kz", "password": "newpass99"}
        )
        self.assertEqual(path, "/dashboard")

    def test_google_disabled(self) -> None:
        """Без ключей кнопка неактивна с подписью «скоро», а /auth/google ведёт на вход."""
        with mock.patch.multiple(config, GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET="",
                                 GOOGLE_REDIRECT_URI=""):
            browser = Browser(self.base_url)
            html = browser.get("/login")[2]
            self.assertRegex(html, r"<button[^>]*disabled>\s*<span class=\"google-mark\">")
            self.assertIn("скоро", html)
            self.assertEqual(browser.get("/auth/google")[1], "/login?msg=google_off")

    def test_google_login(self) -> None:
        """Кнопка ведёт на Google с state; callback проверяет state и создаёт аккаунт."""
        browser = Browser(self.base_url, follow_redirects=False)
        with google_enabled():
            self.assertIn('href="/auth/google"', Browser(self.base_url).get("/register")[2])
            status, _, _, headers = browser.get("/auth/google")
            self.assertEqual(status, 303)
            location = urllib.parse.urlsplit(headers["Location"])
            self.assertEqual(location.netloc, "accounts.google.com")
            query = urllib.parse.parse_qs(location.query)
            state = query["state"][0]
            self.assertEqual(query["client_id"][0], GOOGLE_SETTINGS["GOOGLE_CLIENT_ID"])
            self.assertIn("HttpOnly", headers["Set-Cookie"])

            with mock.patch.object(google_auth, "post_form",
                                   return_value={"id_token": make_id_token()}) as post:
                # Чужой state (подделка ответа) — отказ, в Google не обращаемся.
                status, _, _, headers = browser.get("/auth/google/callback?code=x&state=forged")
                self.assertEqual(headers["Location"], "/login?msg=google_failed")
                post.assert_not_called()

                # Пользователь нажал «Отмена».
                _, _, _, headers = browser.get("/auth/google/callback?error=access_denied")
                self.assertEqual(headers["Location"], "/login")

                status, _, _, headers = browser.get("/auth/google")
                state = urllib.parse.parse_qs(
                    urllib.parse.urlsplit(headers["Location"]).query)["state"][0]
                status, _, _, headers = browser.get(
                    "/auth/google/callback?" + urllib.parse.urlencode({"code": "c", "state": state})
                )
                self.assertEqual((status, headers["Location"]), (303, "/dashboard"))

            status, _, html, _ = browser.get("/dashboard")
            self.assertEqual(status, 200)
            self.assertIn("Айдана Серикова", html)
            user = database.get_user_credentials("google.user@gmail.com")
            self.assertEqual(user["email_verified"], 1)

            # Ошибка Google при обмене кода — понятное сообщение, не падение.
            other = Browser(self.base_url, follow_redirects=False)
            _, _, _, headers = other.get("/auth/google")
            state = urllib.parse.parse_qs(urllib.parse.urlsplit(headers["Location"]).query)["state"][0]
            with mock.patch.object(google_auth, "post_form",
                                   side_effect=google_auth.GoogleAuthError("сеть")):
                _, _, _, headers = other.get(
                    "/auth/google/callback?" + urllib.parse.urlencode({"code": "c", "state": state})
                )
            self.assertEqual(headers["Location"], "/login?msg=google_failed")
