"""When the language model (the scoring agents) says "too many tokens this minute", how long to wait before asking again."""
import re


def _wait_seconds(text: str) -> float | None:
    """The wait in a provider message such as "try again in 13m52.464s", "7.5s" or "320ms", in seconds (None if there is none)."""
    m = re.search(r"try again in\s*(?:(\d+)m(?!s))?\s*(?:(\d+(?:\.\d+)?)(ms|s))?", text)
    if not m or not (m.group(1) or m.group(2)):
        return None
    return int(m.group(1) or 0) * 60 + float(m.group(2) or 0) * (0.001 if m.group(3) == "ms" else 1)


def _retry_wait(error: Exception, attempt: int) -> float | None:
    """Seconds to wait before trying again, or None if the error is not worth retrying."""
    text = f"{type(error).__name__} {error}"
    if "Request too large" in text:                              # one request bigger than the per-minute allowance: waiting cannot help
        return None
    if "RateLimit" in text or "429" in text or "rate_limit" in text:
        if "per day" in text or "(TPD)" in text:                 # the DAILY allowance is used up: waiting a minute will not help
            return None
        value = _wait_seconds(text)
        if value is not None:
            return None if value > 90 else value + 2             # a long wait is not worth holding the applicant for
        return min(10 * (2 ** attempt), 65)
    if "503" in text and "UNAVAILABLE" in text or "overloaded" in text.lower():       # the provider is busy for a moment (Gemini: "high demand")
        return min(5 * (2 ** attempt), 40)
    if "json_validate_failed" in text or "Failed to validate JSON" in text or "tool_use_failed" in text:     # an empty or cut-off answer: one more try
        return 2
    return None
