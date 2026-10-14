"""Settings, looked up in this order: environment variables (.env in development), then Streamlit Secrets
(Streamlit Community Cloud), then the defaults below. The settings are listed in the README."""
import os

from dotenv import load_dotenv

load_dotenv()


# Look up one setting. Order: an environment variable (this is where the .env file puts values), then Streamlit
# Cloud's Secrets, then the default given here.
def _setting(name: str, default: str) -> str:
    if name in os.environ:
        return os.environ[name]
    try:
        from streamlit.runtime import exists

        if exists():  # only inside a running Streamlit app; scripts and tests skip this
            import streamlit as st

            if name in st.secrets:
                return str(st.secrets[name])
    except Exception:
        pass
    return default


# Where the database is. The default points at a local PostgreSQL that only exists on a developer's machine; in
# practice it is always overridden in .env or Secrets.
DATABASE_URL = _setting("DATABASE_URL", "postgresql+psycopg://promoflow:promoflow@localhost:5432/promoflow")

# Must match the embedding model chosen for the policy knowledge base; changing it needs a migration.
EMBEDDING_DIM = int(_setting("EMBEDDING_DIM", "1536"))

# Local folder for evidence files in development; the online test deployment will use Supabase Storage.
EVIDENCE_DIR = _setting("EVIDENCE_DIR", "./data/evidence")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # same limit as the university's current platform

# LLM used by the agents (Groq, free tier). The key lives only in .env / Streamlit Secrets, never in git.
GROQ_API_KEY = _setting("GROQ_API_KEY", "")
# The model name must be one the key can use today. Groq retires models over time (llama-3.3-70b-versatile no longer
# works); the list of available models is at https://api.groq.com/openai/v1/models (needs the key).
GROQ_MODEL = _setting("GROQ_MODEL", "openai/gpt-oss-120b")

# DEVELOPMENT ONLY. When set to 1, the submission-window rule (first week of January, April and October) is ignored,
# so a whole dossier can be submitted and reviewed on any day. Leave it unset everywhere else. The Review & Submit
# page shows a warning banner while it is on.
DEV_IGNORE_SUBMISSION_WINDOW = _setting("DEV_IGNORE_SUBMISSION_WINDOW", "").strip().lower() in ("1", "true", "yes")

# How long a login lasts, and how the lock-out works after repeated wrong passwords.
SESSION_HOURS =int(_setting("SESSION_HOURS", "8"))
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15
