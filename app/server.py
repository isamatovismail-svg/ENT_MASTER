"""HTTP-сервер на стандартной библиотеке: ThreadingHTTPServer + обработчик запросов.

Обработчик разбирает запрос (путь, параметры, форму, cookie), определяет
пользователя по сессии, передаёт запрос маршрутизатору и отправляет ответ.
Любая непредвиденная ошибка записывается в лог, а пользователь видит
аккуратную страницу «Что-то пошло не так» без трейсбека.
"""

import logging
import mimetypes
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import config
from app import auth, router, views
from app.web import Request, Response

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


def _parse_cookies(header: str) -> dict[str, str]:
    """Разбирает заголовок Cookie. Повреждённый заголовок просто игнорируется."""
    cookie = SimpleCookie()
    try:
        cookie.load(header)
    except CookieError:
        return {}
    return {name: morsel.value for name, morsel in cookie.items()}


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
        if method == "POST":
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return views.error_page(None, 400, "Некорректный запрос.")
            if length < 0:
                return views.error_page(None, 400, "Некорректный запрос.")
            if length > config.MAX_REQUEST_BODY_BYTES:
                return views.error_page(None, 413, "Слишком большой запрос.")
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            form = parse_qs(body, keep_blank_values=True)

        request = Request(
            method=method,
            path=url.path,
            query=parse_qs(url.query, keep_blank_values=True),
            form=form,
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
