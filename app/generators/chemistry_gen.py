"""Шаблоны задач по химии. Атомные массы округлены, как в школьных задачах (Cl = 35,5)."""

import random
from dataclasses import dataclass

from app.generators.common import SkipQuestion, matching, multiple, num, number_distractors, single

AR = {"H": 1, "C": 12, "N": 14, "O": 16, "F": 19, "Na": 23, "Mg": 24, "Al": 27, "Si": 28, "P": 31,
      "S": 32, "Cl": 35.5, "K": 39, "Ca": 40, "Fe": 56, "Cu": 64, "Zn": 65, "Br": 80, "Ag": 108,
      "Ba": 137, "Mn": 55}

ELEMENT_NAMES = {"H": "водород", "C": "углерод", "N": "азот", "O": "кислород", "F": "фтор", "Na": "натрий",
                 "Mg": "магний", "Al": "алюминий", "Si": "кремний", "P": "фосфор", "S": "сера", "Cl": "хлор",
                 "K": "калий", "Ca": "кальций", "Fe": "железо", "Cu": "медь", "Zn": "цинк", "Br": "бром",
                 "Ag": "серебро", "Ba": "барий", "Mn": "марганец"}

OXIDE, ACID, BASE, SALT = "оксид", "кислота", "основание", "соль"
CLASSES = (OXIDE, ACID, BASE, SALT)
CLASS_PLURAL = {OXIDE: "оксидами", ACID: "кислотами", BASE: "основаниями", SALT: "солями"}


@dataclass(frozen=True)
class Substance:
    formula: str            # с подстрочными индексами: «H₂SO₄»
    name: str
    atoms: tuple            # состав: (("H", 2), ("S", 1), ("O", 4))
    cls: str | None = None  # класс неорганического вещества (None — не используется в вопросах о классах)

    @property
    def molar_mass(self) -> float:
        return sum(AR[el] * n for el, n in self.atoms)


def S(formula: str, name: str, atoms: str, cls: str | None = None) -> Substance:
    """Короткая запись: атомы строкой «H2 S1 O4»."""
    parsed = []
    for part in atoms.split():
        el = part.rstrip("0123456789")
        parsed.append((el, int(part[len(el):])))
    return Substance(formula, name, tuple(parsed), cls)


