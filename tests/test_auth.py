"""Тесты регистрации, входа, хеширования паролей и сессий."""

from app import auth, database
from app.web import Request
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
    """Проверка полей регистрации."""

    def assert_invalid(
        self, name: str, login: str, password: str, password2: str, fragment: str
    ) -> None:
        """Убеждается, что регистрация отклонена с сообщением, содержащим fragment."""
        with self.assertRaises(auth.ValidationError) as context:
            auth.register_user(name, login, password, password2)
        self.assertTrue(
            any(fragment in error for error in context.exception.errors),
            context.exception.errors,
        )

    def test_register_with_email_and_phone(self) -> None:
        """Можно зарегистрироваться и по почте, и по телефону."""
        password = "password1"
        self.assertGreater(auth.register_user("Айгерим", "Aru@Mail.kz", password, password), 0)
        self.assertGreater(
            auth.register_user("Данияр", "+7 701 123-45-67", password, password), 0
        )
        self.assertTrue(database.login_exists("aru@mail.kz"))
        self.assertTrue(database.login_exists("+77011234567"))

    def test_invalid_fields(self) -> None:
        """Каждое неверное поле даёт понятную ошибку."""
        self.assert_invalid("", "a@b.kz", "password1", "password1", "имя")
        self.assert_invalid("Али", "not-an-email@", "password1", "password1", "Почта")
        self.assert_invalid("Али", "87011234567", "password1", "password1", "+7XXXXXXXXXX")
        self.assert_invalid("Али", "+7701123", "password1", "password1", "+7XXXXXXXXXX")
        self.assert_invalid("Али", "a@b.kz", "short", "short", "не короче 8")
        self.assert_invalid("Али", "a@b.kz", "password1", "password2", "не совпадают")

    def test_duplicate_login_rejected(self) -> None:
        """Повторная регистрация того же логина запрещена (регистр почты не важен)."""
        auth.register_user("Али", "ali@mail.kz", "password1", "password1")
        self.assert_invalid(
            "Али 2", "ALI@mail.kz", "password1", "password1", "уже зарегистрирован"
        )


class LoginAndSessionTests(DatabaseTestCase):
    """Вход по паролю и работа сессий."""

    def setUp(self) -> None:
        """Регистрирует тестового пользователя."""
        super().setUp()
        self.user_id = auth.register_user("Мария", "maria@mail.kz", "password1", "password1")

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
