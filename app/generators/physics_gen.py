"""Шаблоны задач по физике. Ускорение свободного падения g = 10 м/с², как принято в задачах ЕНТ."""

import random

from app.generators.common import (
    SkipQuestion, matching, multiple, num, number_distractors, plural, single, topic,
)

G = 10


def _q(rng, text, value, unit, wrong, expl, context=""):
    """Числовой вопрос с единицей измерения."""
    return single(rng, text, f"{num(value)} {unit}",
                  number_distractors(rng, value, wrong, f" {unit}"), expl, context=context)


# ── Один ответ ───────────────────────────────────────────────────────────────

@topic("01")
def speed(rng):
    v, t = rng.randint(2, 40), rng.randint(2, 60)
    s = v * t
    return _q(rng, f"Тело прошло {s} м за {t} с, двигаясь равномерно. Найдите скорость тела.", v, "м/с",
              [s * t, s - t, v * 2, s / 10],
              f"При равномерном движении v = s / t = {s} / {t} = {v} м/с.")


@topic("01")
def acceleration(rng):
    v0, a, t = rng.randint(0, 20), rng.randint(1, 6), rng.randint(2, 12)
    v = v0 + a * t
    return _q(rng, f"Скорость тела за {t} с изменилась с {v0} м/с до {v} м/с. Найдите ускорение.", a, "м/с²",
              [v / t, (v + v0) / t, v - v0, a * 2],
              f"Ускорение a = (v − v₀) / t = ({v} − {v0}) / {t} = {a} м/с².")


@topic("02")
def newton_second(rng):
    m, a = rng.randint(2, 500), rng.randint(1, 10)
    f = m * a
    return _q(rng, f"Какая сила сообщает телу массой {m} кг ускорение {a} м/с²?", f, "Н",
              [m + a, m / a, f * G, f / 2],
              f"По второму закону Ньютона F = m·a = {m}·{a} = {f} Н.")


@topic("04")
def momentum(rng):
    m, v = rng.randint(1, 80), rng.randint(2, 30)
    return _q(rng, f"Найдите импульс тела массой {m} кг, движущегося со скоростью {v} м/с.", m * v, "кг·м/с",
              [m * v * v / 2, m + v, m * v * 2, m * v / 2],
              f"Импульс p = m·v = {m}·{v} = {m * v} кг·м/с.")


@topic("04")
def kinetic_energy(rng):
    m, v = rng.randint(1, 50), rng.randint(2, 20)
    e = m * v * v / 2
    return _q(rng, f"Найдите кинетическую энергию тела массой {m} кг, движущегося со скоростью {v} м/с.", e, "Дж",
              [m * v, m * v * v, m * v / 2, e / 2],
              f"Кинетическая энергия Eₖ = m·v² / 2 = {m}·{v}² / 2 = {num(e)} Дж.")


@topic("04")
def potential_energy(rng):
    m, h = rng.randint(1, 100), rng.randint(2, 50)
    e = m * G * h
    return _q(rng, f"Тело массой {m} кг подняли на высоту {h} м. На сколько увеличилась его потенциальная энергия? (g = 10 м/с²)",
              e, "Дж", [m * h, e / 2, m * G + h, e * 2],
              f"Потенциальная энергия Eₚ = m·g·h = {m}·10·{h} = {e} Дж.")


@topic("04")
def work(rng):
    f, s = rng.randint(5, 500), rng.randint(2, 100)
    return _q(rng, f"Сила {f} Н перемещает тело на {s} м в направлении действия силы. Найдите работу силы.",
              f * s, "Дж", [f + s, f / s, f * s / 2, f * s * 2],
              f"Работа A = F·s = {f}·{s} = {f * s} Дж.")


@topic("04")
def power_mech(rng):
    p, t = rng.randint(10, 2000), rng.randint(2, 60)
    a = p * t
    return _q(rng, f"Двигатель совершил работу {a} Дж за {t} с. Найдите мощность двигателя.", p, "Вт",
              [a * t, a - t, p * 2, p / 2],
              f"Мощность N = A / t = {a} / {t} = {p} Вт.")


