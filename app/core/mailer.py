"""Отправка писем: коды подтверждения почты и восстановления пароля."""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol

from app import config

logger = logging.getLogger(__name__)


class MailError(Exception):
    """Письмо не удалось отправить."""


class Sender(Protocol):
    """Отправитель писем."""

    def send(self, to: str, subject: str, body: str) -> None:
        """Отправляет письмо или выбрасывает MailError."""


class SMTPSender:
    """Отправка через SMTP с SSL (smtplib.SMTP_SSL)."""

    def __init__(self, host: str, port: int, user: str, password: str, mail_from: str) -> None:
        """Сохраняет настройки подключения."""
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.mail_from = mail_from

    def send(self, to: str, subject: str, body: str) -> None:
        """Подключается к серверу, входит и отправляет письмо."""
        message = EmailMessage()
        message["From"] = self.mail_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        try:
            with smtplib.SMTP_SSL(
                self.host, self.port, context=ssl.create_default_context(), timeout=20
            ) as smtp:
                smtp.login(self.user, self.password)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as error:
            logger.error("Не удалось отправить письмо на %s: %s", to, error)
            raise MailError(str(error)) from error


class ConsoleSender:
    """Режим разработки: письмо печатается в консоль вместо отправки."""

    def send(self, to: str, subject: str, body: str) -> None:
        """Печатает письмо."""
        print(f"\n── Письмо (SMTP не настроен) ──\nКому: {to}\nТема: {subject}\n\n{body}\n", flush=True)


def _default_sender() -> Sender:
    if config.SMTP_HOST and config.SMTP_USER and config.SMTP_PASSWORD:
        return SMTPSender(config.SMTP_HOST, config.SMTP_PORT, config.SMTP_USER,
                          config.SMTP_PASSWORD, config.MAIL_FROM)
    return ConsoleSender()


_sender: Sender | None = None


def set_sender(sender: Sender | None) -> None:
    """Подменяет отправителя (тесты). None — вернуть отправителя по настройкам."""
    global _sender
    _sender = sender


def send(to: str, subject: str, body: str) -> None:
    """Отправляет письмо текущим отправителем (MailError — не получилось)."""
    global _sender
    if _sender is None:
        _sender = _default_sender()
    _sender.send(to, subject, body)
