"""Тесты регистрации, входа, хеширования паролей и сессий."""

from app.core import auth, database
from app.web.http import Request
from tests.base import DatabaseTestCase


class PasswordHashingTests(DatabaseTestCase):
    """Хеширование паролей через pbkdf2_hmac с солью."""

    def test_same_password_gives_different_hashes(self) -> None:
        """Из-за случайной соли одинаковые пароли дают разные хеши."""
        hash1, salt1 = auth.hash_password("secret-pass")
        hash2, salt2 = auth.hash_password("secret-pass")
        self.assertNotEqual(salt1, salt2)
        self.assertNotEqual(hash1, hash2)
        self.assertNotIn("secret-pass", hash1)

    def test_verify_password(self) -> None:
        """Проверка принимает верный пароль и отклоняет неверный."""
        password_hash, salt = auth.hash_password("secret-pass")
        self.assertTrue(auth.verify_password("secret-pass", salt, password_hash))
        self.assertFalse(auth.verify_password("Secret-pass", salt, password_hash))


class RegistrationTests(DatabaseTestCase):
    """Проверка полей регистрации (имя, фамилия, почта, телефон по желанию, пароль)."""

    def register(self, first: str = "Али", last: str = "Ахметов", email: str = "ali@mail.kz",
                 phone: str = "", password: str = "password1", password2: str | None = None) -> int:
        """Регистрация с разумными значениями по умолчанию."""
        return auth.register_user(first, last, email, phone, password,
                                  password if password2 is None else password2)

    def assert_invalid(self, fragment: str, **fields: str) -> None:
        """Убеждается, что регистрация отклонена с сообщением, содержащим fragment."""
        with self.assertRaises(auth.ValidationError) as context:
            self.register(**fields)
        self.assertTrue(
            any(fragment in error for error in context.exception.errors),
            context.exception.errors,
        )

    def test_register_creates_unverified_account(self) -> None:
        """Аккаунт создаётся неподтверждённым; телефон необязателен и нормализуется."""
        first = self.register(email="Aru@Mail.kz", first="Айгерим", last="Касымова")
        second = self.register(email="dan@mail.kz", phone="+7 701 123-45-67")
        user = database.get_user_credentials("aru@mail.kz")
        self.assertEqual((user["id"], user["name"], user["email_verified"]),
                         (first, "Айгерим Касымова", 0))
        self.assertEqual(database.get_user_credentials("+77011234567")["id"], second)

    def test_invalid_fields(self) -> None:
        """Каждое неверное поле даёт понятную ошибку."""
        self.assert_invalid("имя", first="")
        self.assert_invalid("фамилию", last=" ")
        self.assert_invalid("Введите почту", email="")
        self.assert_invalid("Почта", email="not-an-email@")
        self.assert_invalid("10 цифр", phone="8 701 123 45")
        self.assert_invalid("10 цифр", phone="+8 701 123 45 67")
        self.assert_invalid("не короче 8", password="short")
        self.assert_invalid("не совпадают", password2="password2")

    def test_duplicates(self) -> None:
        """Подтверждённую почту и чужой телефон занять нельзя (регистр почты не важен)."""
        user_id = self.register(phone="87011234567")
        database.set_email_verified(user_id)
        self.assert_invalid("уже зарегистрирован", email="ALI@mail.kz")
        self.assert_invalid("уже указан", email="other@mail.kz", phone="7011234567")

    def test_unverified_registration_can_be_repeated(self) -> None:
        """Пока почта не подтверждена, повторная регистрация заменяет имя, телефон и пароль."""
        user_id = self.register(password="password1")
        self.assertEqual(self.register(first="Алихан", phone="87011234567", password="newpass99"),
                         user_id)
        user = auth.authenticate("ali@mail.kz", "newpass99")
        assert user is not None
        self.assertEqual((user.id, user.name, user.email_verified), (user_id, "Алихан Ахметов", False))


