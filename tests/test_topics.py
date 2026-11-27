"""Тесты этапа 5: темы спецификации НЦТ, разметка вопросов, слабые темы, покрытие банка."""

import json
import threading
import time

import config
import seed
from app import auth, database, ent_logic, generators, schools, topics
from app.question_bank import validate_question
from app.server import create_server
from tests import test_pages
from tests.base import DatabaseTestCase
from tests.test_pages import Browser

# Число тем в спецификациях НЦТ (с 2026 года) — каталог должен совпадать с документами.
SPEC_TOPIC_COUNTS = {
    "kz_history": 55, "math_literacy": 10, "reading_literacy": 14, "math": 18, "physics": 25,
    "informatics": 13, "geography": 21, "biology": 12, "chemistry": 19, "world_history": 41, "law": 19,
    "kazakh_language": 4, "kazakh_literature": 31, "russian_language": 30, "russian_literature": 29,
    "foreign_language": 7,
}

# Темы, по которым в банке пока нет вопросов. Это задания-форматы («история в документах»,
# «работа с текстом»), для них нужны авторские тексты и источники. Список можно только сокращать.
KNOWN_GAPS = {
    "kz_history": {"53", "54", "55"},
    "world_history": {"41"},
    "russian_language": {"26", "27", "28", "29", "30"},
}


def all_generated() -> dict[str, list[dict]]:
    """Все сгенерированные вопросы по предметам (как их загружает seed.py)."""
    return {
        subject: [q for qtype in templates
                  for q in generators.generate(subject, qtype, generators.DEFAULT_COUNTS[qtype])]
        for subject, templates in generators.SUBJECT_TEMPLATES.items()
    }


