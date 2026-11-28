"""Шаблоны задач по химии. Атомные массы округлены, как в школьных задачах (Cl = 35,5)."""

from dataclasses import dataclass

from app.generators.common import (
    SkipQuestion, matching, multiple, num, number_distractors, quiz, single, topic,
)

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
    formula: str
    name: str
    atoms: tuple
    cls: str | None = None

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
    S("CO₂", "оксид углерода(IV)", "C1 O2", OXIDE), S("CaO", "оксид кальция", "Ca1 O1", OXIDE),
    S("Na₂O", "оксид натрия", "Na2 O1", OXIDE), S("Al₂O₃", "оксид алюминия", "Al2 O3", OXIDE),
    S("Fe₂O₃", "оксид железа(III)", "Fe2 O3", OXIDE), S("SO₂", "оксид серы(IV)", "S1 O2", OXIDE),
    S("SO₃", "оксид серы(VI)", "S1 O3", OXIDE), S("P₂O₅", "оксид фосфора(V)", "P2 O5", OXIDE),
    S("MgO", "оксид магния", "Mg1 O1", OXIDE), S("CuO", "оксид меди(II)", "Cu1 O1", OXIDE),
    S("SiO₂", "оксид кремния(IV)", "Si1 O2", OXIDE), S("K₂O", "оксид калия", "K2 O1", OXIDE),
    S("BaO", "оксид бария", "Ba1 O1", OXIDE), S("NO₂", "оксид азота(IV)", "N1 O2", OXIDE),
    S("HCl", "соляная кислота", "H1 Cl1", ACID), S("H₂SO₄", "серная кислота", "H2 S1 O4", ACID),
    S("HNO₃", "азотная кислота", "H1 N1 O3", ACID), S("H₃PO₄", "фосфорная кислота", "H3 P1 O4", ACID),
    S("H₂CO₃", "угольная кислота", "H2 C1 O3", ACID), S("H₂S", "сероводородная кислота", "H2 S1", ACID),
    S("HBr", "бромоводородная кислота", "H1 Br1", ACID), S("H₂SO₃", "сернистая кислота", "H2 S1 O3", ACID),
    S("H₂SiO₃", "кремниевая кислота", "H2 Si1 O3", ACID),
    S("NaOH", "гидроксид натрия", "Na1 O1 H1", BASE), S("KOH", "гидроксид калия", "K1 O1 H1", BASE),
    S("Ca(OH)₂", "гидроксид кальция", "Ca1 O2 H2", BASE), S("Ba(OH)₂", "гидроксид бария", "Ba1 O2 H2", BASE),
    S("Mg(OH)₂", "гидроксид магния", "Mg1 O2 H2", BASE), S("Fe(OH)₃", "гидроксид железа(III)", "Fe1 O3 H3", BASE),
    S("Cu(OH)₂", "гидроксид меди(II)", "Cu1 O2 H2", BASE), S("Fe(OH)₂", "гидроксид железа(II)", "Fe1 O2 H2", BASE),
    S("NaCl", "хлорид натрия", "Na1 Cl1", SALT), S("KCl", "хлорид калия", "K1 Cl1", SALT),
    S("CaCO₃", "карбонат кальция", "Ca1 C1 O3", SALT), S("Na₂SO₄", "сульфат натрия", "Na2 S1 O4", SALT),
    S("CuSO₄", "сульфат меди(II)", "Cu1 S1 O4", SALT), S("AgNO₃", "нитрат серебра", "Ag1 N1 O3", SALT),
    S("KNO₃", "нитрат калия", "K1 N1 O3", SALT), S("BaSO₄", "сульфат бария", "Ba1 S1 O4", SALT),
    S("Na₂CO₃", "карбонат натрия", "Na2 C1 O3", SALT), S("MgCl₂", "хлорид магния", "Mg1 Cl2", SALT),
    S("FeCl₃", "хлорид железа(III)", "Fe1 Cl3", SALT), S("Ca₃(PO₄)₂", "фосфат кальция", "Ca3 P2 O8", SALT),
    S("K₂SO₄", "сульфат калия", "K2 S1 O4", SALT), S("CaCl₂", "хлорид кальция", "Ca1 Cl2", SALT),
    S("ZnSO₄", "сульфат цинка", "Zn1 S1 O4", SALT), S("NH₄Cl", "хлорид аммония", "N1 H4 Cl1", SALT),
    S("H₂O", "вода", "H2 O1"), S("NH₃", "аммиак", "N1 H3"), S("CH₄", "метан", "C1 H4"),
    S("C₂H₆", "этан", "C2 H6"), S("C₂H₅OH", "этанол", "C2 H6 O1"), S("C₆H₁₂O₆", "глюкоза", "C6 H12 O6"),
    S("O₂", "кислород", "O2"), S("N₂", "азот", "N2"), S("Cl₂", "хлор", "Cl2"), S("H₂", "водород", "H2"),
]

