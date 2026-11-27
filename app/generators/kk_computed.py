"""Расчётные шаблоны на казахском языке: математика, физика, химия, информатика.

Ответы вычисляются в коде, как и в русских шаблонах; тексты — по-казахски, термины —
как в казахских учебниках. Каждый шаблон помечен темой спецификации НЦТ (@topic).
"""

import random
from fractions import Fraction

from app.generators.common import (
    SkipQuestion, matching, multiple, num, number_distractors, single, topic,
)
from app.generators.math_gen import nonzero, poly, sup

def _with_list(rng: random.Random, text: str, right: list[str], wrong: list[str], explanation: str) -> dict:
    """«Выберите все…» с перечнем вариантов в тексте: так тексты разных заданий различаются."""
    names = sorted(right + wrong)
    return multiple(rng, f"{text[:-1]} ({', '.join(names)})?", right, wrong, explanation)


# ── Математика ───────────────────────────────────────────────────────────────


@topic("05")
def m_linear(rng: random.Random) -> dict:
    a = rng.choice([2, 3, 4, 5, 6, 7, 8, 9, -2, -3, -4, -5])
    x = rng.randint(-12, 12)
    b = nonzero(rng, -20, 20)
    eq = f"{poly([(a, 1), (b, 0)])} = {num(a * x + b)}"
    return single(rng, f"{eq} теңдеуін шешіңіз.", num(x),
                  number_distractors(rng, x, [-x, x + 1, (a * x + b + b) / a if (2 * b) % a == 0 else x - 2]),
                  f"{num(b)}-ні оң жаққа шығарып, {num(a)}-ге бөлеміз: x = ({num(a * x + b)} − ({num(b)})) / {num(a)} = {num(x)}.")


@topic("05")
def m_quadratic(rng: random.Random) -> dict:
    r1, r2 = sorted(rng.sample(range(-9, 10), 2))
    if r1 == 0 or r2 == 0:
        raise SkipQuestion
    eq = f"{poly([(1, 2), (-(r1 + r2), 1), (r1 * r2, 0)])} = 0"
    right = f"{num(r1)} және {num(r2)}"
    wrong = [f"{num(-r2)} және {num(-r1)}" if -r2 < -r1 else f"{num(-r1)} және {num(-r2)}",
             f"{num(r1 - 1)} және {num(r2 + 1)}", f"{num(r1)} және {num(-r2)}", f"{num(r1 + 1)} және {num(r2)}"]
    return single(rng, f"{eq} теңдеуінің түбірлерін табыңыз.", right, wrong,
                  f"Виет теоремасы бойынша түбірлердің қосындысы {num(r1 + r2)}, көбейтіндісі {num(r1 * r2)}. "
                  f"Бұл шарттарға {num(r1)} және {num(r2)} сәйкес келеді.")


