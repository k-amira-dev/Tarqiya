"""Create only the login tables in a local SQLite file and seed the dev accounts.

For trying the login flow without Docker/PostgreSQL. Set DATABASE_URL first, e.g.
    DATABASE_URL=sqlite:///data/dev_auth.db python scripts/init_sqlite_auth.py
"""
import os
import subprocess
import sys
from pathlib import Path

from promoflow.config import DATABASE_URL
from promoflow.db.base import Base
from promoflow.db.models import AUTH_TABLES
from promoflow.db.session import engine

if not DATABASE_URL.startswith("sqlite"):
    sys.exit("DATABASE_URL must point to a sqlite:/// file for this script.")
Path("data").mkdir(exist_ok=True)
Base.metadata.create_all(engine, tables=AUTH_TABLES)
subprocess.run([sys.executable, "-m", "promoflow.db.seed", "--auth-only"], check=True, env=os.environ)
