"""Общий запуск ENT MASTER: сайт (main.py) и Telegram-бот (bot.py) одной командой.

    python run.py           — сайт на этом компьютере: http://localhost:8000
    python run.py --share   — то же + временная публичная ссылка https://….trycloudflare.com
                              (Cloudflare Quick Tunnel, без аккаунта), чтобы показать сайт учителю

Остановить всё (сайт, бот, туннель) — Ctrl+C.

Сайт, бот и туннель работают отдельными процессами, их логи выводятся в этот терминал
с метками [САЙТ], [БОТ] и [ТУННЕЛЬ]. Если в .env нет TELEGRAM_BOT_TOKEN, бот не запускается.
"""

import argparse
import ctypes
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time

import config

SITE_LABEL = "[САЙТ]"
BOT_LABEL = "[БОТ] "
TUNNEL_LABEL = "[ТУННЕЛЬ]"
RUN_LABEL = "[RUN] "
STOP_TIMEOUT_SECONDS = 5      # сколько ждать аккуратной остановки процесса
SITE_START_TIMEOUT_SECONDS = 15
TUNNEL_START_TIMEOUT_SECONDS = 60

# Публичный адрес Quick Tunnel и строка, после которой туннель реально принимает запросы.
TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
TUNNEL_READY_MARK = "Registered tunnel connection"
CLOUDFLARED_INSTALL_HINT = (
    "cloudflared не найден. Установите официальный пакет Cloudflare:\n"
    "  curl -LO https://github.com/cloudflare/cloudflared/releases/latest/download/"
    "cloudflared-linux-amd64.deb\n"
    "  sudo dpkg -i cloudflared-linux-amd64.deb"
)

_print_lock = threading.Lock()


def log(label: str, text: str) -> None:
    """Печатает строку с меткой; блокировка не даёт строкам процессов перемешаться."""
    with _print_lock:
        print(f"{label} {text}", flush=True)


PR_SET_PDEATHSIG = 1  # prctl: какой сигнал получит процесс, когда умрёт его родитель


def _die_with_parent() -> None:
    """(Linux) Дочерний процесс получит SIGTERM, если run.py завершится аварийно (kill -9),
    — сайт, бот и туннель не останутся висеть без хозяина."""
    try:
        ctypes.CDLL(None, use_errno=True).prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
    except (OSError, AttributeError):
        pass


def _popen(command: list[str], env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        command,
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
        # останавливает сайт, бота и туннель, а не все сразу и вперемешку.
        start_new_session=(os.name == "posix"),
        preexec_fn=_die_with_parent if sys.platform.startswith("linux") else None,
    )


def start(script: str, label: str, extra_env: dict[str, str] | None = None) -> subprocess.Popen:
    """Запускает python-скрипт проекта и поток, который печатает его вывод с меткой."""
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8",
           "ENT_RUN_CHILD": "1", **(extra_env or {})}
    process = _popen([sys.executable, "-u", str(config.BASE_DIR / script)], env)

    def pump() -> None:
        for line in process.stdout:
            log(label, line.rstrip("\n"))

    threading.Thread(target=pump, daemon=True).start()
    return process


class Tunnel:
    """Cloudflare Quick Tunnel: cloudflared пробрасывает https://….trycloudflare.com на локальный сайт."""

    def __init__(self, binary: str, local_url: str) -> None:
        self.url = ""
        self.ready = threading.Event()   # туннель зарегистрирован и принимает запросы
        self.process = _popen(
            [binary, "tunnel", "--no-autoupdate", "--grace-period", "1s", "--url", local_url],
            {**os.environ},
        )
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        """Ищет в выводе cloudflared публичную ссылку; печатает только ошибки (остальное — шум)."""
        for line in self.process.stdout:
            line = line.rstrip("\n")
            found = TUNNEL_URL_RE.search(line)
            if found and not self.url:
                self.url = found.group(0)
            if TUNNEL_READY_MARK in line and self.url:
                self.ready.set()
            if " ERR " in line:
                log(TUNNEL_LABEL, line)
        self.ready.set()  # процесс завершился — не ждём дальше

    def wait(self, timeout: float) -> str:
        """Публичная ссылка или '' (cloudflared не смог подключиться к Cloudflare)."""
        self.ready.wait(timeout)
        return self.url if self.process.poll() is None else ""


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


def port_busy() -> bool:
    """True — на порту сайта уже кто-то слушает (например, сайт запущен в другом терминале)."""
    try:
        with socket.create_connection((config.HOST, config.PORT), timeout=0.5):
            return True
    except OSError:
        return False


def share_banner(url: str) -> str:
    """Крупная рамка с публичной ссылкой — её видно в потоке логов."""
    lines = [
        "САЙТ ОТКРЫТ ЧЕРЕЗ ИНТЕРНЕТ — отправьте ссылку учителю:",
        "",
        url,
        "",
        "Ссылка временная: работает, пока открыт этот терминал.",
        "Выключить показ — Ctrl+C (остановятся сайт, бот и туннель).",
        "Демо-администратор в этом режиме войти не может.",
    ]
    width = max(len(line) for line in lines) + 4
    border = "█" * (width + 2)
    body = [f"█  {line.ljust(width - 2)}█" for line in lines]
    return "\n".join(["", border, *body, border, ""])