@topic("05")
def pressure(rng):
    f = rng.randint(10, 5000)
    s = rng.choice([0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2])
    p = f / s
    if p != int(p):
        raise SkipQuestion
    return _q(rng, f"Сила {f} Н действует перпендикулярно на площадь {num(s)} м². Найдите давление.", p, "Па",
              [f * s, p / 10, p * 2, f],
              f"Давление p = F / S = {f} / {num(s)} = {num(p)} Па.")


@topic("11")
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


@topic("11")
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


@topic("11")
def electric_power(rng):
    u = rng.choice([12, 24, 36, 110, 127, 220])
    i = rng.choice([0.5, 1, 2, 2.5, 3, 4, 5, 10])
    p = u * i
    return _q(rng, f"Прибор работает от напряжения {u} В при силе тока {num(i)} А. Найдите его мощность.", p, "Вт",
              [u / i, u + i, p * 2, p / 2],
              f"Мощность тока P = U·I = {u}·{num(i)} = {num(p)} Вт.")


@topic("05")
def density(rng):
    material, rho = rng.choice([("алюминия", 2700), ("железа", 7800), ("меди", 8900), ("воды", 1000),
                                ("льда", 900), ("свинца", 11300), ("дерева", 600)])
    v = rng.choice([0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 2])
    m = rho * v
    return _q(rng, f"Найдите массу тела из {material} объёмом {num(v, 3)} м³, если плотность {material} {rho} кг/м³.",
              m, "кг", [rho / v, m * 10, m / 10, rho + v],
              f"Масса m = ρ·V = {rho}·{num(v, 3)} = {num(m)} кг.")


@topic("08")
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


@topic("17")
def wave(rng):
    v = rng.choice([340, 1500, 300, 5000, 20, 2])
    f = rng.choice([2, 5, 10, 20, 50, 100, 170, 200, 500])
    lam = v / f
    if lam * 100 != int(lam * 100):
        raise SkipQuestion
    return _q(rng, f"Волна распространяется со скоростью {v} м/с, частота колебаний {f} Гц. Найдите длину волны.",
              lam, "м", [v * f, f / v, lam * 2, lam + 1],
              f"Длина волны λ = v / ν = {v} / {f} = {num(lam)} м.")


@topic("05")
def hydrostatic(rng):
    liquid, rho = rng.choice([("воде", 1000), ("морской воде", 1030), ("керосине", 800), ("ртути", 13600)])
    h = rng.choice([0.5, 1, 2, 3, 5, 10, 20, 50])
    p = rho * G * h
    return _q(rng, f"Найдите давление столба жидкости на глубине {num(h)} м в {liquid} (ρ = {rho} кг/м³, g = 10 м/с²).",
              p, "Па", [rho * h, p / 2, p * 10, rho * G],
              f"Гидростатическое давление p = ρ·g·h = {rho}·10·{num(h)} = {num(p)} Па.")


@topic("05")
def archimedes(rng):
    v = rng.choice([0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.5])
    rho = 1000
    f = rho * G * v
    return _q(rng, f"Тело объёмом {num(v, 3)} м³ полностью погружено в воду (ρ = 1000 кг/м³). Найдите выталкивающую силу.",
              f, "Н", [rho * v, f * 10, f / 2, f + 1],
              f"Сила Архимеда F = ρ·g·V = 1000·10·{num(v, 3)} = {num(f)} Н.")


@topic("02")
def spring(rng):
    k = rng.choice([20, 40, 50, 100, 200, 250, 400, 500, 1000])
    x_cm = rng.choice([1, 2, 3, 4, 5, 8, 10, 15, 20])
    f = k * x_cm / 100
    return _q(rng, f"Жёсткость пружины {k} Н/м. Какая сила растянет её на {x_cm} см?", f, "Н",
              [k * x_cm, k / x_cm, f * 10, f * 2],
              f"По закону Гука F = k·x. Переводим в метры: {x_cm} см = {num(x_cm / 100)} м. "
              f"F = {k}·{num(x_cm / 100)} = {num(f)} Н.")


@topic("01")
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


