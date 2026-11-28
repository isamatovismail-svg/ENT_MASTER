"""Шаблоны задач по информатике: системы счисления, информация, логика, Python."""

import itertools

from app.generators.common import (
    SkipQuestion, matching, multiple, num, number_distractors, plural, quiz, single, topic,
)

_SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def based(value: int, base: int) -> str:
    """Запись числа в системе счисления с индексом основания: based(5, 2) → «101₂»."""
    digits = "0123456789ABCDEF"
    if value == 0:
        text = "0"
    else:
        text = ""
        v = value
        while v:
            text = digits[v % base] + text
            v //= base
    return text + str(base).translate(_SUB)


def _to_base_steps(value: int, base: int) -> str:
    steps = []
    v = value
    while v:
        steps.append(f"{v} : {base} = {v // base} (ост. {v % base})")
        v //= base
    return "; ".join(steps)


@topic("04")
def to_decimal(rng):
    base = rng.choice([2, 2, 8, 16])
    value = rng.randint(9, 255 if base == 2 else 999)
    src = based(value, base)
    digits = src[:-len(str(base))] if base < 10 else src[:-2]
    powers = " + ".join(f"{int(d, 16)}·{base}{str(len(digits) - 1 - i).translate(str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹'))}"
                        for i, d in enumerate(digits) if d != "0")
    expl = f"Раскладываем по степеням основания: {src} = {powers} = {value}."
    wrong = [value + 1, value - 1, value * 2, int(digits, 10) if digits.isdigit() else value + 16, value + base]
    return single(rng, f"Переведите число {src} в десятичную систему счисления.", str(value),
                  number_distractors(rng, value, wrong), expl)


@topic("04")
def from_decimal(rng):
    base = rng.choice([2, 2, 8, 16])
    value = rng.randint(9, 255 if base == 2 else 999)
    answer = based(value, base)
    wrong = [based(value + d, base) for d in (1, -1, 2, -2, 4, 8, base)]
    expl = (f"Делим число на {base} с остатком, пока не получим 0: {_to_base_steps(value, base)}. "
            f"Остатки записываем в обратном порядке: {answer}.")
    return single(rng, f"Переведите число {value}₁₀ в систему счисления с основанием {base}.", answer,
                  [w for w in wrong if w != answer], expl)


@topic("04")
def binary_ones(rng):
    value = rng.randint(17, 1023)
    ones = bin(value).count("1")
    expl = f"{value}₁₀ = {based(value, 2)}. В этой записи {ones} {'единица' if ones == 1 else 'единицы' if ones < 5 else 'единиц'}."
    return single(rng, f"Сколько единиц в двоичной записи числа {value}?", str(ones),
                  number_distractors(rng, ones, [ones + 1, ones - 1, value.bit_length(), value.bit_length() - ones]),
                  expl)


@topic("03")
def units(rng):
    kind = rng.choice(["kb_bytes", "mb_kb", "bytes_bits", "kb_bits"])
    n = rng.choice([2, 3, 4, 5, 8, 10, 16, 32, 64, 128, 256, 512])
    if kind == "kb_bytes":
        text, value, unit = f"Сколько байт в {n} Кбайт?", n * 1024, "байт"
        expl = f"1 Кбайт = 1024 байт, значит {n} Кбайт = {n}·1024 = {num(value)} байт."
        wrong = [n * 1000, n * 8, n * 1024 * 8, n * 512]
    elif kind == "mb_kb":
        text, value, unit = f"Сколько Кбайт в {n} Мбайт?", n * 1024, "Кбайт"
        expl = f"1 Мбайт = 1024 Кбайт, значит {n} Мбайт = {n}·1024 = {num(value)} Кбайт."
        wrong = [n * 1000, n * 8, n * 1024 * 1024, n * 100]
    elif kind == "bytes_bits":
        text, value, unit = f"Сколько бит в {n} байтах?", n * 8, "бит"
        expl = f"1 байт = 8 бит, значит {n} байт = {n}·8 = {value} бит."
        wrong = [n * 1024, n * 2, n / 8, n * 10]
    else:
        text, value, unit = f"Сколько бит в {n} Кбайт?", n * 8192, "бит"
        expl = f"1 Кбайт = 1024 байт = 1024·8 = 8192 бит. {n} Кбайт = {n}·8192 = {num(value)} бит."
        wrong = [n * 1024, n * 8000, n * 8, n * 1000]
    return single(rng, text, f"{num(value)} {unit}", number_distractors(rng, value, wrong, f" {unit}"), expl)


