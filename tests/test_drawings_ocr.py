"""Local OCR of scanned drawings: TEST scan built in the test, no network, numbers-only summary."""

import importlib.util
import json
import socket
from pathlib import Path

import pytest

pytest.importorskip("rapidocr")
pytest.importorskip("pypdfium2")


def _scan_pdf(path: Path):
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 26)
    except OSError:
        font = ImageFont.load_default(size=26)
    img = Image.new("L", (2400, 1800), 255)
    d = ImageDraw.Draw(img)
    for x, y, t in [(120, 120, "DB-B1"), (600, 120, "EXIT"), (1000, 120, "EM-03"), (1500, 1500, "MSB"),
                    (1700, 1000, "TESTSECRET"), (1580, 120, "FHC")]:       # MSB/TESTSECRET cross tile borders
        d.text((x, y), t, font=font, fill=0)
    v = Image.new("L", (240, 50), 255)
    ImageDraw.Draw(v).text((10, 8), "L1-05", font=font, fill=0)
    img.paste(v.rotate(90, expand=True), (300, 700))                          # a vertical label
    img.convert("RGB").save(path, "PDF", resolution=150)


def _mod():
    spec = importlib.util.spec_from_file_location("ocr", Path(__file__).resolve().parents[1] / "scripts" / "ocr_drawings.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_scanned_drawing_is_read_locally_and_summary_has_numbers_only(tmp_path, capsys, monkeypatch):
    _scan_pdf(tmp_path / "TECH-DIAG_TEST_Lighting.pdf")
    m = _mod()
    monkeypatch.setattr(socket, "socket", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used")))
    assert m.main(["x", str(tmp_path), "--dpi", "150"]) == 0
    out = capsys.readouterr().out
    summary = out.split("--- Summary")[1].split("Private results")[0]
    assert "TESTSECRET" not in summary and "DB-B1" not in summary and "TECH-DIAG" not in summary
    data = json.loads((tmp_path / "ocr" / "TECH-DIAG_TEST_Lighting.json").read_text(encoding="utf-8"))
    texts = [t["text"] for p in data["pages"] for t in p["texts"]]
    for label in ("DB-B1", "EXIT", "EM-03", "MSB", "TESTSECRET", "FHC", "L1-05"):
        assert sum(label in t for t in texts) == 1, (label, texts)              # found once (tiles deduped)
    vert = next(t for p in data["pages"] for t in p["texts"] if "L1-05" in t["text"])
    x1, y1, x2, y2 = vert["box"]                                            # inside the pasted vertical strip
    assert 295 <= x1 and x2 <= 355 and 700 <= y1 and y2 <= 945 and (y2 - y1) > (x2 - x1)
    assert (tmp_path / "ocr" / "review.html").exists()


def test_tiles_cover_the_page_with_overlap():
    m = _mod()
    t = list(m.tiles(3500, 1700))
    assert t[0] == (0, 0, 1600, 1600) and max(x2 for *_, x2, _ in t) == 3500 and max(y2 for *_, y2 in t) == 1700
