"""Общая основа тестов: временная база данных и быстрые настройки хеширования."""

import re
import tempfile
import unittest
from pathlib import Path

from app import config
from app.core import database, mailer, notifications

CODE_RE = re.compile(r"\b(\d{6})\b")


class FakeMailer:
    """Отправитель писем для тестов: письма складываются в список, в сеть ничего не уходит."""

    active: "FakeMailer | None" = None  # текущий (для помощников, у которых нет self.mail)

    def __init__(self) -> None:
        """Пустой ящик; fail = True — имитировать сбой SMTP."""
        self.messages: list[tuple[str, str, str]] = []
        self.fail = False

    def send(self, to: str, subject: str, body: str) -> None:
        """Запоминает письмо (или выбрасывает MailError, если fail)."""
        if self.fail:
            raise mailer.MailError("SMTP недоступен")
        self.messages.append((to, subject, body))

    def last_code(self, to: str) -> str:
        """6-значный код из последнего письма на этот адрес."""
        for address, _, body in reversed(self.messages):
            if address == to:
                match = CODE_RE.search(body)
                assert match is not None, body
                return match.group(1)
        raise AssertionError(f"писем на {to} не было")


class FakeTelegram:
    """Отправитель уведомлений в Telegram для тестов: сообщения складываются в список."""

    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.fail = False

    def call(self, method: str, **params: object) -> dict:
        if self.fail:
            raise OSError("Telegram недоступен")
        self.messages.append({"method": method, **params})
        return {}


class DatabaseTestCase(unittest.TestCase):
    """Каждый тест работает с новой пустой базой во временной папке."""

    def setUp(self) -> None:
        """Создаёт временную базу, подменяет почту и уменьшает число итераций PBKDF2."""
        self._tmp = tempfile.TemporaryDirectory()
        database.configure(Path(self._tmp.name) / "test.sqlite3")
        database.init_db()
        self._iterations = config.PBKDF2_ITERATIONS
        config.PBKDF2_ITERATIONS = 1_000
        self.mail = FakeMailer()
        FakeMailer.active = self.mail
        mailer.set_sender(self.mail)
        # Уведомления никогда не уходят в настоящий Telegram (в .env может быть токен).
        self.telegram = FakeTelegram()
        notifications.set_sender(self.telegram)

    def tearDown(self) -> None:
        """Возвращает настройки и удаляет временную базу."""
        mailer.set_sender(None)
        notifications.set_sender(None)
        FakeMailer.active = None
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
                subject, qtype, f"{subject} {qtype} №{number}", context, options, left, correct,
                explanation=f"Объяснение к заданию №{number}.",
            )

    def fill_full_bank(self, subjects: list[str]) -> None:
        """Заполняет банк так, чтобы по предметам хватило заданий на полный ЕНТ."""
        for code in subjects:
            for qtype, need in config.SUBJECTS[code].quota:
                self.add_questions(code, qtype, need)