@topic("03")
def message_size(rng):
    i = rng.randint(3, 8)
    power = 2 ** i
    chars = rng.choice([10, 16, 20, 32, 40, 50, 64, 100, 128, 200, 256])
    bits = chars * i
    if rng.random() < 0.5 or bits % 8:
        text = f"Алфавит содержит {power} символов. Каков информационный объём сообщения из {chars} символов (в битах)?"
        expl = (f"Вес одного символа i находим из 2ⁱ = N: 2^{i} = {power}, значит i = {i} бит. "
                f"Объём сообщения: {chars}·{i} = {num(bits)} бит.")
        return single(rng, text, f"{num(bits)} бит",
                      number_distractors(rng, bits, [chars * power, chars + i, bits // 8, chars * (i + 1)], " бит"),
                      expl)
    text = f"Алфавит содержит {power} символов. Каков информационный объём сообщения из {chars} символов (в байтах)?"
    expl = (f"2^{i} = {power}, значит один символ весит {i} бит. {chars}·{i} = {bits} бит = {bits} : 8 = "
            f"{num(bits // 8)} байт.")
    return single(rng, text, f"{num(bits // 8)} байт",
                  number_distractors(rng, bits // 8, [bits, chars * i // 2, chars, bits // 8 + i], " байт"), expl)


@topic("03")
def alphabet_power(rng):
    i = rng.randint(1, 9)
    power = 2 ** i
    if rng.random() < 0.5:
        text = f"Сколько бит нужно на один символ алфавита из {power} символов?"
        expl = f"Алфавит из N символов кодируется i битами, если 2ⁱ ≥ N. 2^{i} = {power}, значит нужно {i} бит."
        return single(rng, text, str(i), number_distractors(rng, i, [i + 1, i - 1, power // 2, i * 2]), expl)
    n = rng.randint(2 ** (i - 1) + 1, power) if i > 1 else 2
    text = f"Какое наименьшее число бит нужно для кодирования одного из {n} различных сигналов?"
    expl = f"Нужно наименьшее i, при котором 2ⁱ ≥ {n}: 2^{i - 1} = {2 ** (i - 1)} мало, 2^{i} = {power} достаточно. Ответ: {i}."
    return single(rng, text, str(i), number_distractors(rng, i, [i + 1, i - 1, n // 2, i + 2]), expl)


@topic("03")
def image_size(rng):
    w, h = rng.choice([(64, 64), (128, 128), (256, 128), (256, 256), (512, 256), (1024, 512), (640, 480), (800, 600)])
    colors = rng.choice([2, 4, 16, 256, 65536])
    i = colors.bit_length() - 1
    bits = w * h * i
    kb = bits / 8 / 1024
    if kb != int(kb):
        raise SkipQuestion
    kb = int(kb)
    text = (f"Растровое изображение размером {w}×{h} пикселей использует палитру из {num(colors)} цветов. "
            f"Сколько Кбайт занимает изображение (без сжатия)?")
    expl = (f"Глубина цвета: 2ⁱ = {num(colors)}, i = {i} бит. Объём: {w}·{h}·{i} = {num(bits)} бит = "
            f"{num(bits // 8)} байт = {num(bits // 8)} : 1024 = {num(kb)} Кбайт.")
    return single(rng, text, f"{num(kb)} Кбайт",
                  number_distractors(rng, kb, [kb * 8, w * h // 1024, kb * 2, kb // 2], " Кбайт"), expl)


@topic("02")
def transfer_time(rng):
    speed_kbit = rng.choice([128, 256, 512, 1024, 2048])
    seconds = rng.choice([8, 16, 32, 64, 10, 20, 40])
    size_kbyte = speed_kbit * seconds // 8
    text = f"Файл размером {num(size_kbyte)} Кбайт передаётся со скоростью {num(speed_kbit)} Кбит/с. Сколько секунд займёт передача?"
    expl = (f"Переводим размер в килобиты: {num(size_kbyte)}·8 = {num(size_kbyte * 8)} Кбит. "
            f"Время = {num(size_kbyte * 8)} : {num(speed_kbit)} = {seconds} с.")
    return single(rng, text, f"{seconds} с",
                  number_distractors(rng, seconds, [seconds // 8, seconds * 8, seconds // 2, seconds + 8], " с"), expl)


_OPS = {"∧": lambda a, b: a and b, "∨": lambda a, b: a or b}


def _expression(rng) -> tuple[str, callable]:
    op1, op2 = rng.choice(list(_OPS)), rng.choice(list(_OPS))
    neg = rng.choice(["A", "B", "C"])
    names = ["A", "B", "C"]
    shown = [f"¬{n}" if n == neg else n for n in names]
    order = rng.choice([0, 1])
    if order == 0:
        text = f"({shown[0]} {op1} {shown[1]}) {op2} {shown[2]}"

        def f(a, b, c):
            vals = {"A": a, "B": b, "C": c}
            v = {n: (not vals[n]) if n == neg else vals[n] for n in names}
            return _OPS[op2](_OPS[op1](v["A"], v["B"]), v["C"])
    else:
        text = f"{shown[0]} {op1} ({shown[1]} {op2} {shown[2]})"

        def f(a, b, c):
            vals = {"A": a, "B": b, "C": c}
            v = {n: (not vals[n]) if n == neg else vals[n] for n in names}
            return _OPS[op1](v["A"], _OPS[op2](v["B"], v["C"]))
    return text, f


@topic("05")
def truth_count(rng):
    text, f = _expression(rng)
    rows = [r for r in itertools.product([0, 1], repeat=3) if f(*r)]
    count = len(rows)
    q = f"Сколько наборов значений переменных A, B, C делают выражение {text} истинным?"
    expl = (f"Перебираем все 8 наборов (A, B, C). Выражение истинно на наборах: "
            + (", ".join("".join(map(str, r)) for r in rows) or "нет таких") + f". Всего {count}. "
            "Напомним: ∧ — «И», ∨ — «ИЛИ», ¬ — «НЕ».")
    return single(rng, q, str(count), number_distractors(rng, count, [8 - count, count + 1, count - 1, count + 2]), expl)


@topic("05")
def truth_value(rng):
    text, f = _expression(rng)
    rows = list(itertools.product([0, 1], repeat=3))
    true_rows = [r for r in rows if f(*r)]
    false_rows = [r for r in rows if not f(*r)]
    if not true_rows or len(false_rows) < 3:
        raise SkipQuestion
    good = rng.choice(true_rows)
    bad = rng.sample(false_rows, 3)
    show = lambda r: f"A = {r[0]}, B = {r[1]}, C = {r[2]}"
    q = f"При каком наборе значений выражение {text} истинно?"
    expl = (f"Подставляем каждый набор (1 — истина, 0 — ложь), сначала выполняем отрицание, затем действие "
            f"в скобках. Истинно только при {show(good)}; на остальных наборах выражение ложно.")
    return single(rng, q, show(good), [show(r) for r in bad], expl)


def _python_snippet(rng) -> tuple[str, str, list[str], str]:
    kind = rng.choice(["divmod", "range_sum", "slice", "len", "power", "list_index", "max_min", "str_mult"])
    if kind == "divmod":
        a, b = rng.randint(10, 99), rng.randint(2, 9)
        code = f"print({a} // {b} + {a} % {b})"
        value = a // b + a % b
        return code, str(value), [str(a / b)[:5], str(a // b), str(a % b), str(value + 1)], \
            f"{a} // {b} = {a // b} (целая часть), {a} % {b} = {a % b} (остаток). Сумма: {value}."
    if kind == "range_sum":
        a, b = rng.randint(0, 10), rng.randint(12, 25)
        code = f"print(sum(range({a}, {b})))"
        value = sum(range(a, b))
        return code, str(value), [str(value + b), str(sum(range(a, b + 1)) + 1), str(value - a - 1), str(b - a)], \
            f"range({a}, {b}) — числа от {a} до {b - 1} (правая граница не входит). Их сумма: {value}."
    if kind == "slice":
        word = rng.choice(["informatika", "programmist", "algoritm", "computer", "keyboard", "kazakhstan"])
        i = rng.randint(0, 3)
        j = rng.randint(i + 2, min(len(word), i + 5))
        code = f'print("{word}"[{i}:{j}])'
        value = word[i:j]
        wrong = [word[i:j + 1], word[i + 1:j + 1], word[i + 1:j], word[:j]]
        return code, value, wrong, (f"Срез [{i}:{j}] берёт символы с индекса {i} по {j - 1} включительно "
                                    f"(нумерация с нуля): «{value}».")
    if kind == "len":
        word = rng.choice(["Python", "Astana", "informatika", "ENT 2026", "hello world", "Almaty!"])
        code = f'print(len("{word}"))'
        value = len(word)
        return code, str(value), [str(value - 1), str(value + 1), str(len(word.replace(" ", "")) + 2)], \
            f"len считает все символы строки, включая пробелы и знаки: «{word}» — {value} символов."
    if kind == "power":
        a, b, c = rng.randint(2, 5), rng.randint(2, 5), rng.randint(2, 9)
        code = f"print({a} ** {b} - {c} * 2)"
        value = a ** b - c * 2
        return code, str(value), [str((a ** b - c) * 2), str(a * b - c * 2), str(a ** b - c), str(value + 2)], \
            f"Сначала степень: {a} ** {b} = {a ** b}, затем умножение: {c} * 2 = {c * 2}. {a ** b} − {c * 2} = {value}."
    if kind == "list_index":
        items = rng.sample(range(1, 50), 5)
        k = rng.randint(-3, 4)
        code = f"a = {items}; print(a[{k}])"
        value = items[k]
        wrong = [items[(k + 1) % 5], items[(k - 1) % 5], items[abs(k) % 5 if k < 0 else (k + 2) % 5]]
        note = ("индексы начинаются с нуля" if k >= 0 else "отрицательный индекс считается с конца, a[−1] — последний")
        return code, str(value), [str(w) for w in wrong] + [str(k)], f"В Python {note}. a[{k}] = {value}."
    if kind == "max_min":
        items = rng.sample(range(-20, 60), 5)
        code = f"print(max({items}) - min({items}))"
        value = max(items) - min(items)
        return code, str(value), [str(max(items)), str(min(items)), str(max(items) + min(items)), str(value + 1)], \
            f"max = {max(items)}, min = {min(items)}, разность {value}."
    s = rng.choice(["ab", "xy", "ok", "hi"])
    n = rng.randint(2, 4)
    code = f'print("{s}" * {n} + "!")'
    value = s * n + "!"
    return code, value, [s + "!" * n, s * (n + 1) + "!", f"{s}{n}!", s * (n - 1) + "!"], \
        f"Умножение строки на число повторяет её {n} раза, затем добавляется «!»: {value}."


@topic("06")
def python_output(rng):
    code, value, wrong, expl = _python_snippet(rng)
    return single(rng, f"Что выведет программа на Python: {code}", value, wrong, expl)


@topic("03")
def photo_context(rng):
    w, h = rng.choice([(1024, 768), (800, 600), (640, 480), (1280, 1024), (1920, 1080)])
    bits = rng.choice([8, 16, 24])
    count = rng.choice([10, 20, 50, 100])
    size_bytes = w * h * bits // 8
    context = (f"Камера делает снимки {w}×{h} пикселей, на каждый пиксель отводится {bits} бит. "
               f"Снимки сохраняются без сжатия.")
    if rng.random() < 0.5:
        kb = size_bytes / 1024
        if kb != int(kb):
            raise SkipQuestion
        text = f"Сколько Кбайт занимает один снимок {w}×{h} при {bits} битах на пиксель?"
        expl = f"{w}·{h}·{bits} бит = {num(size_bytes)} байт = {num(size_bytes)} : 1024 = {num(int(kb))} Кбайт."
        return single(rng, text, f"{num(int(kb))} Кбайт",
                      number_distractors(rng, int(kb), [int(kb) * 8, int(kb) // 2, w * h // 1024, int(kb) * 3],
                                         " Кбайт"), expl, context=context)
    total_mb = size_bytes * count / 1024 / 1024
    if total_mb * 100 != int(total_mb * 100):
        raise SkipQuestion
    text = f"Сколько Мбайт займут {count} снимков {w}×{h} при {bits} битах на пиксель?"
    expl = (f"Один снимок: {w}·{h}·{bits} / 8 = {num(size_bytes)} байт. {count} снимков: {num(size_bytes * count)} байт = "
            f"{num(size_bytes * count)} : 1024 : 1024 = {num(total_mb)} Мбайт.")
    return single(rng, text, f"{num(total_mb)} Мбайт",
                  number_distractors(rng, total_mb, [total_mb * 8, total_mb / 2, total_mb * 2, count], " Мбайт"),
                  expl, context=context)


@topic("06")
def loop_context(rng):
    start, step, limit = rng.randint(0, 5), rng.randint(2, 5), rng.randint(20, 60)
    s, count, x = 0, 0, start
    while x < limit:
        s += x
        count += 1
        x += step
    context = f"Дана программа на Python:  x = {start}; s = 0;  while x < {limit}: s += x; x += {step};  print(s)"
    if rng.random() < 0.5:
        text = f"Что выведет программа (x = {start}, шаг {step}, пока x < {limit}), которая суммирует x?"
        expl = (f"Цикл складывает числа {start}, {start + step}, … меньше {limit} — всего {count} чисел. "
                f"Их сумма: {s}.")
        return single(rng, text, str(s), number_distractors(rng, s, [s + x, s - start, count, s + step]), expl,
                      context=context)
    text = f"Сколько раз выполнится тело цикла (x = {start}, шаг {step}, пока x < {limit})?"
    expl = f"x принимает значения {start}, {start + step}, …, {x - step}; при x = {x} условие ложно. Всего {count} раз."
    return single(rng, text, str(count), number_distractors(rng, count, [count + 1, count - 1, limit // step, s]),
                  expl, context=context)


@topic("04")
def bases_matching(rng):
    values = rng.sample(range(5, 64), 4)
    base = rng.choice([2, 8, 16])
    a, b = values[:2]
    text = f"Установите соответствие между числом и его десятичным значением: 1) {based(a, base)}; 2) {based(b, base)}."
    expl = f"{based(a, base)} = {a}, {based(b, base)} = {b} (раскладываем по степеням {base})."
    return matching(rng, text, [(based(a, base), str(a)), (based(b, base), str(b))], [str(v) for v in values[2:]],
                    expl)


_TERMS = [("Процессор", "обрабатывает данные и выполняет команды"),
          ("Оперативная память", "временно хранит выполняемые программы и данные"),
          ("Жёсткий диск", "долговременно хранит файлы"),
          ("Монитор", "устройство вывода изображения"),
          ("Клавиатура", "устройство ввода текста"),
          ("Сканер", "переводит изображение с бумаги в цифровой вид"),
          ("Принтер", "выводит информацию на бумагу"),
          ("Маршрутизатор", "соединяет сети и передаёт пакеты между ними"),
          ("Компилятор", "переводит всю программу в машинный код до запуска"),
          ("Интерпретатор", "выполняет программу построчно"),
          ("Браузер", "программа для просмотра веб-страниц"),
          ("Антивирус", "обнаруживает и удаляет вредоносные программы")]


@topic("01")
def terms_matching(rng):
    picked = rng.sample(_TERMS, 4)
    a, b = picked[:2]
    text = f"Установите соответствие между понятием и его назначением: 1) {a[0].lower()}; 2) {b[0].lower()}."
    expl = f"{a[0]} — {a[1]}. {b[0]} — {b[1]}."
    return matching(rng, text, [a, b], [p[1] for p in picked[2:]], expl)


@topic("04")
def bigger_multiple(rng):
    limit = rng.randint(30, 120)
    values = rng.sample(range(5, 200), 6)
    right = [v for v in values if v > limit]
    if not 1 <= len(right) <= 3:
        raise SkipQuestion
    wrong = [v for v in values if v <= limit]
    bases = {v: rng.choice([2, 8, 16]) for v in values}
    shown = {v: based(v, bases[v]) for v in values}
    text = f"Какие из чисел больше {limit}₁₀: {', '.join(shown[v] for v in values)}?"
    expl = "Переводим в десятичную систему: " + "; ".join(f"{shown[v]} = {v}" for v in values) + "."
    return multiple(rng, text, [shown[v] for v in right], [shown[v] for v in wrong], expl)


_INPUT = ["Клавиатура", "Мышь", "Сканер", "Микрофон", "Веб-камера", "Джойстик"]
_OUTPUT = ["Монитор", "Принтер", "Колонки", "Наушники", "Проектор", "Плоттер"]


@topic("01")
def devices_multiple(rng):
    if rng.random() < 0.5:
        right_pool, wrong_pool, kind = _INPUT, _OUTPUT, "ввода"
    else:
        right_pool, wrong_pool, kind = _OUTPUT, _INPUT, "вывода"
    right = rng.sample(right_pool, rng.randint(1, 3))
    wrong = rng.sample(wrong_pool, 6 - len(right))
    names = sorted(right + wrong)
    text = f"Какие из устройств являются устройствами {kind}: {', '.join(n.lower() for n in names)}?"
    expl = (f"Устройства ввода передают информацию в компьютер, вывода — из компьютера человеку. "
            f"Устройства {kind} здесь: {', '.join(r.lower() for r in right)}.")
    return multiple(rng, text, right, wrong, expl)


@topic("04")
def even_binary_multiple(rng):
    values = rng.sample(range(8, 128), 6)
    right = [v for v in values if v % 2 == 0]
    if not 1 <= len(right) <= 3:
        raise SkipQuestion
    wrong = [v for v in values if v % 2]
    text = f"Какие из двоичных чисел чётные: {', '.join(based(v, 2) for v in values)}?"
    expl = "Двоичное число чётное, если оно оканчивается на 0. Чётные: " + ", ".join(based(v, 2) for v in right) + "."
    return multiple(rng, text, [based(v, 2) for v in right], [based(v, 2) for v in wrong], expl)


_WORDS = ["informatika", "python", "algoritm", "kompyuter", "astana", "programma", "baiterek", "massiv",
          "funksiya", "rekursiya", "sortirovka", "stroka"]


@topic("07")
def python_strings(rng):
    word = rng.choice(_WORDS)
    start = rng.randint(0, 3)
    stop = start + rng.randint(2, 4)
    variants = [
        (f"len('{word}')", str(len(word)), "функция len возвращает количество символов в строке"),
        (f"'{word}'[{start}:{stop}]", repr(word[start:stop])[1:-1],
         f"срез [{start}:{stop}] берёт символы с индекса {start} по {stop - 1} (нумерация с нуля)"),
        (f"'{word}'[::-1]", word[::-1], "срез [::-1] переворачивает строку"),
        (f"'{word}'.count('{word[1]}')", str(word.count(word[1])),
         f"метод count считает, сколько раз встречается подстрока '{word[1]}'"),
    ]
    expr, answer, why = rng.choice(variants)
    wrong = {str(len(word) - 1), str(len(word) + 1), word[start:stop + 1], word[start + 1:stop + 1], word,
             word[1:], str(word.count(word[1]) + 1)} - {answer}
    return single(rng, f"Что выведет программа на Python: print({expr})?", answer, sorted(wrong),
                  f"Ответ {answer}: {why}.")


@topic("07")
def python_recursion(rng):
    n = rng.randint(3, 8)
    if rng.random() < 0.5:
        code = "def f(n):\n    if n <= 1:\n        return 1\n    return n * f(n - 1)"
        answer = 1
        for k in range(2, n + 1):
            answer *= k
        why = f"f(n) = n·f(n − 1) и f(1) = 1, то есть f({n}) = {n}! = {num(answer)}"
        wrong = [answer // n, answer * (n + 1), n * (n - 1), answer + 1]
    else:
        code = "def f(n):\n    if n == 0:\n        return 0\n    return n + f(n - 1)"
        answer = n * (n + 1) // 2
        why = f"f(n) = n + f(n − 1) и f(0) = 0, то есть сумма 1 + 2 + … + {n} = {answer}"
        wrong = [answer - n, answer + n + 1, n * n, answer + 1]
    kind = "произведение" if "*" in code else "сумма"
    text = f"Дана рекурсивная функция на Python ({kind}). Что выведет print(f({n}))?"
    question = single(rng, text, num(answer), number_distractors(rng, answer, wrong), f"{why}.",
                      context=code)
    return question


SOFTWARE = quiz([
    ("Какая из программ является операционной системой?", "Linux", ["Microsoft Word", "Google Chrome", "Python"],
     "Операционная система управляет ресурсами компьютера; Linux — пример ОС, остальные — прикладные программы."),
    ("Какая программа обеспечивает работу операционной системы с конкретным устройством?", "драйвер",
     ["антивирус", "архиватор", "текстовый редактор"], "Драйвер — системная программа для управления устройством."),
    ("Какое устройство сохраняет данные после выключения компьютера?", "твердотельный накопитель (SSD)",
     ["оперативная память", "регистры процессора", "кэш-память"], "SSD и жёсткий диск — энергонезависимая внешняя память."),
    ("Какая программа предназначена для сжатия файлов?", "архиватор", ["драйвер", "браузер", "компилятор"],
     "Архиваторы (7-Zip, WinRAR) уменьшают размер файлов."),
    ("Какая программа переводит весь текст программы на языке высокого уровня в машинный код до запуска?",
     "компилятор", ["интерпретатор", "отладчик", "редактор"],
     "Компилятор переводит программу целиком, интерпретатор выполняет её построчно."),
    ("Какое устройство выполняет арифметические и логические операции?", "процессор",
     ["монитор", "клавиатура", "блок питания"], "Центральный процессор обрабатывает данные по командам программы."),
], "08")

_STUDENTS = ["Айгерим", "Данияр", "Асель", "Нурлан", "Мадина", "Ерлан", "Алия", "Тимур"]


@topic("09")
def db_records(rng):
    people = rng.sample(_STUDENTS, 6)
    scores = [rng.randint(60, 140) for _ in people]
    limit = rng.randrange(80, 125, 5)
    count = sum(score > limit for score in scores)
    table = "; ".join(f"{p} — {s}" for p, s in zip(people, scores))
    text = (f"Таблица «Ученики» (Имя — Балл): {table}. Сколько записей отберёт фильтр «Балл > {limit}»?")
    explanation = (f"Условию «Балл > {limit}» удовлетворяют: "
                   + (", ".join(f"{p} ({s})" for p, s in zip(people, scores) if s > limit) or "никто")
                   + f" — {count} {plural(count, 'запись', 'записи', 'записей')}.")
    return single(rng, text, num(count), number_distractors(rng, count, [6 - count, count + 1, 6]), explanation)


@topic("10")
def sql_count(rng):
    people = rng.sample(_STUDENTS, 6)
    scores = [rng.randint(60, 140) for _ in people]
    limit = rng.randrange(80, 125, 5)
    op = rng.choice([">=", "<"])
    count = sum((s >= limit) if op == ">=" else (s < limit) for s in scores)
    table = "; ".join(f"{p} — {s}" for p, s in zip(people, scores))
    text = (f"Таблица Students (name — score): {table}. Что вернёт запрос "
            f"SELECT COUNT(*) FROM Students WHERE score {op} {limit}?")
    explanation = (f"COUNT(*) считает строки, для которых выполнено условие score {op} {limit}: "
                   f"таких строк {count}.")
    return single(rng, text, num(count), number_distractors(rng, count, [6 - count, count + 1, 6]), explanation)


IT_TRENDS = quiz([
    ("Как называется молодая компания, которая создаёт новый продукт и ищет масштабируемую бизнес-модель?",
     "стартап", ["холдинг", "франшиза", "монополия"], "Стартап — компания на ранней стадии с инновационной идеей."),
    ("Как называется минимальная версия продукта, выпущенная для проверки идеи на пользователях?", "MVP",
     ["API", "SSD", "CPU"], "MVP (minimum viable product) — минимально жизнеспособный продукт."),
    ("Как называется хранение данных и запуск программ на удалённых серверах через интернет?",
     "облачные вычисления", ["локальная сеть", "дефрагментация", "компиляция"],
     "Облачные сервисы предоставляют ресурсы серверов по сети."),
    ("Как называется сеть бытовых и промышленных устройств, обменивающихся данными через интернет?",
     "интернет вещей (IoT)", ["искусственный интеллект", "блокчейн", "виртуальная реальность"],
     "IoT — «умные» датчики, счётчики, бытовая техника, подключённые к сети."),
    ("Какое устройство создаёт физический объект по цифровой 3D-модели слой за слоем?", "3D-принтер",
     ["плоттер", "сканер", "проектор"], "3D-принтер наносит материал послойно по трёхмерной модели."),
], "11")


@topic("12")
def spreadsheet_formula(rng):
    values = [rng.randint(1, 50) for _ in range(4)]
    func = rng.choice(["СУММ", "МАКС", "МИН", "СРЗНАЧ"])
    if func == "СРЗНАЧ" and sum(values) % 4:
        raise SkipQuestion
    result = {"СУММ": sum(values), "МАКС": max(values), "МИН": min(values),
              "СРЗНАЧ": sum(values) // 4}[func]
    cells = ", ".join(f"A{i + 1} = {v}" for i, v in enumerate(values))
    meaning = {"СУММ": "сумму", "МАКС": "наибольшее значение", "МИН": "наименьшее значение",
               "СРЗНАЧ": "среднее арифметическое"}[func]
    text = f"В электронной таблице {cells}. Какое значение вычислит формула ={func}(A1:A4)?"
    wrong = [sum(values), max(values), min(values), values[0] + values[3]]
    return single(rng, text, num(result), number_distractors(rng, result, wrong),
                  f"Функция {func} находит {meaning} в диапазоне A1:A4: {num(result)}.")


WEB = quiz([
    ("Какой тег HTML создаёт гиперссылку?", "<a>", ["<p>", "<img>", "<ul>"], "Ссылка: <a href=\"адрес\">текст</a>."),
    ("Какой тег HTML вставляет изображение?", "<img>", ["<a>", "<table>", "<h1>"],
     "Изображение: <img src=\"файл\" alt=\"описание\">."),
    ("Какой тег HTML задаёт заголовок первого уровня?", "<h1>", ["<head>", "<title>", "<p>"],
     "Заголовки страницы — теги <h1>…<h6>, <h1> — самый крупный."),
    ("Какой тег HTML создаёт таблицу?", "<table>", ["<tr>", "<div>", "<list>"],
     "Таблица — <table>, строки — <tr>, ячейки — <td>."),
    ("Какое свойство CSS задаёт цвет текста?", "color", ["background", "font-size", "margin"],
     "color — цвет текста, background — фон."),
    ("Как называется язык описания внешнего вида (стилей) веб-страниц?", "CSS", ["HTML", "SQL", "Python"],
     "HTML описывает структуру страницы, CSS — её оформление."),
], "13")


TEMPLATES = {
    "single": [to_decimal, from_decimal, binary_ones, units, message_size, alphabet_power, image_size,
               transfer_time, truth_count, truth_value, python_output, python_strings, SOFTWARE, db_records,
               sql_count, IT_TRENDS, spreadsheet_formula, WEB],
    "context": [photo_context, loop_context, python_recursion],
    "matching": [bases_matching, terms_matching],
    "multiple": [bigger_multiple, devices_multiple, even_binary_multiple],
}
