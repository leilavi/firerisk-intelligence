"""Pipeline robustness tests on TEST fixture workbooks (not real data)."""

from datetime import datetime

from firerisk.config import LOCAL_TZ
from firerisk.engine import run_analysis
from fixtures import NOW, build_snapshot

TNOW = NOW.replace(tzinfo=LOCAL_TZ)


def _run(tmp_path, **kw):
    return run_analysis(build_snapshot(tmp_path / "snap", **kw), now=TNOW)


def test_duplicate_ids_are_kept_and_flagged(tmp_path):
    res = _run(tmp_path)
    ids = [i for i in res.evidence if i.startswith("asset:A1")]
    assert len(ids) == 2 and any("#r" in i for i in ids)
    assert any(q["type"] == "duplicate_record_id" for q in res.data_quality)


def test_unknown_status_is_not_treated_as_resolved(tmp_path):
    res = _run(tmp_path)
    dup = next(e for i, e in res.evidence.items() if i.startswith("asset:A1#"))
    assert dup.values["status_class"] == "unknown" and dup.is_open is None and "unmapped_status" in dup.flags


def test_invalid_meter_value_is_flagged_not_dropped(tmp_path):
    res = _run(tmp_path)
    bad = next(e for e in res.evidence.values() if e.source and e.source.record_id == "mbad")
    assert bad.values["reading"] is None and bad.values["raw_reading"] == "đồng hồ hỏng" and "invalid_reading" in bad.flags


def test_other_branch_records_are_excluded(tmp_path):
    res = _run(tmp_path)
    assert not any("E-ML1" == (e.asset_id or "") for e in res.evidence.values())
    st = next(s for s in res.source_status if s.get("sheet") == "BC hư hỏng TS")
    assert st["excluded_out_of_scope"] == 1


def test_generator_zero_duration_recomputed(tmp_path):
    res = _run(tmp_path)
    g = res.evidence["gen:G1"]
    assert g.values["minutes"] == 17 and "duration_recomputed_from_start_end" in g.flags


def test_overdue_and_stale_status_flags(tmp_path):
    res = _run(tmp_path)
    assert "overdue" in res.evidence["asset:A1"].flags
    stale = next(e for i, e in res.evidence.items() if "T08_2" in i)
    assert "status_possibly_stale" in stale.flags


def test_missing_tab_does_not_stop_analysis(tmp_path):
    res = _run(tmp_path, drop_tab="Dầu M Phát điện")
    st = next(s for s in res.source_status if s.get("sheet") == "Dầu M Phát điện")
    assert "error" in st and any(q["type"] == "source_unavailable" for q in res.data_quality)
    assert res.alerts  # other tabs still analysed


def test_missing_and_corrupt_files_are_reported(tmp_path):
    snap = build_snapshot(tmp_path / "snap")
    (snap / "ops.xlsx").write_bytes(b"this is not an xlsx file")
    res = run_analysis(snap, now=TNOW)
    assert any(s.get("error", "").startswith("workbook unreadable") for s in res.source_status)
    assert any(s.get("source") == "vehicles" and "file not found" in s.get("error", "") for s in res.source_status)
    assert res.alerts == []


def test_every_alert_has_the_14_fields(tmp_path):
    res = _run(tmp_path)
    required = {"problem", "evidence", "comparison", "possible_causes", "consequence", "risk_chain",
                "trigger_condition", "urgency", "preventive_actions", "deadline", "closure_condition", "confidence",
                "sources", "cause_status"}
    for s in res.signals:
        assert required <= set(s.fields), s.signal_id
    for a in res.alerts:
        assert {"headline", "assessment_class", "unknowns", "actions"} <= set(a.fields)


def test_unresolved_water_ingress_alert_is_high_and_traceable(tmp_path):
    res = _run(tmp_path)
    b1 = next(a for a in res.alerts if a.zone == "B1")
    assert b1.severity == "high" and b1.fields["assessment_class"] == "risk_indicator"
    ev = res.evidence[next(i for i in b1.evidence_ids if i.startswith("inc:"))]
    assert ev.source.sheet == "NK thi công - sự cố" and ev.source.row == 2


def test_late_arrival_detected_across_runs(tmp_path):
    from firerisk.store import Store
    store = Store(tmp_path / "db.sqlite")
    snap = build_snapshot(tmp_path / "snap")
    r1 = run_analysis(snap, now=TNOW)
    store.record_run(r1)
    assert store.mark_seen(r1) == []
    # a new record, dated 10 days ago, appears in the next snapshot
    import openpyxl
    wb = openpyxl.load_workbook(snap / "ops.xlsx")
    ws = wb["NK thi công - sự cố"]
    from firerisk.config import BRANCH_PREFIX as B
    from datetime import timedelta
    ws.append([f"{B}----T10_9", "Báo cáo sự cố", NOW - timedelta(days=10), "Late entry", None, None, None, None,
               None, "6. Hoàn tất", B])
    wb.save(snap / "ops.xlsx")
    r2 = run_analysis(snap, now=TNOW + timedelta(days=1))
    store.record_run(r2)
    late = store.mark_seen(r2)
    assert [x["evidence_id"] for x in late] == [f"inc:{B}----T10_9"]
