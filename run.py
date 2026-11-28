"""Запуск ENT MASTER: сайт и Telegram-бот одной командой.

    python run.py           — сайт и бот, сайт на http://localhost:8000
    python run.py --share   — то же + временная публичная ссылка https://….trycloudflare.com
    python run.py site      — только сайт (так его запускает systemd на сервере)
    python run.py bot       — только Telegram-бот
"""

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    """Разбирает аргументы и запускает выбранную часть проекта."""
    parser = argparse.ArgumentParser(description="Запуск сайта ENT MASTER и Telegram-бота.")
    parser.add_argument("part", nargs="?", choices=("site", "bot"), help="запустить только сайт или только бота")
    parser.add_argument("--share", action="store_true",
                        help="показать сайт через интернет (Cloudflare Quick Tunnel, временная ссылка)")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.part == "site":
        from app.web.server import serve
        return serve()
    if args.part == "bot":
        from app.telegram_bot import serve
        return serve()
    from server.launcher import run_all
    return run_all(share=args.share)


if __name__ == "__main__":
    sys.exit(main())
