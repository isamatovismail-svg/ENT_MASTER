"""Шаблоны задач по математике (профильный предмет)."""

import math
import random
from fractions import Fraction

from app.generators.common import (
    SkipQuestion, matching, multiple, num, number_distractors, plural, single, topic,
)

_SUP = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def sup(power: int) -> str:
    """Степень надстрочными цифрами: sup(2) → «²»."""
    return str(power).translate(_SUP)


def term(coef: int, power: int, var: str = "x") -> str:
    """Одночлен без знака: term(3, 2) → «3x²», term(1, 1) → «x»."""
    coef = abs(coef)
    if power == 0:
        return str(coef)
    head = "" if coef == 1 else str(coef)
    return head + var + (sup(power) if power > 1 else "")


def poly(terms: list[tuple[int, int]], var: str = "x") -> str:
    """Многочлен из пар (коэффициент, степень): [(3, 2), (−4, 1), (1, 0)] → «3x² − 4x + 1»."""
    parts: list[str] = []
    for coef, power in terms:
        if coef == 0:
            continue
        body = term(coef, power, var)
        if not parts:
            parts.append(("−" if coef < 0 else "") + body)
        else:
            parts.append(("− " if coef < 0 else "+ ") + body)
    return " ".join(parts) or "0"


def nonzero(rng: random.Random, low: int, high: int) -> int:
    """Случайное целое из [low, high], не равное нулю."""
    while True:
        value = rng.randint(low, high)
        if value:
            return value


@topic("05")
def linear_equation(rng: random.Random) -> dict:
    a = nonzero(rng, -9, 9)
    x = rng.randint(-12, 12)
    b = nonzero(rng, -20, 20)
    c = a * x + b
    eq = f"{poly([(a, 1), (b, 0)])} = {num(c)}"
    if a == 1 or abs(a) == 1:
        raise SkipQuestion
    wrong = [(c + b) / a, -x, x + 1, x - 1, (c - b) * a]
    explanation = (
        f"Переносим {num(b)} в правую часть с противоположным знаком: "
        f"{term(a, 1) if a > 0 else '−' + term(a, 1)} = {num(c)} {'−' if b > 0 else '+'} {num(abs(b))} = {num(c - b)}. "
        f"Делим обе части на {num(a)}: x = {num(x)}. Проверка: {num(a)}·{'(' + num(x) + ')' if x < 0 else num(x)} "
        f"{'+' if b > 0 else '−'} {num(abs(b))} = {num(c)}."
    )
    return single(rng, f"Решите уравнение {eq}.", num(x),
                  number_distractors(rng, x, wrong), explanation)


@topic("05")
def quadratic_roots(rng: random.Random) -> dict:
    p, q = sorted(rng.sample([v for v in range(-9, 10) if v], 2))
    s, prod = p + q, p * q
    eq = poly([(1, 2), (-s, 1), (prod, 0)]) + " = 0"
    answer = f"{num(p)} и {num(q)}"
    wrong = [f"{num(-q)} и {num(-p)}", f"{num(p)} и {num(-q)}", f"{num(-p)} и {num(q)}",
             f"{num(p + 1)} и {num(q - 1)}", f"{num(1)} и {num(prod)}"]
    explanation = (
        f"По теореме Виета сумма корней равна {num(s)}, а произведение равно {num(prod)}. "
        f"Подходят числа {num(p)} и {num(q)}: {num(p)} + {'(' + num(q) + ')' if q < 0 else num(q)} = {num(s)} "
        f"и {num(p)}·{'(' + num(q) + ')' if q < 0 else num(q)} = {num(prod)}."
    )
    return single(rng, f"Найдите корни уравнения {eq}.", answer, wrong, explanation)


@topic("13")
def derivative_at_point(rng: random.Random) -> dict:
    a, b, c = nonzero(rng, -6, 6), nonzero(rng, -9, 9), rng.randint(-9, 9)
    x0 = nonzero(rng, -4, 4)
    value = 2 * a * x0 + b
    f = poly([(a, 2), (b, 1), (c, 0)])
    wrong = [a * x0 * x0 + b * x0 + c, 2 * a * x0, a * x0 + b, 2 * a * x0 - b]
    explanation = (
        f"Производная: f′(x) = {poly([(2 * a, 1), (b, 0)])} (производная x² равна 2x, "
        f"производная константы равна нулю). Подставляем x = {num(x0)}: "
        f"f′({num(x0)}) = {num(2 * a)}·{'(' + num(x0) + ')' if x0 < 0 else num(x0)} "
        f"{'+' if b > 0 else '−'} {num(abs(b))} = {num(value)}."
    )
    return single(rng, f"Найдите значение производной функции f(x) = {f} в точке x = {num(x0)}.",
                  num(value), number_distractors(rng, value, wrong), explanation)


@topic("12")
def arithmetic_nth(rng: random.Random) -> dict:
    a1, d, n = rng.randint(-20, 30), nonzero(rng, -7, 9), rng.randint(6, 40)
    an = a1 + (n - 1) * d
    wrong = [a1 + n * d, a1 + (n - 2) * d, n * d, a1 * n]
    explanation = (
        f"Формула n-го члена арифметической прогрессии: aₙ = a₁ + (n − 1)·d. "
        f"a{_sub(n)} = {num(a1)} + {n - 1}·{'(' + num(d) + ')' if d < 0 else num(d)} = {num(an)}."
    )
    text = (f"В арифметической прогрессии a₁ = {num(a1)}, разность d = {num(d)}. "
            f"Найдите {n}-й член прогрессии.")
    return single(rng, text, num(an), number_distractors(rng, an, wrong), explanation)


