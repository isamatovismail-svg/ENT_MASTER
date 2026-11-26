"""Тесты оповещений главному администратору в Telegram и отправки резервных копий.

В сеть ничего не уходит: вместо Bot API — заглушка FakeSender, вместо urlopen — фальшивый opener.
"""

import io
import json
import threading
from pathlib import Path
from unittest import mock

import backup
import config
import notify
from app import alerts, auth, database
from app.server import create_server, parse_multipart
from app.telegram_bot import TelegramAPI, TelegramError
from tests.base import DatabaseTestCase

DEPLOY_DIR = config.BASE_DIR / "deploy"


class FakeSender:
    """Заглушка Bot API: запоминает сообщения и файлы."""

    def __init__(self, fail: bool = False) -> None:
        self.messages: list[tuple[int, str]] = []
        self.documents: list[tuple[int, str, bytes, str]] = []
        self.fail = fail

    def call(self, method: str, **params):
        if self.fail:
            raise TelegramError("сеть недоступна")
        assert method == "sendMessage"
        self.messages.append((params["chat_id"], params["text"]))
        return True

    def send_document(self, chat_id: int, filename: str, data: bytes, caption: str = ""):
        if self.fail:
            raise TelegramError("сеть недоступна")
        self.documents.append((chat_id, filename, data, caption))
        return True


class AlertTestCase(DatabaseTestCase):
    """Общая подготовка: получатель из .env и файл состояния во временной папке."""

    def setUp(self) -> None:
        super().setUp()
        self.state = Path(self._tmp.name) / "alerts.json"
        self.api = FakeSender()
        patcher = mock.patch.multiple(config, ADMIN_TELEGRAM_CHAT_IDS=[111], ALERT_STATE_PATH=self.state)
        patcher.start()
        self.addCleanup(patcher.stop)


class RecipientsTests(DatabaseTestCase):
    """Кому отправлять оповещения."""

    def test_env_or_linked_admins(self) -> None:
        """Сначала ADMIN_TELEGRAM_CHAT_ID, иначе главные администраторы с привязанным Telegram."""
        admin = auth.create_account("Админ", "admin@mail.kz", "password1")
        database.set_user_role("admin@mail.kz", database.ROLE_ADMIN)
        student = auth.create_account("Ученик", "s@mail.kz", "password1")
        database.bind_telegram(student, 555)
        with mock.patch.object(config, "ADMIN_TELEGRAM_CHAT_IDS", []):
            self.assertEqual(alerts.recipients(), [])
            database.bind_telegram(admin, 777)
            self.assertEqual(alerts.recipients(), [777])
        with mock.patch.object(config, "ADMIN_TELEGRAM_CHAT_IDS", [1, 2]):
            self.assertEqual(alerts.recipients(), [1, 2])

    def test_no_token_or_recipient(self) -> None:
        """Без токена или получателя ничего не отправляется и ничего не ломается."""
        with mock.patch.multiple(config, TELEGRAM_BOT_TOKEN="", ADMIN_TELEGRAM_CHAT_IDS=[1]), \
                self.assertLogs("app.alerts", "WARNING"):
            self.assertEqual(alerts.send("текст"), 0)
        with mock.patch.object(config, "ADMIN_TELEGRAM_CHAT_IDS", []), self.assertLogs("app.alerts", "WARNING"):
            self.assertEqual(alerts.send("текст", FakeSender()), 0)


