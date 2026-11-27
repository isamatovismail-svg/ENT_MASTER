"""Этап 9: двуязычный интерфейс — словарь полный, переключатель работает, на казахских
страницах не остаётся русского текста интерфейса."""

import re
import threading
import unittest
from datetime import date, timedelta
from html import unescape

import config
from app import auth, database, ent_logic, i18n, i18n_keys, notifications, schools
from app.server import create_server
from app.templates import fragment, render
from tests.base import DatabaseTestCase
from tests.test_pages import CSRF_RE, Browser

PASSWORD = "password1"
NEXT_WEEK = (date.today() + timedelta(days=7)).isoformat()
PLACEHOLDER = re.compile(r"\$\w+|\{\w*\}")
KAZAKH_LETTERS = re.compile("[ӘәҒғҚқҢңӨөҰұҮүҺһІі]")
# Служебные слова русского языка, которых нет в казахском тексте интерфейса.
RUSSIAN_WORDS = {
    "и", "в", "во", "на", "для", "или", "что", "это", "вы", "ваш", "ваши", "вам", "по", "из", "от",
    "до", "как", "все", "всё", "нет", "есть", "если", "при", "без", "чтобы", "уже", "только", "ещё",
    "после", "можно", "нужно", "вопрос", "вопросы", "задание", "заданий", "баллов", "тест", "пока",
    "войти", "выйти", "ученик", "учитель", "школа", "пробный", "тренировка", "история",
}
TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S)
TEXT_NODE = re.compile(r">([^<>]+)<")
ATTRIBUTE = re.compile(r'\b(?:placeholder|title|aria-label|alt)="([^"]*)"')
# Содержимое, а не интерфейс: тексты вопросов и вариантов, имена, названия школ.
CONTENT = re.compile(
    r'<(p|span|div|td|li|strong|label)[^>]*class="(?:q-text|option-text|context|q-context)[^"]*"[^>]*>.*?</\1>',
    re.S)


def russian_strings(html: str) -> list[str]:
    """Текстовые узлы и подписи страницы, которые выглядят как русский текст интерфейса."""
    html = CONTENT.sub("", TAG.sub("", html))
    found = []
    for raw in [*TEXT_NODE.findall(html), *ATTRIBUTE.findall(html)]:
        text = " ".join(unescape(raw).split())
        if not re.search("[А-Яа-яЁё]", text):
            continue
        if text in i18n.LANGUAGE_NAMES.values():
            continue  # названия языков в переключателе — на своём языке («Русский», «Қазақ тілі»)
        translation = i18n.KK_DICT.get(text)
        if translation is not None and translation != text:
            found.append(text)   # строка из словаря осталась непереведённой
            continue
        words = set(re.findall(r"[а-яё]+", text.lower()))
        if not KAZAKH_LETTERS.search(text) and words & RUSSIAN_WORDS:
            found.append(text)
    return found


class DictionaryTests(unittest.TestCase):
    """У каждой строки интерфейса есть казахский перевод с теми же метками."""

    def test_every_ui_string_has_kazakh_translation(self) -> None:
        self.assertEqual(i18n_keys.missing(), [])

    def test_placeholders_are_kept(self) -> None:
        for source, translated in i18n.KK_DICT.items():
            self.assertEqual(sorted(PLACEHOLDER.findall(source)), sorted(PLACEHOLDER.findall(translated)), source)

    def test_t_markup_and_lazy_names(self) -> None:
        with i18n.use("kk"):
            self.assertEqual(i18n.t("Ошибка {status}", status=404), "Қате 404")
            self.assertEqual(config.SUBJECTS["kz_history"].name, "Қазақстан тарихы")
            self.assertEqual(config.QUESTION_TYPE_NAMES[config.SINGLE], "Бір жауап")
            self.assertEqual(str(fragment("<b>Войти</b> $name", name="Войти")), "<b>Кіру</b> Войти")
        self.assertEqual(config.SUBJECTS["kz_history"].name, "История Казахстана")
        self.assertEqual(i18n.t("Ошибка {status}", status=404), "Ошибка 404")
        self.assertIn("Тіркелу", str(self._render_register()))

    @staticmethod
    def _render_register():
        with i18n.use("kk"):
            return render("register.html", errors="", first_name="", last_name="", email="", phone="",
                          school_city="", school_name="", min_length=8, google="", language_options="")


