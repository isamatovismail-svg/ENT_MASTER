"""Общий запуск ENT MASTER: сайт (main.py) и Telegram-бот (bot.py) одной командой.

Запуск: python run.py  →  откройте http://localhost:8000. Остановить оба — Ctrl+C.

Сайт и бот работают отдельными процессами, их логи выводятся в этот терминал
с метками [САЙТ] и [БОТ]. Если в .env нет TELEGRAM_BOT_TOKEN, запускается только сайт.
"""

import os
import signal
import socket
import subprocess
import sys
import threading
import time

import config

SITE_LABEL = "[САЙТ]"
BOT_LABEL = "[БОТ] "
RUN_LABEL = "[RUN] "
STOP_TIMEOUT_SECONDS = 5      # сколько ждать аккуратной остановки процесса
SITE_START_TIMEOUT_SECONDS = 15

_print_lock = threading.Lock()


def log(label: str, text: str) -> None:
    """Печатает строку с меткой; блокировка не даёт строкам процессов перемешаться."""
    with _print_lock:
        print(f"{label} {text}", flush=True)


def start(script: str, label: str) -> subprocess.Popen:
    """Запускает python-скрипт проекта и поток, который печатает его вывод с меткой."""
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    process = subprocess.Popen(
        [sys.executable, "-u", str(config.BASE_DIR / script)],
        cwd=config.BASE_DIR,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        # Своя группа процессов: Ctrl+C получает только run.py и сам по очереди
        # останавливает сайт и бота, а не все сразу и вперемешку.
        start_new_session=(os.name == "posix"),
    )

    def pump() -> None:
        for line in process.stdout:
            log(label, line.rstrip("\n"))

    threading.Thread(target=pump, daemon=True).start()
    return process


def stop(process: subprocess.Popen, label: str) -> None:
    """Просит процесс завершиться как по Ctrl+C, при зависании — завершает принудительно."""
    if process.poll() is not None:
        return
    try:
        process.send_signal(signal.SIGINT if os.name == "posix" else signal.SIGTERM)
        process.wait(timeout=STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        log(label, "не остановился вовремя — завершаю принудительно.")
        process.kill()
        process.wait()
    except ProcessLookupError:
        pass  # процесс уже успел завершиться сам


def wait_for_site(process: subprocess.Popen) -> bool:
    """Ждёт, пока сайт начнёт принимать соединения (или процесс упадёт)."""
    deadline = time.monotonic() + SITE_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        try:
            with socket.create_connection((config.HOST, config.PORT), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _raise_keyboard_interrupt(signum, frame) -> None:
    raise KeyboardInterrupt


def main() -> int:
    """Запускает сайт и (если есть токен) бота; ждёт Ctrl+C и останавливает оба."""
    # Ctrl+C работает, даже если run.py запущен с игнорируемым SIGINT (например, через &):
    # обработчик ставится до запуска процессов, и после exec у них SIGINT снова обычный.
    signal.signal(signal.SIGINT, signal.default_int_handler)
    # Кнопка «Стоп» в PyCharm и kill присылают SIGTERM — обрабатываем как Ctrl+C.
    signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)

    processes: list[tuple[subprocess.Popen, str]] = []
    try:
        site = start("main.py", SITE_LABEL)
        processes.append((site, SITE_LABEL))

        bot = None
        if config.TELEGRAM_BOT_TOKEN:
            bot = start("bot.py", BOT_LABEL)
            processes.append((bot, BOT_LABEL))
        else:
            log(RUN_LABEL, "ВНИМАНИЕ: в .env нет TELEGRAM_BOT_TOKEN — Telegram-бот НЕ запущен, "
                           "работает только сайт.")
            log(RUN_LABEL, "Чтобы запустить бота: скопируйте .env.example в .env, "
                           "впишите токен от @BotFather и перезапустите run.py.")

        if wait_for_site(site):
            log(RUN_LABEL, f"Сайт: http://localhost:{config.PORT}")
            log(RUN_LABEL, "Остановить всё: Ctrl+C")

        bot_reported = False
        while True:
            code = site.poll()
            if code is not None:
                log(RUN_LABEL, f"Сайт завершился (код {code}). Останавливаю всё.")
                return code or 1
            if bot is not None and not bot_reported and bot.poll() is not None:
                log(RUN_LABEL, f"Бот завершился (код {bot.returncode}). Сайт продолжает работать.")
                bot_reported = True
            time.sleep(0.3)
    except KeyboardInterrupt:
        log(RUN_LABEL, "Останавливаю сайт и бота…")
        return 0
    finally:
        # Игнорируем повторный Ctrl+C, чтобы остановка дошла до конца.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        for process, label in reversed(processes):
            stop(process, label)
        time.sleep(0.1)  # дать потокам допечатать последние строки
        log(RUN_LABEL, "Всё остановлено.")


if __name__ == "__main__":
    sys.exit(main())
