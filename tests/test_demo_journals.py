"""The fictional journals used for the demo dossier (db/seed.py, --demo-journals) classify as intended: three Class A
journals (top 20% in Scopus, listed in ISI, with an impact factor on the paper) and three Class B journals."""
from decimal import Decimal

from promoflow.db.enums import JournalClass
from promoflow.db.models import Publication
from promoflow.db.seed import DEMO_JOURNALS, seed_demo_journals
from promoflow.dossier.section5 import papers as s5p


def test_demo_journals_classify_as_class_a_and_class_b(app_env):
    with app_env.session_scope() as s:
        seed_demo_journals(s)
        seed_demo_journals(s)                       # running it twice must not create duplicates
    with app_env.session_scope() as s:
        got = {}
        for title, issn, _pub, _src, _isi, _cat, _pct, _q, impact in DEMO_JOURNALS:
            paper = Publication(issn=issn, impact_factor=Decimal(impact))     # in memory only, never saved
            got[title] = s5p.classify(s, paper).journal_class
    classes = list(got.values())
    assert classes[:3] == [JournalClass.CLASS_A] * 3
    assert classes[3:] == [JournalClass.CLASS_B] * 3
    assert len(got) == 6


def test_class_a_needs_the_impact_factor_on_the_paper(app_env):
    with app_env.session_scope() as s:
        seed_demo_journals(s)
    with app_env.session_scope() as s:
        without = s5p.classify(s, Publication(issn="2601-4821", impact_factor=None))
    assert without.journal_class == JournalClass.CLASS_B       # a Scopus journal, but no impact factor claimed
