"""Submission documents must describe the current project (author's rule, 2026-10-30).

Fails when README.md states a test count different from the suite, or when a public document still carries a status
sentence that is known to be outdated. Update the documents in the same commit as the change that made them stale."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DOCS = ["README.md", "PROJECT_STATUS.md", "ARCHITECTURE.md", "HACKATHON_COMPLIANCE.md"]

# Sentences that were true once and are now false. Add to this list when a status changes.
OUTDATED = [
    r"sam-3\.1`?\s*\|[^\n]*not implemented",
    r"video input[^\n]*not yet run",
    r"no real video",
    r"never run against the real API",
    r"Muse Captain",
    r"\b108 tests\b",
    r"\b87 tests\b",
]


def test_readme_test_count_matches_the_suite():
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", str(ROOT / "tests")],
                         capture_output=True, text=True, cwd=ROOT, timeout=120).stdout
    collected = int(re.search(r"(\d+) tests? collected", out).group(1))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    stated = re.search(r"\*\*(\d+) tests \((\d+) pass, (\d+) skipped", readme)
    assert stated, "README must state the test count as '**N tests (P pass, S skipped'"
    n, passed, skipped = map(int, stated.groups())
    assert n == collected, f"README says {n} tests, the suite has {collected}: update README.md and PROJECT_STATUS.md"
    assert passed + skipped == n


def test_public_documents_have_no_outdated_status():
    hits = []
    for name in PUBLIC_DOCS:
        text = (ROOT / name).read_text(encoding="utf-8")
        hits += [f"{name}: /{p}/" for p in OUTDATED if re.search(p, text, re.I)]
    assert hits == [], hits
