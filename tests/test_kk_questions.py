"""Этап 10: проверка казахского перевода вопросов (data/questions/kk/*.json).

Перевод сверяется с русским оригиналом вопрос за вопросом (порядок одинаковый):
- тот же тип, тема и правильный ответ (буква / набор букв / буквы соответствия);
- столько же вариантов и строк соответствия, варианты не повторяются;
- числа и формулы не изменились: варианты без слов совпадают символ в символ,
  а числа и латинские формулы в тексте, контексте, вариантах и строках — те же.
"""

import json
import re
import unittest
from collections import Counter

import config
from app.question_bank import validate_question

KK_DIR = config.QUESTIONS_DIR / "kk"
CYRILLIC = re.compile("[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# Формула: латинская буква и всё, что к ней приклеено (x², f(x), log₃, H₂SO₄, sin).
FORMULA = re.compile(r"[A-Za-z][A-Za-z0-9²³⁴⁵⁶⁷⁸⁹⁰¹ⁿ₀₁₂₃₄₅₆₇₈₉′()^]*")


def _numbers(*parts: str) -> Counter:
    return Counter(n.replace(",", ".") for part in parts for n in NUMBER.findall(part))


def _clean(token: str) -> str:
    """Скобка, закрывающая окружающий текст, — не часть формулы: «(система AB0)» → «AB0»."""
    while token.endswith(")") and token.count("(") < token.count(")"):
        token = token[:-1]
    return token


def _formulas(*parts: str) -> Counter:
    return Counter(_clean(f) for part in parts for f in FORMULA.findall(part))


def pairs() -> list[tuple[str, dict, dict]]:
    """(файл, русский вопрос, казахский вопрос) для всех переведённых файлов."""
    result = []
    for path in sorted(KK_DIR.glob("*.json")):
        ru_data = json.loads((config.QUESTIONS_DIR / path.name).read_text(encoding="utf-8"))
        kk_data = json.loads(path.read_text(encoding="utf-8"))
        assert ru_data["subject"] == kk_data["subject"], path.name
        assert len(ru_data["questions"]) == len(kk_data["questions"]), path.name
        result += [(path.name, ru, kk) for ru, kk in zip(ru_data["questions"], kk_data["questions"])]
    return result


class KazakhTranslationTests(unittest.TestCase):

    def test_files_translated(self) -> None:
        names = {p.name for p in KK_DIR.glob("*.json")}
        for subject in config.SUBJECTS:
            if subject in config.SUBJECT_OWN_LANGUAGE or subject in config.SHARED_LANGUAGE_SUBJECTS:
                self.assertNotIn(f"{subject}.json", names)  # свой язык / общий — не переводятся
            else:
                self.assertIn(f"{subject}.json", names)

    def test_same_answers_numbers_and_formulas(self) -> None:
        for name, ru, kk in pairs():
            where = f"{name}: {ru['text'][:50]}"
            with self.subTest(where):
                subject = json.loads((KK_DIR / name).read_text(encoding="utf-8"))["subject"]
                self.assertEqual(validate_question(kk, subject), [])
                for key in ("type", "topic", "correct"):
                    self.assertEqual(ru.get(key), kk.get(key), key)
                self.assertEqual(len(ru["options"]), len(kk["options"]))
                self.assertEqual(len(ru.get("left", [])), len(kk.get("left", [])))
                self.assertEqual(len(set(kk["options"])), len(kk["options"]), "варианты повторяются")
                self.assertTrue(CYRILLIC.search(kk["text"]), "текст не переведён")
                self.assertNotEqual(ru["text"], kk["text"])
                for ru_option, kk_option in zip(ru["options"], kk["options"]):
                    if not CYRILLIC.search(ru_option):
                        self.assertEqual(ru_option, kk_option, "вариант без слов должен совпадать")
                ru_parts = [ru["text"], ru.get("context", ""), *ru["options"], *ru.get("left", [])]
                kk_parts = [kk["text"], kk.get("context", ""), *kk["options"], *kk.get("left", [])]
                self.assertEqual(_numbers(*ru_parts), _numbers(*kk_parts), "числа изменились")
                self.assertEqual(_formulas(*ru_parts), _formulas(*kk_parts), "формулы изменились")
                self.assertEqual(set(_numbers(ru["explanation"])), set(_numbers(kk["explanation"])),
                                 "числа в объяснении изменились")


if __name__ == "__main__":
    unittest.main()
