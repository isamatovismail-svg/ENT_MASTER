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

from app import config
from app import generators
from app.core import database
from app.core.question_bank import validate_question


def load_file(path: Path, language: str = "ru") -> tuple[int, list[str]]:
    """Загружает один JSON-файл. Возвращает (сколько загружено, список ошибок).

    language — язык обучения, для которого написан файл (data/questions — ru, data/questions/kk — kk).
    """
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
        problems = validate_question(question, subject)
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
            topic=question.get("topic", ""),
            language=config.question_language(subject, language),
        )
        loaded += 1
    return loaded, errors


def load_generated() -> int:
    """Создаёт расчётные задачи генераторами и загружает их. Возвращает их количество."""
    total = 0
    for subject in generators.SUBJECT_TEMPLATES:
        for language in config.LANGUAGES:
            if language != "ru" and generators.templates_for(subject, language) is generators.SUBJECT_TEMPLATES[subject]:
                continue  # у предмета одна версия (свой язык или общий иностранный)
            for qtype in generators.templates_for(subject, language):
                questions = generators.generate(subject, qtype, generators.DEFAULT_COUNTS[qtype], lang=language)
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
    for language, folder in (("ru", questions_dir), ("kk", questions_dir / "kk")):
        for path in sorted(folder.glob("*.json")):
            loaded, errors = load_file(path, language)
            total += loaded
            all_errors.extend(f"{language}/{error}" if language != "ru" else error for error in errors)
    if with_generated:
        total += load_generated()
        if not all_errors:
            retire_stale()
    return total, all_errors


def retire_stale() -> int:
    """Убирает из банка устаревшие вопросы: без темы спецификации, не из админки и не от учителей.

    Все вопросы JSON и генераторов теперь имеют тему, поэтому вопрос без темы — это старый
    сгенерированный вопрос, которого генераторы больше не выдают (например, по произведению
    вне программы НЦТ). Он помечается удалённым: в тесты не попадает, а разбор старых попыток
    сохраняется. Вызывается только после полной загрузки без ошибок.
    """
    retired = database.retire_untagged_questions()
    if retired:
        print(f"Убрано устаревших вопросов без темы: {retired}")
    return retired


def language_table() -> str:
    """Таблица «сколько вопросов на русском и казахском по каждому предмету» (как их видит ученик)."""
    by_language = {lang: database.question_counts(lang) for lang in config.LANGUAGES}
    lines = [f"{'Предмет':<28}{'ru':>8}{'kk':>8}", "-" * 44]
    for code, subject in config.SUBJECTS.items():
        cells = [sum(by_language[lang].get((code, qtype), 0) for qtype in config.QUESTION_TYPES)
                 for lang in config.LANGUAGES]
        note = "  (общие, на английском)" if code in config.SHARED_LANGUAGE_SUBJECTS else (
            f"  (только {config.SUBJECT_OWN_LANGUAGE[code]})" if code in config.SUBJECT_OWN_LANGUAGE else "")
        lines.append(f"{subject.title:<28}{cells[0]:>8}{cells[1]:>8}{note}")
    return "\n".join(lines)


def main() -> int:
    """Запускает загрузку и печатает отчёт по банку вопросов. Код возврата 1 — были ошибки."""
    total, errors = seed(with_generated="--no-generated" not in sys.argv[1:])
    print(f"Загружено вопросов: {total}\n")
    print(language_table())
    if errors:
        print("\nОшибки (эти вопросы не загружены):")
        for error in errors:
            print(f"  - {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