CLASSIFIED = [s for s in SUBSTANCES if s.cls]
SOLUBLE_SALTS = [s for s in CLASSIFIED if s.formula in (
    "NaCl", "KCl", "Na₂SO₄", "CuSO₄", "AgNO₃", "KNO₃", "Na₂CO₃", "MgCl₂", "K₂SO₄", "CaCl₂", "ZnSO₄", "NH₄Cl")]
GASES = [s for s in SUBSTANCES if s.formula in ("CO₂", "SO₂", "NO₂", "NH₃", "CH₄", "C₂H₆", "O₂", "N₂", "Cl₂",
                                                "H₂", "H₂S")]


def _mass_sum(sub: Substance) -> str:
    parts = [(f"{n}·{num(AR[el], 1)}" if n > 1 else num(AR[el], 1)) for el, n in sub.atoms]
    return " + ".join(parts)


def _mass_wrong(sub: Substance) -> list[float]:
    no_index = sum(AR[el] for el, _ in sub.atoms)
    return [no_index, sub.molar_mass + 16, sub.molar_mass - 1, sub.molar_mass * 2]


@topic("18")
def molar_mass(rng):
    sub = rng.choice(SUBSTANCES)
    m = sub.molar_mass
    expl = f"M({sub.formula}) = {_mass_sum(sub)} = {num(m, 1)} г/моль. Атомные массы берём из таблицы Менделеева."
    return single(rng, f"Вычислите молярную массу вещества {sub.formula}.", f"{num(m, 1)} г/моль",
                  number_distractors(rng, m, _mass_wrong(sub), " г/моль", digits=1), expl)


@topic("18")
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


@topic("18")
def amount_from_mass(rng):
    sub = rng.choice(SUBSTANCES)
    n = rng.choice([0.1, 0.2, 0.25, 0.5, 1, 1.5, 2, 2.5, 3, 4, 5])
    mass = round(sub.molar_mass * n, 2)
    expl = f"n = m / M. M({sub.formula}) = {num(sub.molar_mass, 1)} г/моль, n = {num(mass)} / {num(sub.molar_mass, 1)} = {num(n)} моль."
    return single(rng, f"Какое количество вещества содержится в {num(mass)} г {sub.formula}?", f"{num(n)} моль",
                  number_distractors(rng, n, [n * 2, n / 2, mass * sub.molar_mass / 100, n + 1], " моль"), expl)


@topic("18")
def mass_from_amount(rng):
    sub = rng.choice(SUBSTANCES)
    n = rng.choice([0.1, 0.2, 0.5, 1, 1.5, 2, 3, 4, 5])
    mass = sub.molar_mass * n
    expl = f"m = n·M = {num(n)}·{num(sub.molar_mass, 1)} = {num(mass)} г."
    return single(rng, f"Найдите массу {num(n)} моль вещества {sub.formula}.", f"{num(mass)} г",
                  number_distractors(rng, mass, [sub.molar_mass / n, sub.molar_mass, mass * 2, mass + n], " г"), expl)


@topic("18")
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
    power = 23
    while value >= 10:
        value /= 10
        power += 1
    while value < 1:
        value *= 10
        power -= 1
    return f"{num(round(value, 3), 3)}·10{str(power).translate(str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹'))}"


@topic("18")
def molecules(rng):
    sub = rng.choice(SUBSTANCES)
    n = rng.choice([0.1, 0.2, 0.5, 1, 1.5, 2, 3, 5])
    answer = _avogadro(6.02 * n)
    wrong = [_avogadro(6.02 * n * 10), _avogadro(6.02 / n), _avogadro(6.02 * n / 10), _avogadro(6.02 * (n + 1)),
             _avogadro(6.02 * n * 2)]
    expl = f"N = n·Nₐ = {num(n)}·6,02·10²³ = {answer} молекул. Постоянная Авогадро Nₐ = 6,02·10²³ моль⁻¹."
    return single(rng, f"Сколько молекул содержится в {num(n)} моль вещества {sub.formula}?", answer, wrong, expl)


