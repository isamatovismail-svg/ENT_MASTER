"""Сбор всех строк интерфейса, которым нужен перевод (для проверки словаря в tests/test_i18n.py)."""

import ast
import re
from pathlib import Path

from app import config
from app import i18n

UI_MODULES = (
    "app/config.py", "app/web/account_views.py", "app/web/admin_views.py", "app/core/ads.py",
    "app/core/auth.py", "app/core/ent_logic.py", "app/core/google_auth.py", "app/core/notifications.py",
    "app/core/question_bank.py", "app/web/question_form.py", "app/core/schools.py",
    "app/core/student_stats.py", "app/web/teacher_views.py", "app/telegram_bot.py",
    "app/web/telegram_views.py", "app/web/views.py",
)
KAZAKH_SUBJECTS = ("kazakh_language", "kazakh_literature")
IGNORED = {
    "школа", "сош", "средняя", "общеобразовательная", "мектеп", "мектебі", "мектебi", "жом",
    "г", "город", "қ", "қаласы", "Тіл / Язык",
    "Русский", "Қазақ тілі", "РУС", "ҚАЗ", "е", "ё",
    r"(?:школа|сош|мектеп)?\s*№?\s*(\d+)",
    "Google не вернул id_token", "Google не сообщил почту", "Google ответил ошибкой {code}",
    "id_token выдан другому приложению", "id_token выдан не Google", "Нет кода авторизации",
    "Повреждённый id_token", "Почта в Google не подтверждена", "Срок действия id_token истёк",
    "Не удалось связаться с Google: {error}",
}
_CYR = re.compile("[А-Яа-яЁё]")


def _docstrings(tree: ast.AST) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                found.add(id(first.value))
    return found


def _is_log_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    base = func.value.id if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) else ""
    return base in ("logger", "logging") or name in ("print",) or (
        isinstance(func, ast.Name) and func.id in ("GoogleAuthError",) and False)


def python_keys(path: Path) -> set[str]:
    """Русские строки модуля: обычный текст — ключом целиком, HTML — по текстовым узлам."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = _docstrings(tree)
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str) and _CYR.search(node.value)):
            continue
        if id(node) in docs or isinstance(parents.get(id(node)), ast.JoinedStr):
            continue
        chain, current = [], parents.get(id(node))
        while current is not None and len(chain) < 4:
            chain.append(current)
            current = parents.get(id(current))
        if any(_is_log_call(item) for item in chain):
            continue
        text = node.value
        if "<" in text and ">" in text:
            keys.update(i18n.markup_segments(text))
        else:
            keys.add(" ".join(text.split()))
    return keys


def template_keys() -> set[str]:
    keys: set[str] = set()
    for path in sorted(config.TEMPLATES_DIR.glob("*.html")):
        keys.update(i18n.markup_segments(path.read_text(encoding="utf-8")))
    return keys


def topic_keys() -> set[str]:
    """Разделы и темы спецификаций НЦТ (кроме казахских предметов)."""
    from app.core import topics

    keys: set[str] = {"Без темы"}
    for subject, items in topics.TOPICS.items():
        if subject in KAZAKH_SUBJECTS:
            continue
        for item in items:
            keys.update((" ".join(item.section_ru.split()), " ".join(item.name_ru.split())))
    return keys


def all_keys() -> set[str]:
    """Все строки интерфейса, которым нужен казахский перевод."""
    keys = template_keys() | topic_keys()
    for name in UI_MODULES:
        keys.update(python_keys(config.BASE_DIR / name))
    return {key for key in keys if key and key not in IGNORED and _CYR.search(key)}


def missing() -> list[str]:
    """Строки без перевода в словаре KK_DICT."""
    return sorted(key for key in all_keys() if key not in i18n.KK_DICT)
