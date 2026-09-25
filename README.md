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
docker compose up -d                 # PostgreSQL + pgvector (localhost:5432) and pgAdmin (localhost:5050)
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

### Looking at the data

Open http://localhost:5050 (pgAdmin). The server "PromoFlow (local)" is already registered; the first time
you open it, enter the database password `promoflow`. Tables are under
Databases → promoflow → Schemas → public → Tables; right-click a table → View/Edit Data → All Rows.

## Tests

```bash
pytest
```

No database server needed: schema checks compile every table for PostgreSQL, and the login tests (including
the real Streamlit page, headless) run on in-memory SQLite.

## Changing the schema

1. Edit the models in `promoflow/db/models/`.
2. With the Docker database running: `alembic revision --autogenerate -m "short description"`, then review the file.
3. `alembic upgrade head`, and commit the model change and the migration together.
4. Teammates pull and run `alembic upgrade head`.

## Online test deployment

The shared test app runs on Streamlit Community Cloud (entry point `app/Home.py`, packages from
`requirements.txt`) with a Supabase PostgreSQL database. Every push to `main` redeploys it. The database
address is set in the app's Secrets as `DATABASE_URL`, never in the repository.
**Only fictional data goes into the online deployment.**

## Sharing the app for testing

Each developer's database is on their own laptop. To let teammates test against *your* data, run the app and
give them the "Network URL" Streamlit prints (same Wi-Fi only; your laptop must stay on). The database and
pgAdmin are bound to 127.0.0.1, so only the app is reachable from the network. Use fictional data only.

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
docker/              pgAdmin server registration
tests/
```

## Not yet built

Agents (Research, Teaching, Service, Chancellor's Office), Eligibility Checker, Report Builder, LangGraph graph,
dossier pages, review pages, Reminder & Webhook Worker, journal-ranking import.