@topic("15")
def period(rng):
    # Числа подбираются так, чтобы ответ был «круглым»: сначала ответ, потом условие.
    if rng.random() < 0.5:
        per = rng.choice([0.1, 0.2, 0.25, 0.5, 0.8, 1, 1.2, 1.5, 2, 2.5, 3, 4, 5])
        n = rng.randint(5, 100)
        t = round(per * n, 2)
        if t != int(t) or t > 300:
            raise SkipQuestion
        t = int(t)
        return _q(rng, f"Маятник совершил {n} колебаний за {t} с. Найдите период колебаний.", per, "с",
                  [n / t, t * n, per * 2, t - n if t > n else per + 1],
                  f"Период — время одного колебания: T = t / N = {t} / {n} = {num(per)} с.")
    freq = rng.choice([0.5, 1, 1.5, 2, 2.5, 4, 5, 10, 20])
    t = rng.randint(2, 60)
    n = freq * t
    if n != int(n):
        raise SkipQuestion
    n = int(n)
    return _q(rng, f"Тело совершило {n} колебаний за {t} с. Найдите частоту колебаний.", freq, "Гц",
              [t / n, n * t, freq * 2, freq + 1],
              f"Частота — число колебаний за секунду: ν = N / t = {n} / {t} = {num(freq)} Гц.")


# ── По контексту ─────────────────────────────────────────────────────────────

@topic("02")
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


@topic("11")
def circuit_context(rng):
    # Подбираем сопротивления, при которых ток выражается не более чем двумя знаками после запятой.
    for _ in range(50):
        u = rng.choice([6, 9, 12, 24, 36, 220])
        r1, r2 = rng.randint(2, 40), rng.randint(2, 40)
        r = r1 + r2
        i = u / r
        if i * 100 == int(i * 100):
            break
    else:
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


@topic("11")
def units_matching(rng):
    picked = rng.sample(_UNITS, 4)
    pairs, extra = picked[:2], [u for _, u in picked[2:]]
    text = f"Установите соответствие между величиной и её единицей в СИ: 1) {pairs[0][0].lower()}; 2) {pairs[1][0].lower()}."
    expl = f"{pairs[0][0]} измеряется в единицах «{pairs[0][1]}», {pairs[1][0].lower()} — в единицах «{pairs[1][1]}»."
    return matching(rng, text, pairs, extra, expl)


@topic("04")
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


@topic("01")
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


@topic("01")
def si_base_multiple(rng):
    right = rng.sample(_SI_BASE, rng.randint(1, 3))
    wrong = rng.sample(_SI_DERIVED, 6 - len(right))
    names = right + wrong
    rng.shuffle(names)
    text = f"Какие из единиц являются основными единицами СИ: {', '.join(names)}?"
    expl = ("В СИ семь основных единиц: метр, килограмм, секунда, ампер, кельвин, моль и кандела. "
            "Остальные единицы производные — они выражаются через основные (например, 1 Н = 1 кг·м/с²).")
    return multiple(rng, text, right, wrong, expl)


@topic("02")
def bigger_force_multiple(rng):
    masses = rng.sample(range(1, 80), 6)
    forces = {m: m * G for m in masses}
    # Порог выбирается между массами так, чтобы подходило от 1 до 3 тел.
    heavy = sorted(masses, reverse=True)
    k = rng.randint(1, 3)
    target = rng.randint(heavy[k] * G, heavy[k - 1] * G - 1)
    right = [m for m in masses if forces[m] > target]
    wrong = [m for m in masses if forces[m] <= target]
    text = f"На какие тела сила тяжести действует больше чем {target} Н (g = 10 м/с²)? Массы тел: " + \
           ", ".join(f"{m} кг" for m in masses) + "."
    expl = (f"Сила тяжести F = m·g. Нужно m·10 > {target}, то есть m > {num(target / G)} кг. "
            f"Подходят: {', '.join(f'{m} кг' for m in sorted(right))}.")
    return multiple(rng, text, [f"{m} кг" for m in right], [f"{m} кг" for m in wrong], expl)


# ── Темы спецификации НЦТ, которых не было в банке ───────────────────────────

