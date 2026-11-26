"""Шаблоны задач по физике. Ускорение свободного падения g = 10 м/с², как принято в задачах ЕНТ."""


from app.generators.common import SkipQuestion, matching, multiple, num, number_distractors, single

G = 10


def _q(rng, text, value, unit, wrong, expl, context=""):
    """Числовой вопрос с единицей измерения."""
    return single(rng, text, f"{num(value)} {unit}",
                  number_distractors(rng, value, wrong, f" {unit}"), expl, context=context)


# ── Один ответ ───────────────────────────────────────────────────────────────

def speed(rng):
    v, t = rng.randint(2, 40), rng.randint(2, 60)
    s = v * t
    return _q(rng, f"Тело прошло {s} м за {t} с, двигаясь равномерно. Найдите скорость тела.", v, "м/с",
              [s * t, s - t, v * 2, s / 10],
              f"При равномерном движении v = s / t = {s} / {t} = {v} м/с.")


def acceleration(rng):
    v0, a, t = rng.randint(0, 20), rng.randint(1, 6), rng.randint(2, 12)
    v = v0 + a * t
    return _q(rng, f"Скорость тела за {t} с изменилась с {v0} м/с до {v} м/с. Найдите ускорение.", a, "м/с²",
              [v / t, (v + v0) / t, v - v0, a * 2],
              f"Ускорение a = (v − v₀) / t = ({v} − {v0}) / {t} = {a} м/с².")


def newton_second(rng):
    m, a = rng.randint(2, 500), rng.randint(1, 10)
    f = m * a
    return _q(rng, f"Какая сила сообщает телу массой {m} кг ускорение {a} м/с²?", f, "Н",
              [m + a, m / a, f * G, f / 2],
              f"По второму закону Ньютона F = m·a = {m}·{a} = {f} Н.")


def momentum(rng):
    m, v = rng.randint(1, 80), rng.randint(2, 30)
    return _q(rng, f"Найдите импульс тела массой {m} кг, движущегося со скоростью {v} м/с.", m * v, "кг·м/с",
              [m * v * v / 2, m + v, m * v * 2, m * v / 2],
              f"Импульс p = m·v = {m}·{v} = {m * v} кг·м/с.")


def kinetic_energy(rng):
    m, v = rng.randint(1, 50), rng.randint(2, 20)
    e = m * v * v / 2
    return _q(rng, f"Найдите кинетическую энергию тела массой {m} кг, движущегося со скоростью {v} м/с.", e, "Дж",
              [m * v, m * v * v, m * v / 2, e / 2],
              f"Кинетическая энергия Eₖ = m·v² / 2 = {m}·{v}² / 2 = {num(e)} Дж.")


def potential_energy(rng):
    m, h = rng.randint(1, 100), rng.randint(2, 50)
    e = m * G * h
    return _q(rng, f"Тело массой {m} кг подняли на высоту {h} м. На сколько увеличилась его потенциальная энергия? (g = 10 м/с²)",
              e, "Дж", [m * h, e / 2, m * G + h, e * 2],
              f"Потенциальная энергия Eₚ = m·g·h = {m}·10·{h} = {e} Дж.")


def work(rng):
    f, s = rng.randint(5, 500), rng.randint(2, 100)
    return _q(rng, f"Сила {f} Н перемещает тело на {s} м в направлении действия силы. Найдите работу силы.",
              f * s, "Дж", [f + s, f / s, f * s / 2, f * s * 2],
              f"Работа A = F·s = {f}·{s} = {f * s} Дж.")


def power_mech(rng):
    p, t = rng.randint(10, 2000), rng.randint(2, 60)
    a = p * t
    return _q(rng, f"Двигатель совершил работу {a} Дж за {t} с. Найдите мощность двигателя.", p, "Вт",
              [a * t, a - t, p * 2, p / 2],
              f"Мощность N = A / t = {a} / {t} = {p} Вт.")


def pressure(rng):
    f = rng.randint(10, 5000)
    s = rng.choice([0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2])
    p = f / s
    if p != int(p):
        raise SkipQuestion
    return _q(rng, f"Сила {f} Н действует перпендикулярно на площадь {num(s)} м². Найдите давление.", p, "Па",
              [f * s, p / 10, p * 2, f],
              f"Давление p = F / S = {f} / {num(s)} = {num(p)} Па.")


