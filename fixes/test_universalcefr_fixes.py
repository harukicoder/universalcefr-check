# SPDX-License-Identifier: MIT
from universalcefr_fixes import normalise_label, to_spdx, licence_status, check_row

def test_bands():
    for b in ("A1", "A2", "B1", "B2", "C1", "C2"):
        l = normalise_label(b)
        assert (l.cefr_level, l.kind) == (b, "band")

def test_plus():
    l = normalise_label("B1+")
    assert (l.cefr_level, l.cefr_sublevel, l.kind) == ("B1", "B1+", "plus")

def test_band_only():
    l = normalise_label("B")
    assert l.cefr_level is None and l.cefr_range == "B1-B2"

def test_missing():
    for m in ("EMPTY", "NA", "Unassessable", "unrated"):
        l = normalise_label(m)
        assert l.cefr_level is None and l.label_missing_reason == m.lower()

def test_unrecognised_not_guessed():
    assert normalise_label("D3").kind == "unrecognised"

def test_spdx():
    assert to_spdx("CC BY SA NC 4.0") == to_spdx("cc-by-nc-sa-4.0") == "CC-BY-NC-SA-4.0"
    assert to_spdx("CC0 1.0 (Public Domain)") == "CC0-1.0"
    assert to_spdx("public") is None

def test_licence_status():
    assert licence_status("CC BY NC 4.0", "cc-by-nc-4.0") == "format_only"
    assert licence_status("CC BY-SA-NC 4.0", "cc-by-nc-sa-4.0") == "word_order"
    assert licence_status("CC BY-SA 4.0", "cc-by-nc-sa-4.0") == "substantive"

def test_check_row():
    assert check_row({"cefr_level": "NA", "license": "CC BY-NC 4.0"}, "cc-by-nc-4.0") == ["label-outside-cefr"]
    assert check_row({"cefr_level": "A1", "license": "public"}, "cc-by-nc-sa-4.0") == ["licence-unparseable"]