SUBSTANCES = [
    # Оксиды (амфотерные тоже оксиды)
    S("CO₂", "оксид углерода(IV)", "C1 O2", OXIDE), S("CaO", "оксид кальция", "Ca1 O1", OXIDE),
    S("Na₂O", "оксид натрия", "Na2 O1", OXIDE), S("Al₂O₃", "оксид алюминия", "Al2 O3", OXIDE),
    S("Fe₂O₃", "оксид железа(III)", "Fe2 O3", OXIDE), S("SO₂", "оксид серы(IV)", "S1 O2", OXIDE),
    S("SO₃", "оксид серы(VI)", "S1 O3", OXIDE), S("P₂O₅", "оксид фосфора(V)", "P2 O5", OXIDE),
    S("MgO", "оксид магния", "Mg1 O1", OXIDE), S("CuO", "оксид меди(II)", "Cu1 O1", OXIDE),
    S("SiO₂", "оксид кремния(IV)", "Si1 O2", OXIDE), S("K₂O", "оксид калия", "K2 O1", OXIDE),
    S("BaO", "оксид бария", "Ba1 O1", OXIDE), S("NO₂", "оксид азота(IV)", "N1 O2", OXIDE),
    # Кислоты
    S("HCl", "соляная кислота", "H1 Cl1", ACID), S("H₂SO₄", "серная кислота", "H2 S1 O4", ACID),
    S("HNO₃", "азотная кислота", "H1 N1 O3", ACID), S("H₃PO₄", "фосфорная кислота", "H3 P1 O4", ACID),
    S("H₂CO₃", "угольная кислота", "H2 C1 O3", ACID), S("H₂S", "сероводородная кислота", "H2 S1", ACID),
    S("HBr", "бромоводородная кислота", "H1 Br1", ACID), S("H₂SO₃", "сернистая кислота", "H2 S1 O3", ACID),
    S("H₂SiO₃", "кремниевая кислота", "H2 Si1 O3", ACID),
    # Основания (без амфотерных гидроксидов)
    S("NaOH", "гидроксид натрия", "Na1 O1 H1", BASE), S("KOH", "гидроксид калия", "K1 O1 H1", BASE),
    S("Ca(OH)₂", "гидроксид кальция", "Ca1 O2 H2", BASE), S("Ba(OH)₂", "гидроксид бария", "Ba1 O2 H2", BASE),
    S("Mg(OH)₂", "гидроксид магния", "Mg1 O2 H2", BASE), S("Fe(OH)₃", "гидроксид железа(III)", "Fe1 O3 H3", BASE),
    S("Cu(OH)₂", "гидроксид меди(II)", "Cu1 O2 H2", BASE), S("Fe(OH)₂", "гидроксид железа(II)", "Fe1 O2 H2", BASE),
    # Соли
    S("NaCl", "хлорид натрия", "Na1 Cl1", SALT), S("KCl", "хлорид калия", "K1 Cl1", SALT),
    S("CaCO₃", "карбонат кальция", "Ca1 C1 O3", SALT), S("Na₂SO₄", "сульфат натрия", "Na2 S1 O4", SALT),
    S("CuSO₄", "сульфат меди(II)", "Cu1 S1 O4", SALT), S("AgNO₃", "нитрат серебра", "Ag1 N1 O3", SALT),
    S("KNO₃", "нитрат калия", "K1 N1 O3", SALT), S("BaSO₄", "сульфат бария", "Ba1 S1 O4", SALT),
    S("Na₂CO₃", "карбонат натрия", "Na2 C1 O3", SALT), S("MgCl₂", "хлорид магния", "Mg1 Cl2", SALT),
    S("FeCl₃", "хлорид железа(III)", "Fe1 Cl3", SALT), S("Ca₃(PO₄)₂", "фосфат кальция", "Ca3 P2 O8", SALT),
    S("K₂SO₄", "сульфат калия", "K2 S1 O4", SALT), S("CaCl₂", "хлорид кальция", "Ca1 Cl2", SALT),
    S("ZnSO₄", "сульфат цинка", "Zn1 S1 O4", SALT), S("NH₄Cl", "хлорид аммония", "N1 H4 Cl1", SALT),
    # Прочие (только для расчётов)
    S("H₂O", "вода", "H2 O1"), S("NH₃", "аммиак", "N1 H3"), S("CH₄", "метан", "C1 H4"),
    S("C₂H₆", "этан", "C2 H6"), S("C₂H₅OH", "этанол", "C2 H6 O1"), S("C₆H₁₂O₆", "глюкоза", "C6 H12 O6"),
    S("O₂", "кислород", "O2"), S("N₂", "азот", "N2"), S("Cl₂", "хлор", "Cl2"), S("H₂", "водород", "H2"),
]

CLASSIFIED = [s for s in SUBSTANCES if s.cls]
# Растворимые соли — только из них готовим растворы (CaCO₃, BaSO₄, Ca₃(PO₄)₂ в воде не растворяются).
SOLUBLE_SALTS = [s for s in CLASSIFIED if s.formula in (
    "NaCl", "KCl", "Na₂SO₄", "CuSO₄", "AgNO₃", "KNO₃", "Na₂CO₃", "MgCl₂", "K₂SO₄", "CaCl₂", "ZnSO₄", "NH₄Cl")]
GASES = [s for s in SUBSTANCES if s.formula in ("CO₂", "SO₂", "NO₂", "NH₃", "CH₄", "C₂H₆", "O₂", "N₂", "Cl₂",
                                                "H₂", "H₂S")]


def _mass_sum(sub: Substance) -> str:
    """Запись расчёта молярной массы: 2·1 + 32 + 4·16."""
    parts = [(f"{n}·{num(AR[el], 1)}" if n > 1 else num(AR[el], 1)) for el, n in sub.atoms]
    return " + ".join(parts)


def _mass_wrong(sub: Substance) -> list[float]:
    """Типичные ошибки: забыли индексы, сложили номера вместо масс и т.п."""
    no_index = sum(AR[el] for el, _ in sub.atoms)
    return [no_index, sub.molar_mass + 16, sub.molar_mass - 1, sub.molar_mass * 2]


# ── Один ответ ───────────────────────────────────────────────────────────────

def molar_mass(rng):
    sub = rng.choice(SUBSTANCES)
    m = sub.molar_mass
    expl = f"M({sub.formula}) = {_mass_sum(sub)} = {num(m, 1)} г/моль. Атомные массы берём из таблицы Менделеева."
    return single(rng, f"Вычислите молярную массу вещества {sub.formula}.", f"{num(m, 1)} г/моль",
                  number_distractors(rng, m, _mass_wrong(sub), " г/моль", digits=1), expl)


