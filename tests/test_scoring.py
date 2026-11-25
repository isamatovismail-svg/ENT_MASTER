"""Тесты подсчёта баллов и разбора ответов из формы."""

import unittest

import config
from app import database, ent_logic
from app.database import AttemptQuestion


def make_question(
    qtype: str, correct: list[str], options: int = 4, left: int = 0
) -> AttemptQuestion:
    """Создаёт задание попытки для тестов без обращения к базе."""
    return AttemptQuestion(
        id=7, attempt_id=1, question_id=1, subject="math", position=1, qtype=qtype,
        text="?", context="", options=[f"вариант {i}" for i in range(options)],
        left=[f"строка {i}" for i in range(left)], correct=correct, answer=None, points=0,
    )


class ScoreTests(unittest.TestCase):
    """Правила начисления баллов для всех типов заданий."""

    def test_single_and_context(self) -> None:
        """Один ответ: 1 балл за верный, 0 за неверный или пустой."""
        for qtype in (config.SINGLE, config.CONTEXT):
            self.assertEqual(ent_logic.score_answer(qtype, ["B"], ["B"]), 1)
            self.assertEqual(ent_logic.score_answer(qtype, ["B"], ["A"]), 0)
            self.assertEqual(ent_logic.score_answer(qtype, ["B"], None), 0)

    def test_multiple(self) -> None:
        """Несколько ответов: 2 без ошибок, 1 при одной ошибке, 0 при двух и более."""
        correct = ["A", "C", "E"]
        score = ent_logic.score_answer
        self.assertEqual(score(config.MULTIPLE, correct, ["A", "C", "E"]), 2)
        # Пропущен один верный вариант — одна ошибка.
        self.assertEqual(score(config.MULTIPLE, correct, ["A", "C"]), 1)
        # Выбран один лишний вариант — одна ошибка.
        self.assertEqual(score(config.MULTIPLE, correct, ["A", "C", "E", "F"]), 1)
        # Один лишний и два пропущенных — три ошибки.
        self.assertEqual(score(config.MULTIPLE, correct, ["A", "B"]), 0)
        self.assertEqual(score(config.MULTIPLE, correct, ["A"]), 0)
        self.assertEqual(score(config.MULTIPLE, correct, None), 0)
        self.assertEqual(score(config.MULTIPLE, ["A"], []), 0)  # пустой ответ — не «одна ошибка»

    def test_matching(self) -> None:
        """Соответствие: 2 без ошибок, 1 при одной неверной строке, 0 при двух."""
        score = ent_logic.score_answer
        self.assertEqual(score(config.MATCHING, ["B", "D"], ["B", "D"]), 2)
        self.assertEqual(score(config.MATCHING, ["B", "D"], ["B", "A"]), 1)
        self.assertEqual(score(config.MATCHING, ["B", "D"], ["B", ""]), 1)
        self.assertEqual(score(config.MATCHING, ["B", "D"], ["A", "A"]), 0)

    def test_full_mock_max_is_140(self) -> None:
        """Квоты config дают ровно 120 заданий и 140 баллов."""
        self.assertEqual(config.MOCK_TOTAL_QUESTIONS, 120)
        self.assertEqual(config.MOCK_MAX_SCORE, 140)
        self.assertEqual(config.SUBJECTS["math"].max_score, 50)
        self.assertEqual(config.SUBJECTS["kz_history"].max_score, 20)


class ParseAnswerTests(unittest.TestCase):
    """Разбор ответов из HTML-формы, включая подделанные значения."""

    def test_single(self) -> None:
        """Берётся только допустимая буква; пустое значение — нет ответа."""
        question = make_question(config.SINGLE, ["A"])
        self.assertEqual(ent_logic.parse_answer(question, {"q7": ["C"]}), ["C"])
        self.assertIsNone(ent_logic.parse_answer(question, {"q7": [""]}))
        self.assertIsNone(ent_logic.parse_answer(question, {"q7": ["Z"]}))
        self.assertIsNone(ent_logic.parse_answer(question, {}))

    def test_multiple(self) -> None:
        """Буквы сортируются, дубликаты и мусор отбрасываются."""
        question = make_question(config.MULTIPLE, ["A"], options=6)
        form = {"q7": ["E", "A", "A", "X", "<b>"]}
        self.assertEqual(ent_logic.parse_answer(question, form), ["A", "E"])

    def test_matching(self) -> None:
        """Каждая строка соответствия читается из своего поля."""
        question = make_question(config.MATCHING, ["B", "D"], left=2)
        parse = ent_logic.parse_answer
        self.assertEqual(parse(question, {"q7_0": ["B"], "q7_1": ["D"]}), ["B", "D"])
        self.assertEqual(parse(question, {"q7_0": ["B"], "q7_1": [""]}), ["B", ""])
        self.assertIsNone(ent_logic.parse_answer(question, {"q7_0": [""], "q7_1": ["Q"]}))

    def test_question_state(self) -> None:
        """Состояние для подсветки: полный балл, частичный или ноль."""
        question = make_question(config.MULTIPLE, ["A", "C"], options=6)
        for points, state in ((2, "ok"), (1, "partial"), (0, "wrong")):
            question.points = points
            self.assertEqual(ent_logic.question_state(question), state)


class OptionOrderTests(unittest.TestCase):
    """Перестановка вариантов: правильный ответ остаётся тем же текстом."""

    def test_single_correct_follows_its_text(self) -> None:
        """Правильный вариант «B» после перестановки получает новую букву."""
        options, correct = database._apply_option_order(
            ["a", "b", "c", "d"], ["B"], config.SINGLE, "[3, 1, 0, 2]"
        )
        self.assertEqual(options, ["d", "b", "a", "c"])
        self.assertEqual(correct, ["B"])
        options, correct = database._apply_option_order(
            ["a", "b", "c", "d"], ["B"], config.SINGLE, "[1, 0, 2, 3]"
        )
        self.assertEqual((options[0], correct), ("b", ["A"]))

    def test_multiple_and_matching(self) -> None:
        """У нескольких ответов буквы сортируются, у соответствия — порядок строк сохраняется."""
        options, correct = database._apply_option_order(
            ["a", "b", "c", "d"], ["A", "C"], config.MULTIPLE, "[2, 3, 0, 1]"
        )
        self.assertEqual(sorted(options[ord(x) - 65] for x in correct), ["a", "c"])
        self.assertEqual(correct, sorted(correct))
        options, correct = database._apply_option_order(
            ["a", "b", "c", "d"], ["B", "A"], config.MATCHING, "[2, 3, 0, 1]"
        )
        self.assertEqual([options[ord(x) - 65] for x in correct], ["b", "a"])

    def test_bad_order_is_ignored(self) -> None:
        """Пустой или битый порядок — остаётся исходный."""
        for order in (None, "[0, 0, 1, 2]", "[0, 1]", "{}"):
            self.assertEqual(
                database._apply_option_order(["a", "b", "c", "d"], ["B"], config.SINGLE, order),
                (["a", "b", "c", "d"], ["B"]),
            )

if __name__ == "__main__":
    unittest.main()
