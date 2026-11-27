"""Свои рекламные баннеры без JavaScript: картинка + ссылка, места показа и даты.

Сервисы вроде AdSense требуют JavaScript, а CSP сайта запрещает скрипты, поэтому баннеры
свои: администратор загружает картинку (PNG, JPEG, GIF или WebP до 1 МБ, без SVG — в SVG
можно спрятать скрипт), указывает ссылку, места показа и даты. Картинка отдаётся с этого же
сайта (/ad/<id>/image), переход идёт через /ad/<id> — так считаются показы и клики.
На страницах самого теста реклама не показывается.
"""

import random
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlsplit

import config
from app import database
from app.templates import SafeHTML, fragment

# Места показа: код → название в админке.
PLACEMENTS = {
    "landing": "Главная страница",
    "dashboard": "Личный кабинет",
    "result": "Страница результата теста",
    "history": "История попыток",
}

TITLE_MAX_LENGTH = 120
LINK_MAX_LENGTH = 500

# Сигнатуры файлов: тип картинки определяется по содержимому, а не по имени файла.
_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


class BannerError(Exception):
    """Ошибки формы баннера: список понятных сообщений."""

    def __init__(self, errors: list[str]) -> None:
        """Сохраняет сообщения."""
        super().__init__("; ".join(errors))
        self.errors = errors


def image_type(data: bytes) -> str | None:
    """MIME-тип картинки по первым байтам или None (не PNG/JPEG/GIF/WebP)."""
    for signature, mime in _SIGNATURES:
        if data.startswith(signature):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@dataclass
class BannerForm:
    """Проверенные поля формы баннера."""

    title: str
    link_url: str
    placements: str
    starts_on: str
    ends_on: str
    active: bool
    image: bytes | None
    image_type: str


def validate(title: str, link_url: str, placements: list[str], starts_on: str, ends_on: str,
             active: bool, image: bytes | None, image_required: bool) -> BannerForm:
    """Проверяет форму баннера или выбрасывает BannerError."""
    errors: list[str] = []
    title = " ".join(title.split())
    link_url = link_url.strip()
    if not title:
        errors.append("Введите название баннера (оно же подпись к картинке).")
    elif len(title) > TITLE_MAX_LENGTH:
        errors.append(f"Название — не длиннее {TITLE_MAX_LENGTH} символов.")
    parts = urlsplit(link_url)
    if parts.scheme not in ("http", "https") or not parts.netloc or len(link_url) > LINK_MAX_LENGTH:
        errors.append("Ссылка должна начинаться с https:// или http:// и вести на сайт рекламодателя.")
    chosen = [p for p in PLACEMENTS if p in placements]
    if not chosen:
        errors.append("Отметьте хотя бы одно место показа.")
    try:
        start, end = date.fromisoformat(starts_on), date.fromisoformat(ends_on)
    except ValueError:
        errors.append("Укажите даты начала и окончания показа.")
    else:
        if end < start:
            errors.append("Дата окончания не может быть раньше даты начала.")
    mime = ""
    if image:
        if len(image) > config.BANNER_MAX_BYTES:
            errors.append(f"Картинка больше {config.BANNER_MAX_BYTES // 1_000_000} МБ — уменьшите её.")
        mime = image_type(image) or ""
        if not mime:
            errors.append("Картинка должна быть в формате PNG, JPEG, GIF или WebP.")
    elif image_required:
        errors.append("Загрузите картинку баннера.")
    if errors:
        raise BannerError(errors)
    return BannerForm(title, link_url, ",".join(chosen), starts_on, ends_on, active, image or None, mime)


def status(row, today: str | None = None) -> str:
    """Состояние баннера для админки: показывается, запланирован, закончился, выключен."""
    today = today or date.today().isoformat()
    if not row["active"]:
        return "выключен"
    if row["starts_on"] > today:
        return "запланирован"
    if row["ends_on"] < today:
        return "закончился"
    return "показывается"


def shows_ads(user) -> bool:
    """Реклама — только гостям и ученикам; учителям и администраторам — никогда."""
    return user is None or not (user.is_teacher or user.is_admin)


def banner_block(placement: str, user=None, rng: random.Random | None = None) -> SafeHTML:
    """Баннер для места показа (случайный из подходящих) или пустая строка. Учитывает показ.

    user — кто смотрит страницу (None — гость): учителям и администраторам баннер не показывается.
    Страницы теста баннер не вызывают вовсе.
    """
    if not shows_ads(user):
        return SafeHTML("")
    candidates = database.active_banners(placement, date.today().isoformat())
    if not candidates:
        return SafeHTML("")
    banner = (rng or random).choice(candidates)
    database.count_banner_impression(banner["id"])
    return fragment(
        '<aside class="ad-banner" aria-label="Реклама">'
        '<a href="/ad/$id" rel="sponsored noopener" target="_blank">'
        '<img src="/ad/$id/image" alt="$title"></a><small class="ad-label">Реклама</small></aside>',
        id=banner["id"], title=banner["title"],
    )
