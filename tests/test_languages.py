"""Этап 10: вопросы на двух языках — выборка по языку обучения, пары, генераторы, полный тест."""

import re
import threading

from app import config
import seed
from app import generators, i18n
from app.core import auth, database, ent_logic
from app.core.question_bank import validate_question
from app.web.server import create_server
from tests.base import DatabaseTestCase
from tests.test_pages import CSRF_RE, Browser

KAZAKH_LETTERS = re.compile("[ӘәҒғҚқҢңӨөҰұҮүҺһІі]")
RUSSIAN_WORDS = {"и", "на", "для", "или", "что", "это", "по", "из", "от", "до", "как", "какой", "какая",
                 "сколько", "найдите", "чему", "равна", "равен", "выберите", "установите", "соответствие"}


def user(language: str, login: str) -> int:
    user_id = auth.create_account("Ученик", login, "password1")
    database.set_user_language(user_id, language)
    return user_id


class FullBankTests(DatabaseTestCase):
    """Полный банк (JSON на двух языках + генераторы): по каждой паре и языку — 120 заданий."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.generated_kk = {
            (subject, qtype): generators.generate(subject, qtype, 50, lang="kk")
            for subject in generators.KK_TEMPLATES for qtype in generators.KK_TEMPLATES[subject]
        }

    def test_full_mock_for_every_pair_and_language(self) -> None:
        total, errors = seed.seed()
        self.assertEqual(errors, [])
        for language in config.LANGUAGES:
            user_id = user(language, f"{language}@mail.kz")
            for index in config.pairs_for(language):
                with self.subTest(language=language, pair=config.PROFILE_PAIRS[index]):
                    attempt_id = ent_logic.build_mock(user_id, index)
                    attempt = database.get_attempt(attempt_id, user_id)
                    questions = database.get_attempt_questions(attempt_id)
                    self.assertEqual(len(questions), config.MOCK_TOTAL_QUESTIONS)
                    self.assertEqual(attempt.max_score, config.MOCK_MAX_SCORE)
                    self.assertEqual(attempt.shortage, [])
                    ent_logic.finish_attempt(attempt)
        table = seed.language_table()
        self.assertIn("Математика", table)
        self.assertIn("kk", table)

    def test_kazakh_generators_are_kazakh_and_valid(self) -> None:
        for (subject, qtype), questions in self.generated_kk.items():
            with self.subTest(subject=subject, qtype=qtype):
                self.assertTrue(questions, "казахский шаблон не дал ни одного вопроса")
                for question in questions:
                    self.assertEqual(validate_question(question, subject), [])
                    self.assertEqual(question["language"], "kk")
                    whole = " ".join([question["text"], question.get("context", ""), question["explanation"],
                                      *question["options"], *question.get("left", [])])
                    self.assertTrue(KAZAKH_LETTERS.search(whole), question["text"])
                    words = set(re.findall(r"[а-яёәғқңөұүһі]+", question["text"].lower()))
                    self.assertFalse(words & RUSSIAN_WORDS, question["text"])
                    self.assertEqual(len(set(question["options"])), len(question["options"]))


class LanguageSelectionTests(DatabaseTestCase):
    """Ученик получает вопросы только своего языка; пары зависят от языка обучения."""

    def setUp(self) -> None:
        super().setUp()
        for language in ("ru", "kk"):
            for number in range(12):
                database.upsert_question("math", config.SINGLE, f"{language} вопрос {number}", "",
                                         ["1", "2", "3", "4"], [], ["A"], "Объяснение.", "01", language)
        for number in range(12):
            database.upsert_question("foreign_language", config.SINGLE, f"Question {number}", "",
                                     ["a", "b", "c", "d"], [], ["A"], "Because.", "01", "en")

    def test_practice_uses_student_language(self) -> None:
        for language in ("ru", "kk"):
            user_id = user(language, f"{language}@mail.kz")
            attempt_id = ent_logic.build_practice(user_id, "math")
            texts = {aq.text for aq in database.get_attempt_questions(attempt_id)}
            self.assertTrue(texts)
            self.assertTrue(all(text.startswith(language) for text in texts), texts)
            shared = ent_logic.build_practice(user_id, "foreign_language")
            self.assertTrue(database.get_attempt_questions(shared))

    def test_counts_by_language(self) -> None:
        self.assertEqual(database.question_counts("kk")[("math", config.SINGLE)], 12)
        self.assertEqual(database.question_counts("ru")[("math", config.SINGLE)], 12)
        self.assertEqual(database.question_counts()[("math", config.SINGLE)], 24)
        self.assertEqual(database.question_counts("kk")[("foreign_language", config.SINGLE)], 12)

    def test_language_pairs(self) -> None:
        kazakh = config.PROFILE_PAIRS.index(("kazakh_language", "kazakh_literature"))
        russian = config.PROFILE_PAIRS.index(("russian_language", "russian_literature"))
        self.assertIn(kazakh, config.pairs_for("kk"))
        self.assertNotIn(russian, config.pairs_for("kk"))
        self.assertIn(russian, config.pairs_for("ru"))
        self.assertNotIn(kazakh, config.pairs_for("ru"))
        self.assertEqual(len(config.pairs_for("kk")), len(config.PROFILE_PAIRS) - 1)
        with self.assertRaises(ent_logic.TestBuildError):
            ent_logic.build_mock(user("ru", "ru@mail.kz"), kazakh)

    def test_existing_kazakh_subjects_marked_kk_on_migration(self) -> None:
        database.upsert_question("kazakh_language", config.SINGLE, "Сөз табы?", "", ["a", "b", "c", "d"],
                                 [], ["A"], "Түсіндірме.", "01", "ru")
        database.init_db()
        self.assertEqual([q.language for q in database.list_questions("kazakh_language")], ["kk"])


class TeacherQuestionLanguageTests(DatabaseTestCase):
    """Учитель выбирает язык вопроса; админ видит его в проверке."""

    def test_teacher_question_language(self) -> None:
        from app.core import schools
        server = create_server("127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            school = schools.find_or_create_school("Алматы", "1")
            auth.create_account("Мұғалім", "t@mail.kz", "password1")
            database.make_teacher("t@mail.kz", school)
            auth.create_account("Админ", "a@mail.kz", "password1")
            database.set_user_role("a@mail.kz", database.ROLE_ADMIN)
            teacher = Browser(base)
            teacher.post("/login", {"login": "t@mail.kz", "password": "password1"})
            _, _, html, _ = teacher.get("/teacher/questions/new?type=single")
            self.assertIn('name="language" value="kk"', html)
            status, path, _, _ = teacher.post("/teacher/questions/new", {
                "csrf_token": CSRF_RE.search(html).group(1), "type": "single", "subject": "math", "topic": "05",
                "language": "kk", "text": "2x = 8 теңдеуін шешіңіз.", "opt_A": "4", "opt_B": "2", "opt_C": "6",
                "opt_D": "8", "correct": "A", "explanation": "x = 8 / 2 = 4."})
            self.assertIn("/teacher/questions", path)
            question = database.list_pending_questions()[0][0]
            self.assertEqual(question.language, "kk")
            admin = Browser(base)
            admin.post("/login", {"login": "a@mail.kz", "password": "password1"})
            with i18n.use("ru"):
                self.assertIn("Казахский", admin.get("/admin/review")[2])
            self.assertIn("Казахский", admin.get("/admin/topics?subject=math")[2])
        finally:
            server.shutdown()
            server.server_close()
