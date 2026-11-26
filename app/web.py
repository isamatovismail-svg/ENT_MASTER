"""Простые классы запроса и ответа, общие для сервера, маршрутизатора и страниц."""

from dataclasses import dataclass, field

from app.database import User


@dataclass
class UploadedFile:
    """Файл из формы multipart/form-data (например, картинка баннера)."""

    filename: str
    content_type: str
    data: bytes


@dataclass
class Request:
    """Входящий HTTP-запрос в удобном для обработчиков виде."""

    method: str
    path: str
    query: dict[str, list[str]] = field(default_factory=dict)
    form: dict[str, list[str]] = field(default_factory=dict)
    files: dict[str, UploadedFile] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)
    user: User | None = None
    csrf_token: str = ""
    session_key: str = ""  # хеш токена текущей сессии

    def form_value(self, name: str, default: str = "") -> str:
        """Первое значение поля формы (или default, если поля нет)."""
        values = self.form.get(name)
        return values[0] if values else default

    def query_value(self, name: str, default: str = "") -> str:
        """Первое значение параметра из строки запроса (?name=...)."""
        values = self.query.get(name)
        return values[0] if values else default


@dataclass
class Response:
    """Исходящий HTTP-ответ."""

    status: int = 200
    body: bytes = b""
    content_type: str = "text/html; charset=utf-8"
    headers: list[tuple[str, str]] = field(default_factory=list)


def html_response(content: str, status: int = 200) -> Response:
    """Ответ с HTML-страницей."""
    return Response(status=status, body=content.encode("utf-8"))


def redirect(location: str, cookies: list[str] | None = None) -> Response:
    """Перенаправление 303 (браузер повторит запрос методом GET).

    cookies — готовые значения заголовков Set-Cookie.
    """
    headers = [("Location", location)]
    headers.extend(("Set-Cookie", cookie) for cookie in cookies or [])
    return Response(status=303, headers=headers)
