"""Общая основа тестов: временная база данных и быстрые настройки хеширования."""

import tempfile
import unittest
from pathlib import Path

import config
from app import database


class DatabaseTestCase(unittest.TestCase):
    """Каждый тест работает с новой пустой базой во временной папке."""

    def setUp(self) -> None:
        """Создаёт временную базу и уменьшает число итераций PBKDF2 для скорости."""
        self._tmp = tempfile.TemporaryDirectory()
        database.configure(Path(self._tmp.name) / "test.sqlite3")
        database.init_db()
        self._iterations = config.PBKDF2_ITERATIONS
        config.PBKDF2_ITERATIONS = 1_000

    def tearDown(self) -> None:
        """Возвращает настройки и удаляет временную базу."""
        config.PBKDF2_ITERATIONS = self._iterations
        database.configure(config.DATABASE_PATH)
        self._tmp.cleanup()

    @staticmethod
    def add_questions(subject: str, qtype: str, count: int) -> None:
        """Добавляет в банк count простых вопросов нужного типа (правильный ответ — A)."""
        for number in range(count):
            options = ["верно", "неверно 1", "неверно 2", "неверно 3"]
            left: list[str] = []
            correct = ["A"]
            context = ""
            if qtype == config.MATCHING:
                left = ["строка 1", "строка 2"]
                correct = ["A", "B"]
            elif qtype == config.MULTIPLE:
                options = ["да 1", "нет 1", "да 2", "нет 2", "да 3", "нет 3"]
                correct = ["A", "C", "E"]
            elif qtype == config.CONTEXT:
                context = "Небольшой текст для задания."
            database.upsert_question(
                subject, qtype, f"{subject} {qtype} №{number}", context, options, left, correct
            )

    def fill_full_bank(self, subjects: list[str]) -> None:
        """Заполняет банк так, чтобы по предметам хватило заданий на полный ЕНТ."""
        for code in subjects:
            for qtype, need in config.SUBJECTS[code].quota:
                self.add_questions(code, qtype, need)
