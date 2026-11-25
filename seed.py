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

MIN_OPTIONS = 2


def validate_question(question: dict) -> list[str]:
    """Проверяет один вопрос из JSON. Возвращает список ошибок (пустой — всё в порядке)."""
    errors: list[str] = []
    qtype = question.get("type")
    text = question.get("text")
    options = question.get("options")
    correct = question.get("correct")

    explanation = question.get("explanation")

    if qtype not in config.QUESTION_TYPES:
        return [f"неизвестный тип «{qtype}»"]
    if not isinstance(text, str) or not text.strip():
        errors.append("пустой текст вопроса")
    if not isinstance(explanation, str) or not explanation.strip():
        errors.append("нет объяснения explanation (почему ответ правильный)")
    if not isinstance(options, list) or not all(isinstance(o, str) and o.strip() for o in options):
        return errors + ["options должен быть списком непустых строк"]
    if not MIN_OPTIONS <= len(options) <= len(config.OPTION_LETTERS):
        errors.append(f"вариантов должно быть от {MIN_OPTIONS} до {len(config.OPTION_LETTERS)}")
    if len(set(options)) != len(options):
        errors.append("варианты ответов повторяются")
    if not isinstance(correct, list) or not correct:
        return errors + ["correct должен быть непустым списком букв"]

    letters = config.OPTION_LETTERS[: len(options)]
    if any(letter not in letters for letter in correct):
        errors.append(f"в correct есть буква вне диапазона {letters[0]}–{letters[-1]}")

    if qtype in (config.SINGLE, config.CONTEXT) and len(correct) != 1:
        errors.append("у задания с одним ответом должна быть ровно одна правильная буква")
    if qtype == config.CONTEXT and not str(question.get("context", "")).strip():
        errors.append("у задания по контексту нет текста context")
    if qtype == config.MULTIPLE and len(set(correct)) != len(correct):
        errors.append("в correct повторяются буквы")
    if qtype == config.MATCHING:
        left = question.get("left")
        if not isinstance(left, list) or len(left) < 2:
            errors.append("у соответствия должен быть список left минимум из 2 строк")
        elif len(left) != len(correct):
            errors.append("длина correct должна совпадать с числом строк left")
    return errors


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