class ServiceAlertTests(AlertTestCase):
    """Падение служб: ExecStopPost и OnFailure."""

    def test_normal_stop_is_silent(self) -> None:
        """Обычная остановка или перезапуск (SERVICE_RESULT=success) — без сообщения."""
        self.assertFalse(alerts.service_stopped("ent-master-site.service", "success", "killed", "TERM",
                                                self.api))
        self.assertEqual(self.api.messages, [])

    def test_crash_alert_with_cooldown(self) -> None:
        """Падение — сообщение; повторы в течение 10 минут копятся и упоминаются в следующем."""
        unit = "ent-master-site.service"
        self.assertTrue(alerts.service_stopped(unit, "exit-code", "exited", "1", self.api, now=1000))
        chat, text = self.api.messages[0]
        self.assertEqual(chat, 111)
        self.assertIn("упал сайт", text)
        self.assertIn("завершилась с кодом 1", text)
        self.assertIn("journalctl -u ent-master-site.service", text)

        for minute in (1, 2, 3):
            self.assertFalse(alerts.service_stopped(unit, "signal", "killed", "KILL", self.api,
                                                    now=1000 + minute * 60))
        self.assertEqual(len(self.api.messages), 1)
        # Другая служба — своё оповещение, не блокируется сайтом.
        self.assertTrue(alerts.service_stopped("ent-master-bot.service", "signal", "killed", "KILL",
                                               self.api, now=1100))
        self.assertIn("упал Telegram-бот", self.api.messages[-1][1])

        self.assertTrue(alerts.service_stopped(unit, "oom-kill", "", "", self.api, now=1000 + 11 * 60))
        self.assertIn("не хватило памяти", self.api.messages[-1][1])
        self.assertIn("Ещё 3 таких же событий", self.api.messages[-1][1])

    def test_failed_send_is_retried_later(self) -> None:
        """Если Telegram недоступен, сообщение не считается отправленным и уйдёт при следующем сбое."""
        with self.assertLogs("app.alerts", "ERROR"):
            self.assertFalse(alerts.service_stopped("ent-master-site.service", "exit-code", "exited", "1",
                                                    FakeSender(fail=True), now=1000))
        self.assertTrue(alerts.service_stopped("ent-master-site.service", "exit-code", "exited", "1",
                                               self.api, now=1030))

    def test_final_failure(self) -> None:
        """OnFailure: перезапуски исчерпаны — сообщение с командой перезапуска."""
        self.assertTrue(alerts.service_failed("ent-master-bot.service", self.api, now=5000))
        text = self.api.messages[0][1]
        self.assertIn("Telegram-бот не работает", text)
        self.assertIn("sudo systemctl restart ent-master-bot.service", text)

    def test_notify_command_reads_systemd_variables(self) -> None:
        """notify.py stopped берёт причину из переменных окружения systemd."""
        env = {"SERVICE_RESULT": "exit-code", "EXIT_CODE": "exited", "EXIT_STATUS": "2"}
        with mock.patch.dict("os.environ", env), mock.patch.object(alerts, "_api", return_value=self.api):
            self.assertEqual(notify.main(["stopped", "ent-master-site.service"]), 0)
        self.assertIn("завершилась с кодом 2", self.api.messages[0][1])
        with mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(notify.main(["что-то"]), 2)


class HealthcheckTests(AlertTestCase):
    """Проверка «сайт отвечает» по таймеру."""

    def test_down_then_recovered(self) -> None:
        """Одна неудача — тишина, две подряд — сообщение (один раз), ответ — «восстановился»."""
        server = create_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        try:
            self.assertEqual(alerts.healthcheck(url, self.api), "ok")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

        dead = url  # сервер остановлен — порт больше не отвечает
        self.assertEqual(alerts.healthcheck(dead, self.api), "down")
        self.assertEqual(self.api.messages, [])
        self.assertEqual(alerts.healthcheck(dead, self.api), "down")
        self.assertEqual(alerts.healthcheck(dead, self.api), "down")
        self.assertEqual(len(self.api.messages), 1)
        self.assertIn("сайт не отвечает", self.api.messages[0][1])

        with mock.patch.object(alerts, "check_site", return_value=""):
            self.assertEqual(alerts.healthcheck(dead, self.api), "recovered")
            self.assertEqual(alerts.healthcheck(dead, self.api), "ok")
        self.assertIn("снова отвечает", self.api.messages[-1][1])
        self.assertEqual(len(self.api.messages), 2)


