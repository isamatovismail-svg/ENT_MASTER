"""Шаблоны задач по математической грамотности: жизненные ситуации, деньги, время, проценты."""

import random

from app.generators.common import SkipQuestion, num, number_distractors, plural, single

_NAMES = ["Айгерим", "Данияр", "Асель", "Нурлан", "Мадина", "Ерлан", "Алия", "Тимур", "Жанна", "Арман"]
_ITEMS = [("куртка", 18000, 60000), ("кроссовки", 15000, 45000), ("рюкзак", 6000, 20000),
          ("наушники", 5000, 30000), ("телефон", 60000, 250000), ("книга", 2000, 8000),
          ("часы", 10000, 50000), ("велосипед", 40000, 150000)]


def tg(value: float) -> str:
    return f"{num(value)} тг"


def discount(rng: random.Random) -> dict:
    item, low, high = rng.choice(_ITEMS)
    price = rng.randrange(low, high, 500)
    p = rng.choice([10, 15, 20, 25, 30, 40, 50])
    if price * p % 100:
        raise SkipQuestion
    cut = price * p // 100
    answer = price - cut
    text = f"Товар «{item}» стоит {tg(price)}. В магазине скидка {p}%. Сколько стоит товар со скидкой?"
    expl = (f"Скидка {p}% — это {tg(price)}·{num(p / 100)} = {tg(cut)}. "
            f"Цена со скидкой: {tg(price)} − {tg(cut)} = {tg(answer)}. Вариант {tg(cut)} — размер скидки, а не цена.")
    wrong = [cut, price + cut, price - p * 100, answer - cut]
    return single(rng, text, tg(answer), number_distractors(rng, answer, wrong, " тг", digits=0), expl)