class KazakhPagesTests(DatabaseTestCase):
    """Обход страниц в режиме kk: гость, ученик, учитель, главный администратор."""

    def setUp(self) -> None:
        super().setUp()
        for number in range(12):  # вопросы-«содержимое» без совпадений со строками интерфейса
            database.upsert_question("math", config.SINGLE, f"{number + 2} + 2 = ?", "",
                                     [str(number + 4), str(number + 5), str(number + 6), str(number + 7)],
                                     [], ["A"], explanation=f"{number + 2} + 2 = {number + 4}.", topic="01",
                                     language="kk")
        self.server = create_server("127.0.0.1", 0)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.school = schools.find_or_create_school("Шымкент", "1")
        self.teacher_id = auth.create_account("Әсел Мұратқызы", "teacher@mail.kz", PASSWORD)
        database.make_teacher("teacher@mail.kz", self.school)
        self.student_id = auth.create_account("Айгерім Нұрланқызы", "student@mail.kz", PASSWORD)
        database.set_user_school(self.student_id, self.school, database.SCHOOL_APPROVED)
        self.pending_id = auth.create_account("Ерлан Қайратұлы", "new@mail.kz", PASSWORD)
        schools.join_school(self.pending_id, "Шымкент", "1")
        auth.create_account("Бас әкімші", "admin@mail.kz", PASSWORD)
        database.set_user_role("admin@mail.kz", database.ROLE_ADMIN)
        for user_id in (self.teacher_id, self.student_id, self.pending_id):
            database.set_user_language(user_id, "kk")
        database.set_user_language(database.get_user_credentials("admin@mail.kz")["id"], "kk")
        self.assignment = schools.create_assignment(
            self.school, self.teacher_id, "practice", "math", "", "2", NEXT_WEEK, True, [])
        attempt_id = ent_logic.build_practice(self.student_id, "math")
        ent_logic.finish_attempt(database.get_attempt(attempt_id, self.student_id))
        self.attempt_id = attempt_id
        notifications.check_due()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def assert_kazakh(self, browser: Browser, path: str) -> str:
        status, final, html, _ = browser.get(path)
        self.assertLess(status, 500, path)
        self.assertIn('<html lang="kk">', html, path)
        self.assertEqual(russian_strings(html), [], f"{path} → {final}")
        return html

    def login(self, email: str) -> Browser:
        browser = Browser(self.base_url)
        browser.post("/login", {"login": email, "password": PASSWORD})
        return browser

    def test_guest_pages(self) -> None:
        guest = Browser(self.base_url)
        status, path, html, _ = guest.get("/lang/kk?next=/register")
        self.assertEqual(path, "/register")
        for page in ("/", "/login", "/register", "/forgot", "/verify?email=a@b.kz", "/no-such-page"):
            self.assert_kazakh(guest, page)
        # Переключатель обратно на русский.
        _, _, html, _ = guest.get("/lang/ru?next=/")
        self.assertIn('<html lang="ru">', html)
        self.assertIn("Регистрация", html)

    def test_student_pages(self) -> None:
        student = self.login("student@mail.kz")
        for page in ("/dashboard", "/profile", "/notifications", "/mock", "/practice", "/history",
                     f"/result/{self.attempt_id}"):
            self.assert_kazakh(student, page)

    def test_teacher_pages(self) -> None:
        teacher = self.login("teacher@mail.kz")
        for page in (f"/teacher/{self.school}", f"/teacher/{self.school}?period=all&sort=name&dir=asc",
                     f"/teacher/{self.school}/assignments", f"/teacher/{self.school}/assignments/new",
                     f"/teacher/{self.school}/assignments/{self.assignment}",
                     f"/teacher/{self.school}/students/{self.student_id}", "/teacher/questions",
                     "/teacher/questions/new", "/notifications", "/profile"):
            self.assert_kazakh(teacher, page)

    def test_admin_pages(self) -> None:
        admin = self.login("admin@mail.kz")
        for page in ("/admin", "/admin/topics", "/admin/banners", "/admin/banners/new", "/admin/review",
                     "/admin/users", f"/admin/users/{self.student_id}", "/admin/questions/new", "/teacher"):
            self.assert_kazakh(admin, page)

    def test_language_saved_in_profile_and_registration(self) -> None:
        student = self.login("student@mail.kz")
        _, _, html, _ = student.get("/profile")
        student.post("/profile/language", {"csrf_token": CSRF_RE.search(html).group(1), "language": "ru"})
        self.assertEqual(database.get_user_language(self.student_id), "ru")
        self.assertIn('<html lang="ru">', student.get("/dashboard")[2])
        guest = Browser(self.base_url)
        guest.post("/register", {
            "first_name": "Дана", "last_name": "Сапарова", "email": "dana@mail.kz", "language": "kk",
            "password": "password123", "password2": "password123"})
        user = database.get_user_credentials("dana@mail.kz")
        self.assertEqual(user["language"], "kk")
        self.assertIn("Сәлеметсіз бе!", self.mail.messages[-1][2])   # письмо на казахском

    def test_notifications_and_telegram_in_recipient_language(self) -> None:
        database.bind_telegram(self.student_id, 555)
        schools.create_assignment(self.school, self.teacher_id, "practice", "physics", "", "1", NEXT_WEEK,
                                  False, [self.student_id])
        self.assertIn("Жаңа тапсырма", self.telegram.messages[-1]["text"])
        with i18n.use("ru"):
            self.assertIn("Новое задание", notifications.for_user(self.student_id)[0].text)


if __name__ == "__main__":
    unittest.main()
