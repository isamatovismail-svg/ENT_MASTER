"""Telegram-бот ENT MASTER. Запуск: python bot.py (рядом с сайтом, с той же базой).

Токен бота берётся из файла .env (TELEGRAM_BOT_TOKEN=…) или переменной окружения.
Получить токен: @BotFather в Telegram → /newbot. Пример — в файле .env.example.
"""

import logging
import sys

import config
from app import database
from app.telegram_bot import BOT_COMMANDS, TelegramAPI, TelegramError, bot_commands, run_polling


def main() -> int:
    """Проверяет токен и запускает long polling до нажатия Ctrl+C."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("ent_master.bot")
    if not config.TELEGRAM_BOT_TOKEN:
        print(
            "Нет токена бота. Создайте файл .env рядом с bot.py (образец — .env.example):\n"
            "    TELEGRAM_BOT_TOKEN=123456789:ABC...\n"
            "Токен выдаёт @BotFather в Telegram (команда /newbot)."
        )
        return 1

    database.init_db()
    if not database.question_counts():
        logger.warning("Банк вопросов пуст. Загрузите вопросы командой: python seed.py")

    api = TelegramAPI(config.TELEGRAM_BOT_TOKEN)
    try:
        me = api.call("getMe")
        api.call("setMyCommands", commands=BOT_COMMANDS)
        api.call("setMyCommands", commands=bot_commands("kk"), language_code="kk")
    except TelegramError as error:
        print(f"Telegram не принял токен из .env: {error}")
        return 1
    except OSError as error:
        print(f"Нет связи с Telegram: {error}")
        return 1

    logger.info("Бот @%s запущен. Ссылки входа ведут на %s (остановить: Ctrl+C)",
                me.get("username"), config.SITE_URL)
    try:
        run_polling(api)
    except KeyboardInterrupt:
        logger.info("Бот остановлен.")
    except TelegramError as error:
        print(f"Telegram отклонил запрос: {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
