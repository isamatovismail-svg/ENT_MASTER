"""Тесты сборки пробного ЕНТ и тренировки, времени, перемешивания и завершения."""

import sqlite3

import config
from app import auth, database, ent_logic
from tests.base import DatabaseTestCase


class BuildTests(DatabaseTestCase):
    """Сборка теста по квотам из config."""

    def setUp(self) -> None:
        """Создаёт пользователя для попыток."""
        super().setUp()
        self.user_id = auth.create_account("Ерлан", "erlan@mail.kz", "password1")

    def test_full_mock_has_120_questions_and_140_points(self) -> None:
        """При полном банке собирается ровно 120 заданий на 140 баллов без нехватки."""
        subjects = ent_logic.mock_subjects(0)
        self.fill_full_bank(subjects)
        attempt_id = ent_logic.build_mock(self.user_id, 0)
        attempt = database.get_attempt(attempt_id, self.user_id)
        assert attempt is not None

        questions = database.get_attempt_questions(attempt_id)
        self.assertEqual(len(questions), 120)
        self.assertEqual(attempt.max_score, 140)
        self.assertEqual(attempt.shortage, [])
        self.assertEqual(
            attempt.subjects,
            ["kz_history", "math_literacy", "reading_literacy", "math", "physics"],
        )
        self.assertAlmostEqual(
            attempt.deadline - attempt.started_at, config.MOCK_DURATION_MINUTES * 60
        )
        # Порядок: сначала все задания первого предмета, затем второго и т.д.
        self.assertEqual([aq.subject for aq in questions[:20]], ["kz_history"] * 20)
        self.assertEqual(len({aq.question_id for aq in questions}), 120)

    def test_questions_and_options_are_shuffled(self) -> None:
        """Задания внутри предмета и варианты ответа перемешаны, правильный ответ не теряется."""
        subjects = ent_logic.mock_subjects(0)
        self.fill_full_bank(subjects)
        orders = []
        for _ in range(3):
            attempt_id = ent_logic.build_mock(self.user_id, 0)
            questions = database.get_attempt_questions(attempt_id)
            orders.append([aq.question_id for aq in questions])
            for aq in questions:
                # В тестовом банке правильный вариант single — всегда «верно».
                if aq.qtype == config.SINGLE:
                    self.assertEqual(aq.options[config.OPTION_LETTERS.index(aq.correct[0])], "верно")
                if aq.qtype == config.MULTIPLE:
                    chosen = {aq.options[config.OPTION_LETTERS.index(x)] for x in aq.correct}
                    self.assertEqual(chosen, {"да 1", "да 2", "да 3"})
            with database.connect() as connection:
                connection.execute("UPDATE attempts SET status = 'finished'")
        # Вероятность случайно получить три одинаковых порядка из 120 заданий ничтожна.
        self.assertGreater(len({tuple(order) for order in orders}), 1)
        # Типы внутри профильного предмета больше не идут блоками «25 single, затем 5 context…».
        math_types = [aq.qtype for aq in questions if aq.subject == "math"]
        self.assertNotEqual(math_types, sorted(math_types, key=config.QUESTION_TYPES.index))

    def test_mock_duration_is_proportional(self) -> None:
        """Время = 240 мин × (заданий / 120), округление вверх."""
        self.assertEqual(ent_logic.mock_duration_minutes(120), 240)
        self.assertEqual(ent_logic.mock_duration_minutes(66), 132)
        self.assertEqual(ent_logic.mock_duration_minutes(7), 14)
        self.assertEqual(ent_logic.mock_duration_minutes(1), 2)
        # При 240 / 120 результат всегда целый; округление вверх важно, если поменять config.
        original = config.MOCK_DURATION_MINUTES
        config.MOCK_DURATION_MINUTES = 100
        try:
            self.assertEqual(ent_logic.mock_duration_minutes(7), 6)  # 100 × 7 / 120 = 5,83 → 6
        finally:
            config.MOCK_DURATION_MINUTES = original

    def test_partial_bank_reports_shortage(self) -> None:
        """Если вопросов мало, тест собирается из имеющихся, а нехватка записывается."""
        self.add_questions("kz_history", config.SINGLE, 5)
        self.add_questions("math", config.MATCHING, 1)
        attempt_id = ent_logic.build_mock(self.user_id, 0)
        attempt = database.get_attempt(attempt_id, self.user_id)
        assert attempt is not None

        self.assertEqual(len(database.get_attempt_questions(attempt_id)), 6)
        self.assertEqual(attempt.max_score, 5 * 1 + 1 * 2)
        # 6 заданий из 120 → 240 × 6 / 120 = 12 минут.
        self.assertAlmostEqual(attempt.deadline - attempt.started_at, 12 * 60)
        history = next(item for item in attempt.shortage if item["subject"] == "kz_history")
        self.assertEqual((history["have"], history["need"]), (5, 20))

        counts = database.question_counts()
        self.assertEqual(ent_logic.availability("kz_history", counts).have, 5)
        math = ent_logic.availability("math", counts)
        self.assertLess(math.have, math.need)

    def test_empty_bank_and_bad_pair(self) -> None:
        """Пустой банк и неверная пара дают понятную ошибку, а не падение."""
        with self.assertRaises(ent_logic.TestBuildError):
            ent_logic.build_mock(self.user_id, 0)
        with self.assertRaises(ent_logic.TestBuildError):
            ent_logic.build_mock(self.user_id, 99)
        with self.assertRaises(ent_logic.TestBuildError):
            ent_logic.build_practice(self.user_id, "no_such_subject")

    def test_practice_has_ten_questions_of_one_subject(self) -> None:
        """Тренировка — 10 случайных заданий одного предмета без ограничения времени."""
        self.add_questions("physics", config.SINGLE, 12)
        self.add_questions("physics", config.MULTIPLE, 3)
        attempt_id = ent_logic.build_practice(self.user_id, "physics")
        attempt = database.get_attempt(attempt_id, self.user_id)
        assert attempt is not None
        questions = database.get_attempt_questions(attempt_id)
        self.assertEqual(len(questions), config.PRACTICE_QUESTION_COUNT)
        self.assertTrue(all(aq.subject == "physics" for aq in questions))
        self.assertIsNone(attempt.deadline)
        expected_max = sum(ent_logic.question_max_points(aq.qtype) for aq in questions)
        self.assertEqual(attempt.max_score, expected_max)

    def test_practice_check_answer_once(self) -> None:
        """Ответ в тренировке оценивается сразу и не меняется при повторной отправке."""
        self.add_questions("physics", config.MULTIPLE, 2)
        attempt_id = ent_logic.build_practice(self.user_id, "physics")
        attempt = database.get_attempt(attempt_id, self.user_id)
        assert attempt is not None
        aq = database.get_attempt_questions(attempt_id)[0]
        right = {f"q{aq.id}": aq.correct}
        self.assertTrue(ent_logic.check_practice_answer(attempt, aq, right))
        aq = database.get_attempt_questions(attempt_id)[0]
        self.assertTrue(aq.checked)
        self.assertEqual((aq.points, aq.answer), (2, aq.correct))
        self.assertTrue(aq.explanation.startswith("Объяснение к заданию"))
        # Повторная отправка (например, «Назад» в браузере) ничего не меняет.
        self.assertFalse(ent_logic.check_practice_answer(attempt, aq, {}))
        self.assertEqual(database.get_attempt_questions(attempt_id)[0].points, 2)

        ent_logic.finish_attempt(attempt)
        finished = database.get_attempt(attempt_id, self.user_id)
        assert finished is not None
        self.assertEqual(finished.score, 2)  # второе задание без ответа — 0 баллов

        strengths = ent_logic.subject_strengths(self.user_id)
        self.assertEqual([(s.code, s.percent, s.questions) for s in strengths], [("physics", 50, 2)])