def warn_weak_admin_passwords() -> None:
    """Предупреждает, если пароль главного администратора угадывается (проверка в фоне)."""
    try:
        from app import auth, database  # импорт здесь: run.py работает и без базы

        database.init_db()
        weak = auth.weak_admin_logins()
    except Exception as error:  # noqa: BLE001 — проверка не должна мешать запуску
        log(RUN_LABEL, f"Не удалось проверить пароли администраторов: {error}")
        return
    for login in weak:
        log(RUN_LABEL, f"⚠ ВНИМАНИЕ: у главного администратора {login} слабый пароль — сайт открыт "
                       "всему интернету. Смените пароль (Профиль → «Забыли пароль?») или выключите показ.")


def _raise_keyboard_interrupt(signum, frame) -> None:
    raise KeyboardInterrupt


def _ignore_further_interrupts() -> None:
    """Игнорирует повторный Ctrl+C, чтобы остановка дошла до конца.

    Второй Ctrl+C может прилететь прямо во время этой функции — тогда просто повторяем.
    """
    while True:
        try:
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            return
        except KeyboardInterrupt:
            continue


def shutdown(processes: list[tuple[subprocess.Popen, str]]) -> None:
    """Останавливает все процессы (последний запущенный — первым), даже при повторном Ctrl+C."""
    _ignore_further_interrupts()
    for process, label in reversed(processes):
        try:
            stop(process, label)
        except KeyboardInterrupt:  # сигнал, пришедший до SIG_IGN
            process.kill()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Запуск сайта ENT MASTER и Telegram-бота.")
    parser.add_argument("--share", action="store_true",
                        help="показать сайт через интернет (Cloudflare Quick Tunnel, временная ссылка)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Запускает сайт, бота (если есть токен) и туннель (--share); ждёт Ctrl+C и останавливает всё."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    # Ctrl+C работает, даже если run.py запущен с игнорируемым SIGINT (например, через &):
    # обработчик ставится до запуска процессов, и после exec у них SIGINT снова обычный.
    signal.signal(signal.SIGINT, signal.default_int_handler)
    # Кнопка «Стоп» в PyCharm и kill присылают SIGTERM — обрабатываем как Ctrl+C.
    signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)

    processes: list[tuple[subprocess.Popen, str]] = []
    child_env: dict[str, str] = {}
    tunnel: Tunnel | None = None
    if port_busy():
        log(RUN_LABEL, f"Порт {config.PORT} уже занят — похоже, сайт уже запущен в другом терминале "
                       "(или другой проект на этом порту). Остановите его и запустите снова.")
        return 1
    try:
        if args.share:
            binary = shutil.which("cloudflared")
            if binary is None:
                log(RUN_LABEL, CLOUDFLARED_INSTALL_HINT)
                return 1
            log(RUN_LABEL, "Открываю туннель Cloudflare (до минуты)…")
            tunnel = Tunnel(binary, config.LOCAL_URL)
            processes.append((tunnel.process, TUNNEL_LABEL))
            public_url = tunnel.wait(TUNNEL_START_TIMEOUT_SECONDS)
            if not public_url:
                log(RUN_LABEL, "Не удалось открыть туннель (нет интернета или Cloudflare недоступен). "
                               "Попробуйте ещё раз или запустите без --share.")
                return 1
            # Сайт и бот используют публичную ссылку в письмах и ссылках из бота.
            child_env = {"SHARE_MODE": "1", "SITE_URL": public_url}

        site = start("main.py", SITE_LABEL, child_env)
        processes.append((site, SITE_LABEL))

        bot = None
        if config.TELEGRAM_BOT_TOKEN:
            bot = start("bot.py", BOT_LABEL, child_env)
            processes.append((bot, BOT_LABEL))
        else:
            log(RUN_LABEL, "ВНИМАНИЕ: в .env нет TELEGRAM_BOT_TOKEN — Telegram-бот НЕ запущен, "
                           "работает только сайт.")
            log(RUN_LABEL, "Чтобы запустить бота: скопируйте .env.example в .env, "
                           "впишите токен от @BotFather и перезапустите run.py.")

        if wait_for_site(site):
            log(RUN_LABEL, f"Сайт на этом компьютере: {config.LOCAL_URL}")
            if tunnel is not None:
                with _print_lock:
                    print(share_banner(tunnel.url), flush=True)
                threading.Thread(target=warn_weak_admin_passwords, daemon=True).start()
            log(RUN_LABEL, "Остановить всё: Ctrl+C")

        bot_reported = False
        while True:
            code = site.poll()
            if code is not None:
                log(RUN_LABEL, f"Сайт завершился (код {code}). Останавливаю всё.")
                return code or 1
            if tunnel is not None and tunnel.process.poll() is not None:
                log(RUN_LABEL, "Туннель Cloudflare закрылся — показ через интернет выключен. Останавливаю всё.")
                return 1
            if bot is not None and not bot_reported and bot.poll() is not None:
                log(RUN_LABEL, f"Бот завершился (код {bot.returncode}). Сайт продолжает работать.")
                bot_reported = True
            time.sleep(0.3)
    except KeyboardInterrupt:
        _ignore_further_interrupts()
        log(RUN_LABEL, "Останавливаю всё…")
        return 0
    finally:
        shutdown(processes)
        time.sleep(0.1)  # дать потокам допечатать последние строки
        log(RUN_LABEL, "Всё остановлено.")


if __name__ == "__main__":
    sys.exit(main())
