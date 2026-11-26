"""Telegram-бот ENT MASTER на чистом Python: urllib + json, long polling Bot API.

Бот работает с той же базой, что и сайт:
- «Войти на сайт» — одноразовая ссылка /tg/login?token=… (10 минут);
- «Тренировка» — те же попытки practice, что и на сайте: выбор предмета → вопрос
  с inline-кнопками → ✅/❌, правильный ответ и объяснение → следующий вопрос;
- «Мои результаты» — последние попытки и лучший балл.

Состояние выбора хранится прямо в callback_data кнопок (например, отмеченные
варианты в задании «несколько ответов»), поэтому бот не держит ничего в памяти
и переживает перезапуск.
"""

import json
import logging
import secrets
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import config
from app import auth, database, ent_logic
from app.database import Attempt, AttemptQuestion, User

logger = logging.getLogger(__name__)

API_URL = "https://api.telegram.org/bot{token}/{method}"
MESSAGE_LIMIT = 4000          # Telegram ограничивает сообщение 4096 символами
SKIP = "-"                    # «Пропустить» в callback_data
LETTERS = config.OPTION_LETTERS
STATE_ICONS = {"ok": "✅", "partial": "🟡", "wrong": "❌"}


class TelegramError(Exception):
    """Bot API вернул ошибку (ok = false) или неожиданный ответ."""

    def __init__(self, description: str, code: int = 0) -> None:
        """Сохраняет текст и код ошибки Telegram."""
        super().__init__(description)
        self.code = code