class PhoneTests(DatabaseTestCase):
    """Телефон в любом виде приводится к +7XXXXXXXXXX."""

    def test_normalize_phone(self) -> None:
        """Все привычные записи номера дают один и тот же результат."""
        for raw in ("8 705 967 84 20", "+7 (705) 967-84-20", "87059678420", "77059678420",
                    "7059678420", " +77059678420 ", "8(705)967-84-20"):
            self.assertEqual(auth.normalize_phone(raw), "+77059678420", raw)
        for raw in ("", "705967842", "870596784201", "+8 705 967 84 20", "97059678420",
                    "+7 705 abc 84 20", "7+7059678420", "+"):
            with self.assertRaises(ValueError, msg=raw) as context:
                auth.normalize_phone(raw)
            self.assertIn("10 цифр", str(context.exception))

    def test_normalize_login(self) -> None:
        """Почта — в нижний регистр, телефон — к +7…, служебные логины не меняются."""
        self.assertEqual(auth.normalize_login(" Aru@Mail.KZ "), "aru@mail.kz")
        self.assertEqual(auth.normalize_login("8 (705) 967-84-20"), "+77059678420")
        self.assertEqual(auth.normalize_login("8 705 96"), "870596")
        self.assertEqual(auth.normalize_login("tg12345"), "tg12345")

    def test_register_and_login_with_any_format(self) -> None:
        """Зарегистрировался в одном виде — входит в любом другом; дубликат не пройдёт."""
        user_id = auth.register_user("Данияр", "Ким", "dan@mail.kz", "8 705 967 84 20",
                                     "password1", "password1")
        # Старый аккаунт, где телефон был логином, тоже находится по любому виду номера.
        old_id = auth.create_account("Старый", "+77011234567", "password1")
        self.assertEqual(auth.authenticate("8 701 123 45 67", "password1").id, old_id)
        for raw in ("+7 (705) 967-84-20", "87059678420", "77059678420", "7059678420"):
            user = auth.authenticate(raw, "password1")
            self.assertIsNotNone(user, raw)
            assert user is not None
            self.assertEqual(user.id, user_id)
        with self.assertRaises(auth.ValidationError):
            auth.register_user("Другой", "Ким", "x@mail.kz", "7059678420", "password1", "password1")
        with self.assertRaises(auth.ValidationError):
            auth.register_user("Другой", "Ким", "y@mail.kz", "87011234567", "password1", "password1")


class LoginAndSessionTests(DatabaseTestCase):
    """Вход по паролю и работа сессий."""

    def setUp(self) -> None:
        """Регистрирует тестового пользователя."""
        super().setUp()
        self.user_id = auth.create_account("Мария", "maria@mail.kz", "password1")

    def test_authenticate(self) -> None:
        """Вход работает только с правильным паролем и существующим логином."""
        user = auth.authenticate(" MARIA@mail.kz ", "password1")
        self.assertIsNotNone(user)
        assert user is not None
        self.assertEqual(user.id, self.user_id)
        self.assertIsNone(auth.authenticate("maria@mail.kz", "wrong-password"))
        self.assertIsNone(auth.authenticate("nobody@mail.kz", "password1"))

    def test_session_cookie_flags_and_lifecycle(self) -> None:
        """Cookie сессии HttpOnly и SameSite=Lax; после выхода сессия недействительна."""
        header = auth.start_session(self.user_id)
        self.assertIn("HttpOnly", header)
        self.assertIn("SameSite=Lax", header)
        token = header.split(";", 1)[0].split("=", 1)[1]

        request = Request("GET", "/", cookies={"ent_session": token})
        auth.attach_user(request)
        self.assertIsNotNone(request.user)
        self.assertTrue(request.csrf_token)

        request.form = {"csrf_token": [request.csrf_token]}
        self.assertTrue(auth.check_csrf(request))
        request.form = {"csrf_token": ["forged"]}
        self.assertFalse(auth.check_csrf(request))

        auth.end_session(request)
        fresh = Request("GET", "/", cookies={"ent_session": token})
        auth.attach_user(fresh)
        self.assertIsNone(fresh.user)

    def test_unknown_token_gives_anonymous_user(self) -> None:
        """Поддельный токен не даёт доступа."""
        request = Request("GET", "/", cookies={"ent_session": "made-up-token"})
        auth.attach_user(request)
        self.assertIsNone(request.user)