def mass_fraction(rng):
    sub = rng.choice([s for s in SUBSTANCES if len(s.atoms) > 1])
    el, n = rng.choice(sub.atoms)
    m = sub.molar_mass
    w = n * AR[el] / m * 100
    expl = (f"M({sub.formula}) = {_mass_sum(sub)} = {num(m, 1)} г/моль. "
            f"ω({el}) = {n}·{num(AR[el], 1)} / {num(m, 1)}·100% ≈ {num(w, 1)}%.")
    wrong = [AR[el] / m * 100 if n > 1 else w + 10, 100 - w, n / sum(k for _, k in sub.atoms) * 100, w / 2]
    return single(rng, f"Найдите массовую долю элемента {el} ({ELEMENT_NAMES[el]}) в веществе {sub.formula}.",
                  f"{num(w, 1)}%", number_distractors(rng, round(w, 1), [round(x, 1) for x in wrong], "%", digits=1),
                  expl)


def amount_from_mass(rng):
    sub = rng.choice(SUBSTANCES)
    n = rng.choice([0.1, 0.2, 0.25, 0.5, 1, 1.5, 2, 2.5, 3, 4, 5])
    mass = round(sub.molar_mass * n, 2)
    expl = f"n = m / M. M({sub.formula}) = {num(sub.molar_mass, 1)} г/моль, n = {num(mass)} / {num(sub.molar_mass, 1)} = {num(n)} моль."
    return single(rng, f"Какое количество вещества содержится в {num(mass)} г {sub.formula}?", f"{num(n)} моль",
                  number_distractors(rng, n, [n * 2, n / 2, mass * sub.molar_mass / 100, n + 1], " моль"), expl)


def mass_from_amount(rng):
    sub = rng.choice(SUBSTANCES)
    n = rng.choice([0.1, 0.2, 0.5, 1, 1.5, 2, 3, 4, 5])
    mass = sub.molar_mass * n
    expl = f"m = n·M = {num(n)}·{num(sub.molar_mass, 1)} = {num(mass)} г."
    return single(rng, f"Найдите массу {num(n)} моль вещества {sub.formula}.", f"{num(mass)} г",
                  number_distractors(rng, mass, [sub.molar_mass / n, sub.molar_mass, mass * 2, mass + n], " г"), expl)


def gas_volume(rng):
    sub = rng.choice(GASES)
    n = rng.choice([0.1, 0.2, 0.25, 0.5, 1, 1.5, 2, 3, 5])
    v = 22.4 * n
    if rng.random() < 0.5:
        expl = f"При н.у. 1 моль любого газа занимает 22,4 л. V = n·Vm = {num(n)}·22,4 = {num(v)} л."
        return single(rng, f"Какой объём при н.у. занимают {num(n)} моль газа {sub.formula}?", f"{num(v)} л",
                      number_distractors(rng, v, [22.4 / n, n * sub.molar_mass, v * 2, 22.4], " л"), expl)
    mass = sub.molar_mass * n
    expl = (f"Сначала количество вещества: n = m / M = {num(mass)} / {num(sub.molar_mass, 1)} = {num(n)} моль. "
            f"Объём при н.у.: V = {num(n)}·22,4 = {num(v)} л.")
    return single(rng, f"Какой объём при н.у. займут {num(mass)} г газа {sub.formula}?", f"{num(v)} л",
                  number_distractors(rng, v, [mass * 22.4, 22.4, v * 2, mass], " л"), expl)


def _avogadro(value: float) -> str:
    """Число частиц в виде a·10ⁿ (1 ≤ a < 10)."""
    power = 23
    while value >= 10:
        value /= 10
        power += 1
    while value < 1:
        value *= 10
        power -= 1
    return f"{num(round(value, 3), 3)}·10{str(power).translate(str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹'))}"


def molecules(rng):
    sub = rng.choice(SUBSTANCES)
    n = rng.choice([0.1, 0.2, 0.5, 1, 1.5, 2, 3, 5])
    answer = _avogadro(6.02 * n)
    wrong = [_avogadro(6.02 * n * 10), _avogadro(6.02 / n), _avogadro(6.02 * n / 10), _avogadro(6.02 * (n + 1)),
             _avogadro(6.02 * n * 2)]
    expl = f"N = n·Nₐ = {num(n)}·6,02·10²³ = {answer} молекул. Постоянная Авогадро Nₐ = 6,02·10²³ моль⁻¹."
    return single(rng, f"Сколько молекул содержится в {num(n)} моль вещества {sub.formula}?", answer, wrong, expl)


