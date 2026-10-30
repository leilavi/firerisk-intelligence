# Working rules for this repository

* **Documents stay current (author's rule, 2026-10-30).** Every change or new feature updates, in the same commit:
  `README.md`, `PROJECT_STATUS.md`, `CHANGELOG.md`, and when affected `ARCHITECTURE.md`, `HACKATHON_COMPLIANCE.md`,
  `FEATURE_ORIGIN_MATRIX.md`, `TASKS.md`, `DEVELOPMENT_LOG.md`. The repository is judged as submitted; outdated
  content costs points.
* State only what has evidence ("live" = real Meta API / Drive run on the author's PC). Keep real limits visible.
* When the number of tests changes, update the count in README.md and PROJECT_STATUS.md;
  `tests/test_docs_current.py` fails otherwise. When a status becomes outdated, add its old wording to `OUTDATED`
  in that test.
* Real data, keys and the building's name never enter the repository (`data/private/` is git-ignored).
