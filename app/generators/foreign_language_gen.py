"""Foreign language (English): grammar and vocabulary. Questions are in English."""

import random

from app.generators.common import SkipQuestion, matching, single
from app.generators.facts import Category, Fact, build

IRREGULAR = [("go", "went", "gone"), ("buy", "bought", "bought"), ("bring", "brought", "brought"), ("see", "saw", "seen"),
             ("take", "took", "taken"), ("write", "wrote", "written"), ("eat", "ate", "eaten"),
             ("give", "gave", "given"), ("begin", "began", "begun"), ("drink", "drank", "drunk"),
             ("swim", "swam", "swum"), ("speak", "spoke", "spoken"), ("break", "broke", "broken"),
             ("choose", "chose", "chosen"), ("know", "knew", "known"), ("fly", "flew", "flown"),
             ("drive", "drove", "driven"), ("find", "found", "found"), ("think", "thought", "thought"),
             ("teach", "taught", "taught"), ("catch", "caught", "caught"), ("sleep", "slept", "slept"),
             ("leave", "left", "left"), ("feel", "felt", "felt"), ("make", "made", "made"), ("run", "ran", "run"),
             ("come", "came", "come"), ("get", "got", "got"), ("do", "did", "done"), ("sing", "sang", "sung"),
             ("wear", "wore", "worn"), ("forget", "forgot", "forgotten"), ("tell", "told", "told"),
             ("sell", "sold", "sold"), ("build", "built", "built"), ("send", "sent", "sent"),
             ("spend", "spent", "spent"), ("lose", "lost", "lost")]
REGULAR = ["play", "watch", "help", "clean", "cook", "visit", "open", "listen", "walk", "work", "jump", "paint"]


def _regular_past(verb: str) -> str:
    """Typical learner's mistake: adding -ed to an irregular verb."""
    if verb.endswith("e"):
        return verb + "d"
    if verb.endswith("y"):
        return verb[:-1] + "ied"
    return verb + "ed"


def past_simple(rng: random.Random) -> dict:
    base, v2, v3 = rng.choice(IRREGULAR)
    other = rng.choice([v for v in IRREGULAR if v[0] != base])
    wrong = [_regular_past(base), v3 if v3 != v2 else base + "s", other[1], base + "ing"]
    return single(rng, f"What is the Past Simple form of the verb «{base}»?", v2, wrong,
                  f"«{base}» is an irregular verb: {base} — {v2} — {v3}.")


def past_participle(rng: random.Random) -> dict:
    base, v2, v3 = rng.choice(IRREGULAR)
    wrong = [_regular_past(base), v2 if v2 != v3 else base + "s", base + "ing", base + "en" if base + "en" != v3
             else base + "ed"]
    return single(rng, f"What is the Past Participle (V3) of the verb «{base}»?", v3, wrong,
                  f"«{base}» is an irregular verb: {base} — {v2} — {v3}.")


_THIRD = ["He", "She", "My brother", "Aigerim", "Our teacher", "The cat"]
_OTHERS = ["I", "You", "We", "They", "My friends", "The students"]
_VERBS = [("go", "goes", "to school"), ("play", "plays", "football"), ("watch", "watches", "TV in the evening"),
          ("do", "does", "homework"), ("read", "reads", "books"), ("drink", "drinks", "tea"),
          ("study", "studies", "English"), ("wash", "washes", "the dishes"), ("help", "helps", "at home"),
          ("get up", "gets up", "at 7 o'clock")]


_VERB_ING = {"go": "going", "play": "playing", "watch": "watching", "do": "doing", "read": "reading",
             "drink": "drinking", "study": "studying", "wash": "washing", "help": "helping", "get up": "getting up"}


def present_simple(rng: random.Random) -> dict:
    third = rng.random() < 0.5
    subject = rng.choice(_THIRD if third else _OTHERS)
    base, s_form, rest = rng.choice(_VERBS)
    answer = s_form if third else base
    wrong = [base if third else s_form, _VERB_ING[base], "is " + base, "are " + base]
    rule = ("With he / she / it the verb takes -s (-es) in the Present Simple" if third
            else "With I / you / we / they the verb has no ending in the Present Simple")
    return single(rng, f"Choose the correct form: {subject} ___ ({base}) {rest} every day.", answer, wrong,
                  f"{rule}: {subject} {answer} {rest} every day.")