@topic("18")
def solution_fraction(rng):
    salt = rng.choice(SOLUBLE_SALTS)
    for _ in range(50):
        m_salt = rng.choice([5, 10, 15, 20, 25, 30, 40, 50, 60, 80])
        m_water = rng.choice([45, 70, 80, 90, 120, 150, 170, 190, 200, 240])
        total = m_salt + m_water
        w = m_salt / total * 100
        if round(w, 1) == round(w, 4):
            break
    else:
        raise SkipQuestion
    expl = (f"Масса раствора = масса соли + масса воды = {m_salt} + {m_water} = {total} г. "
            f"ω = {m_salt} / {total}·100% = {num(w, 1)}%. Делить нужно на массу раствора, а не воды.")
    return single(rng, f"В {m_water} г воды растворили {m_salt} г {salt.formula}. Найдите массовую долю соли в растворе.",
                  f"{num(w, 1)}%",
                  number_distractors(rng, w, [m_salt / m_water * 100, m_salt, 100 - w, w * 2], "%", digits=1),
                  expl)


@topic("06")
def substance_class(rng):
    sub = rng.choice(CLASSIFIED)
    reasons = {OXIDE: "оксид — соединение двух элементов, один из которых кислород (степень окисления −2)",
               ACID: "кислота состоит из атомов водорода и кислотного остатка",
               BASE: "основание состоит из атома металла и гидроксогрупп OH",
               SALT: "соль состоит из атомов металла (или NH₄) и кислотного остатка"}
    expl = f"{sub.formula} — {sub.name}: {reasons[sub.cls]}."
    return single(rng, f"К какому классу неорганических веществ относится {sub.formula}?", sub.cls,
                  [c for c in CLASSES if c != sub.cls], expl)


@topic("06")
def formula_by_name(rng):
    sub = rng.choice(CLASSIFIED)
    same = [s for s in CLASSIFIED if s is not sub and (s.cls == sub.cls or s.atoms[0][0] == sub.atoms[0][0])]
    if len(same) < 3:
        raise SkipQuestion
    wrong = [s.formula for s in rng.sample(same, min(6, len(same)))]
    return single(rng, f"Какая формула соответствует веществу «{sub.name}»?", sub.formula, wrong,
                  f"«{sub.name}» — это {sub.formula} ({sub.cls}).")


@topic("02")
def element_symbol(rng):
    el = rng.choice(list(ELEMENT_NAMES))
    wrong = rng.sample([e for e in ELEMENT_NAMES if e != el], 6)
    return single(rng, f"Какой символ имеет химический элемент {ELEMENT_NAMES[el]}?", el, wrong,
                  f"Элемент {ELEMENT_NAMES[el]} обозначается символом {el}.")


@topic("18")
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


@topic("18")
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


@topic("06")
def class_matching(rng):
    classes = rng.sample(CLASSES, 2)
    a = rng.choice([s for s in CLASSIFIED if s.cls == classes[0]])
    b = rng.choice([s for s in CLASSIFIED if s.cls == classes[1]])
    text = f"Установите соответствие между формулой вещества и классом: 1) {a.formula}; 2) {b.formula}."
    extra = [c for c in CLASSES if c not in classes]
    expl = f"{a.formula} ({a.name}) — {a.cls}. {b.formula} ({b.name}) — {b.cls}."
    return matching(rng, text, [(a.formula, a.cls), (b.formula, b.cls)], extra, expl)


@topic("18")
def mass_matching(rng):
    picked = rng.sample(SUBSTANCES, 4)
    masses = [num(s.molar_mass, 1) + " г/моль" for s in picked]
    if len(set(masses)) < 4:
        raise SkipQuestion
    a, b = picked[:2]
    text = f"Установите соответствие между веществом и его молярной массой: 1) {a.formula}; 2) {b.formula}."
    expl = f"M({a.formula}) = {_mass_sum(a)} = {masses[0]}. M({b.formula}) = {_mass_sum(b)} = {masses[1]}."
    return matching(rng, text, [(a.formula, masses[0]), (b.formula, masses[1])], masses[2:], expl)


