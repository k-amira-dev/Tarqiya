"""Settings read from the environment (.env in development). See .env.example."""
import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://promoflow:promoflow@localhost:5432/promoflow")

# Must match the embedding model chosen for the policy knowledge base; changing it needs a migration.
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))

# Evidence files are stored on local disk, never in a third-party cloud (privacy decision).
EVIDENCE_DIR = os.getenv("EVIDENCE_DIR", "./data/evidence")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # same limit as the university's current platform

SESSION_HOURS = int(os.getenv("SESSION_HOURS", "8"))
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15
