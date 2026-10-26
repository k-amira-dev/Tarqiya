"""The single place that creates the LLM. Agents call `get_llm()`; none of them import a provider directly, so
switching from Groq to another provider later is a change in this file only."""
from promoflow.config import GROQ_API_KEY, GROQ_MODEL, GROQ_VISION_MODEL


# Raised when no API key is set. Callers catch it and carry on without the model instead of crashing.
class LLMNotConfigured(RuntimeError):
    pass


# Build the chat model. Every agent gets its model from here, so switching provider (Groq, Nebius, ...) is a change
# to THIS function only.
def get_llm(temperature: float = 0.0):
    """Chat model for the agents. Temperature 0 keeps runs as repeatable as possible."""
    # No key = no model. The key is read from .env or Streamlit Secrets (see config.py), never written in code.
    if not GROQ_API_KEY:
        raise LLMNotConfigured("GROQ_API_KEY is not set. Add it to .env (see the README).")
    from langchain_groq import ChatGroq  # imported here so tests and rule-only code never need the key

    return ChatGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY, temperature=temperature)


# The model for reading whole documents into rows. "Low" reasoning effort matters: at the default effort the model spent its
# whole budget thinking and dropped rows or returned nothing on long tables; at "low" it copied every row exactly.
def get_extraction_llm(max_tokens: int = 16000):
    """Chat model for reading documents (tables, certificates). Same provider and key as the agents."""
    if not GROQ_API_KEY:
        raise LLMNotConfigured("GROQ_API_KEY is not set. Add it to .env (see the README).")
    from langchain_groq import ChatGroq

    return ChatGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY, temperature=0.0, reasoning_effort="low", max_tokens=max_tokens)


# The model for reading scanned pages (images). Its answer is capped at about 900 tokens: the free plan allows only 1,000 output tokens a minute.
def get_vision_llm(max_tokens: int = 900):
    if not GROQ_API_KEY:
        raise LLMNotConfigured("GROQ_API_KEY is not set. Add it to .env (see the README).")
    from langchain_groq import ChatGroq

    return ChatGroq(model=GROQ_VISION_MODEL, api_key=GROQ_API_KEY, temperature=0.0, max_tokens=max_tokens)


# The model's name, recorded with each result so a score can be traced back to the model that produced it.
def model_name() -> str:
    return GROQ_MODEL