def ohm(rng):
    r, i = rng.randint(2, 100), rng.choice([0.5, 1, 1.5, 2, 2.5, 3, 4, 5])
    u = r * i
    if u != int(u):
        raise SkipQuestion
    if rng.random() < 0.5:
        return _q(rng, f"Напряжение на резисторе {num(u)} В, его сопротивление {r} Ом. Найдите силу тока.", i, "А",
                  [u * r, r / u, i * 2, i + 1],
                  f"По закону Ома I = U / R = {num(u)} / {r} = {num(i)} А.")
    return _q(rng, f"Через резистор сопротивлением {r} Ом течёт ток {num(i)} А. Найдите напряжение на резисторе.",
              u, "В", [r / i, r + i, u * 2, u / 2],
              f"По закону Ома U = I·R = {num(i)}·{r} = {num(u)} В.")


def resistors(rng):
    r1, r2 = rng.randint(2, 60), rng.randint(2, 60)
    if rng.random() < 0.5:
        return _q(rng, f"Резисторы {r1} Ом и {r2} Ом соединены последовательно. Найдите общее сопротивление.",
                  r1 + r2, "Ом", [r1 * r2 / (r1 + r2), r1 * r2, abs(r1 - r2), (r1 + r2) / 2],
                  f"При последовательном соединении сопротивления складываются: R = {r1} + {r2} = {r1 + r2} Ом.")
    total = r1 * r2 / (r1 + r2)
    if total * 10 != int(total * 10):
        raise SkipQuestion
    return _q(rng, f"Резисторы {r1} Ом и {r2} Ом соединены параллельно. Найдите общее сопротивление.",
              total, "Ом", [r1 + r2, r1 * r2, (r1 + r2) / 2, total * 2],
              f"При параллельном соединении R = R₁·R₂ / (R₁ + R₂) = {r1}·{r2} / {r1 + r2} = {num(total)} Ом. "
              "Общее сопротивление всегда меньше меньшего из резисторов.")


def electric_power(rng):
    u = rng.choice([12, 24, 36, 110, 127, 220])
    i = rng.choice([0.5, 1, 2, 2.5, 3, 4, 5, 10])
    p = u * i
    return _q(rng, f"Прибор работает от напряжения {u} В при силе тока {num(i)} А. Найдите его мощность.", p, "Вт",
              [u / i, u + i, p * 2, p / 2],
              f"Мощность тока P = U·I = {u}·{num(i)} = {num(p)} Вт.")


def density(rng):
    material, rho = rng.choice([("алюминия", 2700), ("железа", 7800), ("меди", 8900), ("воды", 1000),
                                ("льда", 900), ("свинца", 11300), ("дерева", 600)])
    v = rng.choice([0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 2])
    m = rho * v
    return _q(rng, f"Найдите массу тела из {material} объёмом {num(v, 3)} м³, если плотность {material} {rho} кг/м³.",
              m, "кг", [rho / v, m * 10, m / 10, rho + v],
              f"Масса m = ρ·V = {rho}·{num(v, 3)} = {num(m)} кг.")


def heat(rng):
    substance, c = rng.choice([("воды", 4200), ("алюминия", 920), ("меди", 400), ("железа", 460), ("масла", 1700)])
    m = rng.choice([0.2, 0.5, 1, 1.5, 2, 3, 5])
    dt = rng.randint(5, 80)
    q = c * m * dt
    if q != int(q):
        raise SkipQuestion
    return _q(rng, f"Сколько теплоты нужно, чтобы нагреть {num(m)} кг {substance} на {dt} °C? "
                   f"Удельная теплоёмкость {substance} {c} Дж/(кг·°C).",
              q, "Дж", [c * m, c * dt, q / 2, q * 2],
              f"Количество теплоты Q = c·m·Δt = {c}·{num(m)}·{dt} = {num(q)} Дж.")


def wave(rng):
    v = rng.choice([340, 1500, 300, 5000, 20, 2])
    f = rng.choice([2, 5, 10, 20, 50, 100, 170, 200, 500])
    lam = v / f
    if lam * 100 != int(lam * 100):
        raise SkipQuestion
    return _q(rng, f"Волна распространяется со скоростью {v} м/с, частота колебаний {f} Гц. Найдите длину волны.",
              lam, "м", [v * f, f / v, lam * 2, lam + 1],
              f"Длина волны λ = v / ν = {v} / {f} = {num(lam)} м.")


