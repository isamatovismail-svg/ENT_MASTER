"""Назначение ролей: главный администратор и учитель школы.

Запуск:
    python manage_admin.py <логин>                            — сделать администратором
    python manage_admin.py <логин> --teacher <город> <школа>  — сделать учителем школы
    python manage_admin.py <логин> --revoke                   — снять роль (учитель уходит из школы)

Логин — почта или телефон в любом виде (8 705 …, +7 (705) …), как при входе на сайт.
Школа — номер или название, как вводят ученики: «12», «Школа №12», «НИШ».
Если такой школы ещё нет, она создаётся. Пример:
    python manage_admin.py teacher@mail.kz --teacher Алматы 12
Пользователь должен быть уже зарегистрирован на сайте.
"""

import sys

from app import auth, database, schools


def main(argv: list[str]) -> int:
    """Меняет роль пользователя. Код возврата 0 — успех, 1 — ошибка."""
    args = list(argv)
    if len(args) == 2 and args[1] == "--revoke":
        mode = "revoke"
    elif len(args) == 4 and args[1] == "--teacher":
        mode = "teacher"
    elif len(args) == 1 and not args[0].startswith("--"):
        mode = "admin"
    else:
        print(__doc__.strip())
        return 1

    login = auth.normalize_login(args[0])
    database.init_db()
    if mode == "teacher":
        try:
            school = schools.validate_school(args[2], args[3])
        except schools.SchoolError as error:
            print("\n".join(error.errors))
            return 1
        if school is None:
            print("Укажите город и номер (или название) школы.")
            return 1
        school_id = schools.find_or_create_school(*school)
        found = database.make_teacher(login, school_id)
    elif mode == "revoke":
        found = database.revoke_role(login)
    else:
        found = database.set_user_role(login, database.ROLE_ADMIN)

    if not found:
        print(f"Пользователь «{login}» не найден. Сначала зарегистрируйтесь на сайте.")
        return 1
    if mode == "teacher":
        title = schools.school_title(*school)
        print(f"Готово: «{login}» теперь учитель школы «{title}». "
              "Кабинет учителя — http://localhost:8000/teacher")
    elif mode == "revoke":
        print(f"Пользователь «{login}» больше не администратор и не учитель.")
    else:
        print(f"Готово: «{login}» теперь администратор. Админка — http://localhost:8000/admin")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
