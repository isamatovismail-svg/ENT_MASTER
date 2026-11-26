"""Точка входа ENT MASTER: создаёт базу (если нужно) и запускает сайт.

Запуск: python main.py  →  откройте http://localhost:8000
"""

import logging

import config
from app import database
from app.server import create_server


def main() -> None:
    """Готовит базу данных и запускает HTTP-сервер до нажатия Ctrl+C."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("ent_master")

    database.init_db()
    if not database.question_counts():
        logger.warning("Банк вопросов пуст. Загрузите вопросы командой: python seed.py")

    server = create_server(config.HOST, config.PORT)
    logger.info("ENT MASTER запущен: http://%s:%s (остановить: Ctrl+C)", config.HOST, config.PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Сервер остановлен.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