def hydrostatic(rng):
    liquid, rho = rng.choice([("воде", 1000), ("морской воде", 1030), ("керосине", 800), ("ртути", 13600)])
    h = rng.choice([0.5, 1, 2, 3, 5, 10, 20, 50])
    p = rho * G * h
    return _q(rng, f"Найдите давление столба жидкости на глубине {num(h)} м в {liquid} (ρ = {rho} кг/м³, g = 10 м/с²).",
              p, "Па", [rho * h, p / 2, p * 10, rho * G],
              f"Гидростатическое давление p = ρ·g·h = {rho}·10·{num(h)} = {num(p)} Па.")


def archimedes(rng):
    v = rng.choice([0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.5])
    rho = 1000
    f = rho * G * v
    return _q(rng, f"Тело объёмом {num(v, 3)} м³ полностью погружено в воду (ρ = 1000 кг/м³). Найдите выталкивающую силу.",
              f, "Н", [rho * v, f * 10, f / 2, f + 1],
              f"Сила Архимеда F = ρ·g·V = 1000·10·{num(v, 3)} = {num(f)} Н.")


def spring(rng):
    k = rng.choice([20, 40, 50, 100, 200, 250, 400, 500, 1000])
    x_cm = rng.choice([1, 2, 3, 4, 5, 8, 10, 15, 20])
    f = k * x_cm / 100
    return _q(rng, f"Жёсткость пружины {k} Н/м. Какая сила растянет её на {x_cm} см?", f, "Н",
              [k * x_cm, k / x_cm, f * 10, f * 2],
              f"По закону Гука F = k·x. Переводим в метры: {x_cm} см = {num(x_cm / 100)} м. "
              f"F = {k}·{num(x_cm / 100)} = {num(f)} Н.")


def free_fall(rng):
    t = rng.randint(1, 6)
    if rng.random() < 0.5:
        h = G * t * t / 2
        return _q(rng, f"Тело свободно падает без начальной скорости в течение {t} с. Какой путь оно пройдёт? (g = 10 м/с²)",
                  h, "м", [G * t, G * t * t, h / 2, h + G],
                  f"При свободном падении h = g·t² / 2 = 10·{t}² / 2 = {num(h)} м.")
    v = G * t
    return _q(rng, f"Какую скорость приобретёт тело через {t} с свободного падения без начальной скорости? (g = 10 м/с²)",
              v, "м/с", [G * t * t / 2, G * t * t, v / 2, v + G],
              f"Скорость при свободном падении v = g·t = 10·{t} = {v} м/с.")


def period(rng):
    n, t = rng.randint(5, 100), rng.randint(2, 60)
    if rng.random() < 0.5:
        per = t / n
        if per * 100 != int(per * 100):
            raise SkipQuestion
        return _q(rng, f"Маятник совершил {n} колебаний за {t} с. Найдите период колебаний.", per, "с",
                  [n / t, t * n, per * 2, t - n if t > n else per + 1],
                  f"Период — время одного колебания: T = t / N = {t} / {n} = {num(per)} с.")
    freq = n / t
    if freq * 100 != int(freq * 100):
        raise SkipQuestion
    return _q(rng, f"Тело совершило {n} колебаний за {t} с. Найдите частоту колебаний.", freq, "Гц",
              [t / n, n * t, freq * 2, freq + 1],
              f"Частота — число колебаний за секунду: ν = N / t = {n} / {t} = {num(freq)} Гц.")


# ── По контексту ─────────────────────────────────────────────────────────────

