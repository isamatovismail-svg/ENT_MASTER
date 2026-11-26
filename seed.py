"""Загрузка вопросов из data/questions/*.json в базу данных.

Запуск: python seed.py            — вопросы из JSON + сгенерированные расчётные задачи
        python seed.py --no-generated — только вопросы из JSON
Каждый вопрос проверяется (тип, число вариантов, правильные ответы, объяснение).
Ошибочные вопросы не загружаются, а список ошибок выводится в конце.
Скрипт можно запускать повторно: вопросы обновляются, дубликаты не появляются
(генератор при каждом запуске выдаёт одни и те же задачи).
"""

import json
import sys
from pathlib import Path

import config
from app import database, generators
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


def load_generated() -> int:
    """Создаёт расчётные задачи генераторами и загружает их. Возвращает их количество."""
    total = 0
    for subject, templates in generators.SUBJECT_TEMPLATES.items():
        for qtype in templates:
            questions = generators.generate(subject, qtype, generators.DEFAULT_COUNTS[qtype])
            database.upsert_questions(subject, questions)
            total += len(questions)
    return total


def seed(questions_dir: Path = config.QUESTIONS_DIR,
         with_generated: bool = True) -> tuple[int, list[str]]:
    """Загружает все JSON-файлы из папки и (по умолчанию) сгенерированные задачи.

    Возвращает (всего загружено, все ошибки).
    """
    database.init_db()
    total = 0
    all_errors: list[str] = []
    for path in sorted(questions_dir.glob("*.json")):
        loaded, errors = load_file(path)
        total += loaded
        all_errors.extend(errors)
    if with_generated:
        total += load_generated()
    return total, all_errors


def main() -> int:
    """Запускает загрузку и печатает отчёт по банку вопросов. Код возврата 1 — были ошибки."""
    total, errors = seed(with_generated="--no-generated" not in sys.argv[1:])
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
