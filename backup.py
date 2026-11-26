"""Резервная копия базы данных SQLite.

Запуск: python backup.py
    Делает копию ent_master.sqlite3 в папку backups/ (BACKUP_DIR в .env) с датой в имени,
    проверяет её (PRAGMA integrity_check), сжимает gzip и оставляет только последние
    BACKUP_KEEP копий (по умолчанию 14). На сервере запускается раз в сутки таймером systemd
    (deploy/ent-master-backup.timer).

Копия делается встроенным механизмом sqlite3 (Connection.backup): она согласована даже если
сайт и бот в этот момент пишут в базу, в отличие от простого копирования файла.

Восстановление (сайт и бот на это время останавливают):
    gunzip -c backups/ent_master-ГГГГММДД-ЧЧММСС.sqlite3.gz > ent_master.sqlite3
"""

import gzip
import shutil
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

import config

PREFIX = "ent_master-"
SUFFIX = ".sqlite3.gz"


class BackupError(Exception):
    """Копия не получилась или повреждена."""


def make_backup(source: Path = config.DATABASE_PATH, target_dir: Path = config.BACKUP_DIR,
                keep: int = config.BACKUP_KEEP, now: float | None = None) -> Path:
    """Создаёт проверенную сжатую копию базы и удаляет старые. Возвращает путь к копии."""
    if not source.is_file():
        raise BackupError(f"База {source} не найдена")
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    plain = target_dir / f"{PREFIX}{stamp}.sqlite3"
    packed = target_dir / f"{PREFIX}{stamp}{SUFFIX}"

    # closing: соединения закрываются сразу (with sqlite3.connect только фиксирует транзакцию).
    with closing(sqlite3.connect(source, timeout=30)) as src, closing(sqlite3.connect(plain)) as dst:
        src.backup(dst)
    with closing(sqlite3.connect(plain)) as check:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        plain.unlink(missing_ok=True)
        raise BackupError(f"Копия повреждена: {result}")

    with plain.open("rb") as raw, gzip.open(packed, "wb", compresslevel=6) as zipped:
        shutil.copyfileobj(raw, zipped)
    plain.unlink()
    remove_old(target_dir, keep)
    return packed


def list_backups(target_dir: Path = config.BACKUP_DIR) -> list[Path]:
    """Копии в папке, от старой к новой (дата в имени сортируется как строка)."""
    return sorted(target_dir.glob(f"{PREFIX}*{SUFFIX}"))


def remove_old(target_dir: Path, keep: int) -> list[Path]:
    """Оставляет keep последних копий, остальные удаляет. Возвращает удалённые."""
    backups = list_backups(target_dir)
    old = backups[:-keep] if keep > 0 else []
    for path in old:
        path.unlink()
    return old


def main() -> int:
    """Делает копию и печатает результат. Код возврата 1 — ошибка (systemd покажет сбой)."""
    try:
        path = make_backup()
    except (BackupError, sqlite3.Error, OSError) as error:
        print(f"Резервная копия не создана: {error}", file=sys.stderr)
        return 1
    size_kb = path.stat().st_size // 1024
    print(f"Резервная копия: {path} ({size_kb} КБ). Хранится копий: {len(list_backups(path.parent))}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
