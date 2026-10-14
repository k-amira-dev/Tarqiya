"""The pure eligibility rules (promoflow/rules/eligibility.py): submission windows, time in rank, early and
exceptional applications, reapplication, the ORCID check digit and Section 0 validation messages. No database is
needed: the rules are plain functions.
"""
from datetime import date

from promoflow.db.enums import PromotionTrack, Rank
from promoflow.rules.eligibility import (
    Criteria, next_submission_window, orcid_is_valid, section0_checks, validate_section0,
)

ASSOC = Criteria(min_years_in_rank=5, min_years_at_institution=1, early_application_months=4, exceptional_min_years=4,
                 reapply_min_years=1, reapply_new_publications=2, reapply_new_class_a=1, reapply_new_main_author=1)
TODAY = date(2026, 9, 25)  # next window: 1–7 Oct 2026


def checks(**kw):
    base = dict(track=PromotionTrack.TO_ASSOCIATE, current_rank_date=None, appointment_date=None,
                early_application=False, exceptional_case=False, previously_rejected=False, rejection_date=None,
                criteria=ASSOC, today=TODAY)
    base.update(kw)
    return {c.label: c for c in section0_checks(**base)}


def test_submission_windows():
    assert next_submission_window(date(2026, 9, 25)).start == date(2026, 10, 1)
    w = next_submission_window(date(2026, 10, 3))
    assert w.open_now and w.end == date(2026, 10, 7)
    assert next_submission_window(date(2026, 10, 8)).start == date(2027, 1, 1)


def test_time_in_rank_pass_and_fail():
    assert checks(current_rank_date=date(2021, 9, 1))["Time in current rank"].status == "ok"
    assert checks(current_rank_date=date(2023, 1, 1))["Time in current rank"].status == "fail"


def test_early_application_within_four_months():
    # 4 years 10 months on 1 Oct 2026: 2 months short
    assert checks(current_rank_date=date(2021, 12, 1), early_application=True)["Time in current rank"].status == "ok"
    # 8 months short: too early even with the early rule
    assert checks(current_rank_date=date(2022, 6, 1), early_application=True)["Time in current rank"].status == "fail"


def test_exceptional_case_goes_to_the_head_of_department():
    c = checks(current_rank_date=date(2022, 6, 1), exceptional_case=True)["Time in current rank"]
    assert c.status == "warn" and "Head of Department" in c.detail


def test_years_at_institution_counts_from_the_later_date():
    c = checks(current_rank_date=date(2020, 1, 1), appointment_date=date(2026, 3, 1))
    assert c["Years at this university in current rank"].status == "fail"


def test_reapplication_needs_a_year():
    assert checks(previously_rejected=True, rejection_date=date(2026, 3, 1))["Reapplication"].status == "fail"
    assert checks(previously_rejected=True, rejection_date=date(2025, 6, 1))["Reapplication"].status == "ok"


def test_orcid_checksum():
    assert orcid_is_valid("0000-0002-1825-0097")  # ORCID's documented example
    assert not orcid_is_valid("0000-0002-1825-0098")
    assert not orcid_is_valid("0000-0002-1825")


def test_validation_messages():
    errors = validate_section0({"track": PromotionTrack.TO_ASSOCIATE, "rank_on_appointment": Rank.PROFESSOR,
                                "scopus_author_id": "abc", "exceptional_case": True, "early_application": True,
                                "current_rank_date": date(2030, 1, 1)}, TODAY)
    text = " ".join(errors)
    assert "Academic year is required" in text
    assert "cannot be in the future" in text
    assert "cannot be higher than your current rank" in text
    assert "digits only" in text
    assert "not both" in text
    assert "justify" in text


def test_the_window_rule_applies_by_default():
    from promoflow.rules.eligibility import in_submission_window
    assert in_submission_window(date(2026, 10, 3)) and not in_submission_window(date(2026, 12, 15))
    assert not next_submission_window(date(2026, 12, 15)).open_now


def test_the_development_switch_opens_every_day(monkeypatch):
    import promoflow.rules.eligibility as rules
    monkeypatch.setattr(rules, "DEV_IGNORE_SUBMISSION_WINDOW", True)
    assert rules.in_submission_window(date(2026, 12, 15))
    assert rules.next_submission_window(date(2026, 12, 15)).open_now
