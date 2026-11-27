"""Казахские версии шаблонов: предмет → {тип задания: [функции]}.

Расчётные предметы — app/generators/kk_computed.py, предметы «на знание фактов» —
app/generators/kk_facts.py (таблицы на казахском, вопросы собирает app/generators/facts.py).
"""

from app.generators import kk_computed, kk_facts

TEMPLATES: dict[str, dict[str, list]] = {
    "math": kk_computed.MATH,
    "physics": kk_computed.PHYSICS,
    "chemistry": kk_computed.CHEMISTRY,
    "informatics": kk_computed.INFORMATICS,
    "math_literacy": kk_computed.MATH_LITERACY,
    **kk_facts.TEMPLATES,
}
