"""The applicant assistant: answers questions about what an application needs and what is missing.

It never decides or changes anything. `tools.py` reads facts the application already computes (the policy thresholds, the two scoring
forms, and the applicant's own checklist); `chat.py` turns those facts into an answer. A language model only phrases the answer, and the
same facts can be shown without a model, so the assistant still works when a model is unavailable."""