class TelegramAPI:
    """Минимальный клиент Bot API: POST с JSON через urllib."""

    def __init__(self, token: str, opener: Callable[..., Any] = urllib.request.urlopen) -> None:
        """token — токен бота; opener подменяется в тестах."""
        self._token = token
        self._opener = opener

    def call(self, method: str, **params: Any) -> Any:
        """Вызывает метод Bot API и возвращает поле result."""
        request = urllib.request.Request(
            API_URL.format(token=self._token, method=method),
            data=json.dumps(params, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        # Long polling держит запрос до timeout секунд — ждём чуть дольше.
        return self._send(request, int(params.get("timeout", 0)) + 15)

    def send_document(self, chat_id: int, filename: str, data: bytes, caption: str = "") -> Any:
        """Отправляет файл (sendDocument). Тело multipart/form-data собирается вручную."""
        boundary = secrets.token_hex(16)
        parts = []
        for name, value in (("chat_id", str(chat_id)), ("caption", caption)):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                         f"{value}\r\n".encode("utf-8"))
        safe_name = filename.replace('"', "").replace("\r", "").replace("\n", "")
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="document"; '
                     f'filename="{safe_name}"\r\nContent-Type: application/octet-stream\r\n\r\n'
                     .encode("utf-8") + data + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode("ascii"))
        request = urllib.request.Request(
            API_URL.format(token=self._token, method="sendDocument"),
            data=b"".join(parts),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        return self._send(request, 120)

    def _send(self, request: urllib.request.Request, timeout: int) -> Any:
        """Выполняет запрос к Bot API и возвращает поле result (ошибка — TelegramError)."""
        try:
            with self._opener(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            # Telegram отвечает JSON с описанием ошибки и на 4xx.
            with error:
                try:
                    payload = json.loads(error.read().decode("utf-8"))
                except (ValueError, OSError):
                    raise TelegramError(f"HTTP {error.code}", error.code) from None
        if not isinstance(payload, dict) or not payload.get("ok"):
            description = payload.get("description", "неизвестная ошибка") if isinstance(
                payload, dict) else "неожиданный ответ"
            raise TelegramError(description, payload.get("error_code", 0) if isinstance(
                payload, dict) else 0)
        return payload.get("result")


# ── Клавиатуры ───────────────────────────────────────────────────────────────

def _button(text: str, data: str) -> dict:
    """Inline-кнопка с callback_data (Telegram ограничивает её 64 байтами)."""
    assert len(data.encode("utf-8")) <= 64, data
    return {"text": text, "callback_data": data}


def _keyboard(*rows: list[dict]) -> dict:
    """reply_markup с inline-клавиатурой."""
    return {"inline_keyboard": [row for row in rows if row]}


def _chunks(items: list, size: int) -> list[list]:
    """Делит список кнопок на ряды по size штук."""
    return [items[index:index + size] for index in range(0, len(items), size)]


def _is_public_url(url: str) -> bool:
    """Telegram не принимает в кнопках ссылки на localhost — их отправляем только текстом."""
    host = (urlsplit(url).hostname or "").lower()
    return bool(host) and host not in ("localhost", "0.0.0.0", "::1") and not host.startswith("127.")


MENU_KEYBOARD = _keyboard(
    [_button("🔐 Войти на сайт", "login")],
    [_button("🎯 Тренировка", "train"), _button("📊 Мои результаты", "results")],
)


# ── Тексты ───────────────────────────────────────────────────────────────────

def _option(aq: AttemptQuestion, letter: str) -> str:
    """«B) текст» по букве."""
    index = LETTERS.find(letter)
    if letter and 0 <= index < len(aq.options):
        return f"{letter}) {aq.options[index]}"
    return "—"


def _answer_text(aq: AttemptQuestion, answer: list[str] | None) -> str:
    """Ответ в читаемом виде; для соответствия — по строкам."""
    if not answer:
        return "нет ответа"
    if aq.qtype == config.MATCHING:
        lines = []
        for index, left in enumerate(aq.left):
            letter = answer[index] if index < len(answer) else ""
            lines.append(f"  {index + 1}) {left} → {_option(aq, letter)}")
        return "\n" + "\n".join(lines)
    return "; ".join(_option(aq, letter) for letter in answer)


def _fit(text: str) -> str:
    """Обрезает текст под ограничение Telegram."""
    return text if len(text) <= MESSAGE_LIMIT else text[: MESSAGE_LIMIT - 1] + "…"


def question_text(aq: AttemptQuestion, total: int, progress: str = "") -> str:
    """Текст сообщения с вопросом."""
    subject = config.SUBJECTS[aq.subject]
    lines = [
        f"{subject.icon} {subject.name} · вопрос {aq.position} из {total}",
        f"{config.QUESTION_TYPE_NAMES[aq.qtype]} · {ent_logic.question_max_points(aq.qtype)} б.",
        "",
    ]
    if aq.context:
        lines += [aq.context, ""]
    lines += [aq.text, ""]
    if aq.qtype == config.MATCHING:
        lines.append("Строки:")
        lines += [f"{index + 1}) {left}" for index, left in enumerate(aq.left)]
        lines += ["", "Варианты:"]
    lines += [f"{letter}) {option}" for letter, option in zip(LETTERS, aq.options)]
    lines.append("")
    if aq.qtype == config.MATCHING:
        done = len(progress)
        for index in range(done):
            lines.append(f"✔ {index + 1}) {aq.left[index]} → {progress[index]}")
        if done < len(aq.left):
            lines.append(f"👉 Выберите букву для строки {done + 1}: {aq.left[done]}")
    elif aq.qtype == config.MULTIPLE:
        lines.append("👉 Отметьте все верные варианты и нажмите «Готово».")
    else:
        lines.append("👉 Выберите один вариант.")
    return _fit("\n".join(lines))


def question_keyboard(attempt_id: int, aq: AttemptQuestion, state: str = "") -> dict:
    """Кнопки ответа. state — уже отмеченные буквы (несколько ответов) или ответы по строкам."""
    letters = LETTERS[: len(aq.options)]
    ids = f"{attempt_id}:{aq.id}"
    skip = [_button("⏭ Пропустить", f"a:{ids}:{SKIP}")]
    if aq.qtype == config.MULTIPLE:
        buttons = []
        for letter in letters:
            chosen = letter in state
            toggled = "".join(sorted(set(state) ^ {letter}))
            buttons.append(_button(f"✅ {letter}" if chosen else letter, f"t:{ids}:{toggled}"))
        done = _button("Готово ✔", f"a:{ids}:{state or SKIP}")
        return _keyboard(*_chunks(buttons, 4), [done], skip)
    if aq.qtype == config.MATCHING:
        buttons = [_button(letter, f"m:{ids}:{state}{letter}") for letter in letters]
        return _keyboard(*_chunks(buttons, 4), skip)
    buttons = [_button(letter, f"a:{ids}:{letter}") for letter in letters]
    return _keyboard(*_chunks(buttons, 4), skip)


# ── Бот ──────────────────────────────────────────────────────────────────────

class Bot:
    """Обработчик обновлений Telegram. Все данные — в общей базе сайта."""

    def __init__(self, api: TelegramAPI) -> None:
        """api — клиент Bot API (в тестах — заглушка, записывающая вызовы)."""
        self.api = api

    # ── отправка ─────────────────────────────────────────────────────────────

    def send(self, chat_id: int, text: str, keyboard: dict | None = None) -> None:
        """Отправляет сообщение (без превью ссылок)."""
        params: dict[str, Any] = {
            "chat_id": chat_id, "text": _fit(text),
            "link_preview_options": {"is_disabled": True},
        }
        if keyboard is not None:
            params["reply_markup"] = keyboard
        self.api.call("sendMessage", **params)

    def _edit(self, method: str, **params: Any) -> None:
        """Редактирует сообщение; ошибка «не изменилось» и т.п. не мешает работе."""
        try:
            self.api.call(method, **params)
        except TelegramError as error:
            logger.info("Не удалось изменить сообщение: %s", error)

    # ── входящие ─────────────────────────────────────────────────────────────

    def handle_update(self, update: dict) -> None:
        """Обрабатывает одно обновление getUpdates."""
        if "message" in update:
            self._on_message(update["message"])
        elif "callback_query" in update:
            self._on_callback(update["callback_query"])

    def _on_message(self, message: dict) -> None:
        """Текстовые команды. Бот отвечает только в личных сообщениях."""
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        if chat.get("type") != "private" or "id" not in sender:
            return
        command = (message.get("text") or "").strip().split(maxsplit=1)[0:1]
        command = command[0].split("@", 1)[0].lower() if command else ""
        chat_id = chat["id"]
        if command == "/login":
            self.send_login(chat_id, sender)
        elif command == "/train":
            self.send_subjects(chat_id, sender)
        elif command == "/results":
            self.send_results(chat_id, sender)
        else:
            self.send_menu(chat_id, sender)

    def _on_callback(self, query: dict) -> None:
        """Нажатия inline-кнопок."""
        sender = query.get("from") or {}
        message = query.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        data = query.get("data") or ""
        notice = ""
        if chat_id is not None and "id" in sender:
            try:
                notice = self._dispatch(chat_id, message.get("message_id"), sender, data)
            finally:
                # Всегда отвечаем на нажатие, иначе на кнопке «крутятся часики».
                self._edit("answerCallbackQuery", callback_query_id=query.get("id"),
                           text=notice or "")
        else:
            self._edit("answerCallbackQuery", callback_query_id=query.get("id"))

    def _dispatch(self, chat_id: int, message_id: int | None, sender: dict, data: str) -> str:
        """Выполняет действие кнопки. Возвращает короткую подсказку для answerCallbackQuery."""
        action, _, rest = data.partition(":")
        if action == "menu":
            self.send_menu(chat_id, sender)
            return ""
        if action == "login":
            self.send_login(chat_id, sender)
            return ""
        if action == "train":
            self.send_subjects(chat_id, sender)
            return ""
        if action == "results":
            self.send_results(chat_id, sender)
            return ""

        user = self._user(chat_id, sender)
        if user is None:
            return "Сначала войдите на сайт"
        if action == "subj":
            return self.start_practice(chat_id, user, rest)

        parts = rest.split(":")
        try:
            attempt_id = int(parts[0])
        except ValueError:
            return "Кнопка устарела"
        attempt = database.get_attempt(attempt_id, user.id)
        if attempt is None or attempt.mode != ent_logic.PRACTICE:
            return "Эта тренировка не найдена"
        if action == "next":
            return self.send_next(chat_id, attempt)
        if action == "fin":
            return self.finish(chat_id, attempt)

        if len(parts) != 3 or attempt.is_finished:
            return "Тренировка уже завершена" if attempt.is_finished else "Кнопка устарела"
        try:
            aq_id = int(parts[1])
        except ValueError:
            return "Кнопка устарела"
        aq = next((item for item in database.get_attempt_questions(attempt.id) if item.id == aq_id),
                  None)
        if aq is None:
            return "Кнопка устарела"
        if aq.checked:
            return "Вы уже ответили на этот вопрос"
        state = parts[2]
        if any(letter not in LETTERS[: len(aq.options)] for letter in state.replace(SKIP, "")):
            return "Кнопка устарела"
        total = len(database.get_attempt_questions(attempt.id))

        if action == "t" and aq.qtype == config.MULTIPLE:
            self._edit("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
                       reply_markup=question_keyboard(attempt.id, aq, state))
            return ""
        if action == "m" and aq.qtype == config.MATCHING:
            if len(state) < len(aq.left):
                self._edit("editMessageText", chat_id=chat_id, message_id=message_id,
                           text=question_text(aq, total, state),
                           reply_markup=question_keyboard(attempt.id, aq, state))
                return ""
            return self.answer(chat_id, message_id, attempt, aq, state[: len(aq.left)])
        if action == "a":
            return self.answer(chat_id, message_id, attempt, aq, state)
        return "Кнопка устарела"

    # ── экраны ───────────────────────────────────────────────────────────────

    @staticmethod
    def _user(chat_id: int, sender: dict) -> User | None:
        """Пользователь сайта, привязанный к этому Telegram."""
        return database.get_user_by_telegram(int(sender["id"]))

    def _need_login(self, chat_id: int) -> None:
        """Подсказка: без привязки результаты некуда сохранять."""
        self.send(
            chat_id,
            "Чтобы тренироваться и сохранять результаты, войдите на сайт через бота — "
            "это одна ссылка. Тренировки в боте и на сайте будут в одном аккаунте.",
            _keyboard([_button("🔐 Войти на сайт", "login")]),
        )

    def send_menu(self, chat_id: int, sender: dict) -> None:
        """Приветствие и главное меню."""
        user = self._user(chat_id, sender)
        name = sender.get("first_name") or "друг"
        status = (
            f"✅ Аккаунт привязан: {user.name}. Результаты сохраняются на сайте."
            if user is not None else
            "Чтобы результаты сохранялись, нажмите «Войти на сайт»."
        )
        self.send(
            chat_id,
            f"👋 Привет, {name}! Я бот ENT MASTER — помогаю готовиться к ЕНТ.\n\n"
            "🎯 Тренировка — 10 вопросов по предмету: отвечаете кнопками и сразу видите "
            "правильный ответ с объяснением.\n"
            "📊 Мои результаты — последние попытки и лучший балл.\n\n" + status,
            MENU_KEYBOARD,
        )

    def send_login(self, chat_id: int, sender: dict) -> None:
        """Одноразовая ссылка входа на сайт."""
        name = " ".join(filter(None, (sender.get("first_name"), sender.get("last_name"))))
        url = auth.telegram_login_url(int(sender["id"]), name)
        keyboard = _keyboard([{"text": "🌐 Открыть сайт", "url": url}]) if _is_public_url(url) else None
        self.send(
            chat_id,
            f"🔐 Ссылка для входа на сайт (одноразовая, действует "
            f"{config.TELEGRAM_LOGIN_TOKEN_MINUTES} минут):\n\n{url}\n\n"
            "Если аккаунта ещё нет — сайт создаст его в один клик. "
            "Если есть — привяжите его по логину и паролю. Никому не пересылайте эту ссылку.",
            keyboard,
        )

    def send_subjects(self, chat_id: int, sender: dict) -> None:
        """Выбор предмета для тренировки (и «Продолжить», если есть начатая)."""
        user = self._user(chat_id, sender)
        if user is None:
            self._need_login(chat_id)
            return
        rows = []
        current = database.get_in_progress_attempt(user.id, ent_logic.PRACTICE)
        if current is not None:
            questions = database.get_attempt_questions(current.id)
            done = sum(1 for aq in questions if aq.checked)
            subject = config.SUBJECTS[current.subjects[0]]
            rows.append([_button(f"▶️ Продолжить: {subject.name} ({done}/{len(questions)})",
                                 f"next:{current.id}")])
        counts = database.question_counts()
        buttons = [
            _button(f"{subject.icon} {subject.name}", f"subj:{subject.code}")
            for subject in config.SUBJECTS.values()
            if any(counts.get((subject.code, qtype)) for qtype in config.QUESTION_TYPES)
        ]
        rows += _chunks(buttons, 2)
        self.send(
            chat_id,
            f"🎯 Выберите предмет — {config.PRACTICE_QUESTION_COUNT} случайных вопросов. "
            "После каждого ответа покажу правильный ответ и объяснение.",
            _keyboard(*rows),
        )

    def start_practice(self, chat_id: int, user: User, subject_code: str) -> str:
        """Новая тренировка по предмету и первый вопрос."""
        try:
            attempt_id = ent_logic.build_practice(user.id, subject_code)
        except ent_logic.TestBuildError as error:
            return str(error)[:190]
        attempt = database.get_attempt(attempt_id, user.id)
        assert attempt is not None
        return self.send_next(chat_id, attempt)

    def send_next(self, chat_id: int, attempt: Attempt) -> str:
        """Следующий непроверенный вопрос (или итог, если вопросы закончились)."""
        if attempt.is_finished:
            return self.finish(chat_id, attempt)
        questions = database.get_attempt_questions(attempt.id)
        current = next((aq for aq in questions if not aq.checked), None)
        if current is None:
            return self.finish(chat_id, attempt)
        self.send(chat_id, question_text(current, len(questions)),
                  question_keyboard(attempt.id, current))
        return ""

    def answer(self, chat_id: int, message_id: int | None, attempt: Attempt,
               aq: AttemptQuestion, state: str) -> str:
        """Проверяет ответ, убирает кнопки у вопроса и присылает разбор."""
        if state == SKIP or not state:
            form: dict[str, list[str]] = {}
        elif aq.qtype == config.MATCHING:
            form = {f"q{aq.id}_{index}": [letter] for index, letter in enumerate(state)}
        else:
            form = {f"q{aq.id}": list(state)}
        if not ent_logic.check_practice_answer(attempt, aq, form):
            return "Вы уже ответили на этот вопрос"
        self._edit("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
                   reply_markup={"inline_keyboard": []})

        questions = database.get_attempt_questions(attempt.id)
        checked = next(item for item in questions if item.id == aq.id)
        state_name = ent_logic.question_state(checked)
        max_points = ent_logic.question_max_points(checked.qtype)
        if not checked.answer:
            verdict = f"⏭ Пропущено · 0 из {max_points} б."
        elif state_name == "ok":
            verdict = f"✅ Верно! +{checked.points} из {max_points} б."
        elif state_name == "partial":
            verdict = f"🟡 Почти: одна ошибка · {checked.points} из {max_points} б."
        else:
            verdict = f"❌ Неверно · 0 из {max_points} б."
        lines = [verdict, ""]
        if state_name == "ok":
            lines.append(f"Ответ: {_answer_text(checked, checked.correct)}")
        else:
            if checked.answer:
                lines.append(f"Ваш ответ: {_answer_text(checked, checked.answer)}")
            lines.append(f"Правильный ответ: {_answer_text(checked, checked.correct)}")
        if checked.explanation:
            lines += ["", f"💡 Почему так: {checked.explanation}"]

        remaining = sum(1 for item in questions if not item.checked)
        if remaining:
            keyboard = _keyboard([_button("Следующий вопрос ➡️", f"next:{attempt.id}")],
                                 [_button("🏁 Закончить", f"fin:{attempt.id}")])
        else:
            keyboard = _keyboard([_button("🏁 Посмотреть итог", f"fin:{attempt.id}")])
        self.send(chat_id, "\n".join(lines), keyboard)
        return ""

    def finish(self, chat_id: int, attempt: Attempt) -> str:
        """Завершает тренировку и присылает итог."""
        if not attempt.is_finished:
            ent_logic.finish_attempt(attempt)
        finished = database.get_attempt(attempt.id, attempt.user_id)
        assert finished is not None
        questions = database.get_attempt_questions(finished.id)
        subject = config.SUBJECTS[finished.subjects[0]]
        percent = round(finished.score * 100 / finished.max_score) if finished.max_score else 0
        marks = "".join(
            STATE_ICONS[ent_logic.question_state(aq)] if aq.answer else "⏭" for aq in questions
        )
        self.send(
            chat_id,
            f"🏁 Тренировка завершена: {subject.icon} {subject.name}\n\n"
            f"Результат: {finished.score} из {finished.max_score} баллов ({percent}%)\n{marks}\n\n"
            f"Полный разбор на сайте: {config.SITE_URL}/result/{finished.id}",
            _keyboard([_button("🔁 Ещё 10 вопросов", f"subj:{subject.code}")],
                      [_button("🎯 Другой предмет", "train"),
                       _button("📊 Мои результаты", "results")]),
        )
        return ""

    def send_results(self, chat_id: int, sender: dict) -> None:
        """Последние попытки и лучший балл."""
        user = self._user(chat_id, sender)
        if user is None:
            self._need_login(chat_id)
            return
        attempts = database.get_finished_attempts(user.id)
        mocks = [attempt for attempt in attempts if attempt.mode == ent_logic.MOCK]
        practices = [attempt for attempt in attempts if attempt.mode == ent_logic.PRACTICE]
        best = max((attempt.score for attempt in mocks), default=None)
        lines = [f"📊 Результаты: {user.name}", ""]
        lines.append(
            f"🏆 Лучший пробный ЕНТ: {best} из {config.MOCK_MAX_SCORE}" if best is not None
            else "🏆 Пробный ЕНТ ещё не проходили — он доступен на сайте."
        )
        if practices:
            average = round(sum(
                a.score * 100 / a.max_score for a in practices if a.max_score
            ) / len(practices))
            best_practice = max(
                (round(a.score * 100 / a.max_score) for a in practices if a.max_score), default=0
            )
            lines.append(f"🎯 Тренировок: {len(practices)} · средний результат {average}% · "
                         f"лучший {best_practice}%")
        if attempts:
            lines += ["", "Последние попытки:"]
            for attempt in attempts[:5]:
                when = time.strftime("%d.%m %H:%M", time.localtime(attempt.finished_at or 0))
                if attempt.mode == ent_logic.MOCK:
                    what = "Пробный ЕНТ"
                else:
                    subject = config.SUBJECTS[attempt.subjects[0]]
                    what = f"{subject.icon} {subject.name}"
                percent = round(attempt.score * 100 / attempt.max_score) if attempt.max_score else 0
                lines.append(f"• {when} · {what} — {attempt.score}/{attempt.max_score} ({percent}%)")
        else:
            lines += ["", "Пока нет завершённых попыток. Начните с тренировки!"]
        lines += ["", f"Подробно: {config.SITE_URL}/history"]
        self.send(chat_id, "\n".join(lines),
                  _keyboard([_button("🎯 Тренировка", "train"), _button("🏠 Меню", "menu")]))


# ── Long polling ─────────────────────────────────────────────────────────────

BOT_COMMANDS = [
    {"command": "start", "description": "Главное меню"},
    {"command": "train", "description": "Тренировка по предмету"},
    {"command": "results", "description": "Мои результаты"},
    {"command": "login", "description": "Ссылка для входа на сайт"},
]


def run_polling(api: TelegramAPI, max_cycles: int | None = None,
                sleep: Callable[[float], None] = time.sleep) -> None:
    """Получает обновления через getUpdates и обрабатывает их по одному.

    Сетевые ошибки не останавливают бота: пауза растёт до 30 секунд, затем повтор.
    max_cycles и sleep нужны для тестов.
    """
    bot = Bot(api)
    offset: int | None = None
    delay = 1.0
    cycles = 0
    while max_cycles is None or cycles < max_cycles:
        cycles += 1
        params: dict[str, Any] = {"timeout": config.TELEGRAM_POLL_TIMEOUT,
                                  "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            params["offset"] = offset
        try:
            updates = api.call("getUpdates", **params)
        except TelegramError as error:
            if error.code == 401:
                raise  # неверный токен — продолжать бессмысленно
            logger.warning("Telegram вернул ошибку: %s. Повтор через %.0f с.", error, delay)
            sleep(delay)
            delay = min(delay * 2, 30)
            continue
        except (urllib.error.URLError, OSError, ValueError) as error:
            logger.warning("Нет связи с Telegram (%s). Повтор через %.0f с.",
                           type(error).__name__, delay)
            sleep(delay)
            delay = min(delay * 2, 30)
            continue
        delay = 1.0
        for update in updates or []:
            offset = int(update["update_id"]) + 1
            try:
                bot.handle_update(update)
            except Exception:  # одно сломанное обновление не должно ронять бота
                logger.exception("Ошибка при обработке обновления %s", update.get("update_id"))
