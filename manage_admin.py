"""Назначение администратора.

Запуск:
    python manage_admin.py <логин>            — сделать пользователя администратором
    python manage_admin.py <логин> --revoke   — снять права администратора

Логин — почта или телефон (+7XXXXXXXXXX), как при входе на сайт.
Пользователь должен быть уже зарегистрирован на сайте.
"""

import sys

from app import auth, database


def main(argv: list[str]) -> int:
    """Меняет роль пользователя. Код возврата 0 — успех, 1 — ошибка."""
    args = [arg for arg in argv if arg != "--revoke"]
    revoke = len(args) != len(argv)
    if len(args) != 1:
        print(__doc__.strip())
        return 1

    login = auth.normalize_login(args[0])
    database.init_db()
    role = database.ROLE_USER if revoke else database.ROLE_ADMIN
    if not database.set_user_role(login, role):
        print(f"Пользователь «{login}» не найден. Сначала зарегистрируйтесь на сайте.")
        return 1
    if revoke:
        print(f"Пользователь «{login}» больше не администратор.")
    else:
        print(f"Готово: «{login}» теперь администратор. Админка — http://localhost:8000/admin")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