@topic("06")
def name_matching(rng):
    picked = rng.sample(CLASSIFIED, 4)
    a, b = picked[:2]
    text = f"Установите соответствие между формулой и названием вещества: 1) {a.formula}; 2) {b.formula}."
    expl = f"{a.formula} — {a.name}, {b.formula} — {b.name}."
    return matching(rng, text, [(a.formula, a.name), (b.formula, b.name)], [p.name for p in picked[2:]], expl)


@topic("06")
def class_multiple(rng):
    cls = rng.choice(CLASSES)
    right = rng.sample([s for s in CLASSIFIED if s.cls == cls], rng.randint(1, 3))
    wrong = rng.sample([s for s in CLASSIFIED if s.cls != cls], 6 - len(right))
    names = sorted(s.formula for s in right + wrong)
    text = f"Какие из веществ являются {CLASS_PLURAL[cls]}: {', '.join(names)}?"
    expl = ("К этому классу относятся: " + ", ".join(f"{s.formula} ({s.name})" for s in right) + ". "
            + "Остальные: " + ", ".join(f"{s.formula} — {s.cls}" for s in wrong) + ".")
    return multiple(rng, text, [s.formula for s in right], [s.formula for s in wrong], expl)


@topic("18")
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


_SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")

_ATOMS = [("водорода", "H", 1, 1), ("гелия", "He", 2, 4), ("лития", "Li", 3, 7), ("углерода", "C", 6, 12),
          ("азота", "N", 7, 14), ("кислорода", "O", 8, 16), ("фтора", "F", 9, 19), ("натрия", "Na", 11, 23),
          ("магния", "Mg", 12, 24), ("алюминия", "Al", 13, 27), ("фосфора", "P", 15, 31),
          ("серы", "S", 16, 32), ("хлора", "Cl", 17, 35), ("калия", "K", 19, 39), ("кальция", "Ca", 20, 40),
          ("железа", "Fe", 26, 56), ("меди", "Cu", 29, 64), ("цинка", "Zn", 30, 65)]


@topic("01")
def atom_structure(rng):
    name, symbol, z, mass_number = rng.choice(_ATOMS)
    part = rng.choice(["протонов", "нейтронов", "электронов"])
    answer = mass_number - z if part == "нейтронов" else z
    text = f"Сколько {part} в атоме {name} {symbol} с массовым числом {mass_number}?"
    explanation = (f"Порядковый номер {symbol} равен {z}: в ядре {z} протонов, в нейтральном атоме столько же "
                   f"электронов. Нейтронов N = A − Z = {mass_number} − {z} = {mass_number - z}.")
    return single(rng, text, num(answer),
                  number_distractors(rng, answer, [mass_number, z, mass_number - z, mass_number + z]),
                  explanation)


_OXIDATION = [("H₂SO₄", "S", 6), ("SO₂", "S", 4), ("H₂S", "S", -2), ("Na₂SO₃", "S", 4), ("HNO₃", "N", 5),
              ("NH₃", "N", -3), ("NO₂", "N", 4), ("KMnO₄", "Mn", 7), ("MnO₂", "Mn", 4),
              ("K₂Cr₂O₇", "Cr", 6), ("Fe₂O₃", "Fe", 3), ("FeO", "Fe", 2), ("H₃PO₄", "P", 5),
              ("CO₂", "C", 4), ("CH₄", "C", -4), ("Cl₂O₇", "Cl", 7), ("HClO", "Cl", 1), ("KClO₃", "Cl", 5)]


def _sign(value: int) -> str:
    return f"+{value}" if value > 0 else num(value)


@topic("03")
def oxidation_state(rng):
    formula, element, state = rng.choice(_OXIDATION)
    wrong = [_sign(v) for v in (-state, state - 2, state + 2, state - 1, 0) if v != state]
    explanation = (f"Сумма степеней окисления в молекуле равна нулю (у водорода +1, у кислорода −2, у щелочных "
                   f"металлов +1). Отсюда степень окисления {element} в {formula} равна {_sign(state)}.")
    return single(rng, f"Какова степень окисления {element} в соединении {formula}?", _sign(state), wrong,
                  explanation)


