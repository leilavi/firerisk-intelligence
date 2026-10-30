"""Drawing probe: local only, numbers only. TEST PDF built in the test (no real drawing)."""

import importlib.util
import re
from pathlib import Path

import pytest

pytest.importorskip("pdfplumber")


def _pdf(path: Path, text_lines: list[str], n_lines: int = 0):
    """Minimal one-page PDF with text and line objects (hand-written, valid xref)."""
    ops = ["BT /F1 10 Tf"] + [f"1 0 0 1 40 {760 - 14 * i} Tm ({t}) Tj" for i, t in enumerate(text_lines)] + ["ET"]
    ops += [f"{50 + i} 100 m {50 + i} 300 l S" for i in range(n_lines)]
    stream = "\n".join(ops).encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x)
    path.write_bytes(out)


def _mod():
    spec = importlib.util.spec_from_file_location("probe", Path(__file__).resolve().parents[1] / "scripts" / "probe_drawings.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_probe_counts_categories_and_prints_numbers_only(tmp_path, capsys):
    m = _mod()
    secret = ["TESTSECRET-DB-B1", "EXIT", "EM", "L1-03", "4x25mm XLPE", "B1", "Tang 2", "FHC"]
    _pdf(tmp_path / "TECH-DIAG_TEST_Lighting.pdf", secret, n_lines=250)
    assert m.main(["x", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    summary = out.split("--- Summary")[1].split("Details saved")[0]
    assert "TESTSECRET" not in summary and "XLPE" not in summary and "TECH-DIAG" not in summary
    r = __import__("json").loads((tmp_path / "probe.json").read_text())["files"]["TECH-DIAG_TEST_Lighting.pdf"]
    assert r["file_kind"] == "exit_emergency_lighting" and r["page_kinds"] == {"drawing": 1}
    c = r["categories"]
    assert c["exit_sign"] >= 1 and c["emergency_light"] >= 1 and c["panel"] >= 1 and c["fire_equipment"] >= 1
    assert c["circuit_label"] >= 1 and c["cable_spec"] >= 1
    assert r["floors"]["B1"] >= 1 and r["floors"]["F2"] >= 1
    assert not re.search(r"[A-Za-z]{4,}-", summary.replace("exit_emergency_lighting", ""))  # no label text


def test_probe_needs_no_network(tmp_path, monkeypatch):
    import socket
    monkeypatch.setattr(socket, "socket", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used")))
    m = _mod()
    _pdf(tmp_path / "a.pdf", ["TEST"])
    assert m.main(["x", str(tmp_path)]) == 0
