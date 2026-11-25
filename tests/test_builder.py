"""Тесты сборки пробного ЕНТ и тренировки, завершения и истечения времени."""

import config
from app import auth, database, ent_logic
from tests.base import DatabaseTestCase


class BuildTests(DatabaseTestCase):
    """Сборка теста по квотам из config."""

    def setUp(self) -> None:
        """Создаёт пользователя для попыток."""
        super().setUp()
        self.user_id = auth.register_user("Ерлан", "erlan@mail.kz", "password1", "password1")

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

    def test_partial_bank_reports_shortage(self) -> None:
        """Если вопросов мало, тест собирается из имеющихся, а нехватка записывается."""
        self.add_questions("kz_history", config.SINGLE, 5)
        self.add_questions("math", config.MATCHING, 1)
        attempt_id = ent_logic.build_mock(self.user_id, 0)
        attempt = database.get_attempt(attempt_id, self.user_id)
        assert attempt is not None

        self.assertEqual(len(database.get_attempt_questions(attempt_id)), 6)
        self.assertEqual(attempt.max_score, 5 * 1 + 1 * 2)
        history = next(item for item in attempt.shortage if item["subject"] == "kz_history")
        self.assertEqual((history["have"], history["need"]), (5, 20))

        counts = database.question_counts()
        self.assertEqual(ent_logic.availability("kz_history", counts).have, 5)
        self.assertFalse(ent_logic.availability("math", counts).is_complete)

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


class FinishTests(DatabaseTestCase):
    """Завершение попытки и автоматическое завершение по времени."""

    def setUp(self) -> None:
        """Готовит пользователя и попытку с ответами."""
        super().setUp()
        self.user_id = auth.register_user("Асель", "asel@mail.kz", "password1", "password1")
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
                answers[aq.id] = ["A"] if len(answers) < 2 else ["B"]  # 2 верных, 1 неверный
            else:
                answers[aq.id] = ["A", "C"]  # одна ошибка → 1 балл
        database.save_answers(self.attempt_id, answers)

        ent_logic.finish_attempt(self.load(), now=2_000.0)
        attempt = self.load()
        self.assertTrue(attempt.is_finished)
        self.assertEqual(attempt.score, 2 + 1)
        self.assertEqual(attempt.finished_at, 2_000.0)

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
