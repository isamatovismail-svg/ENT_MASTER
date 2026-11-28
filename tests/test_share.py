"""Этап 7: локальный запуск по http, режим показа через интернет (run.py --share)."""

import os
import socket
import stat
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from app import config
from server import launcher as run
from app.core import auth, database
from app.web import server
from app.web.server import create_server
from tests.base import DatabaseTestCase
from tests.test_pages import CSRF_RE, Browser

DEMO_ADMIN = "admin@" + config.DEMO_EMAIL_DOMAIN
DEMO_TEACHER = "teacher@" + config.DEMO_EMAIL_DOMAIN
PASSWORD = "Strong-pass-2026"


class LocalUrlTests(unittest.TestCase):
    """Ссылка для браузера — всегда http://localhost (не 127.0.0.1 и не https)."""

    def test_local_url_is_plain_http_localhost(self) -> None:
        self.assertEqual(config.LOCAL_URL, f"http://localhost:{config.PORT}")

    def test_tunnel_url_pattern(self) -> None:
        line = "2026-11-27T10:00:00Z INF |  https://quiet-river-1234.trycloudflare.com  |"
        self.assertEqual(run.TUNNEL_URL_RE.search(line).group(0),
                         "https://quiet-river-1234.trycloudflare.com")

    def test_share_banner_shows_url(self) -> None:
        banner = run.share_banner("https://abc.trycloudflare.com")
        self.assertIn("https://abc.trycloudflare.com", banner)
        self.assertIn("Ctrl+C", banner)


