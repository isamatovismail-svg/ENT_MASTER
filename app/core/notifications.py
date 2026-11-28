"""Уведомления: колокольчик в меню, страница /notifications и копия в Telegram."""

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app import config
from app import i18n
from app.core import database, schools
from app.i18n import t

logger = logging.getLogger(__name__)

SCHOOL_REQUEST = "school_request"
ASSIGNMENT_DONE = "assignment_done"
REQUEST_APPROVED = "request_approved"
REQUEST_REJECTED = "request_rejected"
ASSIGNMENT_NEW = "assignment_new"
ASSIGNMENT_DUE = "assignment_due"

ICONS = {
    SCHOOL_REQUEST: "🙋", ASSIGNMENT_DONE: "✅", REQUEST_APPROVED: "🏫", REQUEST_REJECTED: "🚫",
    ASSIGNMENT_NEW: "📋", ASSIGNMENT_DUE: "⏰",
}

DUE_SOON_SECONDS = 24 * 60 * 60
DUE_CHECK_INTERVAL_SECONDS = 10 * 60


class Sender(Protocol):
    """То, что отправляет сообщения в Telegram (TelegramAPI или заглушка в тестах)."""

    def call(self, method: str, **params: Any) -> Any:
        """Метод Bot API."""


_sender: Sender | None = None
_due_lock = threading.Lock()
_due_checked_at = 0.0


def set_sender(sender: Sender | None) -> None:
    """Задаёт отправителя Telegram (тесты). None — настоящий Bot API по токену из .env."""
    global _sender
    _sender = sender


@dataclass
class Notification:
    """Уведомление для показа."""

    id: int
    kind: str
    icon: str
    text: str
    link: str
    created_at: float
    read: bool


def _assignment_title(params: dict) -> str:
    return schools.assignment_title(params.get("mode", ""), params.get("target", ""),
                                    int(params.get("count", 0)))


def _deadline(params: dict) -> str:
    return datetime.fromtimestamp(float(params.get("deadline", 0))).strftime("%d.%m.%Y")


def render_text(kind: str, params: dict) -> str:
    """Текст уведомления из его вида и параметров — на языке текущего запроса."""
    student = params.get("student", "")
    school = params.get("school", "")
    if kind == SCHOOL_REQUEST:
        return t("Новая заявка в школу: {student}. Подтвердите или отклоните её.", student=student)
    if kind == ASSIGNMENT_DONE:
        return t("{student} выполнил(а) задание «{title}».", student=student, title=_assignment_title(params))
    if kind == REQUEST_APPROVED:
        return t("Учитель подтвердил вашу заявку: {school}. Теперь вам видны задания.", school=school)
    if kind == REQUEST_REJECTED:
        return t("Заявка в школу отклонена: {school}.", school=school)
    if kind == ASSIGNMENT_NEW:
        return t("Новое задание: {title}. Срок — до {deadline}.", title=_assignment_title(params),
                 deadline=_deadline(params))
    if kind == ASSIGNMENT_DUE:
        return t("До срока задания «{title}» меньше суток (до {deadline}), сделано {done} из {count}.",
                 title=_assignment_title(params), deadline=_deadline(params),
                 done=params.get("done", 0), count=params.get("count", 0))
    return kind


def _from_row(row) -> Notification:
    params = json.loads(row["params_json"] or "{}")
    return Notification(
        id=row["id"], kind=row["kind"], icon=ICONS.get(row["kind"], "🔔"),
        text=render_text(row["kind"], params), link=row["link"], created_at=row["created_at"],
        read=row["read_at"] is not None,
    )


def for_user(user_id: int) -> list[Notification]:
    """Уведомления пользователя, новые сверху."""
    return [_from_row(row) for row in database.list_notifications(user_id)]


def _telegram_send(chat_id: int, text: str) -> None:
    try:
        sender = _sender
        if sender is None:
            if not config.TELEGRAM_BOT_TOKEN:
                return
            from app.telegram_bot import TelegramAPI

            sender = TelegramAPI(config.TELEGRAM_BOT_TOKEN)
        sender.call("sendMessage", chat_id=chat_id, text=text, disable_web_page_preview=True)
    except Exception:
        logger.warning("Не удалось отправить уведомление в Telegram (chat %s)", chat_id, exc_info=True)


def _to_telegram(user_id: int, kind: str, params: dict, link: str) -> None:
    try:
        chat_id = database.get_telegram_id(user_id)
    except Exception:
        logger.exception("Не удалось прочитать Telegram пользователя %s", user_id)
        return
    if not chat_id or (_sender is None and not config.TELEGRAM_BOT_TOKEN):
        return
    with i18n.use(database.get_user_language(user_id)):
        text = f"{ICONS.get(kind, '🔔')} {render_text(kind, params)}"
    if link:
        text += f"\n{config.SITE_URL}{link}"
    if _sender is not None:
        _telegram_send(chat_id, text)
    else:
        threading.Thread(target=_telegram_send, args=(chat_id, text), daemon=True).start()


