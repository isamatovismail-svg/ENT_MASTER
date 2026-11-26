"""Форма вопроса банка — общая для админки и кабинета учителя.

Без JavaScript: тип вопроса выбирается ссылкой (форма перезагружается), для каждого
типа свои поля. Проверка содержимого — validate_question из question_bank.py
(та же, что у seed.py).
"""

from dataclasses import dataclass, field
from urllib.parse import urlencode

import config
from app import views
from app.database import Question
from app.question_bank import validate_question
from app.templates import SafeHTML, fragment, join, render
from app.web import Request

LEFT_ROWS = 6             # строк «слева» в форме задания на соответствие
TEXT_MAX_LENGTH = 4000    # ограничение длины текстовых полей формы
OPTION_MAX_LENGTH = 500


@dataclass
class QuestionForm:
    """Значения полей формы вопроса (в том числе после ошибки — чтобы не вводить заново)."""

    subject: str = ""
    qtype: str = config.SINGLE
    context: str = ""
    text: str = ""
    options: list[str] = field(default_factory=lambda: [""] * len(config.OPTION_LETTERS))
    correct: set[str] = field(default_factory=set)
    left: list[str] = field(default_factory=lambda: [""] * LEFT_ROWS)
    match: list[str] = field(default_factory=lambda: [""] * LEFT_ROWS)
    explanation: str = ""


def form_from_question(question: Question, qtype: str) -> QuestionForm:
    """Заполняет форму данными вопроса (qtype может отличаться — смена типа)."""
    form = QuestionForm(
        subject=question.subject, qtype=qtype, context=question.context,
        text=question.text, explanation=question.explanation,
    )
    for index, option in enumerate(question.options[: len(form.options)]):
        form.options[index] = option
    same_kind = (qtype == config.MATCHING) == (question.qtype == config.MATCHING)
    if same_kind and qtype == config.MATCHING:
        for index, (left, letter) in enumerate(list(zip(question.left, question.correct))[:LEFT_ROWS]):
            form.left[index] = left
            form.match[index] = letter
    elif same_kind:
        form.correct = set(question.correct)
    return form


def form_from_request(request: Request) -> QuestionForm:
    """Читает поля формы из POST-запроса."""
    qtype = request.form_value("type")
    form = QuestionForm(
        subject=request.form_value("subject"),
        qtype=qtype if qtype in config.QUESTION_TYPES else config.SINGLE,
        context=request.form_value("context").strip(),
        text=request.form_value("text").strip(),
        explanation=request.form_value("explanation").strip(),
    )
    letters = config.OPTION_LETTERS
    form.options = [request.form_value(f"opt_{letter}").strip() for letter in letters]
    form.correct = {value for value in request.form.get("correct", []) if value in letters}
    form.left = [request.form_value(f"left_{index}").strip() for index in range(LEFT_ROWS)]
    form.match = [
        value if value in letters else ""
        for value in (request.form_value(f"match_{index}") for index in range(LEFT_ROWS))
    ]
    return form


def _trim(values: list[str]) -> list[str]:
    """Убирает пустые значения в конце списка."""
    values = list(values)
    while values and not values[-1]:
        values.pop()
    return values


