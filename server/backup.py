"""Резервная копия базы данных SQLite."""

import gzip
import shutil
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

from app import config

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


def main(argv: list[str] | None = None) -> int:
    """Делает копию (и по --telegram отправляет её). Код возврата 1 — ошибка (systemd покажет сбой)."""
    argv = sys.argv[1:] if argv is None else argv
    try:
        path = make_backup()
    except (BackupError, sqlite3.Error, OSError) as error:
        print(f"Резервная копия не создана: {error}", file=sys.stderr)
        return 1
    size_kb = path.stat().st_size // 1024
    print(f"Резервная копия: {path} ({size_kb} КБ). Хранится копий: {len(list_backups(path.parent))}.")
    if "--telegram" in argv:
        from server import alerts

        sent = alerts.send_backup(path)
        if not sent:
            print("Копия НЕ отправлена в Telegram: нет токена бота или получателя, либо ошибка сети.",
                  file=sys.stderr)
            return 1
        print(f"Копия отправлена в Telegram получателям: {sent}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
