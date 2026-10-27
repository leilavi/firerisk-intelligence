"""Integration test on the REAL data snapshot (skipped when the private snapshot is absent,
e.g. on a public clone). Checks loader completeness against the source, not specific risk values."""

from datetime import datetime

import pytest

from conftest import SNAPSHOT
from firerisk.config import LOCAL_TZ

pytestmark = pytest.mark.skipif(not (SNAPSHOT / "manifest.json").exists(), reason="private snapshot not present")


def test_every_meter_reading_row_is_loaded_and_traceable():
    import openpyxl
    from firerisk.engine import run_analysis
    from firerisk.config import METERS
    manifest_file = SNAPSHOT / "ops_data.xlsx"
    wb = openpyxl.load_workbook(manifest_file, read_only=True, data_only=True)
    rows = [r for r in wb["chỉ số điện nước"].iter_rows(values_only=True) if any(r)][1:]
    expected = sum(1 for r in rows if r[1] in METERS and isinstance(r[15], (int, float)))
    res = run_analysis(SNAPSHOT, now=datetime.now(LOCAL_TZ))
    loaded = [e for e in res.evidence.values() if e.kind == "meter_reading" and e.asset_id in METERS
              and e.values.get("reading") is not None]
    assert len(loaded) == expected
    assert all(e.source and e.source.row >= 2 and e.source.sheet == "chỉ số điện nước" for e in loaded)


def test_every_alert_evidence_id_resolves():
    from firerisk.engine import run_analysis
    res = run_analysis(SNAPSHOT, now=datetime.now(LOCAL_TZ))
    for a in res.alerts:
        for eid in a.evidence_ids + a.context_ids:
            assert eid in res.evidence
        for link in a.links:
            assert link["a"] in res.evidence and link["b"] in res.evidence and link["reasons"]
