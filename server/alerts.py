"""Оповещения главному администратору в Telegram: сбои сайта и бота, резервные копии базы."""

import json
import logging
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from app import config
from app.core import database
from app.telegram_bot import TelegramAPI, TelegramError

logger = logging.getLogger(__name__)

SERVICE_NAMES = {
    "ent-master-site.service": "сайт",
    "ent-master-bot.service": "Telegram-бот",
    "ent-master-backup.service": "резервная копия базы",
}
HEALTH_FAILURES_TO_ALERT = 2


class Sender(Protocol):
    """То, что умеет отправлять сообщения и файлы (TelegramAPI или заглушка в тестах)."""

    def call(self, method: str, **params: Any) -> Any:
        """Метод Bot API."""

    def send_document(self, chat_id: int, filename: str, data: bytes, caption: str = "") -> Any:
        """Отправка файла."""


def recipients() -> list[int]:
    """Кому отправлять: chat id из .env или привязанные к Telegram главные администраторы."""
    if config.ADMIN_TELEGRAM_CHAT_IDS:
        return list(config.ADMIN_TELEGRAM_CHAT_IDS)
    try:
        return database.admin_telegram_ids()
    except Exception:
        logger.exception("Не удалось прочитать администраторов из базы")
        return []


def _api(api: Sender | None) -> Sender | None:
    if api is not None:
        return api
    if not config.TELEGRAM_BOT_TOKEN:
        logger.warning("Оповещение не отправлено: в .env нет TELEGRAM_BOT_TOKEN")
        return None
    return TelegramAPI(config.TELEGRAM_BOT_TOKEN)


def send(text: str, api: Sender | None = None) -> int:
    """Отправляет сообщение всем получателям. Возвращает, скольким удалось отправить."""
    client = _api(api)
    chats = recipients()
    if client is None or not chats:
        if not chats:
            logger.warning("Оповещение не отправлено: нет получателя (ADMIN_TELEGRAM_CHAT_ID или "
                           "администратора с привязанным Telegram)")
        return 0
    sent = 0
    for chat_id in chats:
        try:
            client.call("sendMessage", chat_id=chat_id, text=text)
            sent += 1
        except (TelegramError, OSError) as error:
            logger.error("Не удалось отправить оповещение в чат %s: %s", chat_id, error)
    return sent


def _load_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(path: Path, state: dict) -> None:
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        logger.exception("Не удалось сохранить состояние оповещений")


def send_once(key: str, text: str, api: Sender | None = None, now: float | None = None,
              state_path: Path | None = None) -> bool:
    """Отправляет оповещение, если такое же (key) не отправлялось последние ALERT_COOLDOWN_SECONDS."""
    now = time.time() if now is None else now
    path = state_path or config.ALERT_STATE_PATH
    state = _load_state(path)
    entry = state.get(key, {})
    if now - entry.get("sent_at", 0) < config.ALERT_COOLDOWN_SECONDS:
        entry["suppressed"] = entry.get("suppressed", 0) + 1
        state[key] = entry
        _save_state(path, state)
        return False
    suppressed = entry.get("suppressed", 0)
    if suppressed:
        text += f"\n(Ещё {suppressed} таких же событий за прошлые минуты.)"
    if not send(text, api):
        return False
    state[key] = {"sent_at": now, "suppressed": 0}
    _save_state(path, state)
    return True


def _host() -> str:
    return socket.gethostname()


def _when(now: float | None = None) -> str:
    return time.strftime("%d.%m.%Y %H:%M:%S", time.localtime(now))


