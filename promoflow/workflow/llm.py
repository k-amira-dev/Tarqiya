"""The single place that creates the LLM. Agents call `get_llm()`; none of them import a provider directly, so
switching from Groq to another provider later is a change in this file only."""
from promoflow.config import ASSISTANT_KEY_VAR, ASSISTANT_MODEL, COMMITTEE_MAX_OUTPUT, COMMITTEE_MODELS, GEMINI_API_KEY, GROQ_API_KEY, GROQ_KEY_FOR, GROQ_MODEL, _setting


def groq_key_name(model: str) -> str:
    """The NAME of the setting holding the Groq key this model uses (GROQ_KEY_FOR, else GROQ_API_KEY)."""
    for part in GROQ_KEY_FOR.split(","):
        name, _, var = part.partition("=")
        if name.strip() == model and var.strip():
            return var.strip()
    return "GROQ_API_KEY"


def groq_key(model: str) -> str:
    return (_setting(groq_key_name(model), "") or GROQ_API_KEY).strip()


def _max_output(name: str) -> int | None:
    """The answer-length cap for a model from COMMITTEE_MAX_OUTPUT ("model=tokens,..."), or None = the provider default."""
    for part in COMMITTEE_MAX_OUTPUT.split(","):
        model, _, tokens = part.partition("=")
        if model.strip() == name and tokens.strip().isdigit():
            return int(tokens)
    return None


# Raised when no API key is set. Callers catch it and carry on without the model instead of crashing.
class LLMNotConfigured(RuntimeError):
    pass


# Build the chat model. Every agent gets its model from here, so switching provider (Groq, Nebius, ...) is a change
# to THIS function only.
def get_llm(temperature: float = 0.0):
    """Chat model for the agents. Temperature 0 keeps runs as repeatable as possible."""
    # No key = no model. The key is read from .env or Streamlit Secrets (see config.py), never written in code.
    key = groq_key(GROQ_MODEL)
    if not key:
        raise LLMNotConfigured("GROQ_API_KEY is not set. Add it to .env (see the README).")
    from langchain_groq import ChatGroq  # imported here so tests and rule-only code never need the key

    return ChatGroq(model=GROQ_MODEL, api_key=key, temperature=temperature)


# The model for the applicant assistant: short answers, a hard time limit (a person is waiting), at most one retry.
def get_assistant_llm():
    provider, _, name = ASSISTANT_MODEL.strip().partition(":")
    if not name:
        provider, name = "groq", ASSISTANT_MODEL.strip()
    if provider.lower() == "groq":
        key = (_setting(ASSISTANT_KEY_VAR, "") if ASSISTANT_KEY_VAR else "").strip() or groq_key(name)
        if not key:
            raise LLMNotConfigured("No Groq key for the assistant: set GROQ_API_KEY or ASSISTANT_KEY_VAR.")
        from langchain_groq import ChatGroq

        extra = {"reasoning_effort": "low"} if name.startswith("openai/gpt-oss") else {}      # a short factual answer needs no long reasoning
        return ChatGroq(model=name, api_key=key, temperature=0.2, max_tokens=700, timeout=25, max_retries=1, **extra)
    return get_model(ASSISTANT_MODEL, 0.2)


# Build ONE committee member from a "provider:model" string (see COMMITTEE_MODELS in config.py).
def get_model(spec: str, temperature: float = 0.0):
    provider, _, name = spec.strip().partition(":")
    if not name:                                        # a bare model name means Groq
        provider, name = "groq", spec.strip()
    provider = provider.lower()
    if provider == "groq":
        key = groq_key(name)
        if not key:
            raise LLMNotConfigured("GROQ_API_KEY is not set.")
        from langchain_groq import ChatGroq

        cap = _max_output(name)
        return ChatGroq(model=name, api_key=key, temperature=temperature, **({"max_tokens": cap} if cap else {}))
    if provider in ("google", "gemini"):
        if not GEMINI_API_KEY:
            raise LLMNotConfigured("GEMINI_API_KEY is not set.")
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as e:
            raise LLMNotConfigured("Install langchain-google-genai to use a Gemini model.") from e
        return ChatGoogleGenerativeAI(model=name, google_api_key=GEMINI_API_KEY, temperature=temperature)
    raise LLMNotConfigured(f"Unknown model provider '{provider}' in COMMITTEE_MODELS.")


# The committee: [(label, model)] for the models listed in COMMITTEE_MODELS. Empty list = committee off (single model). A member that
# cannot be built (missing key, missing package) is skipped, so one missing key never stops the others.
def committee_llms() -> list[tuple[str, object]]:
    members = []
    for spec in [x for x in COMMITTEE_MODELS.split(",") if x.strip()]:
        try:
            members.append((spec.strip().split(":", 1)[-1], get_model(spec)))
        except LLMNotConfigured:
            continue
    return members if len(members) >= 2 else []


# The model's name, recorded with each result so a score can be traced back to the model that produced it.
def model_name() -> str:
    return GROQ_MODEL
