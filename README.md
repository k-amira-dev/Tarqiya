# PromoFlow

Multi-agent decision-support system for faculty promotion review (University of Sharjah senior project).
A human approves every step; the agents prepare and check the evidence.

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
git clone https://github.com/k-amira-dev/PromoFlow.git
cd PromoFlow
python -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]     # macOS/Linux: .venv/bin/python -m pip install -e .[dev]
copy .env.example .env                           # macOS/Linux: cp .env.example .env
```

Put the Supabase connection string in `.env` (ask the team lead privately), then run the app:

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

## Layout

```
app/Home.py          entry point: login gate, role-based navigation
.streamlit/          theme (UoS palette) and client settings
promoflow/
  auth/              password hashing, sessions, roles (UI-independent)
  db/
    models/          SQLAlchemy models, one module per domain (65 tables)
    enums.py         fixed value lists used by the rules
    seed.py          reference data + test accounts
  dossier/           load/save logic per dossier section (section0.py)
  rules/             deterministic checks, no LLM (eligibility.py)
  ui/
    theme.py         design system: colours, fonts, cards, CSS for Streamlit widgets
    auth.py          login and first-login profile screens
    shell.py         black sidebar with the dossier navigator
    views/           one module per page (dashboard, section0)
  config.py          settings from .env or Streamlit Secrets
migrations/          Alembic
tests/
requirements.txt     used by Streamlit Community Cloud
```

## Not yet built

Agents (Research, Teaching, Service, Chancellor's Office), Eligibility Checker, Report Builder, LangGraph graph,
dossier sections 1–11, review pages, file storage on Supabase, Reminder & Webhook Worker, journal-ranking import.
