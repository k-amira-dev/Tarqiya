"""Reading uploaded evidence files and turning them into form values (UI-independent), entirely on this machine.

local_read.py     the one reader: pdfplumber for a PDF with a text layer (text and tables), OCR (RapidOCR) for a scan or a picture
rule_letters.py   plain rules for the letters and certificates (committee, admin, workshop, training, community, attendance)
rule_docs.py      rules for degrees, rank decisions, awards, thesis supervision, innovation reports, policies
rule_text.py      rules for papers, acceptance letters, book chapters, conference papers, funded projects, peer observations, ...
rule_reports.py   the table readers: registrar report, student evaluations, advisee lists, curriculum summary, CV education, classification form
entry_docs*.py    what each kind of document becomes in the forms, and the checks on it
teaching_docs.py  the Section 6 reports and the checks on them (printed totals, difference column, advisee counts)
No language model reads a document: nothing the applicant uploads leaves the machine.
"""