def car_context(rng):
    m = rng.choice([800, 1000, 1200, 1500, 2000])
    v = rng.choice([10, 15, 20, 25, 30])
    t = rng.choice([5, 8, 10, 15, 20])
    a = v / t
    if a * 10 != int(a * 10):
        raise SkipQuestion
    context = (f"Автомобиль массой {m} кг трогается с места и, двигаясь равноускоренно, "
               f"за {t} с разгоняется до скорости {v} м/с.")
    kind = rng.choice(["a", "f", "s", "e"])
    if kind == "a":
        return _q(rng, f"Чему равно ускорение автомобиля массой {m} кг, разогнавшегося до {v} м/с за {t} с?",
                  a, "м/с²", [v * t, t / v, a * 2, m / t],
                  f"a = (v − v₀) / t = ({v} − 0) / {t} = {num(a)} м/с². Масса для ответа не нужна.", context)
    if kind == "f":
        f = m * a
        return _q(rng, f"Какая равнодействующая сила разгоняет автомобиль массой {m} кг до {v} м/с за {t} с?",
                  f, "Н", [m * v, m / a, f * 2, f / 2],
                  f"Ускорение a = {v} / {t} = {num(a)} м/с². По второму закону Ньютона F = m·a = {m}·{num(a)} = {num(f)} Н.",
                  context)
    if kind == "s":
        s = a * t * t / 2
        return _q(rng, f"Какой путь прошёл автомобиль массой {m} кг, разгоняясь до {v} м/с за {t} с?",
                  s, "м", [v * t, a * t * t, s / 2, v * t * 2],
                  f"При разгоне с места s = v·t / 2 = {v}·{t} / 2 = {num(s)} м.", context)
    e = m * v * v / 2
    return _q(rng, f"Какую кинетическую энергию приобрёл автомобиль массой {m} кг, разогнавшись до {v} м/с за {t} с?",
              e, "Дж", [m * v, m * v * v, e / 2, m * a],
              f"Eₖ = m·v² / 2 = {m}·{v}² / 2 = {num(e)} Дж.", context)


def circuit_context(rng):
    u = rng.choice([6, 9, 12, 24, 36, 220])
    r1, r2 = rng.randint(2, 40), rng.randint(2, 40)
    r = r1 + r2
    i = u / r
    if i * 100 != int(i * 100):
        raise SkipQuestion
    context = (f"Два резистора сопротивлением {r1} Ом и {r2} Ом соединены последовательно "
               f"и подключены к источнику напряжением {u} В.")
    if rng.random() < 0.5:
        return _q(rng, f"Найдите силу тока в цепи: {r1} Ом и {r2} Ом последовательно, напряжение {u} В.",
                  i, "А", [u / r1, u * r, i * 2, u / (r1 * r2 / r)],
                  f"Общее сопротивление R = {r1} + {r2} = {r} Ом. Сила тока I = U / R = {u} / {r} = {num(i)} А.", context)
    u1 = i * r1
    return _q(rng, f"Найдите напряжение на резисторе {r1} Ом в цепи: {r1} Ом и {r2} Ом последовательно, {u} В.",
              u1, "В", [u - u1, u, u1 * 2, u / 2 if u / 2 != u1 else u1 + 1],
              f"Ток в цепи I = {u} / ({r1} + {r2}) = {num(i)} А. Напряжение U₁ = I·R₁ = {num(i)}·{r1} = {num(u1)} В.",
              context)


# ── Соответствие ─────────────────────────────────────────────────────────────

_UNITS = [("Сила", "Ньютон"), ("Работа", "Джоуль"), ("Мощность", "Ватт"), ("Давление", "Паскаль"),
          ("Сила тока", "Ампер"), ("Напряжение", "Вольт"), ("Сопротивление", "Ом"), ("Частота", "Герц"),
          ("Электрический заряд", "Кулон"), ("Ёмкость конденсатора", "Фарад"), ("Индуктивность", "Генри"),
          ("Магнитная индукция", "Тесла"), ("Магнитный поток", "Вебер"), ("Температура (абсолютная)", "Кельвин"),
          ("Количество вещества", "Моль"), ("Сила света", "Кандела")]

_FORMULAS = [("Второй закон Ньютона", "F = m·a"), ("Закон Ома для участка цепи", "I = U / R"),
             ("Кинетическая энергия", "Eₖ = m·v² / 2"), ("Потенциальная энергия", "Eₚ = m·g·h"),
             ("Закон Гука", "F = k·x"), ("Импульс тела", "p = m·v"), ("Давление", "p = F / S"),
             ("Сила Архимеда", "F = ρ·g·V"), ("Мощность тока", "P = U·I"), ("Количество теплоты при нагреве", "Q = c·m·Δt"),
             ("Плотность", "ρ = m / V"), ("Механическая работа", "A = F·s"), ("Длина волны", "λ = v / ν"),
             ("Закон всемирного тяготения", "F = G·m₁·m₂ / r²")]


