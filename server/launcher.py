"""Совместный запуск сайта, Telegram-бота и (с --share) туннеля Cloudflare с общим логом."""

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

from app import config

SITE_LABEL = "[САЙТ]"
BOT_LABEL = "[БОТ] "
TUNNEL_LABEL = "[ТУННЕЛЬ]"
RUN_LABEL = "[RUN] "
STOP_TIMEOUT_SECONDS = 5
SITE_START_TIMEOUT_SECONDS = 15
TUNNEL_START_TIMEOUT_SECONDS = 60

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


PR_SET_PDEATHSIG = 1


def _die_with_parent() -> None:
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
        start_new_session=(os.name == "posix"),
        preexec_fn=_die_with_parent if sys.platform.startswith("linux") else None,
    )


def start(part: str, label: str, extra_env: dict[str, str] | None = None) -> subprocess.Popen:
    """Запускает часть проекта (run.py site|bot) и поток, который печатает её вывод с меткой."""
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8",
           "ENT_RUN_CHILD": "1", **(extra_env or {})}
    process = _popen([sys.executable, "-u", str(config.BASE_DIR / "run.py"), part], env)

    def pump() -> None:
        with process.stdout:
            for line in process.stdout:
                log(label, line.rstrip("\n"))

    threading.Thread(target=pump, daemon=True).start()
    return process


class Tunnel:
    """Cloudflare Quick Tunnel: cloudflared пробрасывает https://….trycloudflare.com на локальный сайт."""

    def __init__(self, binary: str, local_url: str) -> None:
        self.url = ""
        self.ready = threading.Event()
        self.process = _popen(
            [binary, "tunnel", "--no-autoupdate", "--grace-period", "1s", "--url", local_url],
            {**os.environ},
        )
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        with self.process.stdout:
            for line in self.process.stdout:
                line = line.rstrip("\n")
                found = TUNNEL_URL_RE.search(line)
                if found and not self.url:
                    self.url = found.group(0)
                if TUNNEL_READY_MARK in line and self.url:
                    self.ready.set()
                if " ERR " in line:
                    log(TUNNEL_LABEL, line)
        self.ready.set()

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
        pass


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
        from app.core import auth, database

        database.init_db()
        weak = auth.weak_admin_logins()
    except Exception as error:
        log(RUN_LABEL, f"Не удалось проверить пароли администраторов: {error}")
        return
    for login in weak:
        log(RUN_LABEL, f"⚠ ВНИМАНИЕ: у главного администратора {login} слабый пароль — сайт открыт "
                       "всему интернету. Смените пароль (Профиль → «Забыли пароль?») или выключите показ.")


def _raise_keyboard_interrupt(signum, frame) -> None:
    raise KeyboardInterrupt


def _ignore_further_interrupts() -> None:
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
        except KeyboardInterrupt:
            process.kill()


def open_tunnel(processes: list[tuple[subprocess.Popen, str]]) -> Tunnel | None:
    """Открывает Quick Tunnel и ждёт публичную ссылку; None — cloudflared нет или он не подключился."""
    binary = shutil.which("cloudflared")
    if binary is None:
        log(RUN_LABEL, CLOUDFLARED_INSTALL_HINT)
        return None
    log(RUN_LABEL, "Открываю туннель Cloudflare (до минуты)…")
    tunnel = Tunnel(binary, config.LOCAL_URL)
    processes.append((tunnel.process, TUNNEL_LABEL))
    if not tunnel.wait(TUNNEL_START_TIMEOUT_SECONDS):
        log(RUN_LABEL, "Не удалось открыть туннель (нет интернета или Cloudflare недоступен). "
                       "Попробуйте ещё раз или запустите без --share.")
        return None
    return tunnel


def run_all(share: bool = False) -> int:
    """Запускает сайт, бота (если есть токен) и туннель (share); ждёт Ctrl+C и останавливает всё."""
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)

    processes: list[tuple[subprocess.Popen, str]] = []
    child_env: dict[str, str] = {}
    tunnel: Tunnel | None = None
    if port_busy():
        log(RUN_LABEL, f"Порт {config.PORT} уже занят — похоже, сайт уже запущен в другом терминале "
                       "(или другой проект на этом порту). Остановите его и запустите снова.")
        return 1
    try:
        if share:
            tunnel = open_tunnel(processes)
            if tunnel is None:
                return 1
            child_env = {"SHARE_MODE": "1", "SITE_URL": tunnel.url}

        site = start("site", SITE_LABEL, child_env)
        processes.append((site, SITE_LABEL))

        bot = None
        if config.TELEGRAM_BOT_TOKEN:
            bot = start("bot", BOT_LABEL, child_env)
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
        time.sleep(0.1)
        log(RUN_LABEL, "Всё остановлено.")