class HttpsAttemptTests(DatabaseTestCase):
    """Браузер стучится по https на http-сервер: понятная подсказка в логе, а не мусор."""

    def setUp(self) -> None:
        super().setUp()
        self.server = create_server("127.0.0.1", 0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        server._tls_warned_at = 0.0

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def test_tls_client_hello_gets_hint_not_400(self) -> None:
        with self.assertLogs("app.web.server", level="WARNING") as logs:
            with socket.create_connection(("127.0.0.1", self.port), timeout=5) as sock:
                sock.sendall(b"\x16\x03\x01\x02\x00\x01\x00\x01\xfc\x03\x03" + b"\x00" * 40 + b"\r\n")
                reply = sock.recv(1024)
        self.assertEqual(reply, b"")
        text = "\n".join(logs.output)
        self.assertIn("http://localhost", text)
        self.assertNotIn("Bad request version", text)

    def test_plain_http_still_works(self) -> None:
        status, _, html, headers = Browser(f"http://127.0.0.1:{self.port}").get("/")
        self.assertEqual(status, 200)
        self.assertNotIn("Strict-Transport-Security", headers)


class ShareModeTests(DatabaseTestCase):
    """В режиме показа демо-админ войти не может, остальные — могут."""

    def setUp(self) -> None:
        super().setUp()
        self.admin_id = auth.create_account("Админ Демо", DEMO_ADMIN, PASSWORD)
        database.set_user_role(DEMO_ADMIN, database.ROLE_ADMIN)
        auth.create_account("Учитель Демо", DEMO_TEACHER, PASSWORD)
        self._share = config.SHARE_MODE

    def tearDown(self) -> None:
        config.SHARE_MODE = self._share
        super().tearDown()

    def test_demo_admin_blocked_only_in_share_mode(self) -> None:
        config.SHARE_MODE = False
        self.assertFalse(auth.is_blocked_demo_admin(DEMO_ADMIN, database.ROLE_ADMIN))
        config.SHARE_MODE = True
        self.assertTrue(auth.is_blocked_demo_admin(DEMO_ADMIN, database.ROLE_ADMIN))
        self.assertTrue(auth.is_blocked_demo_admin(DEMO_ADMIN.upper(), database.ROLE_ADMIN))
        self.assertFalse(auth.is_blocked_demo_admin(DEMO_TEACHER, database.ROLE_TEACHER))
        self.assertFalse(auth.is_blocked_demo_admin("boss@school.kz", database.ROLE_ADMIN))

    def test_existing_demo_admin_session_ignored(self) -> None:
        cookie = auth.start_session(self.admin_id)
        token = cookie.split(";")[0].split("=", 1)[1]
        from app.web.http import Request
        request = Request("GET", "/", cookies={config.SESSION_COOKIE_NAME: token})
        config.SHARE_MODE = True
        auth.attach_user(request)
        self.assertIsNone(request.user)
        config.SHARE_MODE = False
        auth.attach_user(request)
        self.assertIsNotNone(request.user)

    def test_weak_admin_password_detected(self) -> None:
        auth.create_account("Главный", "boss@school.kz", "admin2026")
        database.set_user_role("boss@school.kz", database.ROLE_ADMIN)
        auth.create_account("Второй", "second@school.kz", "Very-Long-Unique-9431")
        database.set_user_role("second@school.kz", database.ROLE_ADMIN)
        self.assertEqual(auth.weak_admin_logins(), ["boss@school.kz"])


class BehindTunnelTests(DatabaseTestCase):
    """Сайт за туннелем: снаружи https, внутри http, заголовки прокси — вход, куки, CSRF, формы."""

    def setUp(self) -> None:
        super().setUp()
        auth.create_account("Админ Демо", DEMO_ADMIN, PASSWORD)
        database.set_user_role(DEMO_ADMIN, database.ROLE_ADMIN)
        auth.create_account("Ученик", "student@" + config.DEMO_EMAIL_DOMAIN, PASSWORD)
        self._share, config.SHARE_MODE = config.SHARE_MODE, True
        self.server = create_server("127.0.0.1", 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.browser = Browser(f"http://127.0.0.1:{self.server.server_address[1]}")
        self.browser.opener.addheaders = [
            ("X-Forwarded-Proto", "https"), ("Cf-Visitor", '{"scheme":"https"}'),
            ("Host", "quiet-river-1234.trycloudflare.com"),
        ]

    def tearDown(self) -> None:
        config.SHARE_MODE = self._share
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def _login(self, login: str) -> tuple[int, str, str, dict]:
        status, _, _, _ = self.browser.get("/login")
        self.assertEqual(status, 200)
        return self.browser.post("/login", {"login": login, "password": PASSWORD, "next": "/dashboard"})

    def test_student_login_cookies_redirects_and_csrf(self) -> None:
        status, path, html, _ = self._login("student@" + config.DEMO_EMAIL_DOMAIN)
        self.assertEqual(status, 200)
        self.assertEqual(path, "/dashboard")
        cookie = next(c for c in self.browser.cookies if c.name == config.SESSION_COOKIE_NAME)
        self.assertTrue(cookie.has_nonstandard_attr("HttpOnly"))
        self.assertNotIn("localhost", html)
        self.assertNotIn("127.0.0.1", html)
        token = CSRF_RE.search(html).group(1)
        status, path, _, _ = self.browser.post("/logout", {"csrf_token": token})
        self.assertEqual(status, 200)
        status, path, _, _ = self.browser.get("/dashboard")
        self.assertTrue(path.startswith("/login"))

    def test_demo_admin_cannot_log_in(self) -> None:
        status, path, html, _ = self._login(DEMO_ADMIN)
        self.assertEqual(status, 400)
        self.assertIn("Демо-администратор не может войти", html)
        self.assertFalse(any(c.name == config.SESSION_COOKIE_NAME for c in self.browser.cookies))


FAKE_CLOUDFLARED = """#!{python}
import signal, sys, time
signal.signal(signal.SIGINT, lambda *a: sys.exit(0))
print("2026-11-27T10:00:00Z INF Requesting new quick Tunnel on trycloudflare.com...", flush=True)
print("2026-11-27T10:00:01Z INF |  https://quiet-river-1234.trycloudflare.com  |", flush=True)
print("2026-11-27T10:00:02Z INF Registered tunnel connection connIndex=0", flush=True)
while True:
    time.sleep(0.1)
"""


@unittest.skipUnless(os.name == "posix", "нужен posix")
class TunnelProcessTests(unittest.TestCase):
    """run.Tunnel находит ссылку в выводе cloudflared и останавливается по Ctrl+C."""

    def test_tunnel_url_and_stop(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            fake = Path(folder) / "cloudflared"
            fake.write_text(FAKE_CLOUDFLARED.format(python=sys.executable), encoding="utf-8")
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            tunnel = run.Tunnel(str(fake), "http://localhost:8000")
            try:
                self.assertEqual(tunnel.wait(10), "https://quiet-river-1234.trycloudflare.com")
            finally:
                started = time.monotonic()
                run.stop(tunnel.process, run.TUNNEL_LABEL)
            self.assertIsNotNone(tunnel.process.poll())
            self.assertLess(time.monotonic() - started, run.STOP_TIMEOUT_SECONDS)


if __name__ == "__main__":
    unittest.main()
