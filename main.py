"""Точка входа ENT MASTER: создаёт базу (если нужно) и запускает сайт.

Запуск: python main.py  →  откройте http://localhost:8000
"""

import logging
import os

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
    # Под run.py ссылку печатает run.py (одну, в конце запуска), здесь — только при запуске main.py.
    if os.environ.get("ENT_RUN_CHILD") != "1":
        logger.info("ENT MASTER запущен: %s (остановить: Ctrl+C)", config.LOCAL_URL)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Сервер остановлен.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
