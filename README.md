# PromoFlow

Multi-agent decision-support system for faculty promotion review (University of Sharjah senior project).
A human approves every step; the agents prepare and check the evidence.

## How the project is organised

Everything in this repository is **code or configuration**. The *data* (accounts, applications, agent results) lives
in the Supabase database, not here, so cloning the repository never gives you anyone's data. The top level has four
folders, and each one has a reason to exist.

**`app/`** is the front door of the website. It holds one small file, `Home.py`, which is what you start
(`streamlit run app/Home.py`) and what Streamlit Cloud runs. It does three things only: show the login page, work out
which pages this person may see (applicant, Head of Department, Dean, ...), and run the page they picked. All the real
work happens in `promoflow/`. It is kept separate and tiny because Streamlit needs a script to start from, and
everything that matters should live in code that can be imported and tested.

**`.streamlit/`** holds Streamlit's own settings. `config.toml` sets the University of Sharjah green theme and the 25 MB
upload limit. Streamlit looks for a folder with exactly this name, so it cannot be renamed. Passwords and keys never go
here: the file `.streamlit/secrets.toml` is ignored by Git, and Streamlit Cloud keeps its secrets in its own settings.

**`migrations/`** is the history of the database's *structure*. The database has 65 tables, and instead of creating
them by hand, every change is a numbered file in `migrations/versions/` (`0001` creates everything, `0002` to `0004`
add later columns). Running `alembic upgrade head` builds a database, or brings an old one up to date, so everyone's
database matches the code. If you change a table in `promoflow/db/models/`, add a migration in the same commit
(see "Changing the database schema" below).

**`promoflow/`** is the application itself, written as one Python package, so files import each other as
`promoflow.db`, `promoflow.workflow` and so on. Inside it:

- **`auth/`**: password hashing, login sessions and role checks. It contains no Streamlit code, so it can be tested alone.
- **`db/`**: everything about the database. `models/` defines the tables, one file per area (case, research, teaching,
  service, referees, assessment for agent results, reports and gate decisions, audit, organisation, reference data).
  `enums.py` holds the fixed lists such as case statuses and roles. `session.py` is how pages and agents open a database
  connection. `seed.py` loads the criteria, the rubrics, the dropdown lists and the test accounts.
- **`dossier/`**: the applicant's form as *logic*, not screens. For each section (0 to 11) it knows how to load, validate
  and save the data, and it records every change in the audit log. The pages and the tests both use this code.
- **`rules/`**: the deterministic policy checks, with no language model: eligibility rules and journal classification.
  These are plain functions, so they are easy to test and to explain to a committee.
- **`ui/`**: everything the user sees. `theme.py` is the colours and styling, `shell.py` the sidebar, `auth.py` the login
  screens, `cache.py` a per-session cache (the database is far away, so repeated queries are slow), and `views/` has one
  file or folder per page: the dossier sections, the dashboard and the Reviews page.
- **`workflow/`**: the agents and the process that connects them.
  - `graph.py` is the flow itself: Eligibility, then Research, Teaching and Service in parallel, then the Report
    Builder, then the Head of Department and Dean approvals, then the Chancellor's referee selection.
  - `service.py` is the only thing the pages call to start or continue a review (`start_review`, `resume`,
    `get_status`). It runs the graph in the background and keeps the case status up to date.
  - `schemas.py` defines the format every agent must return, and the data that travels through the graph.
  - `persist.py` saves an agent's result into the database tables, `verify.py` checks that every claim cites real
    records, and `llm.py` is the one place where the language model is created.
  - `tools.py` has small helper commands (`demo`, `draw`, `setup-db`, `review-demo`).
  - `nodes/` has **one file per agent**: `eligibility.py`, `research.py`, `teaching.py`, `service.py`, `report.py` and
    `chancellor.py`. Each exposes one function, `run(state)`, which returns its result in the shared format. This is
    where each person works, so two people rarely edit the same file: Khadidja's agents are `research.py` and
    `chancellor.py`.
- **Single files:** `config.py` reads settings from `.env` or Streamlit Secrets, `admin.py` creates accounts and
  resets passwords, `storage.py` saves uploaded evidence files, and `countries.py` is the country list.