class MigrationTests(DatabaseTestCase):
    """init_db добавляет новые колонки в базу, созданную старой версией сайта."""

    def test_old_database_gets_new_columns(self) -> None:
        """Старые таблицы без explanation/option_order_json/checked обновляются без потери данных."""
        path = self._tmp.name + "/old.sqlite3"
        old = sqlite3.connect(path)
        old.executescript(
            "CREATE TABLE questions (id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT NOT NULL,"
            " qtype TEXT NOT NULL, text TEXT NOT NULL, context TEXT NOT NULL DEFAULT '',"
            " options_json TEXT NOT NULL, left_json TEXT NOT NULL DEFAULT '[]',"
            " correct_json TEXT NOT NULL, UNIQUE (subject, text));"
            "CREATE TABLE attempt_questions (id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " attempt_id INTEGER NOT NULL, question_id INTEGER NOT NULL, subject TEXT NOT NULL,"
            " position INTEGER NOT NULL, answer_json TEXT, points INTEGER NOT NULL DEFAULT 0,"
            " UNIQUE (attempt_id, question_id));"
            "INSERT INTO questions (subject, qtype, text, options_json, correct_json)"
            " VALUES ('math', 'single', 'старый вопрос', '[\"1\", \"2\"]', '[\"A\"]');"
            "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,"
            " login TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, salt TEXT NOT NULL,"
            " created_at REAL NOT NULL);"
            "INSERT INTO users (name, login, password_hash, salt, created_at)"
            " VALUES ('Старый', 'old@mail.kz', 'h', 's', 0);"
        )
        old.commit()
        old.close()

        database.configure(path)
        database.init_db()
        database.init_db()  # повторный запуск безопасен
        with database.connect() as connection:
            for table, column in (("users", "email_verified"),
                                  ("users", "phone"),
                                  ("questions", "explanation"),
                                  ("questions", "edited_by_admin"),
                                  ("attempt_questions", "option_order_json"),
                                  ("attempt_questions", "checked")):
                columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
                self.assertIn(column, columns)
            row = connection.execute("SELECT text, explanation FROM questions").fetchone()
            user = connection.execute("SELECT email_verified, phone FROM users").fetchone()
        self.assertEqual((row["text"], row["explanation"]), ("старый вопрос", ""))
        # Аккаунты, созданные до подтверждения почты, считаются подтверждёнными.
        self.assertEqual((user["email_verified"], user["phone"]), (1, None))