def price_increase(rng: random.Random) -> dict:
    price = rng.randrange(200, 5000, 50)
    p = rng.choice([5, 8, 10, 12, 15, 20, 25])
    if price * p % 100:
        raise SkipQuestion
    answer = price + price * p // 100
    text = f"Проезд стоил {tg(price)}, затем подорожал на {p}%. Сколько стоит проезд теперь?"
    expl = f"Новая цена составляет {100 + p}% от старой: {tg(price)}·{num((100 + p) / 100)} = {tg(answer)}."
    wrong = [price + p, price * p // 100, price - price * p // 100, answer + price * p // 100]
    return single(rng, text, tg(answer), number_distractors(rng, answer, wrong, " тг", digits=0), expl)


def best_buy(rng: random.Random) -> dict:
    product = rng.choice([("молоко", "л"), ("сок", "л"), ("сахар", "кг"), ("рис", "кг"), ("мука", "кг")])
    v1, v2, v3 = rng.sample([0.5, 1, 1.5, 2, 3, 5], 3)
    unit_prices = rng.sample(range(300, 900, 10), 3)
    packs = [(v1, round(v1 * unit_prices[0])), (v2, round(v2 * unit_prices[1])), (v3, round(v3 * unit_prices[2]))]
    best = min(range(3), key=lambda i: packs[i][1] / packs[i][0])
    labels = [f"{num(v)} {product[1]} за {tg(p)}" for v, p in packs]
    text = (f"В магазине продаётся {product[0]} в трёх упаковках: " + "; ".join(labels)
            + f". Какая цена за 1 {product[1]} самая выгодная?")
    per = [packs[i][1] / packs[i][0] for i in range(3)]
    answer = tg(round(per[best]))
    wrong = [tg(round(per[i])) for i in range(3) if i != best] + [tg(min(p for _, p in packs))]
    expl = ("Делим цену упаковки на её объём: "
            + "; ".join(f"{tg(p)} : {num(v)} = {tg(round(p / v))}" for v, p in packs)
            + f". Самая низкая цена за 1 {product[1]} — {answer}.")
    return single(rng, text, answer, wrong, expl)


def travel_time(rng: random.Random) -> dict:
    speed = rng.choice([40, 50, 60, 70, 75, 80, 90, 100, 120])
    hours = rng.choice([1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 6])
    dist = speed * hours
    if dist != int(dist):
        raise SkipQuestion
    who = rng.choice(_NAMES)
    if rng.random() < 0.5:
        text = f"{who} едет на машине со скоростью {speed} км/ч. За сколько часов будет пройдено {num(dist)} км?"
        expl = f"Время = расстояние : скорость = {num(dist)} : {speed} = {num(hours)} ч."
        return single(rng, text, f"{num(hours)} ч",
                      number_distractors(rng, hours, [hours + 0.5, hours - 0.5, hours * 2, dist / 100], " ч"),
                      expl)
    text = f"{who} ехал {num(hours)} ч со скоростью {speed} км/ч. Какое расстояние он проехал?"
    expl = f"Расстояние = скорость · время = {speed}·{num(hours)} = {num(dist)} км."
    wrong = [speed + hours, dist + speed, dist - speed, speed * (hours + 1)]
    return single(rng, text, f"{num(dist)} км", number_distractors(rng, dist, wrong, " км"), expl)


def recipe_ratio(rng: random.Random) -> dict:
    dish, ingr, unit = rng.choice([("блинов", "муки", "г"), ("плова", "риса", "г"), ("торта", "сахара", "г"),
                                   ("баурсаков", "муки", "г"), ("компота", "ягод", "г")])
    base = rng.choice([2, 3, 4, 5, 6])
    target = rng.choice([v for v in range(2, 16) if v != base])
    amount = rng.randrange(60, 600, 20)
    if amount * target % base:
        raise SkipQuestion
    answer = amount * target // base
    text = (f"Для {dish} на {base} человек нужно {amount} {unit} {ingr}. "
            f"Сколько {ingr} нужно на {target} человек?")
    expl = (f"Количество продукта пропорционально числу человек: {amount}·{target} : {base} = {answer} {unit}.")
    wrong = [amount + target, amount * target, amount + (target - base), answer + amount // base]
    return single(rng, text, f"{answer} {unit}", number_distractors(rng, answer, wrong, f" {unit}"), expl)


def average_grade(rng: random.Random) -> dict:
    who = rng.choice(_NAMES)
    count = rng.randint(4, 7)
    marks = [rng.randint(3, 5) for _ in range(count)]
    if sum(marks) * 10 % count:
        raise SkipQuestion
    avg = sum(marks) / count
    text = f"{who} получил(а) за четверть оценки: {', '.join(map(str, marks))}. Найдите средний балл."
    expl = f"Средний балл = сумма оценок : их количество = {sum(marks)} : {count} = {num(avg, 1)}."
    wrong = [sum(marks) / (count + 1), max(marks), avg + 0.5, sorted(marks)[count // 2] + 0.2]
    return single(rng, text, num(avg, 1), number_distractors(rng, avg, wrong, digits=1), expl)


def mobile_tariff(rng: random.Random) -> dict:
    fee = rng.randrange(1500, 5000, 100)
    free_gb = rng.choice([5, 10, 15, 20])
    extra_price = rng.choice([100, 150, 200, 250, 300])
    used = free_gb + rng.randint(1, 12)
    answer = fee + (used - free_gb) * extra_price
    text = (f"Тариф стоит {tg(fee)} в месяц и включает {free_gb} ГБ интернета. Каждый дополнительный ГБ "
            f"стоит {tg(extra_price)}. Сколько придётся заплатить за месяц, если израсходовано {used} ГБ?")
    expl = (f"Сверх тарифа израсходовано {used} − {free_gb} = {used - free_gb} ГБ. "
            f"Доплата: {used - free_gb}·{extra_price} = {tg((used - free_gb) * extra_price)}. "
            f"Итого: {tg(fee)} + {tg((used - free_gb) * extra_price)} = {tg(answer)}.")
    wrong = [fee + used * extra_price, (used - free_gb) * extra_price, fee, answer + extra_price]
    return single(rng, text, tg(answer), number_distractors(rng, answer, wrong, " тг", digits=0), expl)


def currency(rng: random.Random) -> dict:
    cur, rate_low, rate_high = rng.choice([("долларов", 450, 520), ("евро", 500, 580), ("рублей", 5, 7)])
    rate = rng.randint(rate_low, rate_high) if rate_high > 10 else rng.choice([5.5, 6, 6.2, 6.5])
    amount = rng.choice([20, 50, 100, 150, 200, 300, 500, 1000, 2000])
    answer = amount * rate
    if answer != int(answer):
        raise SkipQuestion
    text = f"Курс: 1 единица валюты стоит {tg(rate)}. Сколько тенге нужно, чтобы купить {amount} {cur}?"
    expl = f"Умножаем количество валюты на курс: {amount}·{num(rate)} = {tg(answer)}."
    wrong = [amount + rate, answer / 10, answer + rate * 10, amount * (rate + 10)]
    return single(rng, text, tg(answer), number_distractors(rng, answer, wrong, " тг", digits=0), expl)


def tiles(rng: random.Random) -> dict:
    length, width = rng.randint(2, 8), rng.randint(2, 6)
    tile = rng.choice([(50, 4), (25, 16), (20, 25)])  # (сторона в см, плиток на 1 м²)
    side, per_m2 = tile
    area = length * width
    answer = area * per_m2
    text = (f"Пол комнаты имеет размер {length} м × {width} м. Сколько квадратных плиток со стороной "
            f"{side} см понадобится, чтобы покрыть весь пол?")
    expl = (f"Площадь пола: {length}·{width} = {area} м². Плитка со стороной {side} см имеет площадь "
            f"{num(side * side / 10000, 4)} м², значит на 1 м² нужно {per_m2} плиток. Всего: {area}·{per_m2} = {answer}.")
    wrong = [area, area * side, 2 * (length + width) * per_m2, area * per_m2 // 2]
    return single(rng, text, num(answer), number_distractors(rng, answer, wrong), expl)


def deposit(rng: random.Random) -> dict:
    sum0 = rng.randrange(100_000, 2_000_000, 50_000)
    rate = rng.choice([8, 10, 12, 14, 15, 16])
    years = rng.choice([1, 2, 3])
    compound = rng.random() < 0.5 and years > 1
    if compound:
        value = sum0 * (1 + rate / 100) ** years
        text = (f"Вклад {tg(sum0)} положили в банк под {rate}% годовых с капитализацией (проценты "
                f"начисляются на накопленную сумму). Сколько будет на счёте через {years} года?")
        expl = (f"Каждый год сумма умножается на {num(1 + rate / 100)}: "
                f"{tg(sum0)}·{num(1 + rate / 100)}{'²' if years == 2 else '³'} = {tg(round(value))}.")
        simple = sum0 * (1 + rate * years / 100)
        wrong = [simple, sum0 * rate * years / 100, value + sum0 * rate / 100, sum0 * (1 + rate / 100)]
    else:
        value = sum0 * (1 + rate * years / 100)
        text = (f"Вклад {tg(sum0)} положили в банк под {rate}% годовых без капитализации. "
                f"Сколько будет на счёте через {years} {'год' if years == 1 else 'года'}?")
        expl = (f"За год начисляется {tg(sum0)}·{num(rate / 100)} = {tg(sum0 * rate / 100)}. "
                f"За {years} {'год' if years == 1 else 'года'}: {tg(sum0 * rate * years / 100)}. "
                f"Итого: {tg(sum0)} + {tg(sum0 * rate * years / 100)} = {tg(value)}.")
        wrong = [sum0 * rate * years / 100, sum0 + sum0 * rate / 100 * (years + 1), value + 10_000, sum0 * rate / 10]
    value = round(value)
    return single(rng, text, tg(value), number_distractors(rng, value, [round(w) for w in wrong], " тг", digits=0),
                  expl)


def dice_probability(rng: random.Random) -> dict:
    kind = rng.choice(["even", "greater", "multiple3", "exact"])
    if kind == "even":
        text, good, why = "Бросают игральный кубик. Какова вероятность, что выпадет чётное число?", 3, "чётные: 2, 4, 6"
    elif kind == "multiple3":
        text, good, why = "Бросают игральный кубик. Какова вероятность, что выпадет число, кратное 3?", 2, "кратные 3: 3 и 6"
    elif kind == "exact":
        k = rng.randint(1, 6)
        text, good, why = f"Бросают игральный кубик. Какова вероятность, что выпадет {k}?", 1, f"подходит только {k}"
    else:
        k = rng.randint(1, 4)
        good = 6 - k
        text = f"Бросают игральный кубик. Какова вероятность, что выпадет число больше {k}?"
        why = "подходят " + ", ".join(str(v) for v in range(k + 1, 7))
    from fractions import Fraction
    p = Fraction(good, 6)
    answer = num(p) if p != 1 else "1"
    wrong = [num(Fraction(good, 12)), num(Fraction(6 - good, 6)) if good != 6 else "0", f"{good}", num(Fraction(1, 6)),
             num(Fraction(1, 2)), num(Fraction(2, 3))]
    expl = f"Всего 6 равновозможных исходов, {why} — это {good} {'исход' if good == 1 else 'исхода'}. Вероятность {good}/6 = {answer}."
    return single(rng, text, answer, wrong, expl)


def change_money(rng: random.Random) -> dict:
    who = rng.choice(_NAMES)
    count = rng.randint(2, 6)
    price = rng.randrange(150, 1500, 50)
    paid = rng.choice([v for v in (2000, 5000, 10000, 20000) if v > count * price])
    answer = paid - count * price
    word = "тетради" if count < 5 else "тетрадей"
    text = f"{who} купил(а) {count} {word} по {tg(price)} и дал(а) кассиру {tg(paid)}. Сколько сдачи нужно получить?"
    expl = f"Покупка: {count}·{tg(price)} = {tg(count * price)}. Сдача: {tg(paid)} − {tg(count * price)} = {tg(answer)}."
    wrong = [paid - price, count * price, answer - price, paid - count * price - 100]
    return single(rng, text, tg(answer), number_distractors(rng, answer, wrong, " тг", digits=0), expl)


def salary_tax(rng: random.Random) -> dict:
    salary = rng.randrange(150_000, 800_000, 10_000)
    tax = 10
    pension = 10
    answer = salary - salary * (tax + pension) // 100
    text = (f"Начисленная зарплата — {tg(salary)}. Из неё удерживают 10% пенсионных взносов и 10% налога "
            f"(для упрощения оба процента считаются от начисленной суммы). Сколько получит работник на руки?")
    expl = (f"Всего удерживается 10% + 10% = 20%: {tg(salary)}·0,2 = {tg(salary // 5)}. "
            f"На руки: {tg(salary)} − {tg(salary // 5)} = {tg(answer)}.")
    wrong = [salary - salary // 10, salary // 5, salary - 20_000, answer - salary // 10]
    return single(rng, text, tg(answer), number_distractors(rng, answer, wrong, " тг", digits=0), expl)


def reading_pages(rng: random.Random) -> dict:
    who = rng.choice(_NAMES)
    pages = rng.randrange(120, 600, 10)
    per_day = rng.choice([10, 15, 20, 25, 30, 40, 50])
    days = -(-pages // per_day)
    text = (f"В книге {pages} страниц. {who} читает {per_day} страниц в день. "
            f"За сколько дней книга будет прочитана полностью?")
    exact = pages / per_day
    if exact == days:
        expl = f"Делим число страниц на скорость чтения: {pages} : {per_day} = {days}. Ответ: {days}."
    else:
        expl = (f"Делим число страниц на скорость чтения: {pages} : {per_day} = {num(exact)}. "
                f"За {days - 1} {plural(days - 1, 'день', 'дня', 'дней')} книга ещё не дочитана, остаток читается на "
                f"{days}-й день. Ответ: {days}.")
    wrong = [days - 1, days + 1, pages - per_day, days * 2]
    return single(rng, text, num(days), number_distractors(rng, days, wrong), expl)


TEMPLATES = {
    "single": [discount, price_increase, best_buy, travel_time, recipe_ratio, average_grade, mobile_tariff,
               currency, tiles, deposit, dice_probability, change_money, salary_tax, reading_pages],
}