@topic("02")
def m_log(rng: random.Random) -> dict:
    base = rng.choice([2, 3, 4, 5, 10])
    power = rng.randint(2, 6 if base <= 3 else 4)
    value = base ** power
    sub = str(base).translate(str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉"))
    return single(rng, f"log{sub} {num(value)} мәнін есептеңіз.", num(power),
                  number_distractors(rng, power, [value // base, power + 1, base]),
                  f"{base}{sup(power)} = {num(value)}, сондықтан log{sub} {num(value)} = {power}.")


@topic("02")
def m_power(rng: random.Random) -> dict:
    a = rng.randint(2, 5)
    m, n = rng.randint(2, 6), rng.randint(2, 6)
    return single(rng, f"{a}{sup(m)} · {a}{sup(n)} : {a}{sup(m + n - 2)} өрнегінің мәнін табыңыз.", num(a * a),
                  number_distractors(rng, a * a, [2 * a, a ** 3, a]),
                  f"Негіздері бірдей дәрежелерді көбейткенде көрсеткіштер қосылады, бөлгенде азаяды: "
                  f"{a}^({m} + {n} − {m + n - 2}) = {a}² = {a * a}.")


@topic("12")
def m_arith(rng: random.Random) -> dict:
    a1, d, n = rng.randint(-5, 10), nonzero(rng, -4, 6), rng.randint(6, 15)
    an = a1 + (n - 1) * d
    total = (a1 + an) * n // 2 if (a1 + an) * n % 2 == 0 else None
    if total is None:
        raise SkipQuestion
    return single(rng, f"a₁ = {num(a1)}, d = {num(d)} болса, арифметикалық прогрессияның алғашқы {n} мүшесінің "
                       f"қосындысын табыңыз.", num(total),
                  number_distractors(rng, total, [an, total + d * n, (a1 + an) * n]),
                  f"aₙ = a₁ + (n − 1)d = {num(an)}. Sₙ = (a₁ + aₙ)·n / 2 = ({num(a1)} + {num(an)})·{n} / 2 = {num(total)}.")


@topic("12")
def m_geom(rng: random.Random) -> dict:
    b1, q, n = rng.randint(1, 5), rng.choice([2, 3, -2]), rng.randint(3, 6)
    bn = b1 * q ** (n - 1)
    return single(rng, f"Геометриялық прогрессия: b₁ = {b1}, q = {num(q)}. b{str(n).translate(str.maketrans('0123456789', '₀₁₂₃₄₅₆₇₈₉'))}-ді табыңыз.",
                  num(bn), number_distractors(rng, bn, [b1 * q ** n, b1 * q * n, -bn]),
                  f"bₙ = b₁·qⁿ⁻¹ = {b1}·({num(q)}){sup(n - 1)} = {num(bn)}.")


@topic("10")
def m_inequality(rng: random.Random) -> dict:
    a = rng.choice([2, 3, 4, 5])
    x0 = rng.randint(-6, 8)
    b = nonzero(rng, -9, 9)
    right = f"x > {num(x0)}"
    wrong = [f"x < {num(x0)}", f"x > {num(x0 + 1)}", f"x > {num(-x0)}" if x0 else f"x ≥ {num(x0)}", f"x ≥ {num(x0 - 1)}"]
    return single(rng, f"{poly([(a, 1), (b, 0)])} > {num(a * x0 + b)} теңсіздігін шешіңіз.", right, wrong,
                  f"{a}x > {num(a * x0)}, оң сан {a}-ге бөлгенде таңба өзгермейді: x > {num(x0)}.")


@topic("13")
def m_derivative(rng: random.Random) -> dict:
    a, b, c = nonzero(rng, -6, 6), nonzero(rng, -9, 9), rng.randint(-9, 9)
    f = poly([(a, 2), (b, 1), (c, 0)])
    right = poly([(2 * a, 1), (b, 0)])
    wrong = [poly([(a, 1), (b, 0)]), poly([(2 * a, 1), (c, 0)]) if c != b else poly([(2 * a, 1)]),
             poly([(2 * a, 2), (b, 1)]), poly([(2 * a, 1), (-b, 0)])]
    return single(rng, f"f(x) = {f} функциясының туындысын табыңыз.", right, wrong,
                  f"(xⁿ)′ = n·xⁿ⁻¹, тұрақтының туындысы нөлге тең: f′(x) = {right}.")


@topic("15")
def m_triangle_area(rng: random.Random) -> dict:
    base, height = rng.randint(3, 20), rng.randint(2, 16)
    if base * height % 2:
        raise SkipQuestion
    area = base * height // 2
    return single(rng, f"Үшбұрыштың табаны {base} см, оған жүргізілген биіктігі {height} см. Үшбұрыштың ауданын табыңыз.",
                  f"{num(area)} см²", number_distractors(rng, area, [base * height, base + height], " см²"),
                  f"S = a·h / 2 = {base}·{height} / 2 = {num(area)} см².")


@topic("16")
def m_cube(rng: random.Random) -> dict:
    a = rng.randint(2, 12)
    return single(rng, f"Қабырғасы {a} см кубтың көлемін табыңыз.", f"{num(a ** 3)} см³",
                  number_distractors(rng, a ** 3, [a * a, 6 * a * a, 3 * a], " см³"),
                  f"Кубтың көлемі V = a³ = {a}³ = {num(a ** 3)} см³.")


@topic("03")
def m_trig(rng: random.Random) -> dict:
    table = [("sin 30°", "1/2"), ("cos 60°", "1/2"), ("sin 90°", "1"), ("cos 0°", "1"), ("tg 45°", "1"),
             ("sin 60°", "√3/2"), ("cos 30°", "√3/2"), ("sin 45°", "√2/2"), ("cos 90°", "0"), ("tg 0°", "0")]
    expr, value = rng.choice(table)
    pool = ["1/2", "√3/2", "√2/2", "1", "0", "√3"]
    return single(rng, f"{expr} неге тең?", value, [v for v in pool if v != value],
                  f"Бұл кестелік мән: {expr} = {value}.")


@topic("05")
def m_context_price(rng: random.Random) -> dict:
    price = rng.choice([2000, 4000, 5000, 6000, 8000, 10000])
    up, down = rng.choice([(10, 10), (20, 20), (25, 20), (20, 25), (50, 50)])
    final = price * (100 + up) * (100 - down) // 10000
    if price * (100 + up) * (100 - down) % 10000:
        raise SkipQuestion
    context = (f"Тауар {num(price)} тг тұрды. Алдымен бағасы {up}%-ға көтерілді, содан кейін жаңа бағадан "
               f"{down}%-ға төмендетілді.")
    return single(rng, f"Екі өзгерістен кейін тауардың бағасы қандай болды ({num(price)} тг, +{up}%, −{down}%)?",
                  f"{num(final)} тг",
                  [f"{num(price)} тг", f"{num(price * (100 + up - down) // 100)} тг", f"{num(final + price // 10)} тг"],
                  f"Көтергеннен кейін: {num(price)}·{num(1 + up / 100)} = {num(price * (100 + up) // 100)} тг. "
                  f"Төмендеткеннен кейін: {num(price * (100 + up) // 100)}·{num(1 - down / 100)} = {num(final)} тг.",
                  context=context)


@topic("13")
def m_context_vertex(rng: random.Random) -> dict:
    h, k = rng.randint(-5, 5), rng.randint(-8, 8)
    b, c = -2 * h, h * h + k
    f = poly([(1, 2), (b, 1), (c, 0)])
    right = f"({num(h)}; {num(k)})"
    wrong = [f"({num(-h)}; {num(k)})", f"({num(h)}; {num(-k)})" if k else f"({num(h)}; 1)",
             f"({num(h)}; {num(c)})" if c != k else f"({num(h + 1)}; {num(k)})", f"({num(k)}; {num(h)})"]
    return single(rng, f"f(x) = {f} параболасы төбесінің координаталарын табыңыз.", right, wrong,
                  f"x₀ = −b / (2a) = {num(h)}, f(x₀) = {num(k)}. Төбесі — {right} нүктесі.",
                  context=f"Функция f(x) = {f} формуласымен берілген. Оның графигі — тармақтары жоғары бағытталған парабола.")


@topic("13")
def m_match_derivative(rng: random.Random) -> dict:
    pool = [("x³", "3x²"), ("sin x", "cos x"), ("cos x", "−sin x"), ("eˣ", "eˣ"), ("x²", "2x"),
            ("ln x", "1/x"), ("√x", "1/(2√x)"), ("x⁴", "4x³")]
    picked = rng.sample(pool, 4)
    (f1, d1), (f2, d2) = picked[0], picked[1]
    return matching(rng, f"Функция мен оның туындысы арасындағы сәйкестікті анықтаңыз: 1) {f1}; 2) {f2}.",
                    [(f"f(x) = {f1}", d1), (f"f(x) = {f2}", d2)], [picked[2][1], picked[3][1]],
                    f"Туындылар кестесі бойынша: ({f1})′ = {d1}, ({f2})′ = {d2}.")


@topic("15")
def m_match_area(rng: random.Random) -> dict:
    pool = [("Радиусы r дөңгелек", "πr²"), ("Қабырғасы a шаршы", "a²"),
            ("Табандары a, b және биіктігі h трапеция", "(a + b)·h / 2"),
            ("Қабырғалары a және b тіктөртбұрыш", "a·b"), ("Табаны a, биіктігі h үшбұрыш", "a·h / 2"),
            ("Табаны a, биіктігі h параллелограмм", "a·h")]
    picked = rng.sample(pool, 4)
    return matching(rng, f"Фигура мен оның ауданының формуласы арасындағы сәйкестікті анықтаңыз: 1) {picked[0][0]}; 2) {picked[1][0]}.",
                    [picked[0], picked[1]], [picked[2][1], picked[3][1]],
                    f"{picked[0][0]}: S = {picked[0][1]}. {picked[1][0]}: S = {picked[1][1]}.")


@topic("01")
def m_multiple_primes(rng: random.Random) -> dict:
    numbers = rng.sample(range(2, 60), 6)
    primes = [n for n in numbers if all(n % d for d in range(2, int(n ** 0.5) + 1))]
    if not 1 <= len(primes) <= 3:
        raise SkipQuestion
    return multiple(rng, f"Барлық жай сандарды таңдаңыз ({', '.join(map(str, sorted(numbers)))}).",
                    [str(p) for p in primes], [str(n) for n in numbers if n not in primes],
                    f"Жай сан тек 1-ге және өзіне бөлінеді. Мұнда жай сандар: {', '.join(map(str, sorted(primes)))}.")


@topic("05")
def m_multiple_abs(rng: random.Random) -> dict:
    a, r = rng.randint(-6, 6), rng.randint(1, 9)
    roots = [a + r, a - r]
    wrong = [-(a + r), -(a - r), a, r, a + r + 1, a - r - 1, r - a]
    wrong = [w for w in dict.fromkeys(wrong) if w not in roots]
    return multiple(rng, f"|{poly([(1, 1), (-a, 0)])}| = {r} теңдеуінің барлық шешімдерін таңдаңыз.",
                    [num(x) for x in roots], [num(x) for x in wrong],
                    f"Модуль ішіндегі өрнек {r}-ге немесе −{r}-ге тең: x = {num(a + r)} немесе x = {num(a - r)}.")


MATH = {
    "single": [m_linear, m_quadratic, m_log, m_power, m_arith, m_geom, m_inequality, m_derivative,
               m_triangle_area, m_cube, m_trig],
    "context": [m_context_price, m_context_vertex],
    "matching": [m_match_derivative, m_match_area],
    "multiple": [m_multiple_primes, m_multiple_abs],
}

# ── Физика ───────────────────────────────────────────────────────────────────


@topic("02")
def p_newton(rng: random.Random) -> dict:
    m, a = rng.randint(2, 50), rng.choice([0.5, 1, 1.5, 2, 2.5, 3, 4, 5])
    f = m * a
    return single(rng, f"Массасы {m} кг дене {num(a)} м/с² үдеумен қозғалады. Тең әсерлі күш неге тең?",
                  f"{num(f)} Н", number_distractors(rng, f, [m / a, m + a, f * 2], " Н"),
                  f"Ньютонның екінші заңы: F = m·a = {m}·{num(a)} = {num(f)} Н.")


@topic("04")
def p_kinetic(rng: random.Random) -> dict:
    m, v = rng.randint(1, 20), rng.randint(1, 12)
    e = Fraction(m * v * v, 2)
    return single(rng, f"{v} м/с жылдамдықпен қозғалатын массасы {m} кг дененің кинетикалық энергиясын табыңыз.",
                  f"{num(e)} Дж", number_distractors(rng, float(e), [m * v * v, m * v, m * v / 2], " Дж"),
                  f"Eₖ = m·v² / 2 = {m}·{v}² / 2 = {num(e)} Дж.")


@topic("04")
def p_potential(rng: random.Random) -> dict:
    m, h = rng.randint(1, 30), rng.randint(2, 50)
    e = m * 10 * h
    return single(rng, f"{h} м биіктіктегі массасы {m} кг дененің потенциалдық энергиясын табыңыз. (g = 10 м/с²)",
                  f"{num(e)} Дж", number_distractors(rng, e, [m * h, e * 10, m * 10 + h], " Дж"),
                  f"Eₚ = m·g·h = {m}·10·{h} = {num(e)} Дж.")


@topic("11")
def p_ohm(rng: random.Random) -> dict:
    r, i = rng.choice([2, 4, 5, 6, 8, 10, 12, 15, 20, 24, 30]), rng.choice([0.5, 1, 1.5, 2, 3, 4])
    u = r * i
    return single(rng, f"Резистордағы кернеу {num(u)} В, ток күші {num(i)} А. Резистордың кедергісі неге тең?",
                  f"{num(r)} Ом", number_distractors(rng, r, [u * i, u + i, i / u if u else 1], " Ом"),
                  f"Ом заңы: R = U / I = {num(u)} / {num(i)} = {num(r)} Ом.")


@topic("01")
def p_speed(rng: random.Random) -> dict:
    v, t = rng.randint(5, 90), rng.randint(2, 12)
    s = v * t
    return single(rng, f"Дене {num(s)} м жолды {t} с ішінде бірқалыпты жүріп өтті. Оның жылдамдығы қандай?",
                  f"{num(v)} м/с", number_distractors(rng, v, [s * t, s - t, v * 2], " м/с"),
                  f"v = s / t = {num(s)} / {t} = {num(v)} м/с.")


@topic("05")
def p_pressure(rng: random.Random) -> dict:
    f, s = rng.choice([100, 200, 300, 500, 600, 800, 1000, 1200]), rng.choice([0.1, 0.2, 0.4, 0.5, 2, 4])
    p = f / s
    return single(rng, f"{num(f)} Н күш {num(s)} м² ауданға перпендикуляр әсер етеді. Ол қандай қысым түсіреді?",
                  f"{num(p)} Па", number_distractors(rng, p, [f * s, f + s, p / 10], " Па"),
                  f"p = F / S = {num(f)} / {num(s)} = {num(p)} Па.")


@topic("04")
def p_power(rng: random.Random) -> dict:
    n, t = rng.choice([20, 50, 100, 150, 200, 300, 500]), rng.randint(2, 20)
    a = n * t
    return single(rng, f"Қозғалтқыш {t} с ішінде {num(a)} Дж жұмыс атқарды. Оның қуаты қандай?",
                  f"{num(n)} Вт", number_distractors(rng, n, [a * t, a - t, n * 2], " Вт"),
                  f"N = A / t = {num(a)} / {t} = {num(n)} Вт.")


@topic("15")
def p_period(rng: random.Random) -> dict:
    nu = rng.choice([2, 4, 5, 10, 20, 25, 50, 100])
    return single(rng, f"Тербеліс жиілігі {nu} Гц. Тербеліс периоды неге тең?", f"{num(1 / nu, 3)} с",
                  number_distractors(rng, 1 / nu, [nu, 2 / nu, 10 / nu], " с", digits=3),
                  f"T = 1 / ν = 1 / {nu} = {num(1 / nu, 3)} с.")


@topic("01")
def p_context_accel(rng: random.Random) -> dict:
    v, t, m = rng.choice([10, 12, 15, 20, 24, 30]), rng.choice([2, 3, 4, 5, 6, 10]), rng.choice([800, 1000, 1200, 1500])
    a = Fraction(v, t)
    return single(rng, f"Үдеу кезіндегі автомобильдің үдеуі неге тең ({v} м/с, {t} с)?", f"{num(a)} м/с²",
                  number_distractors(rng, float(a), [v * t, v / m, float(a) * 2], " м/с²"),
                  f"a = (v − v₀) / t = ({v} − 0) / {t} = {num(a)} м/с². Масса бұл сұраққа қажет емес.",
                  context=f"Массасы {num(m)} кг автомобиль орнынан қозғалып, бірқалыпты үдемелі қозғалыспен "
                          f"{t} с ішінде {v} м/с жылдамдыққа дейін үдейді.")


@topic("11")
def p_context_parallel(rng: random.Random) -> dict:
    r, u = rng.choice([2, 4, 6, 8, 10, 12, 20]), rng.choice([6, 12, 24])
    total = Fraction(r, 2)
    return single(rng, f"Әрқайсысы {r} Ом болатын екі параллель резистордан тұратын бөліктің жалпы кедергісі неге тең?",
                  f"{num(total)} Ом", number_distractors(rng, float(total), [2 * r, r, r * r], " Ом"),
                  f"1/R = 1/{r} + 1/{r}, демек R = {num(total)} Ом — бір резистордың кедергісінің жартысы.",
                  context=f"Кедергісі әрқайсысы {r} Ом болатын екі резистор параллель жалғанып, кернеуі {u} В көзге қосылған.")


@topic("02")
def p_match_units(rng: random.Random) -> dict:
    pool = [("Жұмыс", "Джоуль"), ("Қуат", "Ватт"), ("Күш", "Ньютон"), ("Қысым", "Паскаль"),
            ("Кедергі", "Ом"), ("Жиілік", "Герц"), ("Заряд", "Кулон"), ("Кернеу", "Вольт")]
    picked = rng.sample(pool, 4)
    return matching(rng, f"Физикалық шама мен оның ХБЖ-дағы бірлігі арасындағы сәйкестікті анықтаңыз: 1) {picked[0][0]}; 2) {picked[1][0]}.",
                    [picked[0], picked[1]], [picked[2][1], picked[3][1]],
                    f"{picked[0][0]} — {picked[0][1].lower()}мен, {picked[1][0].lower()} — {picked[1][1].lower()}мен өлшенеді.")


@topic("02")
def p_match_formulas(rng: random.Random) -> dict:
    pool = [("Ньютонның екінші заңы", "F = m·a"), ("Ом заңы", "I = U / R"), ("Кинетикалық энергия", "E = m·v² / 2"),
            ("Қысым", "p = F / S"), ("Қуат", "N = A / t"), ("Тығыздық", "ρ = m / V")]
    picked = rng.sample(pool, 4)
    return matching(rng, f"Физикалық заң немесе шама мен оның формуласы арасындағы сәйкестікті анықтаңыз: 1) {picked[0][0]}; 2) {picked[1][0]}.",
                    [picked[0], picked[1]], [picked[2][1], picked[3][1]],
                    f"{picked[0][0]}: {picked[0][1]}. {picked[1][0]}: {picked[1][1]}.")


@topic("01")
def p_multiple_vectors(rng: random.Random) -> dict:
    vectors = ["Жылдамдық", "Күш", "Үдеу", "Орын ауыстыру", "Импульс"]
    scalars = ["Масса", "Уақыт", "Температура", "Жол", "Энергия", "Көлем"]
    right = rng.sample(vectors, rng.randint(1, 3))
    return _with_list(rng, "Берілген физикалық шамалардың қайсысы векторлық шама болып табылады?", right,
                    rng.sample(scalars, 6 - len(right)),
                    "Векторлық шаманың мәні де, бағыты да болады: " + ", ".join(r.lower() for r in right) + ".")


@topic("22")
def p_multiple_charged(rng: random.Random) -> dict:
    charged = ["Электрон", "Протон", "Позитрон", "Альфа-бөлшек"]
    neutral = ["Нейтрон", "Фотон", "Нейтрино", "Гамма-квант", "Бейтарап атом", "Бейтарап молекула"]
    right = rng.sample(charged, rng.randint(1, 3))
    return _with_list(rng, "Берілген бөлшектердің қайсысының электр заряды бар?", right,
                    rng.sample(neutral, 6 - len(right)),
                    "Зарядталған бөлшектер: " + ", ".join(r.lower() for r in right) + ". Қалғандары электрлік бейтарап.")


PHYSICS = {
    "single": [p_newton, p_kinetic, p_potential, p_ohm, p_speed, p_pressure, p_power, p_period],
    "context": [p_context_accel, p_context_parallel],
    "matching": [p_match_units, p_match_formulas],
    "multiple": [p_multiple_vectors, p_multiple_charged],
}

# ── Химия ────────────────────────────────────────────────────────────────────

# (формула, молярная масса, казахское название)
SUBSTANCES = [("H₂O", 18, "су"), ("CO₂", 44, "көмірқышқыл газы"), ("NaCl", 58.5, "натрий хлориді"),
              ("H₂SO₄", 98, "күкірт қышқылы"), ("NaOH", 40, "натрий гидроксиді"), ("HCl", 36.5, "тұз қышқылы"),
              ("CaCO₃", 100, "кальций карбонаты"), ("O₂", 32, "оттек"), ("CH₄", 16, "метан"),
              ("NH₃", 17, "аммиак"), ("HNO₃", 63, "азот қышқылы"), ("MgO", 40, "магний оксиді")]
ELEMENTS = [("H", 1, "Сутек"), ("He", 2, "Гелий"), ("C", 6, "Көміртек"), ("N", 7, "Азот"), ("O", 8, "Оттек"),
            ("Na", 11, "Натрий"), ("Mg", 12, "Магний"), ("Al", 13, "Алюминий"), ("S", 16, "Күкірт"),
            ("Cl", 17, "Хлор"), ("K", 19, "Калий"), ("Ca", 20, "Кальций"), ("Fe", 26, "Темір"), ("Cu", 29, "Мыс")]


@topic("18")
def c_molar(rng: random.Random) -> dict:
    formula, mass, name = rng.choice(SUBSTANCES)
    return single(rng, f"{name.capitalize()} {formula} молярлық массасы неге тең?", f"{num(mass)} г/моль",
                  number_distractors(rng, mass, [mass + 2, mass - 1, mass * 2], " г/моль"),
                  f"M({formula}) = {num(mass)} г/моль — атомдық массалардың қосындысы.")


@topic("18")
def c_amount(rng: random.Random) -> dict:
    formula, mass, name = rng.choice(SUBSTANCES)
    n = rng.choice([0.5, 1, 2, 3, 4, 5])
    m = mass * n
    return single(rng, f"{num(m)} г {formula} ({name}) құрамында қанша зат мөлшері бар?", f"{num(n)} моль",
                  number_distractors(rng, n, [m * mass, n * 2, n + 1], " моль"),
                  f"n = m / M = {num(m)} / {num(mass)} = {num(n)} моль.")


@topic("01")
def c_protons(rng: random.Random) -> dict:
    symbol, z, name = rng.choice(ELEMENTS)
    return single(rng, f"{name} ({symbol}) атомының ядросында неше протон бар?", str(z),
                  number_distractors(rng, z, [z + 1, z * 2, z - 1]),
                  f"Протондар саны элементтің реттік нөміріне тең: {name.lower()} — {z}-нөмір.")


@topic("18")
def c_volume(rng: random.Random) -> dict:
    n = rng.choice([0.5, 1, 1.5, 2, 3, 4, 5])
    v = round(22.4 * n, 1)
    return single(rng, f"Қалыпты жағдайда кез келген газдың {num(n)} молі қандай көлем алады?", f"{num(v)} л",
                  number_distractors(rng, v, [22.4, v * 2, n], " л"),
                  f"Қ.ж. молярлық көлем 22,4 л/моль: V = {num(n)}·22,4 = {num(v)} л.")


@topic("18")
def c_context_fraction(rng: random.Random) -> dict:
    salt, water = rng.choice([(10, 90), (20, 180), (15, 135), (25, 225), (30, 170), (40, 160), (50, 200)])
    w = Fraction(salt * 100, salt + water)
    if w.denominator != 1:
        raise SkipQuestion
    return single(rng, f"Алынған ерітіндідегі тұздың массалық үлесі қандай ({salt} г тұз, {water} г су)?", f"{num(w)}%",
                  [f"{num(round(salt * 100 / water, 1))}%", f"{num(w * 2)}%", f"{num(w + 5)}%"],
                  f"Ерітіндінің массасы {salt} + {water} = {salt + water} г. ω = {salt} / {salt + water} = {num(w)}%.",
                  context=f"Ерітінді дайындау үшін {water} г суға {salt} г ас тұзы толық ерітілді.")


@topic("18")
def c_context_methane(rng: random.Random) -> dict:
    moles = rng.choice([0.5, 1, 2, 3])
    m_ch4, m_h2o = 16 * moles, 36 * moles
    return single(rng, f"{num(m_ch4)} г метан жанғанда қанша масса су түзіледі?", f"{num(m_h2o)} г",
                  number_distractors(rng, m_h2o, [18 * moles, m_ch4, 72 * moles], " г"),
                  f"n(CH₄) = {num(m_ch4)} / 16 = {num(moles)} моль; теңдеу бойынша n(H₂O) = 2·{num(moles)} моль; "
                  f"m = {num(2 * moles)}·18 = {num(m_h2o)} г.",
                  context="Метанның жануы: CH₄ + 2O₂ → CO₂ + 2H₂O. (Ar(C) = 12, Ar(H) = 1, Ar(O) = 16)")


@topic("02")
def c_match_symbols(rng: random.Random) -> dict:
    picked = rng.sample(ELEMENTS, 4)
    return matching(rng, f"Химиялық элемент пен оның таңбасы арасындағы сәйкестікті анықтаңыз: 1) {picked[0][2]}; 2) {picked[1][2]}.",
                    [(picked[0][2], picked[0][0]), (picked[1][2], picked[1][0])], [picked[2][0], picked[3][0]],
                    f"{picked[0][2]} — {picked[0][0]}, {picked[1][2].lower()} — {picked[1][0]}.")


@topic("06")
def c_match_classes(rng: random.Random) -> dict:
    pool = [("NaOH", "Негіз"), ("KOH", "Негіз"), ("HCl", "Қышқыл"), ("H₂SO₄", "Қышқыл"), ("NaCl", "Тұз"),
            ("K₂SO₄", "Тұз"), ("CaO", "Оксид"), ("CO₂", "Оксид")]
    first = rng.choice(pool)
    second = rng.choice([p for p in pool if p[1] != first[1]])
    rest = [c for c in ("Негіз", "Қышқыл", "Тұз", "Оксид") if c not in (first[1], second[1])]
    return matching(rng, f"Зат пен бейорганикалық қосылыстар класы арасындағы сәйкестікті анықтаңыз: 1) {first[0]}; 2) {second[0]}.",
                    [first, second], rest,
                    f"{first[0]} — {first[1].lower()}, {second[0]} — {second[1].lower()}.")


@topic("06")
def c_multiple_metals(rng: random.Random) -> dict:
    metals = ["Натрий", "Мыс", "Алюминий", "Темір", "Магний", "Калий"]
    nonmetals = ["Күкірт", "Азот", "Фосфор", "Хлор", "Оттек", "Көміртек"]
    right = rng.sample(metals, rng.randint(1, 3))
    return _with_list(rng, "Берілген элементтердің қайсысы металдар?", right, rng.sample(nonmetals, 6 - len(right)),
                    "Металдар: " + ", ".join(r.lower() for r in right) + ". Қалғандары — бейметалдар.")


@topic("06")
def c_multiple_acids(rng: random.Random) -> dict:
    acids = ["HNO₃", "H₂SO₄", "H₃PO₄", "HCl", "H₂CO₃"]
    others = ["NaCl", "KOH", "CaO", "NaOH", "K₂SO₄", "MgO"]
    right = rng.sample(acids, rng.randint(1, 3))
    return _with_list(rng, "Берілген заттардың қайсысы қышқылдар?", right, rng.sample(others, 6 - len(right)),
                    "Қышқылдар: " + ", ".join(right) + " — оларда сутек пен қышқыл қалдығы бар.")


CHEMISTRY = {
    "single": [c_molar, c_amount, c_protons, c_volume],
    "context": [c_context_fraction, c_context_methane],
    "matching": [c_match_symbols, c_match_classes],
    "multiple": [c_multiple_metals, c_multiple_acids],
}

# ── Информатика ──────────────────────────────────────────────────────────────


@topic("04")
def i_bin_to_dec(rng: random.Random) -> dict:
    value = rng.randint(5, 255)
    binary = bin(value)[2:]
    sub = "₂"
    return single(rng, f"{binary}{sub} екілік санын ондық санау жүйесіне аударыңыз.", str(value),
                  number_distractors(rng, value, [int(binary[::-1], 2), value + 1, int(binary) % 1000]),
                  f"Екінің дәрежелері бойынша жіктегенде {binary}{sub} = {value}.")


@topic("04")
def i_dec_to_bin(rng: random.Random) -> dict:
    value = rng.randint(5, 127)
    right = bin(value)[2:] + "₂"
    wrong = [bin(value + d)[2:] + "₂" for d in (1, -1, 2, 4) if value + d > 0]
    return single(rng, f"{value} ондық санын екілік санау жүйесіне аударыңыз.", right, wrong,
                  f"{value} санын 2-ге қалдықпен бөліп, қалдықтарды кері тәртіппен жазамыз: {right}.")


@topic("04")
def i_hex(rng: random.Random) -> dict:
    value = rng.randint(17, 255)
    hexa = format(value, "X") + "₁₆"
    return single(rng, f"{hexa} он алтылық санын ондық санау жүйесіне аударыңыз.", str(value),
                  number_distractors(rng, value, [value + 16, value - 1, int(format(value, 'X'), 10)
                                                  if format(value, 'X').isdigit() else value + 2]),
                  f"{hexa} = {value // 16}·16 + {value % 16} = {value}.")


@topic("03")
def i_units(rng: random.Random) -> dict:
    k = rng.randint(1, 16)
    return single(rng, f"{k} Кбайтта неше байт бар?", num(k * 1024),
                  number_distractors(rng, k * 1024, [k * 1000, k * 8, k * 1024 * 8]),
                  f"1 Кбайт = 1024 байт, сондықтан {k} Кбайт = {num(k * 1024)} байт.")


@topic("06")
def i_python_div(rng: random.Random) -> dict:
    a, b = rng.randint(7, 60), rng.randint(2, 9)
    op = rng.choice(["//", "%"])
    value = a // b if op == "//" else a % b
    return single(rng, f"Python тіліндегі print({a} {op} {b}) командасы не шығарады?", str(value),
                  number_distractors(rng, value, [a % b if op == "//" else a // b, value + 1, round(a / b)]),
                  f"{'// — бүтін бөлу' if op == '//' else '% — бөлудің қалдығы'}: {a} {op} {b} = {value}.")


@topic("05")
def i_logic(rng: random.Random) -> dict:
    a, b = rng.choice([True, False]), rng.choice([True, False])
    op = rng.choice(["and", "or"])
    value = (a and b) if op == "and" else (a or b)
    return single(rng, f"A = {a}, B = {b} болса, «A {op} B» өрнегінің мәні қандай?", str(value),
                  [str(not value), "None", "0" if value else "1"],
                  f"{'and (ЖӘНЕ) екеуі де ақиқат болғанда ғана True' if op == 'and' else 'or (НЕМЕСЕ) кем дегенде біреуі ақиқат болса True'}: "
                  f"{a} {op} {b} = {value}.")


@topic("06")
def i_context_loop(rng: random.Random) -> dict:
    start, stop = rng.randint(0, 3), rng.randint(5, 9)
    total = sum(range(start, stop))
    program = f"s = 0\nfor i in range({start}, {stop}):\n    s += i\nprint(s)"
    return single(rng, f"for i in range({start}, {stop}) циклі бар бағдарлама не шығарады?", str(total),
                  number_distractors(rng, total, [total + stop, total - start, sum(range(start, stop + 1))]),
                  f"range({start}, {stop}) оң жақ шекарасыз: {', '.join(map(str, range(start, stop)))}. "
                  f"Қосындысы {total}.", context=f"Python тіліндегі бағдарлама берілген:\n{program}")


@topic("06")
def i_context_list(rng: random.Random) -> dict:
    items = rng.sample(range(1, 20), 5)
    index = rng.randint(0, 4)
    return single(rng, f"Бағдарлама a[{index}] элементін шығарады. Ол қандай?", str(items[index]),
                  [str(x) for x in items if x != items[index]],
                  f"Python-да тізім индекстері 0-ден басталады, сондықтан a[{index}] = {items[index]}.",
                  context=f"Python тіліндегі бағдарлама берілген:\na = {items}\nprint(a[{index}])")


@topic("01")
def i_match_devices(rng: random.Random) -> dict:
    pool = [("Принтер", "Шығару құрылғысы"), ("Монитор", "Шығару құрылғысы"), ("Пернетақта", "Енгізу құрылғысы"),
            ("Сканер", "Енгізу құрылғысы"), ("Қатты диск", "Деректерді сақтау құрылғысы"),
            ("Маршрутизатор", "Желілік жабдық")]
    first = rng.choice(pool)
    second = rng.choice([p for p in pool if p[1] != first[1]])
    rest = [k for k in ("Шығару құрылғысы", "Енгізу құрылғысы", "Деректерді сақтау құрылғысы", "Желілік жабдық")
            if k not in (first[1], second[1])]
    return matching(rng, f"Құрылғы мен оның түрі арасындағы сәйкестікті анықтаңыз: 1) {first[0]}; 2) {second[0]}.",
                    [first, second], rest,
                    f"{first[0]} — {first[1].lower()}, {second[0].lower()} — {second[1].lower()}.")


@topic("04")
def i_match_binary(rng: random.Random) -> dict:
    values = rng.sample(range(3, 32), 4)
    return matching(rng, f"Екілік сан мен оның ондық мәні арасындағы сәйкестікті анықтаңыз: 1) {bin(values[0])[2:]}₂; 2) {bin(values[1])[2:]}₂.",
                    [(bin(values[0])[2:] + "₂", str(values[0])), (bin(values[1])[2:] + "₂", str(values[1]))],
                    [str(values[2]), str(values[3])],
                    f"{bin(values[0])[2:]}₂ = {values[0]}, {bin(values[1])[2:]}₂ = {values[1]}.")


@topic("08")
def i_multiple_languages(rng: random.Random) -> dict:
    languages = ["Python", "Java", "C++", "Pascal", "JavaScript"]
    others = ["Excel", "Windows", "Chrome", "Word", "Linux", "Photoshop"]
    right = rng.sample(languages, rng.randint(1, 3))
    return _with_list(rng, "Берілгендердің қайсысы бағдарламалау тілдері?", right, rng.sample(others, 6 - len(right)),
                    "Бағдарламалау тілдері: " + ", ".join(right) + ". Қалғандары — бағдарламалар мен жүйелер.")


@topic("04")
def i_multiple_even(rng: random.Random) -> dict:
    numbers = rng.sample(range(3, 64), 6)
    even = [n for n in numbers if n % 2 == 0]
    if not 1 <= len(even) <= 3:
        raise SkipQuestion
    return multiple(rng, "Екілік жазбасы 0-ге аяқталатын сандарды таңдаңыз: " + ", ".join(map(str, numbers)) + ".",
                    [str(n) for n in even], [str(n) for n in numbers if n not in even],
                    "Екілік жазбасы 0-ге аяқталатын сандар — жұп сандар: " + ", ".join(map(str, even)) + ".")


INFORMATICS = {
    "single": [i_bin_to_dec, i_dec_to_bin, i_hex, i_units, i_python_div, i_logic],
    "context": [i_context_loop, i_context_list],
    "matching": [i_match_devices, i_match_binary],
    "multiple": [i_multiple_languages, i_multiple_even],
}

# ── Математикалық сауаттылық ─────────────────────────────────────────────────


@topic("03")
def ml_discount(rng: random.Random) -> dict:
    price = rng.choice([4000, 6000, 8000, 12000, 15000, 20000, 24000, 30000])
    percent = rng.choice([10, 15, 20, 25, 30, 40, 50])
    final = price * (100 - percent) // 100
    return single(rng, f"Тауар {num(price)} тг тұрады. Дүкенде {percent}% жеңілдік бар. Жеңілдікпен тауар қанша тұрады?",
                  f"{num(final)} тг", [f"{num(price - final)} тг", f"{num(price - percent * 10)} тг",
                                       f"{num(price * (100 + percent) // 100)} тг"],
                  f"Жеңілдік: {num(price)}·{percent} / 100 = {num(price - final)} тг. Баға: {num(price)} − {num(price - final)} = {num(final)} тг.")


@topic("02")
def ml_speed(rng: random.Random) -> dict:
    speed, hours = rng.choice([40, 50, 60, 70, 80, 90]), rng.choice([2, 3, 4, 5])
    distance = speed * hours
    return single(rng, f"Автобус {num(distance)} км жолды {hours} сағатта жүріп өтті. Оның орташа жылдамдығы қандай?",
                  f"{speed} км/сағ", number_distractors(rng, speed, [distance * hours, distance - hours, speed + 10], " км/сағ"),
                  f"v = s / t = {num(distance)} / {hours} = {speed} км/сағ.")


@topic("04")
def ml_average(rng: random.Random) -> dict:
    values = [rng.randint(2, 20) for _ in range(5)]
    total = sum(values)
    if total % 5:
        raise SkipQuestion
    mean = total // 5
    listed = ", ".join(map(str, values))
    return single(rng, f"{listed} сандарының арифметикалық ортасын табыңыз.", str(mean),
                  number_distractors(rng, mean, [total, sorted(values)[2], max(values) - min(values)]),
                  f"Қосындысы {total}, сандар саны 5: {total} / 5 = {mean}.")


@topic("09")
def ml_floor(rng: random.Random) -> dict:
    a, b, pack = rng.randint(3, 8), rng.randint(3, 7), rng.choice([2, 3, 4])
    area = a * b
    if area % pack:
        raise SkipQuestion
    return single(rng, f"Өлшемі {a} м × {b} м бөлменің еденіне ламинат төселеді. Бір қорапта {pack} м² бар. Неше қорап керек?",
                  str(area // pack), number_distractors(rng, area // pack, [area, area * pack, 2 * (a + b) // pack]),
                  f"Еденнің ауданы {a}·{b} = {area} м², қораптар саны {area} / {pack} = {area // pack}.")


@topic("05")
def ml_probability(rng: random.Random) -> dict:
    red, blue, green = rng.randint(1, 6), rng.randint(1, 6), rng.randint(1, 6)
    total = red + blue + green
    p = Fraction(red, total)
    return single(rng, f"Қапта {red} қызыл, {blue} көк және {green} жасыл шар бар. Кездейсоқ қызыл шар алу ықтималдығы қандай?",
                  num(p), [num(Fraction(red, blue + green)), num(Fraction(blue, total)) if blue != red else num(Fraction(1, total)),
                           num(Fraction(green, total)) if green != red else num(Fraction(red + 1, total + 1))],
                  f"Барлық шар {total}, қызылы {red}: P = {red}/{total}" + (f" = {num(p)}." if p.denominator != total else "."))


MATH_LITERACY = {"single": [ml_discount, ml_speed, ml_average, ml_floor, ml_probability]}