def solution_fraction(rng):
    salt = rng.choice(SOLUBLE_SALTS)
    m_salt = rng.choice([5, 10, 15, 20, 25, 30, 40, 50, 60, 80])
    m_water = rng.choice([45, 70, 80, 90, 120, 150, 170, 190, 200, 240])
    total = m_salt + m_water
    w = m_salt / total * 100
    if round(w, 1) != round(w, 4):
        raise SkipQuestion
    expl = (f"Масса раствора = масса соли + масса воды = {m_salt} + {m_water} = {total} г. "
            f"ω = {m_salt} / {total}·100% = {num(w, 1)}%. Делить нужно на массу раствора, а не воды.")
    return single(rng, f"В {m_water} г воды растворили {m_salt} г {salt.formula}. Найдите массовую долю соли в растворе.",
                  f"{num(w, 1)}%",
                  number_distractors(rng, w, [m_salt / m_water * 100, m_salt, 100 - w, w * 2], "%", digits=1),
                  expl)


def substance_class(rng):
    sub = rng.choice(CLASSIFIED)
    reasons = {OXIDE: "оксид — соединение двух элементов, один из которых кислород (степень окисления −2)",
               ACID: "кислота состоит из атомов водорода и кислотного остатка",
               BASE: "основание состоит из атома металла и гидроксогрупп OH",
               SALT: "соль состоит из атомов металла (или NH₄) и кислотного остатка"}
    expl = f"{sub.formula} — {sub.name}: {reasons[sub.cls]}."
    return single(rng, f"К какому классу неорганических веществ относится {sub.formula}?", sub.cls,
                  [c for c in CLASSES if c != sub.cls], expl)


def formula_by_name(rng):
    sub = rng.choice(CLASSIFIED)
    same = [s for s in CLASSIFIED if s is not sub and (s.cls == sub.cls or s.atoms[0][0] == sub.atoms[0][0])]
    if len(same) < 3:
        raise SkipQuestion
    wrong = [s.formula for s in rng.sample(same, min(6, len(same)))]
    return single(rng, f"Какая формула соответствует веществу «{sub.name}»?", sub.formula, wrong,
                  f"«{sub.name}» — это {sub.formula} ({sub.cls}).")


def element_symbol(rng):
    el = rng.choice(list(ELEMENT_NAMES))
    wrong = rng.sample([e for e in ELEMENT_NAMES if e != el], 6)
    return single(rng, f"Какой символ имеет химический элемент {ELEMENT_NAMES[el]}?", el, wrong,
                  f"Элемент {ELEMENT_NAMES[el]} обозначается символом {el}.")


# ── По контексту ─────────────────────────────────────────────────────────────

def solution_context(rng):
    total = rng.choice([100, 150, 200, 250, 300, 400, 500])
    w = rng.choice([5, 10, 12, 15, 20, 25])
    m_salt = total * w / 100
    m_water = total - m_salt
    salt = rng.choice(SOLUBLE_SALTS)
    context = f"Для опыта нужно приготовить {total} г раствора соли {salt.formula} с массовой долей соли {w}%."
    if rng.random() < 0.5:
        text = f"Сколько граммов соли нужно взять для {total} г {w}%-го раствора {salt.formula}?"
        expl = f"m(соли) = m(раствора)·ω = {total}·{num(w / 100)} = {num(m_salt)} г."
        return single(rng, text, f"{num(m_salt)} г",
                      number_distractors(rng, m_salt, [m_water, w, total / w, m_salt * 2], " г"), expl, context=context)
    text = f"Сколько граммов воды нужно для {total} г {w}%-го раствора {salt.formula}?"
    expl = f"Соли нужно {total}·{num(w / 100)} = {num(m_salt)} г, воды — {total} − {num(m_salt)} = {num(m_water)} г."
    return single(rng, text, f"{num(m_water)} г",
                  number_distractors(rng, m_water, [m_salt, total, total - w, m_water + m_salt / 2], " г"), expl,
                  context=context)


