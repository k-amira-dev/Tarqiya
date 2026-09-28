"""ISO 3166-1 alpha-2 country list for the dropdowns the spec calls for (§3, §4, ...). One place so every
section's "Country" dropdown looks and sorts the same way.
"""
import pycountry

#: (code, English name), UAE first (the common case here), then the rest alphabetically.
COUNTRY_OPTIONS: list[tuple[str, str]] = [("AE", "United Arab Emirates")] + sorted(
    ((c.alpha_2, c.name) for c in pycountry.countries if c.alpha_2 != "AE"), key=lambda c: c[1]
)
COUNTRY_CODES: list[str] = [code for code, _ in COUNTRY_OPTIONS]
_NAME_BY_CODE = dict(COUNTRY_OPTIONS)


def country_name(code: str | None) -> str:
    return _NAME_BY_CODE.get(code, code or "")