@topic("04")
def vant_hoff(rng):
    gamma = rng.choice([2, 3, 4])
    steps = rng.randint(1, 4)
    times = gamma ** steps
    text = (f"Во сколько раз увеличится скорость реакции при повышении температуры на {10 * steps} °C, "
            f"если температурный коэффициент реакции равен {gamma}?")
    explanation = (f"Правило Вант-Гоффа: v₂/v₁ = γ^(ΔT/10) = {gamma}^{steps} = {times}.")
    return single(rng, text, f"в {times} раз",
                  [f"в {v} раз" for v in (gamma * steps, gamma * 10 * steps, times * gamma, gamma + steps)],
                  explanation)


_SALTS = [("NaCl", "нейтральная"), ("KNO₃", "нейтральная"), ("K₂SO₄", "нейтральная"),
          ("Na₂CO₃", "щелочная"), ("K₂S", "щелочная"), ("CH₃COONa", "щелочная"), ("Na₂SO₃", "щелочная"),
          ("Na₃PO₄", "щелочная"), ("AlCl₃", "кислая"), ("ZnSO₄", "кислая"), ("NH₄Cl", "кислая"),
          ("CuSO₄", "кислая"), ("FeCl₃", "кислая"), ("NH₄NO₃", "кислая")]
_SALT_RULE = {
    "нейтральная": "соль образована сильным основанием и сильной кислотой — гидролиза нет, среда нейтральная",
    "щелочная": "соль образована сильным основанием и слабой кислотой — гидролиз по аниону, среда щелочная",
    "кислая": "соль образована слабым основанием и сильной кислотой — гидролиз по катиону, среда кислая",
}


@topic("05")
def salt_hydrolysis(rng):
    salt, medium = rng.choice(_SALTS)
    options = ["нейтральная", "щелочная", "кислая", "среду определить нельзя"]
    return single(rng, f"Какая среда у водного раствора соли {salt}?", medium,
                  [o for o in options if o != medium], f"{salt}: {_SALT_RULE[medium]}.")


_ALKANE_NAMES = {1: "метан", 2: "этан", 3: "пропан", 4: "бутан", 5: "пентан", 6: "гексан", 7: "гептан",
                 8: "октан", 9: "нонан", 10: "декан"}


def _alkane(n: int) -> str:
    return f"C{str(n).translate(_SUBSCRIPT) if n > 1 else ''}H{str(2 * n + 2).translate(_SUBSCRIPT)}"


@topic("13")
def alkane_molar_mass(rng):
    n = rng.randint(1, 10)
    molar = 14 * n + 2
    text = f"Какова молярная масса алкана {_ALKANE_NAMES[n]} {_alkane(n)}? (Ar(C) = 12, Ar(H) = 1)"
    explanation = (f"Общая формула алканов CₙH₂ₙ₊₂, M = 12n + 2n + 2 = 14n + 2 = 14·{n} + 2 = {molar} г/моль.")
    return single(rng, text, f"{molar} г/моль",
                  number_distractors(rng, molar, [14 * n, 14 * n - 2, 12 * n], " г/моль"), explanation)


@topic("19")
def combustion_formula(rng):
    n = rng.randint(1, 8)
    co2, h2o = 44 * n, 18 * (n + 1)
    text = (f"При полном сгорании 1 моль алкана образовалось {co2} г CO₂ и {h2o} г H₂O. "
            "Какова формула алкана? (M(CO₂) = 44 г/моль, M(H₂O) = 18 г/моль)")
    explanation = (f"n(CO₂) = {co2}/44 = {n} моль, значит в молекуле {n} атом(а) C. n(H₂O) = {h2o}/18 = {n + 1} "
                   f"моль, атомов H — {2 * (n + 1)}. Формула {_alkane(n)}.")
    wrong = [_alkane(n + 1), f"C{str(n).translate(_SUBSCRIPT) if n > 1 else ''}H{str(2 * n).translate(_SUBSCRIPT)}",
             f"C{str(n + 1).translate(_SUBSCRIPT)}H{str(2 * n + 2).translate(_SUBSCRIPT)}"]
    return single(rng, text, _alkane(n), wrong, explanation)