class BackupToTelegramTests(AlertTestCase):
    """Отправка резервной копии файлом."""

    def make_copy(self) -> Path:
        auth.create_account("Али", "ali@mail.kz", "password1")
        return backup.make_backup(database._db_path, Path(self._tmp.name) / "backups")

    def test_send_backup(self) -> None:
        """Файл копии уходит получателю с подписью; слишком большой — только предупреждение."""
        path = self.make_copy()
        self.assertEqual(alerts.send_backup(path, self.api), 1)
        chat, filename, data, caption = self.api.documents[0]
        self.assertEqual((chat, filename, data), (111, path.name, path.read_bytes()))
        self.assertIn("резервная копия базы", caption)
        with mock.patch.object(config, "TELEGRAM_FILE_LIMIT_BYTES", 10):
            self.assertEqual(alerts.send_backup(path, self.api), 1)
        self.assertEqual(len(self.api.documents), 1)
        self.assertIn("больше 50 МБ", self.api.messages[-1][1])

    def test_backup_command_exit_codes(self) -> None:
        """backup.py --telegram: не отправилось — код 1 (systemd пришлёт оповещение о сбое копии)."""
        path = self.make_copy()
        with mock.patch.object(backup, "make_backup", return_value=path), mock.patch("sys.stdout"), \
                mock.patch("sys.stderr"):
            with mock.patch.object(alerts, "send_backup", return_value=1) as sent:
                self.assertEqual(backup.main(["--telegram"]), 0)
                sent.assert_called_once_with(path)
            with mock.patch.object(alerts, "send_backup", return_value=0):
                self.assertEqual(backup.main(["--telegram"]), 1)
            with mock.patch.object(alerts, "send_backup") as not_called:
                self.assertEqual(backup.main([]), 0)
                not_called.assert_not_called()


class SendDocumentTests(DatabaseTestCase):
    """TelegramAPI.send_document собирает корректный multipart-запрос."""

    def test_multipart_request(self) -> None:
        captured = {}

        def opener(request, timeout):
            captured["url"], captured["timeout"] = request.full_url, timeout
            captured["type"], captured["body"] = request.get_header("Content-type"), request.data
            return io.BytesIO(json.dumps({"ok": True, "result": {"message_id": 1}}).encode())

        data = bytes(range(256)) * 10
        api = TelegramAPI("TOKEN", opener=opener)
        self.assertEqual(api.send_document(42, 'копия"1.gz', data, "Подпись"), {"message_id": 1})
        self.assertTrue(captured["url"].endswith("/botTOKEN/sendDocument"))
        form, files = parse_multipart(captured["type"], captured["body"])
        self.assertEqual(form, {"chat_id": ["42"], "caption": ["Подпись"]})
        self.assertEqual((files["document"].filename, files["document"].data), ("копия1.gz", data))

        def failing(request, timeout):
            return io.BytesIO(b'{"ok": false, "description": "Bad Request: file is too big"}')

        with self.assertRaises(TelegramError):
            TelegramAPI("TOKEN", opener=failing).send_document(1, "a.gz", b"x")


class AlertUnitsTests(DatabaseTestCase):
    """Службы systemd подключают оповещения."""

    def test_units(self) -> None:
        for unit in ("ent-master-site.service", "ent-master-bot.service"):
            text = (DEPLOY_DIR / unit).read_text(encoding="utf-8")
            self.assertIn("ExecStopPost=/usr/bin/python3 /opt/ent-master/notify.py stopped %n", text)
            self.assertIn("OnFailure=ent-master-alert@%n.service", text)
        backup_unit = (DEPLOY_DIR / "ent-master-backup.service").read_text(encoding="utf-8")
        self.assertIn("backup.py --telegram", backup_unit)
        self.assertIn("OnFailure=ent-master-alert@%n.service", backup_unit)
        self.assertIn("notify.py failed %i", (DEPLOY_DIR / "ent-master-alert@.service").read_text(encoding="utf-8"))
        self.assertIn("notify.py healthcheck",
                      (DEPLOY_DIR / "ent-master-health.service").read_text(encoding="utf-8"))
        self.assertIn("OnUnitActiveSec=5min", (DEPLOY_DIR / "ent-master-health.timer").read_text(encoding="utf-8"))
        setup = (DEPLOY_DIR / "setup.sh").read_text(encoding="utf-8")
        self.assertIn("ent-master-health.timer", setup)
