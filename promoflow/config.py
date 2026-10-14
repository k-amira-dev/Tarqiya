"""Settings, looked up in this order: environment variables (.env in development), then Streamlit Secrets
(Streamlit Community Cloud), then the defaults below. The settings are listed in the README."""
import os

from dotenv import load_dotenv

load_dotenv()


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


DATABASE_URL = _setting("DATABASE_URL", "postgresql+psycopg://promoflow:promoflow@localhost:5432/promoflow")

# Must match the embedding model chosen for the policy knowledge base; changing it needs a migration.
EMBEDDING_DIM = int(_setting("EMBEDDING_DIM", "1536"))

# Local folder for evidence files in development; the online test deployment will use Supabase Storage.
EVIDENCE_DIR = _setting("EVIDENCE_DIR", "./data/evidence")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # same limit as the university's current platform

# LLM used by the agents (Groq, free tier). The key lives only in .env / Streamlit Secrets, never in git.
GROQ_API_KEY = _setting("GROQ_API_KEY", "")
GROQ_MODEL = _setting("GROQ_MODEL", "llama-3.3-70b-versatile")

SESSION_HOURS =int(_setting("SESSION_HOURS", "8"))
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15