def build_question(form: QuestionForm, question_id: int = 0) -> tuple[Question | None, list[str]]:
    """Проверяет форму и собирает из неё вопрос. Возвращает (вопрос или None, ошибки)."""
    errors: list[str] = []
    if form.subject not in config.SUBJECTS:
        errors.append("Выберите предмет.")
    for name, value, limit in (("Текст вопроса", form.text, TEXT_MAX_LENGTH),
                               ("Контекст", form.context, TEXT_MAX_LENGTH),
                               ("Объяснение", form.explanation, TEXT_MAX_LENGTH)):
        if len(value) > limit:
            errors.append(f"{name}: не длиннее {limit} символов.")
    if any(len(option) > OPTION_MAX_LENGTH for option in form.options + form.left):
        errors.append(f"Варианты и строки — не длиннее {OPTION_MAX_LENGTH} символов.")

    options = _trim(form.options)
    if "" in options:
        errors.append("Варианты ответа заполняйте подряд: A, B, C… без пропусков.")
    letters = config.OPTION_LETTERS[: len(options)]

    left: list[str] = []
    if form.qtype == config.MATCHING:
        rows = list(zip(form.left, form.match))
        while rows and not rows[-1][0] and not rows[-1][1]:
            rows.pop()
        left = [row[0] for row in rows]
        correct = [row[1] for row in rows]
        if any(not item for item in left):
            errors.append("Строки соответствия заполняйте подряд, без пропусков.")
        if any(not letter for letter in correct):
            errors.append("Для каждой строки соответствия выберите правильную букву.")
    else:
        correct = sorted(letter for letter in form.correct if letter in letters)
        if not correct:
            errors.append("Отметьте правильный ответ.")

    data = {
        "type": form.qtype,
        "text": form.text,
        "context": form.context if form.qtype == config.CONTEXT else "",
        "options": options,
        "left": left,
        "correct": correct,
        "explanation": form.explanation,
    }
    if not errors:
        errors.extend(problem[:1].upper() + problem[1:] + "." for problem in validate_question(data))
    if errors:
        return None, errors
    return Question(
        id=question_id, subject=form.subject, qtype=form.qtype, text=data["text"],
        context=data["context"], options=options, left=left, correct=correct,
        explanation=form.explanation,
    ), []


def _type_switch(base_url: str, current: str, subject: str) -> SafeHTML:
    """Ссылки выбора типа вопроса (без JavaScript форма перезагружается)."""
    return join(
        fragment(
            '<a class="type-chip$active" href="$href">$name</a>',
            active=SafeHTML(" type-chip-active" if qtype == current else ""),
            href=f"{base_url}?{urlencode({'type': qtype, 'subject': subject} if subject else {'type': qtype})}",
            name=config.QUESTION_TYPE_NAMES[qtype],
        )
        for qtype in config.QUESTION_TYPES
    )


def _option_rows(form: QuestionForm) -> SafeHTML:
    """Поля вариантов ответа; рядом — отметка правильного (кроме соответствия)."""
    input_type = {config.MULTIPLE: "checkbox", config.MATCHING: ""}.get(form.qtype, "radio")
    rows = []
    for index, letter in enumerate(config.OPTION_LETTERS):
        mark = SafeHTML("")
        if input_type:
            mark = fragment(
                '<label class="correct-mark"><input type="$type" name="correct" value="$letter" $checked>'
                "<span>верный</span></label>",
                type=input_type, letter=letter,
                checked=SafeHTML("checked" if letter in form.correct else ""),
            )
        rows.append(fragment(
            '<div class="option-edit"><span class="letter">$letter</span>'
            '<input type="text" name="opt_$letter" value="$value" maxlength="$max" '
            'aria-label="Вариант $letter" placeholder="$placeholder">$mark</div>',
            letter=letter, value=form.options[index], max=OPTION_MAX_LENGTH, mark=mark,
            placeholder="обязательно" if index < 2 else "необязательно",
        ))
    return join(rows)


def _matching_rows(form: QuestionForm) -> SafeHTML:
    """Строки «слева» для соответствия и выбор правильной буквы для каждой."""
    if form.qtype != config.MATCHING:
        return SafeHTML("")
    rows = []
    for index in range(LEFT_ROWS):
        choices = join(
            [fragment('<option value="">— буква —</option>')] + [
                fragment('<option value="$l" $sel>$l</option>', l=letter,
                         sel=SafeHTML("selected" if form.match[index] == letter else ""))
                for letter in config.OPTION_LETTERS
            ]
        )
        rows.append(fragment(
            '<div class="option-edit"><span class="letter">$n</span>'
            '<input type="text" name="left_$i" value="$value" maxlength="$max" '
            'aria-label="Строка $n" placeholder="$placeholder">'
            '<select name="match_$i" aria-label="Правильная буква для строки $n">$choices</select></div>',
            n=index + 1, i=index, value=form.left[index], max=OPTION_MAX_LENGTH, choices=choices,
            placeholder="обязательно" if index < 2 else "необязательно",
        ))
    return fragment(
        '<fieldset class="admin-fieldset"><legend>Строки слева — что сопоставляем</legend>'
        '<p class="muted small">Для каждой строки выберите букву правильного варианта справа.</p>'
        "$rows</fieldset>",
        rows=join(rows),
    )