def units_matching(rng):
    picked = rng.sample(_UNITS, 4)
    pairs, extra = picked[:2], [u for _, u in picked[2:]]
    text = f"Установите соответствие между величиной и её единицей в СИ: 1) {pairs[0][0].lower()}; 2) {pairs[1][0].lower()}."
    expl = f"{pairs[0][0]} измеряется в единицах «{pairs[0][1]}», {pairs[1][0].lower()} — в единицах «{pairs[1][1]}»."
    return matching(rng, text, pairs, extra, expl)


def formulas_matching(rng):
    picked = rng.sample(_FORMULAS, 4)
    pairs, extra = picked[:2], [f for _, f in picked[2:]]
    text = f"Установите соответствие между законом (величиной) и формулой: 1) {pairs[0][0].lower()}; 2) {pairs[1][0].lower()}."
    expl = f"{pairs[0][0]}: {pairs[0][1]}. {pairs[1][0]}: {pairs[1][1]}."
    return matching(rng, text, pairs, extra, expl)


# ── Несколько ответов ────────────────────────────────────────────────────────

_VECTORS = ["Скорость", "Сила", "Ускорение", "Импульс", "Перемещение", "Напряжённость электрического поля",
            "Магнитная индукция"]
_SCALARS = ["Масса", "Время", "Температура", "Работа", "Энергия", "Путь", "Мощность", "Объём", "Заряд",
            "Плотность", "Давление"]


def vectors_multiple(rng):
    right = rng.sample(_VECTORS, rng.randint(1, 3))
    wrong = rng.sample(_SCALARS, 6 - len(right))
    names = right + wrong
    rng.shuffle(names)
    text = f"Какие из величин являются векторными: {', '.join(n.lower() for n in names)}?"
    expl = (f"Векторная величина имеет числовое значение и направление. Векторные здесь: "
            f"{', '.join(r.lower() for r in right)}. Остальные — скаляры, у них есть только значение.")
    return multiple(rng, text, right, wrong, expl)


_SI_BASE = ["Метр", "Килограмм", "Секунда", "Ампер", "Кельвин", "Моль", "Кандела"]
_SI_DERIVED = ["Ньютон", "Джоуль", "Ватт", "Паскаль", "Вольт", "Ом", "Герц", "Кулон", "Тесла"]


def si_base_multiple(rng):
    right = rng.sample(_SI_BASE, rng.randint(1, 3))
    wrong = rng.sample(_SI_DERIVED, 6 - len(right))
    names = right + wrong
    rng.shuffle(names)
    text = f"Какие из единиц являются основными единицами СИ: {', '.join(names)}?"
    expl = ("В СИ семь основных единиц: метр, килограмм, секунда, ампер, кельвин, моль и кандела. "
            "Остальные единицы производные — они выражаются через основные (например, 1 Н = 1 кг·м/с²).")
    return multiple(rng, text, right, wrong, expl)


def bigger_force_multiple(rng):
    target = rng.randint(50, 500)
    masses = rng.sample(range(1, 80), 6)
    forces = {m: m * G for m in masses}
    right = [m for m in masses if forces[m] > target]
    if not 1 <= len(right) <= 3:
        raise SkipQuestion
    wrong = [m for m in masses if forces[m] <= target]
    text = f"На какие тела сила тяжести действует больше чем {target} Н (g = 10 м/с²)? Массы тел: " + \
           ", ".join(f"{m} кг" for m in masses) + "."
    expl = (f"Сила тяжести F = m·g. Нужно m·10 > {target}, то есть m > {num(target / G)} кг. "
            f"Подходят: {', '.join(f'{m} кг' for m in sorted(right))}.")
    return multiple(rng, text, [f"{m} кг" for m in right], [f"{m} кг" for m in wrong], expl)


TEMPLATES = {
    "single": [speed, acceleration, newton_second, momentum, kinetic_energy, potential_energy, work,
               power_mech, pressure, ohm, resistors, electric_power, density, heat, wave, hydrostatic,
               archimedes, spring, free_fall, period],
    "context": [car_context, circuit_context],
    "matching": [units_matching, formulas_matching],
    "multiple": [vectors_multiple, si_base_multiple, bigger_force_multiple],
}
