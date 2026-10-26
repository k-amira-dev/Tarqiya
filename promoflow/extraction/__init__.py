"""Reading uploaded evidence files and turning them into text and form values (UI-independent).

THE IDEA: instead of typing everything into the forms, the applicant uploads the evidence file first. This package
reads the file, pulls out the values the form needs (with the line they came from), and the page prefills the boxes.
The applicant checks and corrects them. Later, only these short checked snippets (never the whole file) are shown to
the review agents.

Step by step, one file per step:
    pdf_text.py   uploaded PDF (bytes) -> plain text, or a clear reason why there is none
"""
