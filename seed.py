"""Загрузка вопросов из data/questions/*.json в базу данных.

Запуск: python seed.py
Каждый вопрос проверяется (тип, число вариантов, правильные ответы, объяснение).
Ошибочные вопросы не загружаются, а список ошибок выводится в конце.
Скрипт можно запускать повторно: вопросы обновляются, дубликаты не появляются.
"""

import json
import sys
from pathlib import Path

import config
from app import database
from app.question_bank import validate_question


def load_file(path: Path) -> tuple[int, list[str]]:
    """Загружает один JSON-файл. Возвращает (сколько загружено, список ошибок)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return 0, [f"{path.name}: не удалось прочитать файл ({error})"]

    subject = data.get("subject")
    if subject not in config.SUBJECTS:
        return 0, [f"{path.name}: неизвестный предмет «{subject}»"]

    loaded = 0
    errors: list[str] = []
    for number, question in enumerate(data.get("questions", []), start=1):
        problems = validate_question(question)
        if problems:
            errors.append(f"{path.name}, вопрос {number}: " + "; ".join(problems))
            continue
        database.upsert_question(
            subject=subject,
            qtype=question["type"],
            text=question["text"].strip(),
            context=question.get("context", "").strip(),
            options=question["options"],
            left=question.get("left", []),
            correct=question["correct"],
            explanation=question["explanation"].strip(),
        )
        loaded += 1
    return loaded, errors


def seed(questions_dir: Path = config.QUESTIONS_DIR) -> tuple[int, list[str]]:
    """Загружает все JSON-файлы из папки. Возвращает (всего загружено, все ошибки)."""
    database.init_db()
    total = 0
    all_errors: list[str] = []
    for path in sorted(questions_dir.glob("*.json")):
        loaded, errors = load_file(path)
        total += loaded
        all_errors.extend(errors)
    return total, all_errors


def main() -> int:
    """Запускает загрузку и печатает отчёт по банку вопросов. Код возврата 1 — были ошибки."""
    total, errors = seed()
    counts = database.question_counts()
    print(f"Загружено вопросов: {total}")
    for code, subject in config.SUBJECTS.items():
        by_type = ", ".join(
            f"{config.QUESTION_TYPE_NAMES[qtype].lower()}: {counts.get((code, qtype), 0)}"
            for qtype in config.QUESTION_TYPES
            if counts.get((code, qtype), 0)
        )
        print(f"  {subject.name}: {by_type or 'нет вопросов'}")
    if errors:
        print("\nОшибки (эти вопросы не загружены):")
        for error in errors:
            print(f"  - {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
