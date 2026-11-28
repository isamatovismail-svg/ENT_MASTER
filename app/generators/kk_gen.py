"""Казахские версии шаблонов: предмет → {тип задания: [функции]}."""

from app.generators import kk_computed, kk_facts

TEMPLATES: dict[str, dict[str, list]] = {
    "math": kk_computed.MATH,
    "physics": kk_computed.PHYSICS,
    "chemistry": kk_computed.CHEMISTRY,
    "informatics": kk_computed.INFORMATICS,
    "math_literacy": kk_computed.MATH_LITERACY,
    **kk_facts.TEMPLATES,
}