def service_stopped(unit: str, result: str, exit_code: str = "", exit_status: str = "",
                    api: Sender | None = None, now: float | None = None,
                    state_path: Path | None = None) -> bool:
    """Служба остановилась (ExecStopPost). Обычная остановка (result=success) — без сообщения."""
    if result in ("", "success"):
        return False
    name = SERVICE_NAMES.get(unit, unit)
    reason = {"exit-code": f"завершилась с кодом {exit_status}", "signal": f"убита сигналом {exit_status}",
              "core-dump": f"аварийно завершилась ({exit_status})", "timeout": "не ответила вовремя",
              "watchdog": "зависла (watchdog)", "oom-kill": "не хватило памяти"}.get(
        result, f"{result} {exit_code} {exit_status}".strip())
    text = (f"⚠️ ENT MASTER: упал {name}.\nПричина: {reason}.\nСервер: {_host()}, {_when(now)}.\n"
            f"systemd перезапустит службу автоматически. Журнал: journalctl -u {unit} -n 50")
    return send_once(f"stopped:{unit}", text, api, now, state_path)


def service_failed(unit: str, api: Sender | None = None, now: float | None = None,
                   state_path: Path | None = None) -> bool:
    """Служба окончательно остановлена systemd (OnFailure): перезапуски не помогли."""
    name = SERVICE_NAMES.get(unit, unit)
    text = (f"❌ ENT MASTER: {name} не работает — systemd перестал перезапускать службу.\n"
            f"Сервер: {_host()}, {_when(now)}.\n"
            f"Посмотрите журнал: journalctl -u {unit} -n 100\n"
            f"Запустить снова: sudo systemctl restart {unit}")
    return send_once(f"failed:{unit}", text, api, now, state_path)


def check_site(url: str | None = None, timeout: float = 10) -> str:
    """Пустая строка — сайт отвечает, иначе описание проблемы."""
    url = url or config.HEALTHCHECK_URL
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            if response.status != 200:
                return f"ответ {response.status}"
    except urllib.error.HTTPError as error:
        return f"ответ {error.code}"
    except (OSError, ValueError) as error:
        return f"нет ответа ({error})"
    return ""


def healthcheck(url: str | None = None, api: Sender | None = None, now: float | None = None,
                state_path: Path | None = None) -> str:
    """Проверяет сайт; сообщает о сбое после нескольких неудач подряд и о восстановлении."""
    path = state_path or config.ALERT_STATE_PATH
    problem = check_site(url)
    state = _load_state(path)
    health = state.get("health", {"failures": 0, "alerted": False})
    if not problem:
        recovered = health.get("alerted", False)
        state["health"] = {"failures": 0, "alerted": False}
        _save_state(path, state)
        if recovered:
            send(f"✅ ENT MASTER: сайт снова отвечает. Сервер: {_host()}, {_when(now)}.", api)
            return "recovered"
        return "ok"
    health["failures"] = health.get("failures", 0) + 1
    if health["failures"] >= HEALTH_FAILURES_TO_ALERT and not health.get("alerted"):
        sent = send(f"🔴 ENT MASTER: сайт не отвечает ({problem}).\n"
                    f"Проверок подряд без ответа: {health['failures']}. Сервер: {_host()}, {_when(now)}.\n"
                    "Журнал: journalctl -u ent-master-site -n 50", api)
        health["alerted"] = sent > 0
    state["health"] = health
    _save_state(path, state)
    return "down"


def send_backup(path: Path, api: Sender | None = None) -> int:
    """Отправляет файл резервной копии получателям. Возвращает, скольким удалось."""
    client = _api(api)
    chats = recipients()
    if client is None or not chats:
        logger.warning("Копия не отправлена в Telegram: нет токена бота или получателя")
        return 0
    size = path.stat().st_size
    caption = (f"🗄 ENT MASTER: резервная копия базы {path.name} ({size // 1024} КБ). "
               "Восстановление: gunzip -c файл.gz > ent_master.sqlite3")
    if size > config.TELEGRAM_FILE_LIMIT_BYTES:
        return send(f"⚠️ ENT MASTER: копия {path.name} ({size // (1024 * 1024)} МБ) больше 50 МБ — "
                    "Telegram её не примет. Заберите копию с сервера вручную.", client)
    data = path.read_bytes()
    sent = 0
    for chat_id in chats:
        try:
            client.send_document(chat_id, path.name, data, caption)
            sent += 1
        except (TelegramError, OSError) as error:
            logger.error("Не удалось отправить копию в чат %s: %s", chat_id, error)
    return sent