def form_content(request: Request, form: QuestionForm, action: str, base_url: str, title: str,
                 errors: list[str], note: SafeHTML | None = None, *, back_url: str,
                 back_label: str, submit_label: str) -> SafeHTML:
    """Содержимое страницы формы вопроса (общее для админки и кабинета учителя)."""
    subject_options = join(
        [fragment('<option value="">— выберите предмет —</option>')] + [
            fragment('<option value="$code" $sel>$icon $name</option>', code=code, icon=info.icon,
                     name=info.name, sel=SafeHTML("selected" if code == form.subject else ""))
            for code, info in config.SUBJECTS.items()
        ]
    )
    context_field = SafeHTML("")
    if form.qtype == config.CONTEXT:
        context_field = fragment(
            '<label class="field"><span>Контекст — текст, таблица или данные к заданию</span>'
            '<textarea name="context" rows="5" maxlength="$max" required>$value</textarea></label>',
            max=TEXT_MAX_LENGTH, value=form.context,
        )
    hints = {
        config.SINGLE: "Заполните от 2 до 8 вариантов и отметьте один верный.",
        config.CONTEXT: "Заполните контекст, от 2 до 8 вариантов и отметьте один верный.",
        config.MULTIPLE: "Заполните от 2 до 8 вариантов и отметьте все верные.",
        config.MATCHING: "Справа — варианты (A, B, C…), слева — строки. Вариантов может быть больше, "
                         "чем строк.",
    }
    return render(
        "question_form.html",
        title=title,
        note=note or SafeHTML(""),
        type_switch=_type_switch(base_url, form.qtype, form.subject),
        errors=views._errors_block(errors),
        action=action,
        csrf=views._csrf_field(request),
        qtype=form.qtype,
        subject_options=subject_options,
        context_field=context_field,
        text=form.text,
        text_max=TEXT_MAX_LENGTH,
        matching_rows=_matching_rows(form),
        options_legend="Варианты справа" if form.qtype == config.MATCHING else "Варианты ответа",
        option_hint=hints[form.qtype],
        option_rows=_option_rows(form),
        explanation=form.explanation,
        back_url=back_url,
        back_label=back_label,
        submit_label=submit_label,
    )


def requested_type(request: Request, default: str) -> str:
    """Тип вопроса из ?type= (или default)."""
    qtype = request.query_value("type")
    return qtype if qtype in config.QUESTION_TYPES else default


def duplicate_error() -> list[str]:
    """Сообщение о дубликате текста (UNIQUE subject + text)."""
    return ["У этого предмета уже есть вопрос с таким текстом (возможно, удалённый или на "
            "проверке). Измените формулировку."]


def preview(question: Question) -> SafeHTML:
    """Вопрос целиком для проверки: контекст, варианты (верные отмечены), объяснение."""
    context = (fragment('<p class="q-context">$c</p>', c=question.context)
               if question.context else SafeHTML(""))
    left = SafeHTML("")
    if question.qtype == config.MATCHING:
        left = fragment(
            '<ol class="preview-left">$rows</ol>',
            rows=join(fragment("<li>$text → <b>$letter</b></li>", text=text, letter=letter)
                      for text, letter in zip(question.left, question.correct)),
        )
    options = join(
        fragment('<li class="$cls"><b>$letter.</b> $text$mark</li>', letter=letter, text=text,
                 cls="preview-correct" if (letter in question.correct
                                           and question.qtype != config.MATCHING) else "",
                 mark=SafeHTML(" ✅" if letter in question.correct
                               and question.qtype != config.MATCHING else ""))
        for letter, text in zip(config.OPTION_LETTERS, question.options)
    )
    return fragment(
        '<div class="question-preview">'
        '<p class="muted small">$icon $subject · $type</p>$context'
        '<p class="q-text"><strong>$text</strong></p>$left<ul class="preview-options">$options</ul>'
        '<p class="small"><b>Объяснение:</b> $explanation</p></div>',
        icon=views._icon(question.subject), subject=config.SUBJECTS[question.subject].name,
        type=config.QUESTION_TYPE_NAMES[question.qtype], context=context, text=question.text,
        left=left, options=options, explanation=question.explanation,
    )