**`tests/`** holds the automated checks, run with `pytest`. There is roughly one file per area of the code. They run
without PostgreSQL (a temporary SQLite database is used) and without a real language model (a fake one is used), so
anyone can run them with no keys and no internet. Run them before every push: they are how we change shared code without
breaking each other's work.

A few files sit at the top level as well. `pyproject.toml` lists the project and its libraries (add a new library here),
`requirements.txt` is the one line Streamlit Cloud uses to install the project, `alembic.ini` configures the migrations,
`.gitignore` lists what must never reach GitHub (`.env`, `.venv`, caches), and `.gitattributes` keeps line endings
consistent between Windows and Mac. `b-codespace-end` is Khadidja's first graph prototype, kept for reference.

## Stack

| Part | Choice |
| --- | --- |
| UI | Streamlit (calls the orchestrator in-process, no REST API) |
| Orchestration | LangGraph with human-in-the-loop gates and a PostgreSQL checkpointer |
| Database | PostgreSQL + pgvector on Supabase (shared test environment) |
| ORM / migrations | SQLAlchemy 2 / Alembic |
| Hosting | Streamlit Community Cloud – redeploys automatically on every push to `main` |
| Login | Local accounts (argon2id) now; university single sign-on (`st.login`) later |

**The online environment holds fictional data only.** A real deployment would run on university infrastructure.

## Setup for developers

Prerequisite: Python 3.12+.

```bash
git clone https://github.com/seniorprojeco-ux/promoflow.git
cd promoflow
python -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]     # macOS/Linux: .venv/bin/python -m pip install -e .[dev]
```

Create a file named `.env` in the project folder (it is never committed). Only the first line is required; ask the
team lead for the connection string privately, never share it on GitHub or in a chat group:

```
DATABASE_URL=postgresql+psycopg://...        # Supabase: Connect > Session pooler, with the password filled in
GROQ_API_KEY=...                             # only needed to run the language-model agents
DEV_PASSWORD=...                             # optional: password of the seeded test accounts (default promoflow-dev)
```

Then run the app:

```bash
.venv\Scripts\python -m streamlit run app/Home.py
```

Your local app uses the same shared database as the online app, so everyone sees the same data.

Test accounts (password = `DEV_PASSWORD`, default `promoflow-dev`): `applicant@`, `hod.cs@`, `dean.comp@`,
`chancellor@`, `admin@` — all `…@promoflow.test`, in a fictional college.

To look at the data: Supabase dashboard → **Table Editor**.

## Creating accounts

Until the Admin › Users & roles page exists, accounts are created from the command line. The password is
typed at a hidden prompt and never stored in plain text:

```bash
.venv\Scripts\python -m promoflow.admin create-user --email name@sharjah.ac.ae --name "Dr. Full Name" --college "College name" --department "Department name"
.venv\Scripts\python -m promoflow.admin set-password --email name@sharjah.ac.ae
```

Add `--role hod`, `--role dean`, ... for reviewers (default: applicant). New colleges and departments are
created automatically.

## Tests

```bash
.venv\Scripts\python -m pytest
```

No database needed: schema checks compile every table for PostgreSQL, and the login tests (including the real
Streamlit page, headless) run on in-memory SQLite.

## Changing the database schema

The database is shared, so coordinate with the team before changing it.

1. Edit the models in `promoflow/db/models/`.
2. `.venv\Scripts\python -m alembic revision --autogenerate -m "short description"`, then review the new file in
   `migrations/versions/`.
3. `.venv\Scripts\python -m alembic upgrade head`, and commit the model change and the migration together.

Reference data (criteria, rubrics, dropdown lists, test accounts) is loaded with
`.venv\Scripts\python -m promoflow.db.seed` (safe to run again; it never duplicates rows).

## Status

Built: the applicant side (dossier sections 0 to 11, with live eligibility preview and submission), the Eligibility
Checker, the Teaching Agent, the Report Builder, the workflow graph with the Head of Department and Dean approval
pages, and the review service that connects the pages to the agents.

Not built yet: the Research, Service and Chancellor's Office agents (placeholders in `promoflow/workflow/nodes/`),
the Chancellor's referee-selection page, file storage on Supabase, the admin pages, the Reminder and Webhook Worker,
and the journal-ranking import.
