"""Тесты генераторов задач и выбора «сначала новые вопросы»."""

import random
import unittest
from fractions import Fraction

import config
import seed
from app import auth, database, ent_logic, generators
from app.generators.common import num, plural, space_thousands
from app.question_bank import validate_question
from tests.base import DatabaseTestCase


def _correct_values(question: dict) -> list[str]:
    """Тексты правильных вариантов вопроса."""
    return [question["options"][config.OPTION_LETTERS.index(letter)] for letter in question["correct"]]


class FormatTests(unittest.TestCase):
    """Оформление чисел по-русски."""

    def test_num(self) -> None:
        self.assertEqual(num(1234.5), "1 234,5")
        self.assertEqual(num(-3), "−3")
        self.assertEqual(num(2.0), "2")
        self.assertEqual(num(Fraction(-1, 2)), "−1/2")
        self.assertEqual(num(0.0625, 4), "0,0625")

    def test_plural(self) -> None:
        self.assertEqual([plural(n, "место", "места", "мест") for n in (1, 3, 5, 11, 21, 24)],
                         ["место", "места", "мест", "мест", "место", "места"])

    def test_space_thousands(self) -> None:
        self.assertEqual(space_thousands("F = 3122 Н, x²=10000"), "F = 3 122 Н, x²=10 000")
        self.assertEqual(space_thousands("0,0625 и 1 234"), "0,0625 и 1 234")


class FactTests(unittest.TestCase):
    """Шаблоны по таблицам фактов."""

    def test_century_boundaries(self) -> None:
        from app.generators.facts import _century
        cases = {800: "VIII", 801: "IX", 1800: "XVIII", 1801: "XIX", 1900: "XIX", 1901: "XX", 2001: "XXI"}
        for year, expected in cases.items():
            self.assertEqual(_century((year - 1) // 100 * 100), expected, year)

    def test_every_profile_subject_fills_its_quota(self) -> None:
        for subject in generators.SUBJECT_TEMPLATES:
            for qtype, need in config.SUBJECTS[subject].quota:
                with self.subTest(subject=subject, qtype=qtype):
                    self.assertGreaterEqual(len(generators.generate(subject, qtype, need * 4)), need * 4)


class GeneratorTests(unittest.TestCase):
    """Каждый шаблон выдаёт корректные вопросы в формате ЕНТ."""

    def test_every_template_makes_valid_questions(self) -> None:
        rng = random.Random(1)
        for subject, templates in generators.SUBJECT_TEMPLATES.items():
            for qtype, functions in templates.items():
                for function in functions:
                    made = 0
                    for _ in range(300):
                        try:
                            question = function(rng)
                        except generators.SkipQuestion:
                            continue
                        made += 1
                        with self.subTest(template=function.__name__):
                            self.assertEqual(validate_question(question), [])
                            self.assertEqual(question["type"], qtype)
                            options = question["options"]
                            self.assertEqual(len(set(options)), len(options))
                            if qtype in (config.SINGLE, config.CONTEXT):
                                self.assertEqual(len(options), 4)
                            if qtype == config.MULTIPLE:
                                self.assertEqual(len(options), 6)
                                self.assertTrue(1 <= len(question["correct"]) <= 3)
                            # Объяснение не ссылается на буквы — варианты перемешиваются.
                            self.assertNotRegex(question["explanation"], r"(вариант|ответ) [A-H]\b")
                    self.assertGreater(made, 50, function.__name__)

    def test_generate_is_reproducible_and_unique(self) -> None:
        first = generators.generate("math", config.SINGLE, 300)
        second = generators.generate("math", config.SINGLE, 300)
        self.assertEqual(first, second)
        texts = [q["text"] for q in first]
        self.assertEqual(len(texts), len(set(texts)))
        self.assertEqual(len(first), 300)

    def test_answers_are_computed(self) -> None:
        """Выборочная независимая проверка: правильный вариант действительно верен."""
        for question in generators.generate("math", config.SINGLE, 600):
            text = question["text"]
            answer = _correct_values(question)[0]
            if text.startswith("Найдите ") and "% от числа" in text:
                percent, number = text.removeprefix("Найдите ").removesuffix(".").split("% от числа ")
                expected = int(number.replace(" ", "")) * int(percent) // 100
                self.assertEqual(answer.replace(" ", ""), str(expected), text)
        for question in generators.generate("physics", config.SINGLE, 600):
            if question["text"].startswith("Резисторы") and "последовательно" in question["text"]:
                parts = question["text"].split()
                r1, r2 = int(parts[1]), int(parts[4])
                self.assertEqual(_correct_values(question)[0], f"{r1 + r2} Ом")


class SeedAndSelectionTests(DatabaseTestCase):
    """Загрузка сгенерированных задач и выбор невиденных вопросов."""

    def test_seed_fills_generated_subjects(self) -> None:
        _, errors = seed.seed()
        self.assertEqual(errors, [])
        counts = database.question_counts()
        for subject in generators.SUBJECT_TEMPLATES:
            if subject in config.COMPULSORY_CODES:
                continue
            for qtype, need in config.SUBJECTS[subject].quota:
                self.assertGreaterEqual(counts[(subject, qtype)], need * 3, subject)
        self.assertGreaterEqual(counts[("math_literacy", config.SINGLE)], 300)
        self.assertGreaterEqual(counts[("kz_history", config.SINGLE)], 150)
        # Полный пробный ЕНТ (120 заданий) собирается для каждой пары профильных предметов.
        for index, pair in enumerate(config.PROFILE_PAIRS):
            self.assertEqual(ent_logic.pair_question_count(index, counts), config.MOCK_TOTAL_QUESTIONS, pair)
        # Повторный запуск не создаёт дубликатов.
        seed.seed()
        self.assertEqual(database.question_counts(), counts)

    def test_unseen_questions_come_first(self) -> None:
        self.add_questions("physics", config.SINGLE, 30)
        user_id = auth.create_account("Асель", "asel@mail.kz", "password1")
        seen: set[int] = set()
        for _ in range(3):  # 3 тренировки по 10 заданий = все 30 вопросов без повторов
            attempt_id = ent_logic.build_practice(user_id, "physics")
            ids = {aq.question_id for aq in database.get_attempt_questions(attempt_id)}
            self.assertEqual(len(ids), config.PRACTICE_QUESTION_COUNT)
            self.assertFalse(ids & seen, "вопрос повторился, хотя есть невиденные")
            seen |= ids
        self.assertEqual(len(seen), 30)

    def test_other_users_history_does_not_matter(self) -> None:
        self.add_questions("physics", config.SINGLE, 10)
        first = auth.create_account("Тимур", "timur@mail.kz", "password1")
        second = auth.create_account("Жанна", "zhanna@mail.kz", "password1")
        ent_logic.build_practice(first, "physics")
        attempt_id = ent_logic.build_practice(second, "physics")
        self.assertEqual(len(database.get_attempt_questions(attempt_id)), 10)


if __name__ == "__main__":
    unittest.main()