GROUPS_1_3 = quiz([
    ("Какой металл хранят под слоем керосина из-за его высокой активности?", "натрий",
     ["алюминий", "медь", "железо"], "Натрий бурно реагирует с водой и кислородом воздуха, поэтому его хранят под керосином."),
    ("Какой газ выделяется при взаимодействии натрия с водой?", "водород", ["кислород", "азот", "углекислый газ"],
     "2Na + 2H₂O → 2NaOH + H₂↑."),
    ("Как в быту называют гидроксид кальция Ca(OH)₂?", "гашёная известь", ["негашёная известь", "мел", "гипс"],
     "CaO — негашёная известь; при взаимодействии с водой она «гасится» и превращается в Ca(OH)₂."),
    ("Какой металл не разрушается на воздухе благодаря прочной оксидной плёнке, хотя он активен?", "алюминий",
     ["натрий", "калий", "кальций"], "Плёнка Al₂O₃ защищает алюминий от дальнейшего окисления."),
    ("Какое вещество — основной компонент мела, мрамора и известняка?", "CaCO₃", ["CaO", "Ca(OH)₂", "CaSO₄"],
     "Мел, мрамор и известняк состоят в основном из карбоната кальция CaCO₃."),
    ("Какие соли обусловливают временную жёсткость воды?", "гидрокарбонаты кальция и магния",
     ["хлорид натрия", "сульфат натрия", "нитрат калия"],
     "Временную жёсткость дают Ca(HCO₃)₂ и Mg(HCO₃)₂; при кипячении они разлагаются, выпадает накипь."),
], "07")

GROUP_4 = quiz([
    ("Какой газ образуется при полном сгорании угля?", "CO₂", ["CO", "CH₄", "O₂"],
     "C + O₂ → CO₂. При недостатке кислорода образуется угарный газ CO."),
    ("Какое аллотропное видоизменение углерода — самое твёрдое природное вещество?", "алмаз",
     ["графит", "карбин", "сажа"], "В алмазе каждый атом углерода связан с четырьмя соседями прочными связями."),
    ("Какой оксид углерода называют угарным газом?", "CO", ["CO₂", "C₂H₂", "CH₄"],
     "CO очень ядовит: он прочно связывается с гемоглобином крови."),
    ("Какой элемент — основа полупроводниковых микросхем и солнечных батарей?", "кремний",
     ["углерод", "свинец", "олово"], "Кремний — главный полупроводниковый материал электроники."),
    ("Как называется оксид кремния SiO₂, из которого состоят песок и кварц?", "кремнезём",
     ["корунд", "малахит", "пирит"], "SiO₂ — кремнезём, его кристаллическая форма — кварц."),
], "08")

GROUP_5 = quiz([
    ("Какой газ составляет около 78 % воздуха по объёму?", "азот", ["кислород", "аргон", "углекислый газ"],
     "Воздух содержит около 78 % азота, 21 % кислорода и около 1 % аргона."),
    ("Какое вещество получают в промышленности из азота и водорода?", "аммиак",
     ["азотную кислоту", "оксид азота(II)", "мочевину"], "N₂ + 3H₂ ⇄ 2NH₃ (катализатор — железо, высокое давление)."),
    ("Какой газ с резким запахом выделяется при нагревании хлорида аммония со щёлочью?", "аммиак",
     ["азот", "хлор", "водород"], "NH₄Cl + NaOH → NaCl + NH₃↑ + H₂O."),
    ("Какая модификация фосфора ядовита и светится в темноте?", "белый фосфор",
     ["красный фосфор", "чёрный фосфор", "фосфорит"], "Белый фосфор P₄ очень активен и ядовит; красный фосфор устойчивее."),
    ("Какое вещество — основа простого суперфосфата?", "Ca(H₂PO₄)₂", ["KNO₃", "NH₄NO₃", "KCl"],
     "Простой суперфосфат — смесь дигидрофосфата кальция Ca(H₂PO₄)₂ и гипса."),
], "09")

GROUP_6 = quiz([
    ("Какой газ образуется при обжиге пирита FeS₂ на первой стадии производства серной кислоты?", "SO₂",
     ["SO₃", "H₂S", "O₂"], "4FeS₂ + 11O₂ → 2Fe₂O₃ + 8SO₂."),
    ("Какой катализатор используют при окислении SO₂ в SO₃ в контактном способе производства серной кислоты?",
     "V₂O₅", ["Fe", "MnO₂", "Ni"], "2SO₂ + O₂ ⇄ 2SO₃ на ванадиевом катализаторе V₂O₅."),
    ("Чем поглощают SO₃ в производстве серной кислоты?", "концентрированной серной кислотой",
     ["водой", "раствором щёлочи", "соляной кислотой"],
     "SO₃ поглощают концентрированной H₂SO₄ (образуется олеум): с водой образовался бы сернокислотный туман."),
    ("Какой газ имеет запах тухлых яиц?", "H₂S", ["SO₂", "NH₃", "Cl₂"], "Сероводород H₂S — ядовитый газ с запахом тухлых яиц."),
    ("Какое аллотропное видоизменение кислорода защищает Землю от ультрафиолета?", "озон O₃",
     ["кислород O₂", "пероксид водорода", "углекислый газ"], "Озоновый слой стратосферы поглощает жёсткое ультрафиолетовое излучение."),
], "10")

