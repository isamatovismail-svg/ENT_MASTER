"""Вход через Google: OAuth 2.0, Authorization Code Flow — только urllib."""

import base64
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlencode

from app import config
from app.i18n import t

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")


class GoogleAuthError(Exception):
    """Google не подтвердил вход (ошибка сети, неверный код или токен)."""


@dataclass
class GoogleUser:
    """Данные пользователя из id_token."""

    email: str
    first_name: str
    last_name: str


def enabled() -> bool:
    """True, если в .env заданы все ключи Google — тогда кнопка входа активна."""
    return bool(config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET
                and config.GOOGLE_REDIRECT_URI)


def authorization_url(state: str) -> str:
    """Адрес страницы входа Google."""
    query = urlencode({
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": config.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    })
    return f"{AUTH_URL}?{query}"


def post_form(url: str, fields: dict[str, str]) -> dict:
    """POST application/x-www-form-urlencoded и разбор JSON-ответа."""
    request = urllib.request.Request(
        url, data=urlencode(fields).encode("ascii"), method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise GoogleAuthError(t("Google ответил ошибкой {code}", code=error.code)) from error
    except (OSError, ValueError) as error:
        raise GoogleAuthError(t("Не удалось связаться с Google: {error}", error=error)) from error


def _decode_segment(segment: str) -> dict:
    padded = segment + "=" * (-len(segment) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, UnicodeError) as error:
        raise GoogleAuthError(t("Повреждённый id_token")) from error
    if not isinstance(data, dict):
        raise GoogleAuthError(t("Повреждённый id_token"))
    return data


def parse_id_token(id_token: str, now: float | None = None) -> GoogleUser:
    """Проверяет aud, iss, exp и подтверждённость почты, возвращает данные пользователя."""
    parts = id_token.split(".")
    if len(parts) != 3:
        raise GoogleAuthError(t("Повреждённый id_token"))
    claims = _decode_segment(parts[1])
    now = time.time() if now is None else now
    if claims.get("aud") != config.GOOGLE_CLIENT_ID:
        raise GoogleAuthError(t("id_token выдан другому приложению"))
    if claims.get("iss") not in ISSUERS:
        raise GoogleAuthError(t("id_token выдан не Google"))
    exp = claims.get("exp")
    if not isinstance(exp, (int, float)) or exp < now:
        raise GoogleAuthError(t("Срок действия id_token истёк"))
    email = claims.get("email")
    if not isinstance(email, str) or "@" not in email:
        raise GoogleAuthError(t("Google не сообщил почту"))
    if claims.get("email_verified") not in (True, "true"):
        raise GoogleAuthError(t("Почта в Google не подтверждена"))
    return GoogleUser(
        email=email.strip().lower(),
        first_name=str(claims.get("given_name") or claims.get("name") or ""),
        last_name=str(claims.get("family_name") or ""),
    )


def exchange_code(code: str) -> GoogleUser:
    """Меняет code из callback на токены и возвращает пользователя из id_token."""
    if not code or len(code) > 2000:
        raise GoogleAuthError(t("Нет кода авторизации"))
    tokens = post_form(TOKEN_URL, {
        "code": code,
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "redirect_uri": config.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    })
    id_token = tokens.get("id_token")
    if not isinstance(id_token, str):
        raise GoogleAuthError(t("Google не вернул id_token"))
    return parse_id_token(id_token)