def reaction_context(rng):
    metal, oxide_formula, k_metal, k_oxide = rng.choice([
        ("Mg", "MgO", 2, 2), ("Ca", "CaO", 2, 2), ("Zn", "ZnO", 2, 2), ("Cu", "CuO", 2, 2),
    ])
    n = rng.choice([0.1, 0.2, 0.5, 1, 1.5, 2])
    m_metal = AR[metal] * n
    m_oxide = (AR[metal] + 16) * n
    context = f"Металл {ELEMENT_NAMES[metal]} сгорает в кислороде по уравнению 2{metal} + O₂ = 2{oxide_formula}."
    text = f"Какая масса {oxide_formula} образуется при сгорании {num(m_metal)} г {metal}?"
    expl = (f"n({metal}) = {num(m_metal)} / {AR[metal]} = {num(n)} моль. По уравнению n({oxide_formula}) = n({metal}) = "
            f"{num(n)} моль. m({oxide_formula}) = {num(n)}·{AR[metal] + 16} = {num(m_oxide)} г.")
    wrong = [m_metal, m_oxide / 2, m_oxide * 2, m_metal + 32 * n]
    return single(rng, text, f"{num(m_oxide)} г", number_distractors(rng, m_oxide, wrong, " г"), expl, context=context)


# ── Соответствие ─────────────────────────────────────────────────────────────

def class_matching(rng):
    classes = rng.sample(CLASSES, 2)
    a = rng.choice([s for s in CLASSIFIED if s.cls == classes[0]])
    b = rng.choice([s for s in CLASSIFIED if s.cls == classes[1]])
    text = f"Установите соответствие между формулой вещества и классом: 1) {a.formula}; 2) {b.formula}."
    extra = [c for c in CLASSES if c not in classes]
    expl = f"{a.formula} ({a.name}) — {a.cls}. {b.formula} ({b.name}) — {b.cls}."
    return matching(rng, text, [(a.formula, a.cls), (b.formula, b.cls)], extra, expl)


def mass_matching(rng):
    picked = rng.sample(SUBSTANCES, 4)
    masses = [num(s.molar_mass, 1) + " г/моль" for s in picked]
    if len(set(masses)) < 4:
        raise SkipQuestion
    a, b = picked[:2]
    text = f"Установите соответствие между веществом и его молярной массой: 1) {a.formula}; 2) {b.formula}."
    expl = f"M({a.formula}) = {_mass_sum(a)} = {masses[0]}. M({b.formula}) = {_mass_sum(b)} = {masses[1]}."
    return matching(rng, text, [(a.formula, masses[0]), (b.formula, masses[1])], masses[2:], expl)


def name_matching(rng):
    picked = rng.sample(CLASSIFIED, 4)
    a, b = picked[:2]
    text = f"Установите соответствие между формулой и названием вещества: 1) {a.formula}; 2) {b.formula}."
    expl = f"{a.formula} — {a.name}, {b.formula} — {b.name}."
    return matching(rng, text, [(a.formula, a.name), (b.formula, b.name)], [p.name for p in picked[2:]], expl)


# ── Несколько ответов ────────────────────────────────────────────────────────

def class_multiple(rng):
    cls = rng.choice(CLASSES)
    right = rng.sample([s for s in CLASSIFIED if s.cls == cls], rng.randint(1, 3))
    wrong = rng.sample([s for s in CLASSIFIED if s.cls != cls], 6 - len(right))
    names = sorted(s.formula for s in right + wrong)
    text = f"Какие из веществ являются {CLASS_PLURAL[cls]}: {', '.join(names)}?"
    expl = ("К этому классу относятся: " + ", ".join(f"{s.formula} ({s.name})" for s in right) + ". "
            + "Остальные: " + ", ".join(f"{s.formula} — {s.cls}" for s in wrong) + ".")
    return multiple(rng, text, [s.formula for s in right], [s.formula for s in wrong], expl)


def heavy_multiple(rng):
    limit = rng.choice([40, 50, 60, 80, 100])
    picked = rng.sample(SUBSTANCES, 6)
    right = [s for s in picked if s.molar_mass > limit]
    if not 1 <= len(right) <= 3:
        raise SkipQuestion
    wrong = [s for s in picked if s.molar_mass <= limit]
    text = (f"У каких веществ молярная масса больше {limit} г/моль: "
            f"{', '.join(s.formula for s in picked)}?")
    expl = "Считаем молярные массы: " + "; ".join(f"M({s.formula}) = {num(s.molar_mass, 1)}" for s in picked) + "."
    return multiple(rng, text, [s.formula for s in right], [s.formula for s in wrong], expl)


TEMPLATES = {
    "single": [molar_mass, mass_fraction, amount_from_mass, mass_from_amount, gas_volume, molecules,
               solution_fraction, substance_class, formula_by_name, element_symbol],
    "context": [solution_context, reaction_context],
    "matching": [class_matching, mass_matching, name_matching],
    "multiple": [class_multiple, heavy_multiple],
}