@topic("03")
def lever(rng: random.Random) -> dict:
    l1 = rng.randrange(10, 101, 10)
    l2 = rng.randrange(10, 101, 10)
    f2 = rng.randrange(10, 201, 10)
    if (f2 * l2) % l1 or l1 == l2:
        raise SkipQuestion
    f1 = f2 * l2 // l1
    text = (f"Рычаг находится в равновесии. На плечо длиной {l2} см действует сила {f2} Н. "
            f"Какая сила действует на другое плечо длиной {l1} см?")
    explanation = (f"Условие равновесия рычага (правило моментов): F₁l₁ = F₂l₂, "
                   f"F₁ = F₂l₂ / l₁ = {f2}·{l2} / {l1} = {num(f1)} Н.")
    return single(rng, text, f"{num(f1)} Н",
                  number_distractors(rng, f1, [f2 * l1 / l2, f2, f2 * l2], " Н"), explanation)


_GASES = [("кислорода O₂", 32), ("азота N₂", 28), ("углекислого газа CO₂", 44), ("гелия He", 4),
          ("водорода H₂", 2), ("метана CH₄", 16)]


@topic("06")
def amount_of_gas(rng: random.Random) -> dict:
    name, molar = rng.choice(_GASES)
    nu = rng.randint(2, 12)
    mass = nu * molar
    text = f"Сколько молей вещества содержится в {mass} г {name} (M = {molar} г/моль)?"
    explanation = f"ν = m / M = {mass} / {molar} = {nu} моль."
    return single(rng, text, f"{nu} моль",
                  number_distractors(rng, nu, [mass * molar, nu * 2, nu + 1], " моль"), explanation)


@topic("07")
def gas_law(rng: random.Random) -> dict:
    if rng.random() < 0.5:
        p1, v1, v2 = rng.randrange(100, 501, 50), rng.randint(2, 20), rng.randint(2, 20)
        if (p1 * v1) % v2 or v1 == v2:
            raise SkipQuestion
        p2 = p1 * v1 // v2
        text = (f"Газ при постоянной температуре сжали (или расширили) от {v1} л до {v2} л. "
                f"Начальное давление {p1} кПа. Каким стало давление?")
        explanation = (f"Изотермический процесс (закон Бойля — Мариотта): p₁V₁ = p₂V₂, "
                       f"p₂ = {p1}·{v1} / {v2} = {num(p2)} кПа.")
        return single(rng, text, f"{num(p2)} кПа",
                      number_distractors(rng, p2, [p1 * v2 / v1, p1, p1 * v1], " кПа"), explanation)
    t1 = rng.choice([200, 250, 300, 400])
    v1 = rng.randint(2, 12)
    t2 = rng.choice([t for t in (200, 250, 300, 400, 500, 600) if t != t1])
    if (v1 * t2) % t1:
        raise SkipQuestion
    v2 = v1 * t2 // t1
    text = (f"Газ при постоянном давлении нагрели (или охладили) от {t1} К до {t2} К. "
            f"Начальный объём {v1} л. Каким стал объём?")
    explanation = (f"Изобарный процесс (закон Гей-Люссака): V₁/T₁ = V₂/T₂, "
                   f"V₂ = {v1}·{t2} / {t1} = {num(v2)} л.")
    return single(rng, text, f"{num(v2)} л", number_distractors(rng, v2, [v1 * t1 / t2, v1, v1 + 1], " л"),
                  explanation)


@topic("09")
def mechanical_stress(rng: random.Random) -> dict:
    force = rng.randint(1, 40)       # кН
    area = rng.choice([1, 2, 4, 5])  # см²
    if (force * 10) % area:
        raise SkipQuestion
    sigma = force * 10 // area       # МПа: 1 кН / 1 см² = 10 МПа
    text = (f"Стержень с площадью поперечного сечения {area} см² растягивают силой {force} кН. "
            "Каково механическое напряжение в стержне?")
    explanation = (f"σ = F / S = {force}·10³ Н / ({area}·10⁻⁴ м²) = {num(sigma)}·10⁶ Па = {num(sigma)} МПа.")
    return single(rng, text, f"{num(sigma)} МПа",
                  number_distractors(rng, sigma, [force / area, force * area, sigma * 10], " МПа"), explanation)


