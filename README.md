# PromoFlow

Multi-agent decision-support system for faculty promotion review (University of Sharjah senior project).
A human approves every step; the agents prepare and check the evidence.

## Stack

| Part | Choice |
| --- | --- |
| UI | Streamlit (calls the orchestrator in-process, no REST API) |
| Orchestration | LangGraph with human-in-the-loop gates and a PostgreSQL checkpointer |
| Database | PostgreSQL 16 + pgvector, run locally with Docker (privacy) |
| ORM / migrations | SQLAlchemy 2 / Alembic |
| Login | Local accounts (argon2id) now; university single sign-on (`st.login`) later |

## First-time setup

Prerequisites: Python 3.12+ and [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
docker compose up -d                 # PostgreSQL + pgvector on localhost:5432
python -m venv .venv
.venv\Scripts\activate               # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -e .[dev]
copy .env.example .env               # macOS/Linux: cp .env.example .env
alembic upgrade head                 # create all tables
python -m promoflow.db.seed          # policy criteria, rubrics, dropdown lists, dev accounts
streamlit run app/Home.py
```

Development accounts (password = `DEV_PASSWORD` in `.env`, default `promoflow-dev`):
`applicant@`, `hod.cs@`, `dean.comp@`, `chancellor@`, `admin@` — all `…@promoflow.test`.
They belong to a fictional college. Never put real faculty data in a development database.

### Trying the login without Docker

The login tables use only portable types, so they also run on SQLite:

```bash
set DATABASE_URL=sqlite:///data/dev_auth.db     # macOS/Linux: export DATABASE_URL=...
python scripts/init_sqlite_auth.py
streamlit run app/Home.py
```

## Tests

```bash
pytest
```

The tests need no database server: schema checks compile every table for PostgreSQL, and the login tests
(including the real Streamlit page, headless) run on in-memory SQLite.

## Changing the schema

1. Edit the models in `promoflow/db/models/`.
2. With the Docker database running: `alembic revision --autogenerate -m "short description"`, review the file.
3. `alembic upgrade head`, commit the model change and the migration together.
4. Refresh the schema document: `python scripts/export_schema.py`, `python scripts/draw_er_overview.py`,
   `node scripts/build_schema_doc.js PromoFlow_Database_Schema.docx` (needs `npm install docx`).

The first migration (`0001`) was generated without a database by `scripts/generate_initial_migration.py`.

## Layout

```
app/                 Streamlit pages (Home.py = login + dashboard)
promoflow/
  auth/              password hashing, sessions, roles (UI-independent)
  db/
    models/          SQLAlchemy models, one module per domain (65 tables)
    enums.py         fixed value lists used by the rules
    seed.py          reference data + dev accounts
  ui/                Streamlit helpers (login gate)
migrations/          Alembic
scripts/             migration generator, schema export, ER diagram, schema document builder
docs/                schema.json, schema.sql, er_overview.png
tests/
```

## Not yet built

Agents (Research, Teaching, Service, Chancellor's Office), Eligibility Checker, Report Builder, LangGraph graph,
dossier pages, review pages, Reminder & Webhook Worker, journal-ranking import.