GROUP_7 = quiz([
    ("Какой галоген при обычных условиях — жидкость?", "бром", ["хлор", "фтор", "йод"],
     "Бром — единственный неметалл, жидкий при комнатной температуре."),
    ("Какой элемент самый электроотрицательный?", "фтор", ["хлор", "кислород", "йод"],
     "Фтор имеет наибольшую электроотрицательность (4,0 по Полингу)."),
    ("Каким реактивом обнаруживают хлорид-ионы в растворе?", "AgNO₃", ["BaCl₂", "NaOH", "KMnO₄"],
     "Ag⁺ + Cl⁻ → AgCl↓ — белый творожистый осадок."),
    ("Какой газ выделяется на аноде при электролизе раствора поваренной соли?", "хлор",
     ["водород", "кислород", "азот"], "2NaCl + 2H₂O → 2NaOH + H₂↑ (катод) + Cl₂↑ (анод)."),
    ("Какое вещество окрашивает крахмал в синий цвет?", "йод", ["хлор", "бром", "фтор"],
     "Синее окрашивание с йодом — качественная реакция на крахмал."),
], "11")

TRANSITION = quiz([
    ("Что представляет собой ржавчина по составу?", "гидратированный оксид железа(III)",
     ["оксид меди(II)", "оксид цинка", "карбонат кальция"], "Ржавчина — в основном Fe₂O₃·nH₂O."),
    ("Какой металл — основа чугуна и стали?", "железо", ["медь", "хром", "алюминий"],
     "Чугун и сталь — сплавы железа с углеродом (в чугуне более 2 % углерода)."),
    ("Какой цвет имеет водный раствор сульфата меди(II)?", "голубой", ["зелёный", "бесцветный", "жёлтый"],
     "Ионы Cu²⁺ в водном растворе окрашены в голубой цвет."),
    ("В каком соединении хром имеет степень окисления +6?", "K₂Cr₂O₇", ["Cr₂O₃", "CrCl₃", "CrO"],
     "В дихромате калия: 2·(+1) + 2x + 7·(−2) = 0, x = +6."),
    ("Как называется комплексное соединение K₄[Fe(CN)₆]?", "жёлтая кровяная соль",
     ["красная кровяная соль", "берлинская лазурь", "медный купорос"],
     "K₄[Fe(CN)₆] — жёлтая кровяная соль, K₃[Fe(CN)₆] — красная кровяная соль."),
], "12")

OXYGEN_ORGANIC = quiz([
    ("Какая функциональная группа характерна для спиртов?", "гидроксильная −OH",
     ["карбоксильная −COOH", "альдегидная −CHO", "аминогруппа −NH₂"], "Спирты содержат гидроксильную группу −OH."),
    ("Какая функциональная группа характерна для карбоновых кислот?", "карбоксильная −COOH",
     ["гидроксильная −OH", "альдегидная −CHO", "нитрогруппа −NO₂"], "Карбоновые кислоты содержат группу −COOH."),
    ("Каким реактивом обнаруживают многоатомные спирты (образуется ярко-синий раствор)?", "Cu(OH)₂",
     ["AgNO₃", "FeCl₃", "Br₂"], "Глицерин и другие многоатомные спирты растворяют Cu(OH)₂ с образованием ярко-синего раствора."),
    ("Как называется реакция кислоты со спиртом, в которой образуется сложный эфир?", "этерификация",
     ["гидролиз", "полимеризация", "гидрирование"], "Кислота + спирт ⇄ сложный эфир + вода — реакция этерификации."),
    ("Какие вещества дают реакцию «серебряного зеркала»?", "альдегиды", ["кетоны", "спирты", "простые эфиры"],
     "Альдегиды окисляются аммиачным раствором оксида серебра, на стенках выделяется серебро."),
], "14")