_ING = {"read": "reading", "swim": "swimming", "dance": "dancing", "write": "writing", "run": "running",
        "play": "playing", "cook": "cooking", "sing": "singing", "sleep": "sleeping", "draw": "drawing"}


def present_continuous(rng: random.Random) -> dict:
    subject, aux = rng.choice([("I", "am"), ("She", "is"), ("He", "is"), ("They", "are"), ("We", "are"),
                               ("The children", "are"), ("My mother", "is"), ("You", "are")])
    verb, ing = rng.choice(list(_ING.items()))
    answer = f"{aux} {ing}"
    others = [a for a in ("am", "is", "are") if a != aux]
    wrong = [f"{others[0]} {ing}", f"{others[1]} {ing}", verb if subject not in ("She", "He", "My mother") else verb + "s",
             ing]
    return single(rng, f"Look! {subject} ___ ({verb}) now.", answer, wrong,
                  f"An action happening now — Present Continuous: am / is / are + -ing. {subject} {answer} now.")


PLURALS = [("child", "children"), ("man", "men"), ("woman", "women"), ("mouse", "mice"), ("tooth", "teeth"),
           ("foot", "feet"), ("person", "people"), ("sheep", "sheep"), ("goose", "geese"), ("knife", "knives"),
           ("leaf", "leaves"), ("box", "boxes"), ("city", "cities"), ("potato", "potatoes")]


def plural(rng: random.Random) -> dict:
    word, answer = rng.choice(PLURALS)
    wrong = [word + "s", word + "es", answer + "s", word + "ies"]
    return single(rng, f"What is the plural of «{word}»?", answer, wrong, f"The plural of «{word}» is «{answer}».")


COMPARATIVES = [("good", "better", "the best"), ("bad", "worse", "the worst"), ("big", "bigger", "the biggest"),
                ("happy", "happier", "the happiest"), ("beautiful", "more beautiful", "the most beautiful"),
                ("hot", "hotter", "the hottest"), ("interesting", "more interesting", "the most interesting"),
                ("little", "less", "the least"), ("many", "more", "the most"), ("easy", "easier", "the easiest"),
                ("tall", "taller", "the tallest"), ("expensive", "more expensive", "the most expensive")]


def comparative(rng: random.Random) -> dict:
    word, comp, sup = rng.choice(COMPARATIVES)
    if rng.random() < 0.5:
        wrong = [word + "er" if word + "er" != comp else "more " + word, "more " + comp, sup, "most " + word]
        return single(rng, f"Choose the comparative form of «{word}».", comp, wrong,
                      f"{word} — {comp} — {sup}.")
    wrong = [comp, "the " + word + "est" if "the " + word + "est" != sup else "the more " + word,
             "most " + comp, "the " + comp]
    return single(rng, f"Choose the superlative form of «{word}».", sup, wrong, f"{word} — {comp} — {sup}.")


PREPOSITIONS = [("Monday", "on"), ("July", "in"), ("7 o'clock", "at"), ("2020", "in"), ("night", "at"),
                ("the morning", "in"), ("my birthday", "on"), ("winter", "in"), ("noon", "at"), ("15 May", "on"),
                ("the 21st century", "in"), ("Friday evening", "on"), ("midnight", "at"), ("summer", "in"),
                ("New Year's Day", "on"), ("half past six", "at")]


def preposition(rng: random.Random) -> dict:
    item, answer = rng.choice(PREPOSITIONS)
    rule = {"on": "days and dates", "in": "months, years, seasons, centuries and parts of the day",
            "at": "clock times, night, noon and midnight"}[answer]
    return single(rng, f"Choose the correct preposition: ___ {item}.", answer,
                  [p for p in ("in", "on", "at", "by") if p != answer], f"We use «{answer}» with {rule}.")


VOCAB = [
    ("library", "a place where you can borrow books"), ("hospital", "a place where sick people are treated"),
    ("airport", "a place where planes take off and land"), ("museum", "a place where you can see old and valuable objects"),
    ("pharmacy", "a shop where you can buy medicine"), ("bakery", "a shop where bread and cakes are made and sold"),
    ("stadium", "a large place where people watch sports games"), ("zoo", "a place where wild animals are kept for people to see"),
    ("pilot", "a person who flies a plane"), ("dentist", "a doctor who looks after your teeth"),
    ("farmer", "a person who grows crops or keeps animals"), ("journalist", "a person who writes news for newspapers or TV"),
    ("architect", "a person who designs buildings"), ("vet", "a doctor who treats animals"),
    ("cook", "a person who prepares food"), ("lawyer", "a person who gives legal advice and helps people in court"),
]
FACTS = [Fact(word, meaning, f"Which word means «{meaning}»?", "1", "word") for word, meaning in VOCAB]
FACTS += [Fact(base, v2, f"Which verb has the Past Simple form «{v2}»?", "1", "verb") for base, v2, _ in IRREGULAR]
TITLES = {"word": "the words with their meanings", "verb": "the verbs with their Past Simple forms"}
WHAT = {"word": "What does the word «{name}» mean?", "verb": "Which is the Past Simple form of «{name}»?"}


