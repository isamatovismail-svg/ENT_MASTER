# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

ENT MASTER — a website for preparing for the ЕНТ (Kazakhstan's Unified National Test): full mock exams, per-subject practice, answer review, attempt history. UI text, comments, docstrings and the README are in Russian; keep new code consistent with that.

**Hard constraint:** Python 3.11+ standard library, HTML and CSS only. No JavaScript (the CSP header forbids all scripts), no frameworks, no third-party packages / `pip install`.

## Commands

```bash
python seed.py      # validate data/questions/*.json and upsert into SQLite (idempotent, keyed on subject+text)
python manage_admin.py <login> [--revoke]   # grant/revoke the admin role (user must be registered)
python bot.py       # Telegram bot (long polling); needs TELEGRAM_BOT_TOKEN in .env (see .env.example)
python main.py      # init DB and serve on http://localhost:8000 (127.0.0.1:8000 from config.py)
python run.py       # site + bot together (two subprocesses, logs prefixed [САЙТ]/[БОТ], Ctrl+C stops both; bot skipped with a warning if no token)

python -m unittest                                              # all tests
python -m unittest tests.test_auth                              # one module
python -m unittest tests.test_scoring.ScoreTests.test_matching  # one test
```

The local DB is `ent_master.sqlite3` in the repo root (gitignored). There is no linter/build config. The shared PyCharm run configuration «Run» (`.idea/runConfigurations/Run.xml`, the only tracked part of `.idea/`) launches `run.py`.

## Architecture

Request flow: `app/server.py` (`ThreadingHTTPServer` handler: parses request/cookies, serves `/static`, sets security headers, turns exceptions into a generic error page) → `auth.attach_user` resolves the session cookie → `router.dispatch` matches the `ROUTES` table (`<int:x>` / `<x>` path params; more specific paths must come first; path-match-but-wrong-method → 405) → view function in `app/views.py` → returns `web.Response`.

- **`config.py` is the single source of truth for exam structure**: subjects (`SubjectInfo` with per-question-type quotas), allowed profile pairs, points per question type, durations, security params. Totals (120 questions / 140 points) are derived from quotas — change the format here, not in logic code.
- **`app/database.py` holds all SQL** (parameterized only) and the dataclasses `User`, `Attempt`, `AttemptQuestion`. JSON columns (`options_json`, `correct_json`, `answer_json`, `subjects_json`, `shortage_json`) store lists. `database.configure(path)` swaps the DB file (used by tests). Schema changes to existing tables go in `_ADDED_COLUMNS` — `init_db()` ALTERs old databases, so the user's local `ent_master.sqlite3` survives upgrades.
- **Option shuffling**: each `attempt_questions` row stores `option_order_json` (shown index → original index). `get_attempt_questions()` returns options and `correct` already remapped to the *shown* letters, and `answer_json` is stored in shown letters — so all scoring/parsing/rendering code works in shown letters only. Explanations in `data/questions/*.json` must therefore never reference option letters.
- **`app/ent_logic.py`**: building attempts and scoring. `build_mock` picks random questions per subject per quota; if the bank is short it uses what exists and records a `shortage` list on the attempt, which the UI displays. Questions are shuffled within each subject. Scoring: single/context = 1 point; matching/multiple = 2 points with no mistakes, 1 with one mistake. Timer is server-side: `deadline` stored on the attempt (`mock_duration_minutes`: 240 × questions/120, ceil), expired attempts are auto-finished on the user's next request (`finish_expired_attempts`).
- **Two test modes with different UIs**: mock exam (`/attempt/<id>/<subject>`, no answer highlighting until the result page) and practice (`/practice/<id>`, one question per page: POST checks it via `check_practice_answer` → sets `checked=1`, then `/practice/<id>/review/<n>` shows red/green + explanation). Section/finish-confirm views redirect practice attempts to `/practice/<id>`; both modes finish via `POST /attempt/<id>/finish`.
- **CSP forbids inline `style` attributes** (and all scripts). Dynamic visuals use classes instead: `.subj-<code>` sets per-subject `--c1/--c2` colors (defined in `static/style.css`, emoji icon in `config.SubjectInfo.icon`), `.p-0…p-100` (step 5) for the result ring, and `<progress>` for bars. Dark theme is `prefers-color-scheme` overriding CSS variables.
- **Admin panel** (`app/admin_views.py`, routes under `/admin`): every view is wrapped in `admin_required` (= `views.login_required` + `user.is_admin`, else 403). `users.role` is `'user'`/`'admin'`. Question deletion is soft (`questions.deleted = 1`) when the question appears in any attempt, hard otherwise; every bank query (`random_questions`, `question_counts`, `list_questions`, `get_question`) must filter `deleted = 0`, while `get_attempt_questions` must not (old reviews keep working). Question validation lives in `app/question_bank.py`, shared by `seed.py` and the admin forms. Admin edits go to the DB only — `seed.py` overwrites/undeletes questions whose text matches the JSON. `views.result_content()` renders a result for both the student page and the admin attempt view.
- **Telegram bot** (`app/telegram_bot.py`, `bot.py`): stdlib `TelegramAPI` (urllib POST JSON) + `Bot.handle_update` + `run_polling`. The bot is stateless — multi-step answer state (checked letters for multiple, per-row letters for matching) lives in `callback_data` (`a:`/`t:`/`m:<attempt>:<aq>:<letters>`, ≤64 bytes). Bot practice uses the same `practice` attempts and `ent_logic.check_practice_answer` as the site, and requires a linked account (`users.telegram_id`, unique partial index created in `init_db`). Tests use a `FakeAPI` — never hit the network. `config.py` loads `.env` (`load_env`; real env vars win) for `TELEGRAM_BOT_TOKEN` and `SITE_URL`.
- **Telegram login** (`app/telegram_views.py`, `/tg/login`): one-time 10-minute tokens (`telegram_login_tokens`, SHA-256 stored). GET must never consume the token (link previews); consumption happens only on POST via `use_telegram_token`. Telegram-only accounts get login `tg<telegram_id>` and an unknown random password.
- **Mock test UI without JS**: each subject section is one HTML form; the subject tabs and Back/Next/Save/Finish are submit buttons of that same form, so every navigation POSTs and saves the section's answers first (`section_submit`), then redirects.
- **`app/templates.py`**: `string.Template` files in `templates/` with `$name` placeholders. Every substituted value is `html.escape`d unless it is a `SafeHTML` instance. Build HTML fragments with `fragment()`/`join()`/`render()` so escaping is preserved — never wrap untrusted strings in `SafeHTML`. Missing placeholders raise `KeyError`. Views wrap content via `views.page()` into `base.html`.
- **Auth (`app/auth.py`)**: PBKDF2-SHA256 passwords; session cookie holds a random token, DB stores only its SHA-256. `views.login_required` redirects anonymous users to `/login?next=…` and enforces the CSRF token on all POSTs — new POST forms for logged-in users must include `_csrf_field(request)`. Queries for attempts must always filter by `user_id`.

## Question bank

`data/questions/<subject>.json` — one file per subject, `"subject"` must be a code from `config.SUBJECTS`. Every question requires a non-empty `explanation` (validated by `seed.py`). Types: `single`, `context` (adds `context`), `matching` (adds `left`; `correct` has one letter per `left` row, in order), `multiple`. Options are lettered A–H by position. `seed.py` validates and rejects malformed questions. See README.md for the full format.

## Question generators

`app/generators/` builds computed questions (math, math_literacy, physics, chemistry, informatics) from templates, and fact-based questions from tables (`facts.py`: `Event`/`Fact` tables → «в каком году», «год → событие», «кто», «чем известен», matching; plus `Category` tables for multiple-choice «выберите все…», context templates (`by_description` uses `note` without the name, `by_about`, event notes) and `build()` that assembles all four ЕНТ types for a profile subject; used by every non-computed subject (history, geography, biology, law, languages, literatures via `literature.py`); `lang="ru"|"kk"|"en"` picks the service phrases (`PHRASES`) — Kazakh subjects are written in Kazakh, foreign_language in English; a template that keeps raising `SkipQuestion` counts as exhausted, so it never loops forever; `what_phrases` keeps the «чем известен» wording valid for every option in a group). Only subjects in `NUMERIC_SUBJECTS` get thousands spacing (years must stay «1771»). Computed templates: each template is `fn(rng: random.Random) -> dict` returning a question in the JSON format, built via `common.single` / `multiple` / `matching` (they shuffle options and set `correct` letters; ЕНТ format: 4 options for single/context, 6 with 1–3 correct for multiple, 2 rows + 4 options for matching). Answers are computed in code, never typed. `generators.generate(subject, qtype, count, seed)` is deterministic and dedupes by `text` (the DB unique key is `(subject, text)`, so a template must put its varying numbers into `text`, not only into `context`/`left`); output passes `common.polish` (thousands spacing) and `validate_question`. Raise `SkipQuestion` for unlucky random values. `seed.py` loads JSON files and then generated questions via `database.upsert_questions` (one transaction); `--no-generated` skips them. `database.random_questions(..., user_id)` orders by how many times this user has already seen each question, then `RANDOM()`, so unseen questions come first (index `idx_attempt_questions_question`).

## Tests

`tests/base.py::DatabaseTestCase` gives each test a fresh temp DB and lowers `PBKDF2_ITERATIONS` for speed; `add_questions` / `fill_full_bank` create synthetic questions. `tests/test_pages.py` starts the real server in a thread on a free port with the JSON question bank seeded (`seed.seed(with_generated=False)`, its assertions depend on those counts) and drives it via a urllib-based `Browser` (cookies, CSRF extraction from forms).