@topic("10")
def capacitor(rng: random.Random) -> dict:
    c = rng.choice([2, 4, 5, 10, 20, 50])   # мкФ
    u = rng.randrange(10, 201, 10)          # В
    if rng.random() < 0.5:
        q = c * u
        return single(rng, f"Конденсатор ёмкостью {c} мкФ зарядили до напряжения {u} В. Каков его заряд?",
                      f"{num(q)} мкКл", number_distractors(rng, q, [u / c, c + u, q * 2], " мкКл"),
                      f"q = CU = {c} мкФ · {u} В = {num(q)} мкКл.")
    w = c * u * u // 2
    return single(rng, f"Конденсатор ёмкостью {c} мкФ заряжен до напряжения {u} В. Какова энергия его "
                       "электрического поля?", f"{num(w)} мкДж",
                  number_distractors(rng, w, [c * u * u, c * u, c * u // 2], " мкДж"),
                  f"W = CU²/2 = {c}·{u}² / 2 = {num(w)} мкДж.")


@topic("12")
def electrolysis(rng: random.Random) -> dict:
    current = rng.randint(1, 10)
    minutes = rng.choice([5, 10, 15, 20, 25, 30])
    charge = current * minutes * 60
    mass = round(1.12 * charge)
    text = (f"Через раствор соли серебра {minutes} мин пропускали ток {current} А. Какая масса серебра "
            "выделилась на катоде? Электрохимический эквивалент серебра k = 1,12 мг/Кл.")
    explanation = (f"Закон электролиза Фарадея: m = kIt = 1,12 мг/Кл · {current} А · {minutes * 60} с = "
                   f"{num(mass)} мг.")
    return single(rng, text, f"{num(mass)} мг",
                  number_distractors(rng, mass, [round(1.12 * current * minutes), charge, mass * 2], " мг"),
                  explanation)


@topic("13")
def ampere_force(rng: random.Random) -> dict:
    b = rng.choice([0.2, 0.5, 1, 2])
    current = rng.randint(1, 20)
    length = rng.choice([0.1, 0.2, 0.5, 1])
    force = round(b * current * length, 2)
    text = (f"Проводник длиной {num(length)} м с током {current} А расположен перпендикулярно линиям "
            f"однородного магнитного поля с индукцией {num(b)} Тл. С какой силой поле действует на проводник?")
    explanation = (f"Сила Ампера F = BIl·sin 90° = {num(b)}·{current}·{num(length)} = {num(force)} Н.")
    return single(rng, text, f"{num(force)} Н",
                  number_distractors(rng, force, [b * current, current * length, force * 2], " Н"), explanation)


@topic("14")
def induction_emf(rng: random.Random) -> dict:
    turns = rng.choice([1, 10, 20, 50, 100])
    dt = rng.choice([1, 2, 4, 5, 10])                  # мс
    dphi = dt * rng.randint(1, 20)                     # мВб
    emf = turns * dphi // dt
    text = (f"Магнитный поток через катушку из {turns} {plural(turns, 'витка', 'витков', 'витков')} "
            f"равномерно изменился на {dphi} мВб за {dt} мс. Какая ЭДС индукции возникла в катушке?")
    explanation = (f"Закон электромагнитной индукции: ε = N·ΔΦ/Δt = {turns}·{dphi} мВб / {dt} мс = {num(emf)} В.")
    return single(rng, text, f"{num(emf)} В",
                  number_distractors(rng, emf, [dphi // dt, turns * dphi, emf * 2], " В"), explanation)


@topic("16")
def transformer(rng: random.Random) -> dict:
    n1 = rng.choice([100, 200, 400, 500, 1000, 2000])
    n2 = rng.choice([50, 100, 200, 500, 1000, 4000])
    u1 = rng.choice([12, 24, 36, 120, 220, 380])
    if (u1 * n2) % n1 or n1 == n2:
        raise SkipQuestion
    u2 = u1 * n2 // n1
    text = (f"Первичная обмотка трансформатора содержит {n1} витков, вторичная — {n2} витков. "
            f"На первичную обмотку подано {u1} В. Каково напряжение на вторичной обмотке?")
    explanation = f"U₁/U₂ = N₁/N₂, поэтому U₂ = U₁·N₂/N₁ = {u1}·{n2}/{n1} = {num(u2)} В."
    return single(rng, text, f"{num(u2)} В",
                  number_distractors(rng, u2, [u1 * n1 / n2, u1, u2 * 2], " В"), explanation)


@topic("18")
def radio_wavelength(rng: random.Random) -> dict:
    freq = rng.choice([1, 2, 3, 5, 6, 10, 12, 15, 20, 25, 30, 50, 60, 75, 100, 150, 300])  # МГц
    length = 300 // freq
    text = f"Радиостанция работает на частоте {freq} МГц. Какова длина излучаемой электромагнитной волны?"
    explanation = (f"λ = c/ν = 3·10⁸ м/с / ({freq}·10⁶ Гц) = {num(length)} м.")
    return single(rng, text, f"{num(length)} м",
                  number_distractors(rng, length, [freq * 3, 3000 // freq, length * 2], " м"), explanation)


@topic("19")
def grating_period(rng: random.Random) -> dict:
    lines = rng.choice([50, 100, 200, 250, 400, 500, 1000])
    period = 1000 / lines
    text = f"Дифракционная решётка имеет {lines} штрихов на 1 мм. Каков её период в микрометрах?"
    explanation = f"Период решётки d = 1 мм / {lines} = {num(period)} мкм (1 мм = 1000 мкм)."
    return single(rng, text, f"{num(period)} мкм",
                  number_distractors(rng, period, [lines / 1000, lines, period * 10], " мкм"), explanation)


@topic("20")
def lens_power(rng: random.Random) -> dict:
    if rng.random() < 0.5:
        focus = rng.choice([10, 20, 25, 40, 50, 100, 200])  # см
        power = 100 / focus
        return single(rng, f"Фокусное расстояние собирающей линзы {focus} см. Какова её оптическая сила?",
                      f"{num(power)} дптр", number_distractors(rng, power, [focus, focus / 100, power * 2], " дптр"),
                      f"D = 1/F, где F в метрах: D = 1 / {num(focus / 100)} м = {num(power)} дптр.")
    n, name = rng.choice([(1.5, "стекле"), (2, "некотором кристалле"), (1.25, "некоторой жидкости"),
                          (2.4, "алмазе")])
    speed = round(300000 / n)
    return single(rng, f"Показатель преломления света в {name} равен {num(n)}. С какой скоростью свет "
                       "распространяется в этой среде (c = 300 000 км/с)?", f"{num(speed)} км/с",
                  number_distractors(rng, speed, [300000 * n, 300000 - speed, speed // 2], " км/с"),
                  f"n = c/v, поэтому v = c/n = 300 000 / {num(n)} = {num(speed)} км/с.")


@topic("21")
def time_dilation(rng: random.Random) -> dict:
    if rng.random() < 0.5:
        t0 = 4 * rng.randint(1, 15)
        t = t0 * 5 // 4
        text = (f"По часам космического корабля, летящего со скоростью 0,6c, прошло {t0} мин. "
                "Сколько времени прошло по часам наблюдателя на Земле?")
        explanation = (f"t = t₀/√(1 − v²/c²) = {t0}/√(1 − 0,36) = {t0}/0,8 = {num(t)} мин.")
    else:
        t0 = 3 * rng.randint(1, 20)
        t = t0 * 5 // 3
        text = (f"По часам космического корабля, летящего со скоростью 0,8c, прошло {t0} мин. "
                "Сколько времени прошло по часам наблюдателя на Земле?")
        explanation = (f"t = t₀/√(1 − v²/c²) = {t0}/√(1 − 0,64) = {t0}/0,6 = {num(t)} мин.")
    return single(rng, text, f"{num(t)} мин", number_distractors(rng, t, [t0, t0 * 0.8, t0 * 2], " мин"),
                  explanation)


@topic("22")
def photoeffect(rng: random.Random) -> dict:
    work = rng.choice([2, 3, 4, 5])
    energy = work + rng.randint(1, 8)
    kinetic = energy - work
    text = (f"На металл с работой выхода {work} эВ падают фотоны с энергией {energy} эВ. "
            "Какова максимальная кинетическая энергия вылетевших электронов?")
    explanation = (f"Уравнение Эйнштейна для фотоэффекта: hν = A + Eк, Eк = {energy} − {work} = {kinetic} эВ.")
    return single(rng, text, f"{kinetic} эВ",
                  number_distractors(rng, kinetic, [energy + work, energy, work], " эВ"), explanation)


_NUCLIDES = [("углерода", "C", 12, 6), ("углерода", "C", 14, 6), ("азота", "N", 14, 7),
             ("кислорода", "O", 16, 8), ("натрия", "Na", 23, 11), ("алюминия", "Al", 27, 13),
             ("железа", "Fe", 56, 26), ("меди", "Cu", 64, 29), ("радия", "Ra", 226, 88),
             ("урана", "U", 235, 92), ("урана", "U", 238, 92), ("свинца", "Pb", 207, 82)]


@topic("23")
def nucleus(rng: random.Random) -> dict:
    if rng.random() < 0.6:
        name, symbol, mass_number, z = rng.choice(_NUCLIDES)
        neutrons = mass_number - z
        return single(rng, f"Сколько нейтронов в ядре изотопа {name} {symbol}-{mass_number} (Z = {z})?",
                      num(neutrons), number_distractors(rng, neutrons, [mass_number, z, mass_number + z]),
                      f"Число нейтронов N = A − Z = {mass_number} − {z} = {neutrons}.")
    half = rng.choice([2, 5, 8, 10, 20])
    periods = rng.randint(1, 4)
    start = 2 ** periods * rng.randint(1, 10)
    left = start // 2 ** periods
    return single(rng, f"Период полураспада изотопа {half} сут. Сколько граммов из {start} г останется "
                       f"через {half * periods} сут?", f"{num(left)} г",
                  number_distractors(rng, left, [start / 2, start - left, start // periods], " г"),
                  f"Прошло {half * periods} / {half} = {periods} "
                  f"{plural(periods, 'период', 'периода', 'периодов')} полураспада, за каждый масса "
                  f"уменьшается вдвое: {start} / 2^{periods} = {start} / {2 ** periods} = {num(left)} г.")


@topic("24")
def nano_units(rng: random.Random) -> dict:
    micro = rng.randint(1, 50)
    nano = micro * 1000
    text = f"Сколько нанометров в {micro} мкм?"
    explanation = (f"1 мкм = 10⁻⁶ м, 1 нм = 10⁻⁹ м, поэтому 1 мкм = 1000 нм и {micro} мкм = {num(nano)} нм. "
                   "Нанотехнологии работают с объектами размером от 1 до 100 нм.")
    return single(rng, text, f"{num(nano)} нм",
                  number_distractors(rng, nano, [micro * 100, micro * 10 ** 6, micro * 10], " нм"), explanation)


@topic("25")
def hubble_law(rng: random.Random) -> dict:
    distance = rng.randrange(10, 501, 10)
    speed = 70 * distance
    text = (f"Галактика находится на расстоянии {distance} Мпк. С какой скоростью она удаляется от нас? "
            "Постоянная Хаббла H = 70 км/(с·Мпк).")
    explanation = f"Закон Хаббла: v = H·r = 70·{distance} = {num(speed)} км/с."
    return single(rng, text, f"{num(speed)} км/с",
                  number_distractors(rng, speed, [distance / 70, 7 * distance, speed * 10], " км/с"), explanation)


TEMPLATES = {
    "single": [speed, acceleration, newton_second, momentum, kinetic_energy, potential_energy, work,
               power_mech, pressure, ohm, resistors, electric_power, density, heat, wave, hydrostatic,
               archimedes, spring, free_fall, period, lever, amount_of_gas, gas_law, mechanical_stress,
               capacitor, electrolysis, ampere_force, induction_emf, transformer, radio_wavelength,
               grating_period, lens_power, time_dilation, photoeffect, nucleus, nano_units, hubble_law],
    "context": [car_context, circuit_context],
    "matching": [units_matching, formulas_matching],
    "multiple": [vectors_multiple, si_base_multiple, bigger_force_multiple],
}
