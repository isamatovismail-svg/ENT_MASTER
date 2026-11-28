"""Оповещения главному администратору в Telegram (вызываются systemd на сервере)."""

import logging
import os
import sys

from server import alerts

USAGE = """\
Запуск:
    python -m server.notify test              — пробное сообщение (проверить токен и получателя)
    python -m server.notify stopped <служба>  — служба остановилась (ExecStopPost; обычная остановка молчит)
    python -m server.notify failed <служба>   — служба окончательно упала (OnFailure)
    python -m server.notify healthcheck       — проверить, что сайт отвечает (таймер каждые 5 минут)

Получатели — ADMIN_TELEGRAM_CHAT_ID из .env или главные администраторы, привязавшие Telegram.
"""


def main(argv: list[str]) -> int:
    """Разбирает аргументы и отправляет нужное оповещение."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    command = argv[0] if argv else ""
    if command == "test":
        sent = alerts.send("🔔 ENT MASTER: пробное оповещение. Если вы это читаете — оповещения работают.")
        print(f"Отправлено получателям: {sent}")
    elif command == "stopped" and len(argv) == 2:
        alerts.service_stopped(argv[1], os.environ.get("SERVICE_RESULT", ""),
                               os.environ.get("EXIT_CODE", ""), os.environ.get("EXIT_STATUS", ""))
    elif command == "failed" and len(argv) == 2:
        alerts.service_failed(argv[1])
    elif command == "healthcheck":
        print(f"Сайт: {alerts.healthcheck()}")
    else:
        print(USAGE.strip())
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