CARBOHYDRATES = quiz([
    ("Какой углевод образуется в листьях растений при фотосинтезе?", "глюкоза",
     ["сахароза", "целлюлоза", "лактоза"], "6CO₂ + 6H₂O → C₆H₁₂O₆ + 6O₂ (на свету, в хлоропластах)."),
    ("Какой полисахарид — главный компонент клеточных стенок растений?", "целлюлоза",
     ["крахмал", "гликоген", "глюкоза"], "Клеточные стенки растений состоят в основном из целлюлозы."),
    ("Каким реактивом обнаруживают крахмал?", "раствором йода", ["AgNO₃", "Cu(OH)₂", "фенолфталеином"],
     "Крахмал с йодом даёт синее окрашивание."),
    ("Какой дисахарид называют свекловичным или тростниковым сахаром?", "сахароза",
     ["лактоза", "мальтоза", "глюкоза"], "Обычный сахар — сахароза C₁₂H₂₂O₁₁."),
    ("Какое вещество образуется вместе с CO₂ при спиртовом брожении глюкозы?", "этанол",
     ["метанол", "уксусная кислота", "глицерин"], "C₆H₁₂O₆ → 2C₂H₅OH + 2CO₂."),
], "15")

NITROGEN_ORGANIC = quiz([
    ("Какая функциональная группа характерна для аминов?", "аминогруппа −NH₂",
     ["гидроксильная −OH", "карбоксильная −COOH", "нитрогруппа −NO₂"], "Амины — производные аммиака с группой −NH₂."),
    ("Как называется связь между остатками аминокислот в молекуле белка?", "пептидная",
     ["водородная", "ионная", "гликозидная"], "Аминокислоты соединяются пептидной связью −CO−NH−."),
    ("Какое вещество получают восстановлением нитробензола (реакция Зинина)?", "анилин",
     ["фенол", "бензол", "толуол"], "C₆H₅NO₂ + 6[H] → C₆H₅NH₂ + 2H₂O."),
    ("Какие соединения содержат и аминогруппу, и карбоксильную группу?", "аминокислоты",
     ["амины", "спирты", "альдегиды"], "Аминокислоты содержат −NH₂ и −COOH, поэтому амфотерны."),
    ("Как называется реакция белков с концентрированной азотной кислотой (жёлтое окрашивание)?",
     "ксантопротеиновая", ["биуретовая", "йодная", "реакция серебряного зеркала"],
     "Ксантопротеиновая реакция обнаруживает в белке остатки ароматических аминокислот."),
], "16")

POLYMERS = quiz([
    ("Из какого мономера получают полиэтилен?", "этилен", ["ацетилен", "стирол", "пропан"],
     "nCH₂=CH₂ → (−CH₂−CH₂−)ₙ — реакция полимеризации."),
    ("Из какого мономера получают поливинилхлорид (ПВХ)?", "винилхлорид", ["этилен", "хлорметан", "стирол"],
     "ПВХ получают полимеризацией винилхлорида CH₂=CHCl."),
    ("Как называется разделение нефти на фракции по температурам кипения?", "перегонка (ректификация)",
     ["крекинг", "риформинг", "гидрирование"], "При перегонке нефть разделяют на бензин, керосин, дизельное топливо, мазут."),
    ("Как называется расщепление крупных молекул углеводородов нефти на более мелкие?", "крекинг",
     ["перегонка", "изомеризация", "гидратация"], "Крекинг увеличивает выход бензина из нефти."),
    ("Какая из фракций перегонки нефти кипит при самой низкой температуре?", "бензин",
     ["керосин", "дизельное топливо", "мазут"], "Бензин кипит примерно до 200 °C, мазут — остаток после перегонки."),
], "17")


TEMPLATES = {
    "single": [molar_mass, mass_fraction, amount_from_mass, mass_from_amount, gas_volume, molecules,
               solution_fraction, substance_class, formula_by_name, element_symbol, atom_structure,
               oxidation_state, vant_hoff, salt_hydrolysis, alkane_molar_mass, combustion_formula,
               GROUPS_1_3, GROUP_4, GROUP_5, GROUP_6, GROUP_7, TRANSITION, OXYGEN_ORGANIC, CARBOHYDRATES,
               NITROGEN_ORGANIC, POLYMERS],
    "context": [solution_context, reaction_context],
    "matching": [class_matching, mass_matching, name_matching],
    "multiple": [class_multiple, heavy_multiple],
}
