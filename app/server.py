"""HTTP-сервер на стандартной библиотеке: ThreadingHTTPServer + обработчик запросов.

Обработчик разбирает запрос (путь, параметры, форму, cookie), определяет
пользователя по сессии, передаёт запрос маршрутизатору и отправляет ответ.
Любая непредвиденная ошибка записывается в лог, а пользователь видит
аккуратную страницу «Что-то пошло не так» без трейсбека.
"""

import logging
import mimetypes
import threading
import time
from email.parser import BytesParser
from email.policy import HTTP
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import config
from app import auth, router, views
from app.web import Request, Response, UploadedFile

logger = logging.getLogger(__name__)

# Заголовки безопасности для каждого ответа. CSP запрещает любые скрипты
# и внешние ресурсы: страницы используют только свой CSS.
SECURITY_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "same-origin"),
    (
        "Content-Security-Policy",
        "default-src 'none'; style-src 'self'; img-src 'self' data:; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    ),
)


# Первый байт TLS-рукопожатия (ClientHello). Так начинается запрос, если браузер
# открыл https:// на нашем http-сервере.
TLS_HANDSHAKE_BYTE = 0x16
TLS_WARNING_INTERVAL_SECONDS = 60
_tls_warning_lock = threading.Lock()
_tls_warned_at = 0.0


def https_hint() -> str:
    """Понятное объяснение для лога вместо «Bad request version» с мусорными байтами."""
    return (
        f"Браузер открыл сайт по https://, а здесь сайт работает по http. Откройте {config.LOCAL_URL} "
        "(именно http). Если Chrome сам переходит на https:// — у него в кэше остался редирект "
        "от другого проекта на этом порту: откройте ссылку с localhost или очистите кэш "
        "(chrome://settings/clearBrowserData → «Изображения и другие файлы, сохранённые в кеше»)."
    )


def _warn_https_attempt() -> None:
    """Пишет подсказку про https в лог, но не чаще раза в минуту (браузер шлёт много попыток)."""
    global _tls_warned_at
    with _tls_warning_lock:
        now = time.monotonic()
        if _tls_warned_at and now - _tls_warned_at < TLS_WARNING_INTERVAL_SECONDS:
            return
        _tls_warned_at = now
    logger.warning(https_hint())


def _parse_cookies(header: str) -> dict[str, str]:
    """Разбирает заголовок Cookie. Повреждённый заголовок просто игнорируется."""
    cookie = SimpleCookie()
    try:
        cookie.load(header)
    except CookieError:
        return {}
    return {name: morsel.value for name, morsel in cookie.items()}


def parse_multipart(content_type: str, body: bytes) -> tuple[dict[str, list[str]], dict[str, UploadedFile]]:
    """Разбирает тело формы multipart/form-data: текстовые поля и файлы.

    Используется email.parser (модуль cgi убран из Python 3.13). Повреждённое тело даёт
    пустую форму — обработчик ответит ошибкой проверки (например, csrf).
    """
    form: dict[str, list[str]] = {}
    files: dict[str, UploadedFile] = {}
    header = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("latin-1", "replace")
    try:
        message = BytesParser(policy=HTTP).parsebytes(header + body)
        parts = list(message.iter_parts()) if message.is_multipart() else []
    except Exception:  # noqa: BLE001 — любой мусор во входных данных = пустая форма
        return {}, {}
    for part in parts:
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        data = part.get_payload(decode=True) or b""
        filename = part.get_filename()
        if filename is not None:
            if data:
                files[name] = UploadedFile(filename, part.get_content_type(), data)
            continue
        charset = part.get_content_charset() or "utf-8"
        form.setdefault(name, []).append(data.decode(charset, errors="replace"))
    return form, files


def serve_static(relative_path: str) -> Response:
    """Отдаёт файл из папки static/. Выйти за пределы папки (../) нельзя."""
    static_root = config.STATIC_DIR.resolve()
    file_path = (static_root / relative_path).resolve()
    if not file_path.is_relative_to(static_root) or not file_path.is_file():
        return Response(status=404, body=b"Not found", content_type="text/plain; charset=utf-8")
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    if content_type.startswith("text/"):
        content_type += "; charset=utf-8"
    return Response(
        body=file_path.read_bytes(),
        content_type=content_type,
        headers=[("Cache-Control", "no-cache")],
    )


class RequestHandler(BaseHTTPRequestHandler):
    """Обрабатывает каждый HTTP-запрос в отдельном потоке."""

    server_version = "ENTMaster/1.0"

    def parse_request(self) -> bool:
        """Отсекает попытки открыть сайт по https:// с понятным сообщением в логе."""
        if self.raw_requestline[:1] == bytes([TLS_HANDSHAKE_BYTE]):
            _warn_https_attempt()
            self.close_connection = True
            return False
        return super().parse_request()

    def do_GET(self) -> None:  # noqa: N802 (имя задано BaseHTTPRequestHandler)
        """Обработка GET-запросов."""
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        """Обработка POST-запросов (отправка форм)."""
        self._handle("POST")

    def _handle(self, method: str) -> None:
        """Строит ответ и отправляет его; ошибки превращаются в страницу 500."""
        try:
            response = self._build_response(method)
        except Exception:
            logger.exception("Ошибка при обработке %s %s", method, self.path)
            response = views.server_error()
        self._send(response)

    def _build_response(self, method: str) -> Response:
        """Разбирает запрос и передаёт его маршрутизатору."""
        url = urlsplit(self.path)
        if method == "GET" and url.path.startswith("/static/"):
            return serve_static(url.path.removeprefix("/static/"))

        form: dict[str, list[str]] = {}
        files: dict[str, UploadedFile] = {}
        if method == "POST":
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return views.error_page(None, 400, "Некорректный запрос.")
            if length < 0:
                return views.error_page(None, 400, "Некорректный запрос.")
            if length > config.MAX_REQUEST_BODY_BYTES:
                return views.error_page(None, 413, "Слишком большой запрос.")
            body = self.rfile.read(length)
            content_type = self.headers.get("Content-Type", "")
            if content_type.lower().startswith("multipart/form-data"):
                form, files = parse_multipart(content_type, body)
            else:
                form = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)

        request = Request(
            method=method,
            path=url.path,
            query=parse_qs(url.query, keep_blank_values=True),
            form=form,
            files=files,
            cookies=_parse_cookies(self.headers.get("Cookie", "")),
        )
        auth.attach_user(request)
        return router.dispatch(request)

    def _send(self, response: Response) -> None:
        """Отправляет статус, заголовки и тело ответа."""
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        if response.content_type.startswith("text/html"):
            # Личные страницы не кэшируем: после выхода «Назад» их не покажет.
            self.send_header("Cache-Control", "no-store")
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        for name, value in response.headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(response.body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Пишет журнал запросов через logging вместо stderr."""
        logger.info("%s - %s", self.address_string(), format % args)


def create_server(host: str = config.HOST, port: int = config.PORT) -> ThreadingHTTPServer:
    """Создаёт многопоточный HTTP-сервер (port=0 — выбрать свободный порт)."""
    server = ThreadingHTTPServer((host, port), RequestHandler)
    server.daemon_threads = True
    return server
