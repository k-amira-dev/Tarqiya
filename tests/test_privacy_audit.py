"""The privacy scanner finds personal data, and does not flag the harmless things that look like it."""
from promoflow import privacy_audit as P


def _prompt(human):
    return P.Prompt(1, "t", "Your three tasks: be fair.", human)


def _needles():
    n = P.Needles()
    n.applicant_name = {"Amira Khan", "Khan", "Amira"}
    n.applicant_email = {"amira@uni.test"}
    n.referee = {"Hans Muller"}
    return n


def test_finds_identifiers():
    hits = P.scan(_prompt("Dr. Amira Khan wrote to amira@uni.test; referee Hans Muller, tel +41 44 123 4567, ORCID 0000-0002-1825-0097"), _needles())
    assert {"applicant_name", "applicant_email", "referee_identity", "email_address", "phone_number", "orcid_id", "titled_person"} <= set(hits)


def test_ignores_years_dates_and_the_system_prompt():
    n = _needles()
    assert P.scan(_prompt('"2022-2024", "2025-2025", 2026-09-01, 40 students'), n) == {}
    n.applicant_name.add("Three")
    assert "applicant_name" not in P.scan(_prompt("three tasks"), n)      # a common word is not a name; the case matters for a single name


def test_recorder_captures_and_stops():
    rec = P.RecordingLLM()
    try:
        rec.with_structured_output(dict).invoke([("system", "s"), ("human", "h")])
    except P.Captured:
        pass
    assert rec.calls == [[("system", "s"), ("human", "h")]]