def all_json() -> dict[str, list[dict]]:
    """Все вопросы из data/questions/*.json по предметам."""
    result: dict[str, list[dict]] = {}
    for path in sorted(config.QUESTIONS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        result.setdefault(data["subject"], []).extend(data["questions"])
    return result


class CatalogTests(DatabaseTestCase):
    """Каталог тем и разметка банка."""

    def test_catalog_matches_specifications(self) -> None:
        """У каждого предмета ЕНТ — темы спецификации, пронумерованные подряд."""
        self.assertEqual(set(topics.TOPICS), set(config.SUBJECTS))
        for subject, count in SPEC_TOPIC_COUNTS.items():
            items = topics.topics_for(subject)
            self.assertEqual(len(items), count, subject)
            self.assertEqual([t.code for t in items], [f"{n:02d}" for n in range(1, count + 1)])
            self.assertTrue(all(t.section and t.name for t in items))
        self.assertEqual(topics.topic_label("math", "12"), "12. Арифметическая и геометрическая прогрессии")
        self.assertEqual(topics.topic_label("math", "99"), "Без темы")

    def test_every_question_has_a_valid_topic_and_gaps_only_shrink(self) -> None:
        """Каждый вопрос JSON и генераторов размечен темой своего предмета; пустые темы — только известные."""
        covered: dict[str, set[str]] = {}
        for source in (all_generated(), all_json()):
            for subject, questions in source.items():
                for question in questions:
                    code = question.get("topic", "")
                    self.assertIsNotNone(topics.get_topic(subject, code),
                                         f"{subject}: «{question['text'][:60]}» без темы ({code!r})")
                    covered.setdefault(subject, set()).add(code)
        for subject in config.SUBJECTS:
            empty = {t.code for t in topics.topics_for(subject)} - covered.get(subject, set())
            self.assertLessEqual(empty, KNOWN_GAPS.get(subject, set()), subject)

    def test_literature_only_program_works(self) -> None:
        """Вопросы по литературе — только о произведениях из спецификации НЦТ."""
        generated = all_generated()["russian_literature"]
        text = " ".join(q["text"] + " " + " ".join(q["options"]) for q in generated)
        for work in ("Отцы и дети", "Мастер и Маргарита", "Анна Каренина", "Вишнёвый сад", "Тихий Дон"):
            self.assertNotIn(work, text)

    def test_validate_question_checks_topic(self) -> None:
        """Тема должна принадлежать предмету вопроса."""
        question = {"type": "single", "text": "?", "options": ["1", "2"], "correct": ["A"],
                    "explanation": "x", "topic": "05"}
        self.assertEqual(validate_question(question, "math"), [])
        self.assertTrue(validate_question({**question, "topic": "77"}, "math"))
        self.assertTrue(validate_question({**question, "topic": 5}, "math"))
        self.assertEqual(validate_question({**question, "topic": ""}, "math"), [])


class SeedRetireTests(DatabaseTestCase):
    """seed.py убирает устаревшие вопросы без темы, не трогая ручные."""

    def test_retire_untagged(self) -> None:
        """Устаревший сгенерированный вопрос убирается, вопрос админа и учителя остаются."""
        database.upsert_question("math", "single", "Старый вопрос без темы", "", ["1", "2"], [], ["A"], "x")
        database.upsert_question("math", "single", "Вопрос с темой", "", ["1", "2"], [], ["A"], "x", topic="05")
        admin_q = database.Question(0, "math", "single", "Вопрос админа", "", ["1", "2"], [], ["A"], "x")
        database.insert_question(admin_q)
        teacher = auth.create_account("Учитель", "t@mail.kz", "password1")
        database.insert_teacher_question(
            database.Question(0, "math", "single", "Вопрос учителя", "", ["1", "2"], [], ["A"], "x"),
            teacher, time.time())

        self.assertEqual(database.retire_untagged_questions(), 1)
        texts = {q.text for q in database.list_questions("math")}
        self.assertEqual(texts, {"Вопрос с темой", "Вопрос админа"})
        self.assertEqual(database.topic_counts(), {("math", "05"): 1, ("math", ""): 1})

    def test_json_seed_sets_topics(self) -> None:
        """seed.py записывает тему из JSON в базу."""
        seed.seed(with_generated=False)
        counts = database.topic_counts()
        self.assertGreater(counts.get(("math", "05"), 0), 0)
        self.assertNotIn(("math", ""), counts)


class WeakTopicsTests(DatabaseTestCase):
    """Слабые темы ученика: процент баллов по темам спецификации."""

    def test_weak_topics(self) -> None:
        """Тема с ошибками попадает в слабые, тема без ошибок — нет; мало заданий — не учитывается."""
        for number in range(6):
            database.upsert_question("math", "single", f"Прогрессия {number}", "", ["1", "2"], [], ["A"], "x",
                                     topic="12")
            database.upsert_question("math", "single", f"Уравнение {number}", "", ["1", "2"], [], ["A"], "x",
                                     topic="05")
        database.upsert_question("math", "single", "Тригонометрия", "", ["1", "2"], [], ["A"], "x", topic="03")
        user_id = auth.create_account("Ученик", "s@mail.kz", "password1")
        for _ in range(2):
            attempt_id = ent_logic.build_practice(user_id, "math")
            answers = {}
            for aq in database.get_attempt_questions(attempt_id):
                question = database.get_question(aq.question_id)
                right = question.topic == "05"
                answers[aq.id] = aq.correct if right else [l for l in "AB" if l not in aq.correct][:1]
            database.save_answers(attempt_id, answers)
            ent_logic.finish_attempt(database.get_attempt(attempt_id, user_id))

        strengths = {(item.subject, item.topic): item for item in ent_logic.topic_strengths(user_id)}
        self.assertEqual(strengths[("math", "12")].percent, 0)
        self.assertEqual(strengths[("math", "05")].percent, 100)
        weak = ent_logic.weak_topics(user_id)
        self.assertIn(("math", "12"), [(w.subject, w.topic) for w in weak])
        self.assertNotIn(("math", "05"), [(w.subject, w.topic) for w in weak])
        if ("math", "03") in strengths:  # одно задание — слишком мало, чтобы судить
            self.assertLess(strengths[("math", "03")].questions, ent_logic.MIN_TOPIC_QUESTIONS)
            self.assertNotIn(("math", "03"), [(w.subject, w.topic) for w in weak])
        self.assertEqual(weak[0].label, "12. Арифметическая и геометрическая прогрессии")


class TopicPagesTests(DatabaseTestCase):
    """Отчёт покрытия, тема в форме вопроса и слабые темы в карточке ученика."""

    def setUp(self) -> None:
        """Сервер, администратор, учитель школы и подтверждённый ученик."""
        super().setUp()
        self.server = create_server("127.0.0.1", 0)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        auth.create_account("Админ", "admin@mail.kz", "password1")
        database.set_user_role("admin@mail.kz", database.ROLE_ADMIN)
        self.school = schools.find_or_create_school("Алматы", "12")
        auth.create_account("Учитель", "teacher@mail.kz", "password1")
        database.make_teacher("teacher@mail.kz", self.school)
        self.student = auth.create_account("Ученик", "student@mail.kz", "password1")
        database.set_user_school(self.student, self.school, database.SCHOOL_APPROVED)

    def tearDown(self) -> None:
        """Останавливает сервер."""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    csrf = staticmethod(test_pages.PagesTests.csrf)

    def login(self, email: str) -> Browser:
        """Браузер, вошедший в аккаунт."""
        browser = Browser(self.base_url)
        _, path, _, _ = browser.post("/login", {"login": email, "password": "password1"})
        self.assertTrue(path == "/dashboard" or path.startswith("/teacher"), path)  # учитель — в свой кабинет
        return browser

    def test_topics_report(self) -> None:
        """Отчёт: сводка по предметам и темы предмета, пустые темы выделены; только для админа."""
        database.upsert_question("math", "single", "Прогрессия", "", ["1", "2"], [], ["A"], "x", topic="12")
        admin = self.login("admin@mail.kz")
        status, _, html, _ = admin.get("/admin/topics")
        self.assertEqual(status, 200)
        self.assertIn("Темы ЕНТ и покрытие банка", html)
        self.assertIn("1 из 18", html)
        _, _, html, _ = admin.get("/admin/topics?subject=math")
        self.assertIn("Арифметическая и геометрическая прогрессии", html)
        self.assertIn("<td>100%</td>", html)
        self.assertIn('class="topic-empty"', html)
        self.assertEqual(self.login("student@mail.kz").get("/admin/topics")[0], 403)

    def test_question_form_requires_topic_of_subject(self) -> None:
        """Без темы или с темой другого предмета вопрос не сохраняется."""
        admin = self.login("admin@mail.kz")
        url = "/admin/questions/new"
        _, _, html, _ = admin.get(url)
        self.assertIn("Тема спецификации НЦТ", html)
        self.assertIn('<optgroup label="Математика">', html)
        fields = {"type": "single", "subject": "math", "text": "Новый вопрос", "opt_A": "1", "opt_B": "2",
                  "correct": "A", "explanation": "Потому что."}
        for topic in ("", "77"):
            status, _, html, _ = admin.post(url, {"csrf_token": self.csrf(html), **fields, "topic": topic})
            self.assertEqual(status, 400)
            self.assertIn("Выберите тему спецификации НЦТ", html)
        _, path, _, _ = admin.post(url, {"csrf_token": self.csrf(html), **fields, "topic": "05"})
        self.assertTrue(path.startswith("/admin/questions"), path)
        self.assertEqual(database.list_questions("math")[0].topic, "05")

    def test_weak_topics_in_student_card(self) -> None:
        """Карточка ученика у учителя и кабинет ученика показывают слабые темы."""
        for number in range(10):
            database.upsert_question("math", "single", f"Прогрессия {number}", "", ["1", "2"], [], ["A"], "x",
                                     topic="12")
        attempt_id = ent_logic.build_practice(self.student, "math")
        database.save_answers(attempt_id, {aq.id: [l for l in "AB" if l not in aq.correct][:1]
                                           for aq in database.get_attempt_questions(attempt_id)})
        ent_logic.finish_attempt(database.get_attempt(attempt_id, self.student))

        teacher = self.login("teacher@mail.kz")
        _, _, html, _ = teacher.get(f"/teacher/{self.school}/students/{self.student}")
        self.assertIn("Слабые темы", html)
        self.assertIn("12. Арифметическая и геометрическая прогрессии", html)
        _, _, html, _ = self.login("student@mail.kz").get("/dashboard")
        self.assertIn("Слабые темы ЕНТ", html)
        self.assertIn("12. Арифметическая и геометрическая прогрессии", html)
