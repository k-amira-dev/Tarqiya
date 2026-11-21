"""The preview table gives a typed or edited date back as text or a timestamp; an entry must store a plain date (a mix made the degree check crash)."""
from datetime import date, datetime

import pandas as pd

from promoflow.extraction.entry_docs import Col
from promoflow.ui.views import entries_ui as U

DATE = Col("Study from", "study_from", "date")


def test_every_form_a_date_cell_can_come_back_in_becomes_a_plain_date():
    assert U._back(date(2010, 9, 1), DATE) == date(2010, 9, 1)
    assert U._back("2010-09-01", DATE) == date(2010, 9, 1)                      # typed into an empty cell
    assert U._back("01 September 2010", DATE) == date(2010, 9, 1)
    assert U._back(pd.Timestamp("2010-09-01"), DATE) == date(2010, 9, 1)
    assert type(U._back(pd.Timestamp("2010-09-01"), DATE)) is date and type(U._back(datetime(2010, 9, 1, 8, 30), DATE)) is date
    assert U._back(None, DATE) is None and U._back(pd.NaT, DATE) is None and U._back("not a date", DATE) is None


def test_the_degree_check_no_longer_compares_a_date_with_text():
    start, end = U._back("2008-09-01", DATE), U._back(pd.Timestamp("2010-07-20"), DATE)
    assert end > start                                                          # this comparison raised TypeError before