def verb_matching(rng: random.Random) -> dict:
    picked = rng.sample(IRREGULAR, 4)
    if len({p[2] for p in picked}) < 4:
        raise SkipQuestion
    a, b = picked[:2]
    text = f"Match the verbs with their Past Participle (V3): 1) {a[0]}; 2) {b[0]}."
    return matching(rng, text, [(a[0], a[2]), (b[0], b[2])], [p[2] for p in picked[2:]],
                    f"{a[0]} — {a[1]} — {a[2]}; {b[0]} — {b[1]} — {b[2]}.")


TENSES = ["Present Simple", "Present Continuous", "Present Perfect", "Past Simple", "Past Continuous",
          "Past Perfect", "Future Simple", "Future Continuous"]
TENSE_SENTENCES = [
    ("She has lived in Almaty since 2015.", "has lived", "Present Perfect"),
    ("They were playing football when it started to rain.", "were playing", "Past Continuous"),
    ("I will call you tomorrow.", "will call", "Future Simple"),
    ("We usually have breakfast at 8.", "have", "Present Simple"),
    ("Look! The baby is sleeping.", "is sleeping", "Present Continuous"),
    ("He visited his grandparents last summer.", "visited", "Past Simple"),
    ("By the time we arrived, the film had started.", "had started", "Past Perfect"),
    ("I have just finished my homework.", "have finished", "Present Perfect"),
    ("Tomorrow at 5 p.m. I will be flying to London.", "will be flying", "Future Continuous"),
    ("Water boils at 100 degrees.", "boils", "Present Simple"),
    ("She is writing a letter now.", "is writing", "Present Continuous"),
    ("We were watching TV at 9 o'clock yesterday.", "were watching", "Past Continuous"),
    ("They had left before I came.", "had left", "Past Perfect"),
    ("I saw a great film yesterday.", "saw", "Past Simple"),
    ("Next year I will start university.", "will start", "Future Simple"),
    ("Have you ever been to Turkistan?", "have been", "Present Perfect"),
    ("At this time tomorrow we will be sitting in the exam.", "will be sitting", "Future Continuous"),
    ("My father works at a bank.", "works", "Present Simple"),
    ("When I came home, my sister was cooking dinner.", "was cooking", "Past Continuous"),
    ("The students are listening to the teacher at the moment.", "are listening", "Present Continuous"),
]


def tense_in_context(rng: random.Random) -> dict:
    sentence, verb, tense = rng.choice(TENSE_SENTENCES)
    wrong = rng.sample([t for t in TENSES if t != tense], 3)
    return single(rng, f"Read the sentence. Which tense is the verb «{verb}» in: «{sentence}»?", tense, wrong,
                  f"«{verb}» is {tense}.", context=sentence)


CATEGORIES = [
    Category("Which of these verbs are irregular", tuple(v[0] for v in IRREGULAR), tuple(REGULAR),
             "Irregular verbs do not form the past with -ed."),
    Category("Which of these nouns are uncountable",
             ("water", "information", "advice", "furniture", "money", "music", "bread", "homework"),
             ("apple", "chair", "book", "idea", "coin", "song", "bottle", "friend"),
             "Uncountable nouns have no plural form and are not used with «a / an»."),
    Category("Which of these words are adjectives",
             ("beautiful", "quick", "happy", "large", "careful", "difficult"),
             ("quickly", "happily", "beauty", "run", "carefully", "slowly", "teacher"),
             "Adjectives describe nouns; words ending in -ly here are adverbs."),
]

TEMPLATES = build(facts=FACTS, titles=TITLES, what_phrases=WHAT, categories=CATEGORIES, lang="en",
                  extra={"single": [past_simple, past_participle, present_simple, present_continuous, plural,
                                    comparative, preposition],
                         "matching": [verb_matching], "context": [tense_in_context]})
