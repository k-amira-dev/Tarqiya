"""The Research evaluation's card: the checks table first, the long explanation in an expander under it (like Teaching and Service)."""
from streamlit.testing.v1 import AppTest

SCRIPT = '''
from promoflow.ui import theme
from promoflow.ui.views import reviews
theme.inject()
out = {"component": "research", "verdict": "pass", "is_stub": False,
       "narrative": "8 paper(s) submitted. - Total counted publications: 9 of 6 required, met. - Class A papers: 3 of 2 required, met. The portfolio is coherent.",
       "criteria": [{"key": "min_total_publications", "label": "Total publications", "required": 6.0, "actual": 9.0, "passed": True}],
       "rubric": []}
reviews._agent_card("research", out)
'''


def labels(node):
    out = [getattr(node, "label", "") or ""]
    for child in getattr(node, "children", {}).values():
        out += labels(child)
    return out


def test_research_reasoning_sits_in_an_expander_under_the_table():
    at = AppTest.from_string(SCRIPT, default_timeout=30).run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Why these results" in x for x in labels(at.main))
    page = " ".join(m.value for m in at.markdown)
    assert "Total publications" in page and "pf-reason" in page
    assert "8 paper(s) submitted." in page and page.count('class="pf-reason"') == 3      # one line per point, not one paragraph


def test_the_papers_table_lists_each_paper_with_its_decisions(app_env):
    from sqlalchemy import select

    from promoflow.db.models import Publication
    from promoflow.dossier import doc_entries
    from promoflow.extraction import entry_docs as E
    from promoflow.extraction import entry_docs_more as M
    from tests.test_extraction_entry_docs import make_case
    from tests.test_extraction_more_docs import paper

    uid = make_case(app_env)
    with app_env.session_scope() as s:
        ctx = doc_entries.load_ctx(s, "Dr. Samira Al-Tamimi", uid)
    values, _ = M.build_paper(paper(issn="2297-7775", issue="1"), ctx)
    with app_env.session_scope() as s:
        doc_entries.add_entries(s, uid, "paper", [E.EntryDraft("paper", "p.pdf", b"%PDF-1.4 x", values, [], "text")], ctx)
        pid = s.scalars(select(Publication)).one().id
    script = f'''
from promoflow.ui import theme
from promoflow.ui.views import reviews
theme.inject()
out = {{"component": "research", "verdict": "pass", "is_stub": False, "model_name": "m", "narrative": "x", "flags": [], "rubric": [],
       "criteria": [{{"key": "k", "label": "Total", "required": 1.0, "actual": 1.0, "passed": True}}],
       "items": [{{"entity_table": "publication", "entity_id": {pid}, "counted": True, "classification": "class_b", "credited_role": "main author"}}]}}
reviews._agent_card("research", out, 1)
'''
    at = AppTest.from_string(script, default_timeout=30).run()
    assert not at.exception, [e.value for e in at.exception]
    page = " ".join(m.value for m in at.markdown)
    assert "Algorithmic Visibility" in page and "Fits the field (AI)" in page and "Main author" in page