@topic("12")
def arithmetic_sum(rng: random.Random) -> dict:
    a1, d, n = rng.randint(-10, 20), nonzero(rng, -5, 8), rng.randint(5, 30)
    an = a1 + (n - 1) * d
    total = (a1 + an) * n // 2 if (a1 + an) * n % 2 == 0 else None
    if total is None:
        raise SkipQuestion
    wrong = [(a1 + an) * n, a1 * n + n * d, (a1 + an + d) * n // 2, total + an]
    explanation = (
        f"Сначала найдём последний член: a{_sub(n)} = {num(a1)} + {n - 1}·{'(' + num(d) + ')' if d < 0 else num(d)} = {num(an)}. "
        f"Сумма: Sₙ = (a₁ + aₙ)·n / 2 = ({num(a1)} + {'(' + num(an) + ')' if an < 0 else num(an)})·{n} / 2 = {num(total)}."
    )
    text = (f"Найдите сумму первых {n} членов арифметической прогрессии, "
            f"если a₁ = {num(a1)}, d = {num(d)}.")
    return single(rng, text, num(total), number_distractors(rng, total, wrong), explanation)


@topic("12")
def geometric_nth(rng: random.Random) -> dict:
    b1 = nonzero(rng, -6, 8)
    q = rng.choice([-3, -2, 2, 3, 4])
    n = rng.randint(3, 7)
    bn = b1 * q ** (n - 1)
    wrong = [b1 * q ** n, b1 * q ** (n - 2), b1 * q * (n - 1), -bn]
    explanation = (
        f"Формула n-го члена геометрической прогрессии: bₙ = b₁·qⁿ⁻¹. "
        f"b{_sub(n)} = {num(b1)}·{'(' + num(q) + ')' if q < 0 else num(q)}{sup(n - 1)} = "
        f"{num(b1)}·{num(q ** (n - 1))} = {num(bn)}."
    )
    text = (f"В геометрической прогрессии b₁ = {num(b1)}, знаменатель q = {num(q)}. "
            f"Найдите b{_sub(n)}.")
    return single(rng, text, num(bn), number_distractors(rng, bn, wrong), explanation)


@topic("02")
def logarithm(rng: random.Random) -> dict:
    base = rng.choice([2, 3, 4, 5, 6, 7, 10])
    k = rng.randint(-3, 6)
    if base ** abs(k) > 100_000 or k == 1:
        raise SkipQuestion
    arg = Fraction(base) ** k
    arg_text = num(arg)
    wrong = [k + 1, k - 1, -k, base * k, k + 2]
    rule = (f"{num(base)}{sup(k)} = {arg_text}" if k >= 0
            else f"{num(base)}{sup(k)} = 1/{num(base)}{sup(-k)} = {arg_text}")
    explanation = (
        f"Логарифм — это показатель степени, в которую нужно возвести основание, чтобы получить число. "
        f"Так как {rule}, то log{_sub(base)} {arg_text} = {num(k)}."
    )
    return single(rng, f"Вычислите log{_sub(base)} {arg_text}.", num(k),
                  number_distractors(rng, k, wrong), explanation)


_SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def _sub(value: int) -> str:
    return str(value).translate(_SUB)


@topic("02")
def power_rules(rng: random.Random) -> dict:
    var = rng.choice(["a", "b", "x", "y", "m"])
    m, n, p = rng.randint(2, 12), rng.randint(2, 12), rng.randint(2, 15)
    result = m + n - p
    if result in (0, 1):
        raise SkipQuestion

    def show(power: int) -> str:
        return f"{var}{sup(power)}"

    wrong = [show(m * n - p), show(m + n + p), show(m * n // max(p, 1)), show(result + 1), show(result - 1)]
    explanation = (
        f"При умножении степеней с одинаковым основанием показатели складываются, "
        f"при делении — вычитаются: {m} + {n} − {p} = {num(result)}. Ответ: {show(result)}."
    )
    text = f"Упростите выражение {show(m)}·{show(n)} : {show(p)}."
    return single(rng, text, show(result), wrong, explanation)


@topic("01")
def percent_of_number(rng: random.Random) -> dict:
    p = rng.choice([5, 10, 12, 15, 20, 25, 30, 35, 40, 45, 60, 75, 80, 120, 150])
    n = rng.randrange(20, 4000, 20)
    if n * p % 100:
        raise SkipQuestion
    value = n * p // 100
    wrong = [n - value, n * p // 10, value * 2, n + value]
    explanation = f"Чтобы найти {p}% от числа, нужно умножить его на {num(p / 100)}: {num(n)}·{num(p / 100)} = {num(value)}."
    return single(rng, f"Найдите {p}% от числа {num(n)}.", num(value),
                  number_distractors(rng, value, wrong), explanation)


@topic("08")
def linear_system(rng: random.Random) -> dict:
    x, y = rng.randint(-9, 9), rng.randint(-9, 9)
    a, b = rng.randint(1, 5), rng.randint(1, 5)
    if x == y or (a, b) == (1, 1):
        raise SkipQuestion
    s1, s2 = a * x + y, x - b * y
    answer = f"({num(x)}; {num(y)})"
    wrong = [f"({num(y)}; {num(x)})", f"({num(x)}; {num(-y)})", f"({num(-x)}; {num(y)})",
             f"({num(x + 1)}; {num(y - 1)})"]
    text = (f"Решите систему уравнений: {poly([(a, 1)])} + y = {num(s1)} и "
            f"x − {term(b, 1, 'y')} = {num(s2)}. Ответ запишите в виде (x; y).")
    explanation = (
        f"Из второго уравнения x = {num(s2)} + {term(b, 1, 'y')}. Подставляем в первое и решаем: y = {num(y)}, "
        f"тогда x = {num(x)}. Проверка: {num(a)}·{'(' + num(x) + ')' if x < 0 else num(x)} + "
        f"{'(' + num(y) + ')' if y < 0 else num(y)} = {num(s1)} и "
        f"{num(x)} − {num(b)}·{'(' + num(y) + ')' if y < 0 else num(y)} = {num(s2)}."
    )
    return single(rng, text, answer, wrong, explanation)


_TRIPLES = [(3, 4, 5), (5, 12, 13), (8, 15, 17), (7, 24, 25), (20, 21, 29), (9, 40, 41)]


@topic("15")
def pythagoras(rng: random.Random) -> dict:
    a, b, c = rng.choice(_TRIPLES)
    k = rng.randint(1, 8)
    a, b, c = a * k, b * k, c * k
    if rng.random() < 0.5:
        text = f"Катеты прямоугольного треугольника равны {a} см и {b} см. Найдите гипотенузу."
        answer, wrong = c, [a + b, c + k, abs(b - a), c - k]
        expl = f"По теореме Пифагора c² = a² + b² = {a * a} + {b * b} = {c * c}, значит c = {c} см."
    else:
        text = f"Гипотенуза прямоугольного треугольника равна {c} см, один из катетов — {a} см. Найдите второй катет."
        answer, wrong = b, [c - a, c + a, b + k, b - k]
        expl = f"По теореме Пифагора b² = c² − a² = {c * c} − {a * a} = {b * b}, значит b = {b} см."
    return single(rng, text, f"{answer} см", number_distractors(rng, answer, wrong, " см"), expl)


@topic("10")
def linear_inequality(rng: random.Random) -> dict:
    a = nonzero(rng, -7, 7)
    k = rng.randint(-10, 10)
    b = nonzero(rng, -15, 15)
    if abs(a) == 1:
        raise SkipQuestion
    sign = rng.choice([">", "<", "≥", "≤"])
    flip = {">": "<", "<": ">", "≥": "≤", "≤": "≥"}
    c = a * k + b
    result_sign = sign if a > 0 else flip[sign]
    answer = f"x {result_sign} {num(k)}"
    wrong = [f"x {flip[result_sign]} {num(k)}", f"x {result_sign} {num(-k)}",
             f"x {flip[result_sign]} {num(-k)}", f"x {result_sign} {num(k + 1)}"]
    note = ("Делим на положительное число, знак неравенства не меняется." if a > 0
            else "Делим на отрицательное число, поэтому знак неравенства меняется на противоположный.")
    explanation = (
        f"Переносим {num(b)} вправо: {'−' if a < 0 else ''}{term(a, 1)} {sign} {num(c - b)}. {note} "
        f"Получаем {answer}."
    )
    text = f"Решите неравенство {poly([(a, 1), (b, 0)])} {sign} {num(c)}."
    return single(rng, text, answer, wrong, explanation)


@topic("01")
def fraction_sum(rng: random.Random) -> dict:
    b, d = rng.randint(2, 12), rng.randint(2, 12)
    a, c = rng.randint(1, b - 1), rng.randint(1, d - 1)
    if b == d or math.gcd(a, b) != 1 or math.gcd(c, d) != 1:
        raise SkipQuestion
    op = rng.choice(["+", "−"])
    result = Fraction(a, b) + Fraction(c, d) if op == "+" else Fraction(a, b) - Fraction(c, d)
    naive = Fraction(a + c, b + d) if op == "+" else Fraction(abs(a - c) or 1, b + d)
    wrong = [num(naive), num(Fraction(a * c, b * d)), num(-result), num(result + Fraction(1, b * d)),
             num(result + Fraction(1, math.lcm(b, d)))]
    lcm = math.lcm(b, d)
    n1, n2 = a * lcm // b, c * lcm // d
    top = n1 + n2 if op == "+" else n1 - n2
    raw = f"{num(top)}/{lcm}"
    tail = "" if Fraction(top, lcm).denominator == lcm else f" = {num(result)}"
    explanation = (
        f"Приводим дроби к общему знаменателю {lcm}: {a}/{b} = {n1}/{lcm}, {c}/{d} = {n2}/{lcm}. "
        f"Тогда {n1}/{lcm} {op} {n2}/{lcm} = {raw}{tail}. "
        "Складывать или вычитать числители и знаменатели по отдельности нельзя."
    )
    return single(rng, f"Вычислите {a}/{b} {op} {c}/{d}.", num(result), wrong, explanation)


@topic("04")
def function_value(rng: random.Random) -> dict:
    a, b, c = nonzero(rng, -5, 5), rng.randint(-9, 9), rng.randint(-12, 12)
    x0 = nonzero(rng, -5, 5)
    value = a * x0 * x0 + b * x0 + c
    f = poly([(a, 2), (b, 1), (c, 0)])
    wrong = [a * x0 * 2 + b * x0 + c, -a * x0 * x0 + b * x0 + c, a * x0 * x0 - b * x0 + c, value + c]
    x_show = f"({num(x0)})" if x0 < 0 else num(x0)
    explanation = (
        f"Подставляем x = {num(x0)} в формулу: f({num(x0)}) = {num(a)}·{x_show}² "
        f"{'+' if b >= 0 else '−'} {num(abs(b))}·{x_show} {'+' if c >= 0 else '−'} {num(abs(c))} = {num(value)}. "
        f"Помните, что квадрат отрицательного числа положителен."
    )
    return single(rng, f"Найдите значение функции f(x) = {f} при x = {num(x0)}.", num(value),
                  number_distractors(rng, value, wrong), explanation)


@topic("15")
def circle_area(rng: random.Random) -> dict:
    r = rng.randint(2, 30)
    if rng.random() < 0.5:
        text = f"Найдите площадь круга радиуса {r} см."
        answer = f"{num(r * r)}π см²"
        wrong = [f"{num(2 * r)}π см²", f"{num(r)}π см²", f"{num(2 * r * r)}π см²", f"{num(r * r)} см²"]
        expl = f"Площадь круга S = πr² = π·{r}² = {num(r * r)}π см². Формула 2πr — это длина окружности, а не площадь."
    else:
        text = f"Найдите длину окружности радиуса {r} см."
        answer = f"{num(2 * r)}π см"
        wrong = [f"{num(r * r)}π см", f"{num(r)}π см", f"{num(4 * r)}π см", f"{num(2 * r)} см"]
        expl = f"Длина окружности C = 2πr = 2·π·{r} = {num(2 * r)}π см."
    return single(rng, text, answer, wrong, expl)


@topic("15")
def triangle_area(rng: random.Random) -> dict:
    a, h = rng.randint(3, 40), rng.randint(2, 30)
    if a * h % 2:
        raise SkipQuestion
    s = a * h // 2
    wrong = [a * h, a + h, s + a, 2 * (a + h)]
    expl = f"Площадь треугольника равна половине произведения стороны на высоту к ней: S = ½·{a}·{h} = {s} см²."
    text = f"Сторона треугольника равна {a} см, а высота, проведённая к ней, — {h} см. Найдите площадь треугольника."
    return single(rng, text, f"{s} см²", number_distractors(rng, s, wrong, " см²"), expl)


@topic("13")
def parabola_vertex(rng: random.Random) -> dict:
    a = rng.choice([-3, -2, -1, 1, 2, 3])
    x0, y0 = rng.randint(-6, 6), rng.randint(-9, 9)
    b, c = -2 * a * x0, a * x0 * x0 + y0
    f = poly([(a, 2), (b, 1), (c, 0)])
    direction = "вверх" if a > 0 else "вниз"
    context = f"Функция задана формулой f(x) = {f}. Её график — парабола, ветви которой направлены {direction}."
    answer = f"({num(x0)}; {num(y0)})"
    wrong = [f"({num(-x0)}; {num(y0)})", f"({num(x0)}; {num(c)})", f"({num(y0)}; {num(x0)})",
             f"({num(-x0)}; {num(a * x0 * x0 + 2 * a * x0 * x0 + c)})", f"({num(x0 + 1)}; {num(y0)})"]
    explanation = (
        f"Абсцисса вершины x₀ = −b / (2a) = {num(-b)} / {'(' + num(2 * a) + ')' if a < 0 else num(2 * a)} = {num(x0)}. "
        f"Подставляем: f({num(x0)}) = {num(y0)}. Вершина — точка {answer}."
    )
    return single(rng, f"Найдите координаты вершины параболы f(x) = {f}.", answer, wrong,
                  explanation, context=context)


@topic("12")
def theater_rows(rng: random.Random) -> dict:
    first, d, n = rng.randint(10, 30), rng.randint(1, 4), rng.randint(8, 25)
    last = first + (n - 1) * d
    total = (first + last) * n // 2 if (first + last) * n % 2 == 0 else None
    seats = plural(first, "место", "места", "мест")
    context = (f"В зрительном зале {n} {plural(n, 'ряд', 'ряда', 'рядов')}. В первом ряду {first} {seats}, "
               f"а в каждом следующем ряду на {d} {plural(d, 'место', 'места', 'мест')} больше, чем в предыдущем.")
    if rng.random() < 0.5 or total is None:
        text = f"Сколько мест в последнем ряду зала, где {n} {plural(n, 'ряд', 'ряда', 'рядов')} и в первом ряду {first} {seats} (+{d} в каждом ряду)?"
        answer, wrong = last, [first + n * d, first + (n - 2) * d, n * d]
        expl = f"Число мест образует арифметическую прогрессию: a{_sub(n)} = {first} + ({n} − 1)·{d} = {last}."
    else:
        text = f"Сколько всего мест в зале, где {n} {plural(n, 'ряд', 'ряда', 'рядов')} и в первом ряду {first} {seats} (+{d} в каждом ряду)?"
        answer, wrong = total, [first * n, last * n, total + last]
        expl = (f"Последний ряд: {first} + ({n} − 1)·{d} = {last}. Сумма арифметической прогрессии: "
                f"({first} + {last})·{n} / 2 = {total}.")
    return single(rng, text, num(answer), number_distractors(rng, answer, wrong), expl, context=context)


@topic("15")
def garden_plot(rng: random.Random) -> dict:
    a, b, c = rng.choice(_TRIPLES)
    k = rng.randint(1, 5)
    length, width, diag = b * k, a * k, c * k
    context = (f"Участок имеет форму прямоугольника длиной {length} м и шириной {width} м. "
               f"Хозяин хочет огородить участок и проложить дорожку по диагонали.")
    kind = rng.choice(["perimeter", "area", "diagonal"])
    if kind == "perimeter":
        text = f"Сколько метров забора нужно для участка {length} м × {width} м?"
        answer, wrong = 2 * (length + width), [length + width, length * width, 4 * length]
        expl = f"Периметр прямоугольника P = 2·(a + b) = 2·({length} + {width}) = {answer} м."
        unit = " м"
    elif kind == "area":
        text = f"Чему равна площадь участка {length} м × {width} м?"
        answer, wrong = length * width, [2 * (length + width), length + width, length * width // 2]
        expl = f"Площадь прямоугольника S = a·b = {length}·{width} = {answer} м²."
        unit = " м²"
    else:
        text = f"Какой длины будет дорожка по диагонали участка {length} м × {width} м?"
        answer, wrong = diag, [length + width, length + width - diag // 2, diag + k]
        expl = (f"Диагональ делит прямоугольник на два прямоугольных треугольника. По теореме Пифагора "
                f"d² = {length}² + {width}² = {length * length + width * width}, d = {diag} м.")
        unit = " м"
    return single(rng, text, f"{num(answer)}{unit}", number_distractors(rng, answer, wrong, unit),
                  expl, context=context)


def _derivative_pair(rng: random.Random) -> tuple[str, str, str]:
    kind = rng.choice(["power", "power", "sin", "cos", "exp", "ln"])
    a = rng.randint(2, 9)
    if kind == "power":
        n = rng.randint(2, 6)
        return term(a, n), term(a * n, n - 1), term(a, n - 1) if n > 1 else str(a)
    if kind == "sin":
        return f"{a}sin x", f"{a}cos x", f"−{a}cos x"
    if kind == "cos":
        return f"{a}cos x", f"−{a}sin x", f"{a}sin x"
    if kind == "exp":
        return f"{a}eˣ", f"{a}eˣ", f"{a}xeˣ⁻¹"
    return f"{a}ln x", f"{a}/x", f"1/({a}x)"


@topic("13")
def derivatives_matching(rng: random.Random) -> dict:
    (f1, d1, e1), (f2, d2, e2) = _derivative_pair(rng), _derivative_pair(rng)
    if f1 == f2:
        raise SkipQuestion
    text = f"Установите соответствие между функцией и её производной: 1) y = {f1}; 2) y = {f2}."
    explanation = (
        f"Используем таблицу производных: (xⁿ)′ = n·xⁿ⁻¹, (sin x)′ = cos x, (cos x)′ = −sin x, "
        f"(eˣ)′ = eˣ, (ln x)′ = 1/x; постоянный множитель выносится. "
        f"Поэтому ({f1})′ = {d1} и ({f2})′ = {d2}."
    )
    return matching(rng, text, [(f"y = {f1}", d1), (f"y = {f2}", d2)], [e1, e2], explanation)


@topic("05")
def equations_matching(rng: random.Random) -> dict:
    pairs, lines = [], []
    roots = rng.sample(range(-9, 10), 4)
    for root in roots[:2]:
        a, b = rng.randint(2, 9), nonzero(rng, -15, 15)
        eq = f"{poly([(a, 1), (b, 0)])} = {num(a * root + b)}"
        pairs.append((eq, num(root)))
        lines.append(f"{eq} → x = {num(root)}")
    text = f"Установите соответствие между уравнением и его корнем: 1) {pairs[0][0]}; 2) {pairs[1][0]}."
    explanation = ("Решаем каждое уравнение: переносим свободный член вправо и делим на коэффициент при x. "
                   + "; ".join(lines) + ".")
    return matching(rng, text, pairs, [num(roots[2]), num(roots[3])], explanation)


@topic("12")
def progression_matching(rng: random.Random) -> dict:
    a1, d = rng.randint(-5, 10), nonzero(rng, -4, 6)
    n1, n2 = rng.sample(range(3, 15), 2)
    v1, v2 = a1 + (n1 - 1) * d, a1 + (n2 - 1) * d
    if v1 == v2:
        raise SkipQuestion
    text = (f"Арифметическая прогрессия: a₁ = {num(a1)}, d = {num(d)}. "
            f"Установите соответствие между номером члена и его значением: 1) a{_sub(n1)}; 2) a{_sub(n2)}.")
    extra = [num(a1 + n1 * d), num(a1 + n2 * d), num(v1 + 1), num(v2 - 1)]
    d_show = f"({num(d)})" if d < 0 else num(d)
    explanation = (f"По формуле aₙ = a₁ + (n − 1)·d: a{_sub(n1)} = {num(a1)} + {n1 - 1}·{d_show} = {num(v1)}, "
                   f"a{_sub(n2)} = {num(a1)} + {n2 - 1}·{d_show} = {num(v2)}.")
    return matching(rng, text, [(f"a{_sub(n1)}", num(v1)), (f"a{_sub(n2)}", num(v2))], extra, explanation)


def _is_prime(n: int) -> bool:
    return n > 1 and all(n % d for d in range(2, int(n ** 0.5) + 1))


@topic("01")
def primes_multiple(rng: random.Random) -> dict:
    count = rng.randint(1, 3)
    primes = rng.sample([p for p in range(11, 200) if _is_prime(p)], count)
    composites = rng.sample([c for c in range(10, 200) if not _is_prime(c) and c % 2], 6 - count)
    numbers = primes + composites
    rng.shuffle(numbers)
    text = f"Какие из чисел {', '.join(map(str, numbers))} являются простыми?"
    factors = []
    for c in composites:
        d = next(d for d in range(3, c) if c % d == 0)
        factors.append(f"{c} = {d}·{c // d}")
    explanation = (f"Простое число делится только на 1 и на само себя. Простые: {', '.join(map(str, primes))}. "
                   f"Остальные составные: {', '.join(factors)}.")
    return multiple(rng, text, [str(p) for p in primes], [str(c) for c in composites], explanation)


@topic("01")
def divisors_multiple(rng: random.Random) -> dict:
    n = rng.randint(24, 400)
    divs = [d for d in range(2, n) if n % d == 0]
    non = [d for d in range(2, n) if n % d]
    if len(divs) < 3 or len(non) < 5:
        raise SkipQuestion
    right = rng.sample(divs, rng.randint(1, 3))
    wrong = rng.sample(non, 6 - len(right))
    explanation = (f"Делитель — число, на которое {n} делится без остатка. "
                   + ", ".join(f"{n} : {d} = {n // d}" for d in right)
                   + ". Остальные числа дают остаток.")
    return multiple(rng, f"Выберите все делители числа {n}.", [str(d) for d in right],
                    [str(d) for d in wrong], explanation)


@topic("10")
def inequality_multiple(rng: random.Random) -> dict:
    a, k = rng.randint(2, 7), rng.randint(-8, 8)
    b = nonzero(rng, -12, 12)
    good = list(range(k + 1, k + 9))
    bad = list(range(k - 8, k + 1))
    right = rng.sample(good, rng.randint(1, 3))
    wrong = rng.sample(bad, 6 - len(right))
    text = f"Какие из чисел удовлетворяют неравенству {poly([(a, 1), (b, 0)])} > {num(a * k + b)}?"
    explanation = (f"Решаем: {term(a, 1)} > {num(a * k)}, x > {num(k)}. Подходят числа больше {num(k)}: "
                   f"{', '.join(num(v) for v in sorted(right))}. Число {num(k)} не подходит — неравенство строгое.")
    return multiple(rng, text, [num(v) for v in right], [num(v) for v in wrong], explanation)


@topic("05")
def roots_multiple(rng: random.Random) -> dict:
    p, q = rng.sample([v for v in range(-9, 10) if v], 2)
    eq = poly([(1, 2), (-(p + q), 1), (p * q, 0)]) + " = 0"
    pool = [v for v in range(-12, 13) if v not in (p, q)]
    wrong = rng.sample(pool, 4)
    explanation = (f"Корни находим по теореме Виета: сумма {num(p + q)}, произведение {num(p * q)}, "
                   f"значит корни {num(min(p, q))} и {num(max(p, q))}. Подстановка остальных чисел не даёт нуля.")
    return multiple(rng, f"Какие из чисел являются корнями уравнения {eq}?",
                    [num(p), num(q)], [num(v) for v in wrong], explanation)


_TRIG = {
    "sin": {0: "0", 30: "1/2", 45: "√2/2", 60: "√3/2", 90: "1", 120: "√3/2", 135: "√2/2", 150: "1/2",
            180: "0"},
    "cos": {0: "1", 30: "√3/2", 45: "√2/2", 60: "1/2", 90: "0", 120: "−1/2", 135: "−√2/2",
            150: "−√3/2", 180: "−1"},
    "tg": {0: "0", 30: "√3/3", 45: "1", 60: "√3", 120: "−√3", 135: "−1", 150: "−√3/3", 180: "0"},
}
_TRIG_POOL = sorted({value for table in _TRIG.values() for value in table.values()})


@topic("03")
def trig_value(rng: random.Random) -> dict:
    func = rng.choice(sorted(_TRIG))
    angle = rng.choice(sorted(_TRIG[func]))
    value = _TRIG[func][angle]
    wrong = [v for v in _TRIG_POOL if v != value]
    rng.shuffle(wrong)
    explanation = (f"По таблице значений тригонометрических функций {func} {angle}° = {value}."
                   + (" Для тупого угла используют формулы приведения: например, "
                      "sin(180° − α) = sin α, cos(180° − α) = −cos α." if angle > 90 else ""))
    return single(rng, f"Чему равен {func} {angle}°?", value, wrong, explanation)


@topic("03")
def trig_identity(rng: random.Random) -> dict:
    k = rng.randint(2, 15)
    m = nonzero(rng, -20, 20)
    answer = k + m
    text = f"Найдите значение выражения {k}sin²α + {k}cos²α {'+' if m > 0 else '−'} {abs(m)}."
    explanation = (f"По основному тригонометрическому тождеству sin²α + cos²α = 1, поэтому "
                   f"{k}(sin²α + cos²α) {'+' if m > 0 else '−'} {abs(m)} = {k} {'+' if m > 0 else '−'} "
                   f"{abs(m)} = {num(answer)}.")
    return single(rng, text, num(answer), number_distractors(rng, answer, [k, m, 2 * k + m, k - m]),
                  explanation)


_TRIG_EQUATIONS = [
    ("sin x = 0", "x = πk, k ∈ Z"), ("sin x = 1", "x = π/2 + 2πk, k ∈ Z"),
    ("sin x = −1", "x = −π/2 + 2πk, k ∈ Z"), ("cos x = 0", "x = π/2 + πk, k ∈ Z"),
    ("cos x = 1", "x = 2πk, k ∈ Z"), ("cos x = −1", "x = π + 2πk, k ∈ Z"),
    ("tg x = 1", "x = π/4 + πk, k ∈ Z"), ("tg x = −1", "x = −π/4 + πk, k ∈ Z"),
]


@topic("06")
def trig_equation(rng: random.Random) -> dict:
    equation, answer = rng.choice(_TRIG_EQUATIONS)
    wrong = [a for _, a in _TRIG_EQUATIONS if a != answer]
    rng.shuffle(wrong)
    explanation = (f"Это частный случай простейшего тригонометрического уравнения, его решения: {answer}. "
                   "Проверить удобно по единичной окружности.")
    return single(rng, f"Решите уравнение {equation}.", answer, wrong, explanation)


@topic("06")
def irrational_equation(rng: random.Random) -> dict:
    a = rng.randint(1, 6)
    x = rng.randint(-10, 15)
    c = rng.randint(1, 9)
    b = c * c - a * x
    if b == 0:
        raise SkipQuestion
    text = f"Решите уравнение √({poly([(a, 1), (b, 0)])}) = {c}."
    explanation = (f"Возводим обе части в квадрат: {poly([(a, 1), (b, 0)])} = {c * c}, "
                   f"{term(a, 1)} = {num(c * c - b)}, x = {num(x)}. Проверка: подкоренное выражение равно "
                   f"{c * c} ≥ 0, а √{c * c} = {c}.")
    wrong = [x + 1, x - 1, -x, (c - b) / a, c * c]
    return single(rng, text, num(x), number_distractors(rng, x, wrong), explanation)


def _power_text(base: int, k: int) -> str:
    if k == 0:
        return f"{base}ˣ"
    return f"{base}ˣ{'⁺' if k > 0 else '⁻'}{sup(abs(k))}"


@topic("07")
def exponential_equation(rng: random.Random) -> dict:
    base = rng.choice([2, 3, 5])
    m = rng.randint(2, {2: 10, 3: 6, 5: 4}[base])
    k = nonzero(rng, -6, 6)
    x = m - k
    text = f"Решите уравнение {_power_text(base, k)} = {num(base ** m)}."
    explanation = (f"{num(base ** m)} = {base}{sup(m)}, поэтому показатели равны: x {'+' if k > 0 else '−'} "
                   f"{abs(k)} = {m}, x = {num(x)}.")
    return single(rng, text, num(x), number_distractors(rng, x, [m, m + k, -x, base ** m - k]), explanation)


@topic("07")
def log_equation(rng: random.Random) -> dict:
    base = rng.choice([2, 3, 5])
    m = rng.randint(1, {2: 6, 3: 4, 5: 3}[base])
    k = nonzero(rng, -9, 9)
    x = base ** m - k
    text = f"Решите уравнение log{_sub(base)}({poly([(1, 1), (k, 0)])}) = {m}."
    explanation = (f"По определению логарифма x {'+' if k > 0 else '−'} {abs(k)} = {base}{sup(m)} = "
                   f"{base ** m}, x = {num(x)}. Проверка: аргумент логарифма {base ** m} > 0.")
    return single(rng, text, num(x), number_distractors(rng, x, [base * m - k, base ** m + k, m - k]),
                  explanation)


@topic("09")
def exponential_system(rng: random.Random) -> dict:
    base = rng.choice([2, 3])
    x, y = rng.randint(-3, 6), rng.randint(-3, 6)
    if x == y:
        raise SkipQuestion
    s, d = x + y, x - y
    if s < 1 or base ** s > 2000:
        raise SkipQuestion
    text = (f"Решите систему уравнений: {base}ˣ · {base}ʸ = {num(base ** s)}, "
            f"x − y = {num(d)}. В ответе укажите пару (x; y).")
    answer = f"({num(x)}; {num(y)})"
    wrong = [f"({num(y)}; {num(x)})", f"({num(x)}; {num(-y)})", f"({num(s)}; {num(d)})",
             f"({num(x + 1)}; {num(y - 1)})"]
    explanation = (f"{base}ˣ · {base}ʸ = {base}ˣ⁺ʸ, а {num(base ** s)} = {base}{sup(s)}, значит x + y = {s}. "
                   f"Складываем с x − y = {num(d)}: 2x = {num(s + d)}, x = {num(x)}, тогда y = {num(y)}.")
    return single(rng, text, answer, wrong, explanation)


@topic("11")
def inequality_system(rng: random.Random) -> dict:
    left = rng.randint(-8, 8)
    right = left + rng.randint(2, 9)
    a1, a2 = rng.randint(2, 6), rng.randint(2, 6)
    b1, b2 = nonzero(rng, -10, 10), nonzero(rng, -10, 10)
    count = right - left - 1
    text = (f"Сколько целых решений имеет система неравенств: {poly([(a1, 1), (b1, 0)])} > "
            f"{num(a1 * left + b1)} и {poly([(a2, 1), (b2, 0)])} < {num(a2 * right + b2)}?")
    explanation = (f"Из первого неравенства x > {num(left)}, из второго x < {num(right)}. "
                   f"Целые числа строго между ними: {', '.join(num(v) for v in range(left + 1, right))} — "
                   f"всего {count}.")
    return single(rng, text, num(count), number_distractors(rng, count, [count + 1, count + 2, count - 1]),
                  explanation)


@topic("14")
def polygon_angles(rng: random.Random) -> dict:
    if rng.random() < 0.5:
        n = rng.randint(3, 20)
        total = (n - 2) * 180
        return single(rng, f"Чему равна сумма внутренних углов выпуклого {n}-угольника?", f"{num(total)}°",
                      [f"{num(v)}°" for v in (n * 180, (n - 1) * 180, (n - 3) * 180 or 90, 360)],
                      f"Сумма углов выпуклого n-угольника равна 180°·(n − 2) = 180°·{n - 2} = {num(total)}°.")
    n = rng.choice([3, 4, 5, 6, 8, 9, 10, 12, 15, 18, 20, 24, 30, 36])
    angle = (n - 2) * 180 // n
    return single(rng, f"Чему равен внутренний угол правильного {n}-угольника?", f"{angle}°",
                  [f"{v}°" for v in (360 // n, 180 - angle + 10 if angle != 170 else 150, angle + 10, angle - 10)],
                  f"Сумма углов равна 180°·({n} − 2) = {num((n - 2) * 180)}°, все {n} углов равны: "
                  f"{num((n - 2) * 180)}° : {n} = {angle}°. Можно и через внешний угол: 180° − 360°/{n} = {angle}°.")


@topic("16")
def polyhedron_elements(rng: random.Random) -> dict:
    n = rng.randint(3, 12)
    kind = rng.choice(["призмы", "пирамиды"])
    element = rng.choice(["вершин", "рёбер", "граней"])
    values = {"призмы": {"вершин": 2 * n, "рёбер": 3 * n, "граней": n + 2},
              "пирамиды": {"вершин": n + 1, "рёбер": 2 * n, "граней": n + 1}}
    answer = values[kind][element]
    others = [v for k in values.values() for v in k.values()] + [n, 4 * n]
    explanation = (f"У n-угольной призмы 2n вершин, 3n рёбер и n + 2 грани; у n-угольной пирамиды "
                   f"n + 1 вершина, 2n рёбер и n + 1 грань. При n = {n}: {answer}.")
    return single(rng, f"Сколько {element} у {n}-угольной {kind}?", num(answer),
                  number_distractors(rng, answer, others), explanation)


@topic("17")
def box_volume(rng: random.Random) -> dict:
    a, b, c = rng.randint(2, 15), rng.randint(2, 15), rng.randint(2, 15)
    volume = a * b * c
    area = 2 * (a * b + b * c + a * c)
    if rng.random() < 0.5:
        return single(rng, f"Найдите объём прямоугольного параллелепипеда с рёбрами {a} см, {b} см и {c} см.",
                      f"{num(volume)} см³", number_distractors(rng, volume, [area, a + b + c, a * b], " см³"),
                      f"V = abc = {a}·{b}·{c} = {num(volume)} см³.")
    return single(rng, f"Найдите площадь полной поверхности прямоугольного параллелепипеда с рёбрами "
                       f"{a} см, {b} см и {c} см.", f"{num(area)} см²",
                  number_distractors(rng, area, [volume, area // 2, a * b + b * c + a * c + a * b], " см²"),
                  f"S = 2(ab + bc + ac) = 2({a * b} + {b * c} + {a * c}) = {num(area)} см².")


@topic("17")
def cylinder_cone_volume(rng: random.Random) -> dict:
    r, h = rng.randint(1, 9), rng.randint(2, 15)
    if rng.random() < 0.5:
        v = r * r * h
        return single(rng, f"Найдите объём цилиндра с радиусом основания {r} см и высотой {h} см.",
                      f"{num(v)}π см³", [f"{num(x)}π см³" for x in (2 * r * h, r * h, 2 * r * r * h, v + r)],
                      f"V = πr²h = π·{r}²·{h} = {num(v)}π см³.")
    h = 3 * rng.randint(1, 6)
    v = r * r * h // 3
    return single(rng, f"Найдите объём конуса с радиусом основания {r} см и высотой {h} см.",
                  f"{num(v)}π см³", [f"{num(x)}π см³" for x in (r * r * h, 3 * v + r, 2 * v, v + h)],
                  f"V = ⅓πr²h = ⅓·π·{r}²·{h} = {num(v)}π см³.")


_QUADRUPLES = [(1, 2, 2, 3), (2, 3, 6, 7), (1, 4, 8, 9), (4, 4, 7, 9), (2, 6, 9, 11), (6, 6, 7, 11),
               (2, 10, 11, 15)]


@topic("18")
def space_vector_length(rng: random.Random) -> dict:
    *coords, length = rng.choice(_QUADRUPLES)
    k = rng.randint(1, 3)
    coords = [c * k * rng.choice([1, -1]) for c in coords]
    rng.shuffle(coords)
    length *= k
    x, y, z = coords
    text = f"Найдите длину вектора a({num(x)}; {num(y)}; {num(z)})."
    explanation = (f"|a| = √(x² + y² + z²) = √({x * x} + {y * y} + {z * z}) = √{length * length} = {length}.")
    return single(rng, text, num(length),
                  number_distractors(rng, length, [abs(x) + abs(y) + abs(z), length * length, length + 1]),
                  explanation)


@topic("18")
def space_dot_product(rng: random.Random) -> dict:
    a = [rng.randint(-5, 5) for _ in range(3)]
    b = [rng.randint(-5, 5) for _ in range(3)]
    dot = sum(p * q for p, q in zip(a, b))
    text = (f"Найдите скалярное произведение векторов a({num(a[0])}; {num(a[1])}; {num(a[2])}) "
            f"и b({num(b[0])}; {num(b[1])}; {num(b[2])}).")
    parts = " + ".join(f"{num(p)}·{'(' + num(q) + ')' if q < 0 else num(q)}" for p, q in zip(a, b))
    explanation = f"a·b = x₁x₂ + y₁y₂ + z₁z₂ = {parts} = {num(dot)}."
    wrong = [dot + 1, -dot if dot else 2, sum(a) + sum(b), dot - 2]
    return single(rng, text, num(dot), number_distractors(rng, dot, wrong), explanation)


TEMPLATES = {
    "single": [linear_equation, quadratic_roots, derivative_at_point, arithmetic_nth, arithmetic_sum,
               geometric_nth, logarithm, power_rules, percent_of_number, linear_system, pythagoras,
               linear_inequality, fraction_sum, function_value, circle_area, triangle_area,
               trig_value, trig_identity, trig_equation, irrational_equation, exponential_equation,
               log_equation, exponential_system, inequality_system, polygon_angles, polyhedron_elements,
               box_volume, cylinder_cone_volume, space_vector_length, space_dot_product],
    "context": [parabola_vertex, theater_rows, garden_plot],
    "matching": [derivatives_matching, equations_matching, progression_matching],
    "multiple": [primes_multiple, divisors_multiple, inequality_multiple, roots_multiple],
}
