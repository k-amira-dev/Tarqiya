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
# Make the connection to any remote database encrypted: add sslmode=require unless the URL already says what to do.
# A local database (a developer's own PostgreSQL) is left alone because it normally has no SSL.
def _require_ssl(url: str) -> str:
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    if "sslmode=" in (parts.query or "") or (parts.hostname or "localhost") in ("localhost", "127.0.0.1", "::1"):
        return url
    return url + ("&" if parts.query else "?") + "sslmode=require"


DATABASE_URL = _require_ssl(_setting("DATABASE_URL", "postgresql+psycopg://promoflow:promoflow@localhost:5432/promoflow"))

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

# The model "committee" for the Teaching and Service judgment items. EMPTY (the default) = one model, as before. To turn it on, list
# models as `provider:model`, comma-separated, e.g.
#   COMMITTEE_MODELS=groq:openai/gpt-oss-120b,groq:qwen/qwen3.8-27b,google:<a Gemini model name>
# Providers: `groq` (uses GROQ_API_KEY) and `google` (uses GEMINI_API_KEY, needs `pip install langchain-google-genai`).
COMMITTEE_MODELS = _setting("COMMITTEE_MODELS", "")
GEMINI_API_KEY = _setting("GEMINI_API_KEY", "")
# The models "disagree" on an item when the highest and lowest points differ by more than this share of the item's range
# (with a floor of 1 point). A disagreement flags the item "needs a human".
# Read scanned pages with OCR on THIS machine (1, the default) instead of sending the page picture to a vision model. Set 0 to turn it off.
LOCAL_OCR = _setting("LOCAL_OCR", "1").strip().lower() in ("1", "true", "yes")

# A model with a small context window gets its items in several requests instead of one. Format: `model=tokens`, comma-separated, e.g.
#   COMMITTEE_INPUT_BUDGETS=allam-2-7b=2000
# (allam-2-7b rejects a request above about 3,200 input tokens; 2,000 leaves room for its answer). Models not listed get one request.
# The free Groq plan refuses a request above a model's per-minute allowance (gpt-oss-120b: 8,000 tokens in and out; qwen: 1,000 output tokens),
# so by default these two models are asked ONE criterion per request (a budget of 1 puts every item alone; the retry waits for the minute to
# roll over). Gemini has no such limit and gets everything at once. Set the variable in .env to change it.
COMMITTEE_INPUT_BUDGETS = _setting("COMMITTEE_INPUT_BUDGETS", "openai/gpt-oss-120b=1,qwen/qwen3.8-27b=1")
# Cap on the tokens a model may write in one answer. Format `model=tokens`. qwen's allowance is 1,000 output tokens per minute and a request
# is refused when its max_tokens is above it, so one criterion's answer is limited to 900.
COMMITTEE_MAX_OUTPUT = _setting("COMMITTEE_MAX_OUTPUT", "qwen/qwen3.8-27b=900")
# Which Groq key each model uses, as `model=NAME_OF_THE_SETTING` (the NAME of a setting in .env, never the key itself), e.g.
#   GROQ_KEY_FOR=openai/gpt-oss-120b=GROQ_API_KEY_1,qwen/qwen3.8-27b=GROQ_API_KEY_2
# A model not listed uses GROQ_API_KEY. Groq's limits are per account, so keys from different accounts have separate allowances; to move to the
# next pair of keys, change the two names here.
GROQ_KEY_FOR = _setting("GROQ_KEY_FOR", "")
# The applicant assistant (the chat box in the app). It has its own model and, optionally, its own key so that its few small requests do not
# use the allowance the review agents need: ASSISTANT_KEY_VAR is the NAME of the setting holding that key (for example GROQ_API_KEY_1).
ASSISTANT_MODEL = _setting("ASSISTANT_MODEL", "groq:openai/gpt-oss-120b")
ASSISTANT_KEY_VAR = _setting("ASSISTANT_KEY_VAR", "").strip()
COMMITTEE_SPREAD = float(_setting("COMMITTEE_SPREAD", "0.25"))

# DEVELOPMENT ONLY. When set to 1, the submission-window rule (first week of January, April and October) is ignored,
# so a whole dossier can be submitted and reviewed on any day. Leave it unset everywhere else. The Review & Submit
# page shows a warning banner while it is on.
DEV_IGNORE_SUBMISSION_WINDOW = _setting("DEV_IGNORE_SUBMISSION_WINDOW", "").strip().lower() in ("1", "true", "yes")

# How long a login lasts, and how the lock-out works after repeated wrong passwords.
SESSION_HOURS =int(_setting("SESSION_HOURS", "8"))
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15

# Scholarly data, used by both: OpenAlex only
OPENALEX_API_KEY = _setting("OPENALEX_API_KEY", "")   # set it in .env or Streamlit Secrets: never put a key in code

# Security keys (never in code; set them in .env or Streamlit Secrets, and keep a copy outside the repo).
# DOCUMENT_ENCRYPTION_KEY: 32 random bytes, URL-safe base64, used to encrypt every stored evidence file (AES-256-GCM).
# AUDIT_HMAC_KEY: a long random string that seals the audit log and the model-score records against edits.
DOCUMENT_ENCRYPTION_KEY = _setting("DOCUMENT_ENCRYPTION_KEY", "").strip()
AUDIT_HMAC_KEY = _setting("AUDIT_HMAC_KEY", "").strip()

# Reviewer Outreach only. Our own institution, for the referee "same institution" conflict check.
INSTITUTION_NAME = _setting("INSTITUTION_NAME", "University of Sharjah")
INSTITUTION_OPENALEX_ID = _setting("INSTITUTION_OPENALEX_ID", "")   # e.g. I123456789 (look it up on openalex.org)
# Reviewer Outreach only. Outgoing referee emails; with no SMTP_HOST, messages stay queued and nothing is sent.
SMTP_HOST = _setting("SMTP_HOST", "")
SMTP_PORT = int(_setting("SMTP_PORT", "587"))
SMTP_USER = _setting("SMTP_USER", "")
SMTP_PASSWORD = _setting("SMTP_PASSWORD", "")
OUTREACH_FROM = _setting("OUTREACH_FROM", "")              # the sender address the referees see
# Reviewer Outreach only. When "true", the applicant is told the referee result the moment the last needed report arrives. Default: a person from
# the Chancellor's Office releases it first.
REFEREE_RESULT_AUTO_RELEASE = _setting("REFEREE_RESULT_AUTO_RELEASE", "false").strip().lower() in ("1", "true", "yes")
# Reviewer Outreach only. The public address of this application: the Accept / Decline links in referee emails point here.
APP_BASE_URL = _setting("APP_BASE_URL", "http://localhost:8501")
# SAFETY SWITCH for testing and demos: when set, EVERY outgoing referee email goes only to this address (the real recipient is shown in
# the subject), so a test can never reach a real researcher. Leave it empty only in production.
OUTREACH_REDIRECT_TO = _setting("OUTREACH_REDIRECT_TO", "")
