"""Тесты этапа 6: настройки сервера, резервные копии, загрузка файлов, рекламные баннеры."""

import gzip
import os
import sqlite3
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import uuid
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from app import config
from app.core import ads, auth, database, ent_logic
from app.web.server import create_server, parse_multipart
from server import backup
from tests import test_pages
from tests.base import DatabaseTestCase
from tests.test_pages import Browser

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4
JPEG = b"\xff\xd8\xff\xe0" + b"\x00\xff" * 100
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
SERVER_DIR = config.BASE_DIR / "server"
UNITS_DIR = SERVER_DIR / "systemd"


def multipart(fields: dict, files: dict[str, tuple[str, str, bytes]]) -> tuple[bytes, str]:
    """Тело multipart/form-data и заголовок Content-Type (как отправляет браузер)."""
    boundary = uuid.uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields.items():
        for item in value if isinstance(value, list) else [value]:
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                          f"{item}\r\n".encode("utf-8"))
    for name, (filename, mime, data) in files.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
                      f'filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode("utf-8") + data + b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def post_multipart(browser: Browser, path: str, fields: dict, files: dict) -> tuple[int, str, str]:
    """POST формы с файлом через «браузер» теста (с его cookie)."""
    body, content_type = multipart(fields, files)
    request = urllib.request.Request(browser.base_url + path, data=body,
                                     headers={"Content-Type": content_type})
    try:
        with browser.opener.open(request, timeout=10) as response:
            return (response.status, response.geturl().removeprefix(browser.base_url),
                    response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        with error:
            return error.code, path, error.read().decode("utf-8")


class ConfigTests(DatabaseTestCase):
    """Настройки запуска из .env / окружения и cookie с флагом Secure."""

    def test_env_overrides(self) -> None:
        """HOST, PORT, DATABASE_PATH, COOKIE_SECURE и BACKUP_* читаются из окружения."""
        env = {**os.environ, "HOST": "0.0.0.0", "PORT": "8080", "DATABASE_PATH": "/tmp/x.sqlite3",
               "COOKIE_SECURE": "1", "BACKUP_DIR": "/tmp/b", "BACKUP_KEEP": "3"}
        code = ("from app import config; print(config.HOST, config.PORT, config.DATABASE_PATH, config.COOKIE_SECURE, "
                "config.BACKUP_DIR, config.BACKUP_KEEP)")
        result = subprocess.run([sys.executable, "-c", code], cwd=config.BASE_DIR, env=env,
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.split(), ["0.0.0.0", "8080", "/tmp/x.sqlite3", "True", "/tmp/b", "3"])

    def test_secure_cookies(self) -> None:
        """С COOKIE_SECURE=1 cookie сессии и OAuth отправляются только по HTTPS."""
        user_id = auth.create_account("Али", "ali@mail.kz", "password1")
        self.assertNotIn("Secure", auth.start_session(user_id))
        with mock.patch.object(config, "COOKIE_SECURE", True):
            self.assertIn("Secure", auth.start_session(user_id))
            from app.web import account_views
            self.assertIn("Secure", account_views._state_cookie("x", 60))


class BackupTests(DatabaseTestCase):
    """python backup.py: согласованная сжатая копия и ротация."""

    def test_backup_restore_and_rotation(self) -> None:
        """Копия восстанавливается и содержит данные; хранятся только последние keep копий."""
        auth.create_account("Али", "ali@mail.kz", "password1")
        target = Path(self._tmp.name) / "backups"
        made = [backup.make_backup(database._db_path, target, keep=3, now=1_800_000_000 + i * 60)
                for i in range(5)]
        self.assertEqual(backup.list_backups(target), made[-3:])
        restored = Path(self._tmp.name) / "restored.sqlite3"
        restored.write_bytes(gzip.decompress(made[-1].read_bytes()))
        with sqlite3.connect(restored) as connection:
            self.assertEqual(connection.execute("SELECT login FROM users").fetchone()[0], "ali@mail.kz")
        self.assertFalse(list(target.glob("*.sqlite3")))

    def test_missing_database(self) -> None:
        """Нет базы — понятная ошибка и код возврата 1."""
        with self.assertRaises(backup.BackupError):
            backup.make_backup(Path(self._tmp.name) / "nope.sqlite3", Path(self._tmp.name) / "b")
        with mock.patch.object(backup, "make_backup", side_effect=backup.BackupError("нет базы")), \
                mock.patch("sys.stderr"):
            self.assertEqual(backup.main(), 1)


class MultipartTests(DatabaseTestCase):
    """Разбор форм с файлами без модуля cgi."""

    def test_parse_fields_and_binary_file(self) -> None:
        """Текст в UTF-8 и двоичный файл (все 256 значений байта) разбираются без искажений."""
        body, content_type = multipart({"title": "Баннер", "places": ["a", "b"]},
                                       {"image": ("x.png", "image/png", PNG)})
        form, files = parse_multipart(content_type, body)
        self.assertEqual(form, {"title": ["Баннер"], "places": ["a", "b"]})
        self.assertEqual((files["image"].filename, files["image"].data), ("x.png", PNG))

    def test_broken_body(self) -> None:
        """Мусор вместо формы — пустая форма, а не ошибка сервера."""
        self.assertEqual(parse_multipart("multipart/form-data; boundary=zz", b"\x00garbage"), ({}, {}))
        self.assertEqual(parse_multipart("multipart/form-data", b"--x\r\n"), ({}, {}))


class BannerLogicTests(DatabaseTestCase):
    """Проверка формы баннера, тип картинки, выбор баннера для показа."""

    def valid(self, **changes):
        """Проверка формы с разумными значениями."""
        today = date.today()
        values = {"title": "Курсы английского", "link_url": "https://example.kz", "placements": ["landing"],
                  "starts_on": today.isoformat(), "ends_on": (today + timedelta(days=7)).isoformat(),
                  "active": True, "image": PNG, "image_required": True, **changes}
        return ads.validate(**values)

    def test_image_types(self) -> None:
        """Тип определяется по содержимому; SVG и прочее не принимаются."""
        self.assertEqual(ads.image_type(PNG), "image/png")
        self.assertEqual(ads.image_type(JPEG), "image/jpeg")
        self.assertEqual(ads.image_type(b"GIF89a..."), "image/gif")
        self.assertEqual(ads.image_type(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "image/webp")
        self.assertIsNone(ads.image_type(SVG))

    def test_form_errors(self) -> None:
        """Каждая ошибка формы — понятное сообщение."""
        cases = (
            ({"title": " "}, "название"),
            ({"link_url": "javascript:alert(1)"}, "https://"),
            ({"link_url": "ftp://x"}, "https://"),
            ({"placements": ["exam"]}, "место показа"),
            ({"ends_on": "2000-01-01"}, "раньше даты начала"),
            ({"starts_on": "вчера"}, "даты"),
            ({"image": SVG}, "PNG, JPEG"),
            ({"image": None}, "Загрузите картинку"),
            ({"image": PNG + b"0" * config.BANNER_MAX_BYTES}, "больше 1 МБ"),
        )
        for changes, fragment in cases:
            with self.assertRaises(ads.BannerError, msg=changes) as context:
                self.valid(**changes)
            self.assertIn(fragment, " ".join(context.exception.errors), changes)
        form = self.valid(placements=["dashboard", "landing", "exam"])
        self.assertEqual((form.placements, form.image_type), ("landing,dashboard", "image/png"))
        self.assertIsNone(self.valid(image=None, image_required=False).image)

    def test_only_active_banners_in_their_dates_and_places(self) -> None:
        """Показываются включённые баннеры этого места, у которых сегодня в сроке."""
        today = date.today()
        day = timedelta(days=1)
        rows = [("сейчас", "landing,result", today - day, today + day, True),
                ("будущий", "landing", today + day, today + 5 * day, True),
                ("прошедший", "landing", today - 5 * day, today - day, True),
                ("выключен", "landing", today - day, today + day, False),
                ("последний день", "dashboard", today - day, today, True)]
        ids = {title: database.create_banner(title, "https://e.kz", PNG, "image/png", places,
                                             start.isoformat(), end.isoformat(), active, 0)
               for title, places, start, end, active in rows}
        iso = today.isoformat()
        self.assertEqual([r["title"] for r in database.active_banners("landing", iso)], ["сейчас"])
        self.assertEqual([r["title"] for r in database.active_banners("dashboard", iso)], ["последний день"])
        self.assertEqual(database.active_banners("history", iso), [])
        self.assertEqual({ads.status(database.get_banner(i)) for i in ids.values()},
                         {"показывается", "запланирован", "закончился", "выключен"})

        html = str(ads.banner_block("result"))
        self.assertIn(f'href="/ad/{ids["сейчас"]}"', html)
        self.assertIn('rel="sponsored noopener"', html)
        self.assertIn("Реклама", html)
        self.assertEqual(database.get_banner(ids["сейчас"])["impressions"], 1)
        self.assertEqual(str(ads.banner_block("history")), "")


class BannerPagesTests(DatabaseTestCase):
    """Раздел «Реклама» в админке и показ баннеров на сайте."""

    def setUp(self) -> None:
        """Сервер, администратор и ученик."""
        super().setUp()
        self.server = create_server("127.0.0.1", 0)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        auth.create_account("Админ", "admin@mail.kz", "password1")
        database.set_user_role("admin@mail.kz", database.ROLE_ADMIN)
        self.student_id = auth.create_account("Ученик", "student@mail.kz", "password1")

    def tearDown(self) -> None:
        """Останавливает сервер."""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    csrf = staticmethod(test_pages.PagesTests.csrf)

    def login(self, email: str) -> Browser:
        """Браузер, вошедший в аккаунт."""
        browser = Browser(self.base_url)
        _, path, _, _ = browser.post("/login", {"login": email, "password": "password1"})
        self.assertEqual(path, "/dashboard")
        return browser

    def banner_fields(self, html: str, **changes) -> dict:
        """Поля формы баннера с csrf-токеном."""
        today = date.today()
        return {"csrf_token": self.csrf(html), "title": "Курсы английского", "link_url": "https://example.kz/ent",
                "placements": ["landing", "dashboard"], "starts_on": today.isoformat(),
                "ends_on": (today + timedelta(days=10)).isoformat(), "active": "1", **changes}

    def test_admin_creates_banner_and_it_is_shown_and_counted(self) -> None:
        """Загрузка картинки, показ на главной, картинка с этого сайта, клик с переходом."""
        admin = self.login("admin@mail.kz")
        _, _, html, _ = admin.get("/admin/banners/new")
        self.assertIn('enctype="multipart/form-data"', html)

        fields = self.banner_fields(html)
        status, _, _ = post_multipart(admin, "/admin/banners/new", {**fields, "csrf_token": "x"},
                                      {"image": ("a.png", "image/png", PNG)})
        self.assertEqual(status, 403)
        status, _, page = post_multipart(admin, "/admin/banners/new", fields,
                                         {"image": ("a.svg", "image/svg+xml", SVG)})
        self.assertEqual(status, 400)
        self.assertIn("PNG, JPEG, GIF или WebP", page)
        self.assertIn('value="Курсы английского"', page)

        status, path, page = post_multipart(admin, "/admin/banners/new", fields,
                                            {"image": ("a.png", "image/png", PNG)})
        self.assertEqual(path, "/admin/banners?msg=banner_saved")
        self.assertIn("показывается", page)
        banner_id = database.list_banners()[0]["id"]

        _, _, html, _ = Browser(self.base_url).get("/")
        self.assertIn(f'src="/ad/{banner_id}/image"', html)
        self.assertIn("Реклама", html)
        self.assertNotIn("<script", html.lower())

        with urllib.request.urlopen(f"{self.base_url}/ad/{banner_id}/image", timeout=10) as response:
            self.assertEqual(response.headers["Content-Type"], "image/png")
            self.assertIn("max-age", response.headers["Cache-Control"])
            self.assertEqual(response.read(), PNG)

        status, _, _, headers = Browser(self.base_url, follow_redirects=False).get(f"/ad/{banner_id}")
        self.assertEqual((status, headers["Location"]), (303, "https://example.kz/ent"))
        row = database.get_banner(banner_id)
        self.assertEqual((row["impressions"], row["clicks"]), (1, 1))
        self.assertEqual(Browser(self.base_url).get("/ad/999")[0], 404)

        student = self.login("student@mail.kz")
        self.assertIn(f"/ad/{banner_id}/image", student.get("/dashboard")[2])
        self.assertNotIn("ad-banner", student.get("/history")[2])

        _, _, html, _ = admin.get(f"/admin/banners/{banner_id}/edit")
        self.assertIn("Загрузите новый файл, только если", html)
        fields = self.banner_fields(html, title="Новое название")
        fields.pop("active")
        status, path, page = post_multipart(admin, f"/admin/banners/{banner_id}/edit", fields, {})
        self.assertIn("выключен", page)
        self.assertEqual(database.get_banner_image(banner_id), (PNG, "image/png"))
        self.assertNotIn("ad-banner", Browser(self.base_url).get("/")[2])

        _, _, html, _ = admin.get(f"/admin/banners/{banner_id}/edit")
        status, path, _, _ = admin.post(f"/admin/banners/{banner_id}/delete", {"csrf_token": self.csrf(html)})
        self.assertEqual(path, "/admin/banners?msg=banner_deleted")
        self.assertEqual(database.list_banners(), [])

    def test_no_ads_during_test_and_admin_only(self) -> None:
        """На странице самого теста рекламы нет; раздел рекламы — только для администратора."""
        today = date.today()
        database.create_banner("Баннер", "https://e.kz", PNG, "image/png", ",".join(ads.PLACEMENTS),
                               today.isoformat(), today.isoformat(), True, 0)
        self.add_questions("kz_history", config.SINGLE, 3)
        student = self.login("student@mail.kz")
        attempt_id = ent_logic.build_mock(self.student_id, 0)
        status, _, html, _ = student.get(f"/attempt/{attempt_id}/kz_history")
        self.assertEqual(status, 200)
        self.assertNotIn("ad-banner", html)
        self.assertEqual(student.get("/admin/banners")[0], 403)
        self.assertEqual(student.get("/admin/banners/new")[0], 403)


class DeployFilesTests(DatabaseTestCase):
    """Файлы для сервера: службы systemd, Caddy, скрипты установки."""

    def test_units_and_scripts(self) -> None:
        """Службы запускают существующие скрипты проекта; Caddy проксирует на адрес сайта."""
        for unit, command, script in (
                ("ent-master-site.service", "/opt/ent-master/run.py site", "run.py"),
                ("ent-master-bot.service", "/opt/ent-master/run.py bot", "run.py"),
                ("ent-master-backup.service", "-m server.backup", "server/backup.py")):
            text = (UNITS_DIR / unit).read_text(encoding="utf-8")
            self.assertIn(command, text)
            self.assertIn("WorkingDirectory=/opt/ent-master", text)
            self.assertTrue((config.BASE_DIR / script).is_file(), script)
            self.assertIn("User=ent", text)
            self.assertIn("NoNewPrivileges=yes", text)
        self.assertIn("OnCalendar=", (UNITS_DIR / "ent-master-backup.timer").read_text(encoding="utf-8"))
        caddy = (SERVER_DIR / "Caddyfile").read_text(encoding="utf-8")
        self.assertIn(f"reverse_proxy {config.HOST}:{config.PORT}", caddy)
        for script in ("setup.sh", "update.sh"):
            subprocess.run(["bash", "-n", str(SERVER_DIR / script)], check=True)

    def test_backups_are_not_committed(self) -> None:
        """Резервные копии и .env не попадают в git."""
        ignore = (config.BASE_DIR / ".gitignore").read_text(encoding="utf-8")
        for pattern in ("backups/", "*.sqlite3.gz", ".env"):
            self.assertIn(pattern, ignore)