class FinishTests(DatabaseTestCase):
    """Завершение попытки и автоматическое завершение по времени."""

    def setUp(self) -> None:
        """Готовит пользователя и попытку с ответами."""
        super().setUp()
        self.user_id = auth.create_account("Асель", "asel@mail.kz", "password1")
        self.add_questions("kz_history", config.SINGLE, 3)
        self.add_questions("math", config.MULTIPLE, 1)
        self.attempt_id = ent_logic.build_mock(self.user_id, 0, now=1_000.0)

    def load(self) -> database.Attempt:
        """Перечитывает попытку из базы."""
        attempt = database.get_attempt(self.attempt_id, self.user_id)
        assert attempt is not None
        return attempt

    def test_finish_scores_saved_answers(self) -> None:
        """Сохранённые ответы оцениваются, повторное завершение ничего не меняет."""
        questions = database.get_attempt_questions(self.attempt_id)
        answers = {}
        for aq in questions:
            if aq.qtype == config.SINGLE:
                wrong = next(x for x in "ABCD" if x != aq.correct[0])
                answers[aq.id] = aq.correct if len(answers) < 2 else [wrong]  # 2 верных, 1 неверный
            else:
                answers[aq.id] = aq.correct[:2]  # пропущен один верный вариант → 1 балл
        database.save_answers(self.attempt_id, answers)

        ent_logic.finish_attempt(self.load(), now=1_100.0)
        attempt = self.load()
        self.assertTrue(attempt.is_finished)
        self.assertEqual(attempt.score, 2 + 1)
        self.assertEqual(attempt.finished_at, 1_100.0)

        # После завершения ответы менять нельзя.
        database.save_answers(self.attempt_id, {aq.id: None for aq in questions})
        self.assertTrue(all(aq.answer for aq in database.get_attempt_questions(self.attempt_id)))

    def test_expired_attempt_finishes_at_deadline(self) -> None:
        """По истечении времени попытка завершается, временем окончания считается дедлайн."""
        attempt = self.load()
        assert attempt.deadline is not None
        self.assertFalse(ent_logic.is_expired(attempt, now=attempt.deadline - 1))
        self.assertTrue(ent_logic.is_expired(attempt, now=attempt.deadline + 1))
        self.assertEqual(ent_logic.remaining_seconds(attempt, now=attempt.deadline - 90), 90)

        ent_logic.finish_expired_attempts(self.user_id, now=attempt.deadline + 500)
        finished = self.load()
        self.assertTrue(finished.is_finished)
        self.assertEqual(finished.finished_at, attempt.deadline)