def notify(user_id: int, kind: str, params: dict, link: str = "", dedup_key: str | None = None,
           now: float | None = None) -> bool:
    """Создаёт уведомление (и копию в Telegram). False — такое уже было (dedup_key)."""
    now = time.time() if now is None else now
    try:
        created = database.add_notification(
            user_id, kind, json.dumps(params, ensure_ascii=False), link, now, dedup_key)
    except Exception:
        logger.exception("Не удалось сохранить уведомление %s для %s", kind, user_id)
        return False
    if created is None:
        return False
    _to_telegram(user_id, kind, params, link)
    return True


def _assignment_params(assignment) -> dict:
    return {"assignment_id": assignment["id"], "mode": assignment["mode"],
            "target": assignment["target"], "count": assignment["count"],
            "deadline": assignment["deadline"]}


def school_request(school_id: int, student_name: str, student_id: int) -> None:
    """Ученик подал заявку в школу — уведомить её учителей."""
    for teacher_id in database.school_teachers(school_id):
        notify(teacher_id, SCHOOL_REQUEST, {"student": student_name, "student_id": student_id},
               f"/teacher/{school_id}")


def request_decided(school_id: int, user_id: int, approved: bool) -> None:
    """Учитель принял или отклонил заявку — уведомить ученика."""
    school = database.get_school(school_id)
    title = schools.school_title(school["city"], school["name"]) if school is not None else ""
    if approved:
        notify(user_id, REQUEST_APPROVED, {"school": title}, "/dashboard")
    else:
        notify(user_id, REQUEST_REJECTED, {"school": title}, "/profile")


def assignment_created(assignment_id: int, school_id: int) -> None:
    """Учитель выдал задание — уведомить каждого, кому оно выдано."""
    assignment = database.get_assignment(assignment_id, school_id)
    if assignment is None:
        return
    params = _assignment_params(assignment)
    for row in database.assignment_students(assignment):
        notify(row["id"], ASSIGNMENT_NEW, params, "/dashboard",
               dedup_key=f"new:{assignment_id}")


def attempt_finished(user_id: int, now: float | None = None) -> None:
    """Ученик завершил попытку: если задание стало выполненным — уведомить учителя."""
    try:
        assignments = database.list_student_assignments(user_id)
        for assignment in assignments:
            progress = schools.student_progress(assignment, user_id, now)
            if progress is None or progress.status != "done":
                continue
            teachers = ([assignment["created_by"]] if assignment["created_by"]
                        else database.school_teachers(assignment["school_id"]))
            params = {**_assignment_params(assignment), "student": progress.name, "student_id": user_id}
            for teacher_id in teachers:
                notify(teacher_id, ASSIGNMENT_DONE, params,
                       f"/teacher/{assignment['school_id']}/assignments/{assignment['id']}",
                       dedup_key=f"done:{assignment['id']}:{user_id}")
    except Exception:
        logger.exception("Не удалось проверить задания ученика %s", user_id)


def check_due(now: float | None = None, user_id: int | None = None) -> int:
    """«До срока меньше суток, а задание не выполнено» — по одному уведомлению на ученика и задание."""
    now = time.time() if now is None else now
    created = 0
    try:
        if user_id is not None:
            assignments = [a for a in database.list_student_assignments(user_id)
                           if now < a["deadline"] <= now + DUE_SOON_SECONDS]
        else:
            assignments = database.active_assignments(now, now + DUE_SOON_SECONDS)
        for assignment in assignments:
            if assignment["deadline"] - assignment["created_at"] <= DUE_SOON_SECONDS:
                continue
            for progress in schools.assignment_progress(assignment, now):
                if user_id is not None and progress.user_id != user_id:
                    continue
                if progress.status != "active":
                    continue
                params = {**_assignment_params(assignment), "done": progress.done}
                if notify(progress.user_id, ASSIGNMENT_DUE, params, "/dashboard",
                          dedup_key=f"due:{assignment['id']}", now=now):
                    created += 1
    except Exception:
        logger.exception("Не удалось проверить сроки заданий")
    return created


def check_due_throttled(now: float | None = None) -> None:
    """Проверка сроков по всем заданиям не чаще раза в DUE_CHECK_INTERVAL_SECONDS (вызывается сайтом)."""
    global _due_checked_at
    now = time.time() if now is None else now
    with _due_lock:
        if _due_checked_at and now - _due_checked_at < DUE_CHECK_INTERVAL_SECONDS:
            return
        _due_checked_at = now
    check_due(now)
