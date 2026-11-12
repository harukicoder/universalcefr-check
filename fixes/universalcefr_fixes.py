#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Alvaro Serrano
"""Proposed fixes for the public UniversalCEFR collection, as code.

Implements three proposals from "UniversalCEFR public collection: observations
and proposed fixes" (A. Serrano, 30 Sep 2026), sections 3.2, 3.3 and 4:

  (a) normalise_label(): map the 17 cefr_level strings found in the 24 public
      corpora onto the six CEFR bands, keeping plus-levels, band-only labels and
      the reason a label is missing in separate fields;
  (b) check_row(): flag rows whose label falls outside the declared CEFR scheme,
      or whose row-level licence differs from the licence on the dataset card;
  (c) report(): count how many rows each proposed change affects, per corpus.

Nothing here edits or redistributes data. It reads the published parquet exports
(fetched with --download) and the public dataset cards, and prints counts.

    python3 universalcefr_fixes.py --download        # fetch the 24 exports + cards
    python3 universalcefr_fixes.py                   # print the report
    python3 universalcefr_fixes.py --csv report.csv  # also write it as CSV
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import os
import re
import sys
import unicodedata
import urllib.request
from dataclasses import dataclass, asdict
from typing import Optional

DATASETS = [
    "caes_es", "hablacultura_es", "kwiqiz_es", "cople2_pt", "peapl2_pt", "readme_en",
    "readme_fr", "readme_ru", "readme_ar", "readme_hi", "merlin_cs", "merlin_de",
    "merlin_it", "elg_cefr_de", "elg_cefr_en", "elg_cefr_nl", "elle_et", "icle500_en",
    "kwiqiz_fr", "learn_welsh_cy", "cefr_sp_en", "cefr_asag_en", "cambridge_exams_en",
    "zaebuc_ar",
]
PQ_URL = "https://huggingface.co/api/datasets/UniversalCEFR/{d}/parquet/default/train/0.parquet"
CARD_URL = "https://huggingface.co/api/datasets/UniversalCEFR/{d}"

BANDS = ("A1", "A2", "B1", "B2", "C1", "C2")
# Markers used in the public exports to record that a text has no CEFR label.
MISSING_MARKERS = {"EMPTY", "NA", "UNASSESSABLE", "UNRATED", "NONE", "NULL", ""}
# A bare level letter means "somewhere in this band" (e.g. hablacultura_es "B").
BAND_ONLY = {"A": ("A1", "A2"), "B": ("B1", "B2"), "C": ("C1", "C2")}


# --------------------------------------------------------------------------
# (a) label normalisation
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Label:
    cefr_level: Optional[str]      # one of the six bands, or None
    cefr_sublevel: Optional[str]   # e.g. "B1+" when the source used a plus-level
    cefr_range: Optional[str]      # e.g. "B1-B2" when the source gave only a band letter
    label_missing_reason: Optional[str]  # original marker when there is no label
    original: Optional[str]        # the string exactly as published
    kind: str                      # "band" | "plus" | "band_only" | "missing" | "unrecognised"


def normalise_label(raw: Optional[str]) -> Label:
    """Map one published cefr_level string onto the six-band scheme.

    The six bands stay as they are. "B1+" becomes cefr_level="B1",
    cefr_sublevel="B1+" (nothing is lost, and a six-band filter now keeps it).
    A bare "B" cannot be resolved to one band, so cefr_level is None and
    cefr_range="B1-B2". The four missing-label markers become None, with the
    original marker kept in label_missing_reason. Anything else is reported as
    "unrecognised" rather than guessed.
    """
    s = (raw or "").strip()
    u = s.upper()
    if u in BANDS:
        return Label(u, None, None, None, raw, "band")
    m = re.fullmatch(r"([ABC][12])\s*\+", u)
    if m:
        return Label(m.group(1), m.group(1) + "+", None, None, raw, "plus")
    if u in BAND_ONLY:
        lo, hi = BAND_ONLY[u]
        return Label(None, None, f"{lo}-{hi}", None, raw, "band_only")
    if u in MISSING_MARKERS or raw is None:
        return Label(None, None, None, s.lower() or "null", raw, "missing")
    return Label(None, None, None, None, raw, "unrecognised")


# --------------------------------------------------------------------------
# licence normalisation
# --------------------------------------------------------------------------
_CC_TOKENS = ("by", "nc", "nd", "sa")


def to_spdx(lic: Optional[str]) -> Optional[str]:
    """Best-effort SPDX id for the licence strings used in the collection.

    "CC BY SA NC 4.0", "CC BY-SA-NC 4.0" and "cc-by-nc-sa-4.0" all become
    "CC-BY-NC-SA-4.0" (SPDX orders the elements BY, NC, ND, SA). Returns None
    when the string does not name a licence (e.g. "public").
    """
    if not lic:
        return None
    s = lic.lower()
    if "cc0" in s or "public domain" in s:
        return "CC0-1.0"
    if not re.search(r"\bcc\b|cc-", s):
        return None
    ver = re.search(r"(\d\.\d)", s)
    toks = set(re.findall(r"\b(by|nc|nd|sa)\b", s.replace("-", " ").replace("_", " ")))
    if "by" not in toks or not ver:
        return None
    return "CC-" + "-".join(t.upper() for t in _CC_TOKENS if t in toks) + "-" + ver.group(1)


# --------------------------------------------------------------------------
# (b) row check against the declared scheme and the dataset card
# --------------------------------------------------------------------------
def licence_status(row_lic: Optional[str], card_lic: Optional[str]) -> str:
    """'same' | 'format_only' | 'word_order' | 'substantive' | 'unparseable'."""
    if (row_lic or "") == (card_lic or ""):
        return "same"
    a, b = to_spdx(row_lic), to_spdx(card_lic)
    if a is None or b is None:
        return "unparseable"
    if a != b:
        return "substantive"
    key = lambda x: re.sub(r"[\s_-]+", "-", (x or "").lower().strip())
    if key(row_lic) == key(card_lic):
        return "format_only"     # case / spaces vs hyphens only
    return "word_order"          # same elements, different order


def check_row(row: dict, card_licence: Optional[str]) -> list[str]:
    """Return the flags for one row.

    label-outside-cefr  the label is neither one of the six bands nor a plus-level
                        (i.e. it is band-only, missing or unrecognised). The
                        dataset cards declare no label set of their own; the
                        collection declares the six CEFR levels, so that is the
                        scheme checked against.
    plus-level          the label is a plus-level (valid, but dropped by a
                        six-band filter); informational.
    licence-<status>    the row licence differs from the card licence.
    """
    flags = []
    lab = normalise_label(row.get("cefr_level"))
    if lab.kind in ("band_only", "missing", "unrecognised"):
        flags.append("label-outside-cefr")
    elif lab.kind == "plus":
        flags.append("plus-level")
    st = licence_status(row.get("license"), card_licence)
    if st not in ("same", "format_only"):
        flags.append("licence-" + st)
    return flags


def apply_label_fix(row: dict) -> dict:
    """Return a copy of a row with the proposed label fields (section 3.2)."""
    out = dict(row)
    out.update({k: v for k, v in asdict(normalise_label(row.get("cefr_level"))).items()
                if k in ("cefr_level", "cefr_sublevel", "cefr_range", "label_missing_reason")})
    out["cefr_level_original"] = row.get("cefr_level")
    return out


# --------------------------------------------------------------------------
# helpers shared with universalcefr-check (same definitions)
# --------------------------------------------------------------------------
def norm(t: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", t or "")).strip().lower()


def digest(t: str) -> str:
    return hashlib.sha256(norm(t).encode()).hexdigest()


def _fetch_json(url: str):
    try:
        with urllib.request.urlopen(url, timeout=30) as fh:
            return json.load(fh)
    except Exception:
        import subprocess
        out = subprocess.run(["curl", "-sL", "--max-time", "30", url], capture_output=True, text=True)
        return json.loads(out.stdout)


def download(dest: str) -> None:
    os.makedirs(dest, exist_ok=True)
    for d in DATASETS:
        out = os.path.join(dest, d + ".parquet")
        if not os.path.exists(out):
            print(f"  fetching {d}", file=sys.stderr)
            urllib.request.urlretrieve(PQ_URL.format(d=d), out)
        card = os.path.join(dest, d + ".card.json")
        if not os.path.exists(card):
            with open(card, "w") as fh:
                json.dump(_fetch_json(CARD_URL.format(d=d)), fh)


def load(src: str):
    import pyarrow.parquet as pq
    rows, cards = {}, {}
    for d in DATASETS:
        rows[d] = pq.read_table(os.path.join(src, d + ".parquet")).to_pylist()
        with open(os.path.join(src, d + ".card.json")) as fh:
            j = json.load(fh)
        cards[d] = {"licence": j.get("license") or (j.get("cardData") or {}).get("license"),
                    "sha": j.get("sha")}
    return rows, cards


# --------------------------------------------------------------------------
# (c) report
# --------------------------------------------------------------------------
CHANGES = [
    ("label_plus_to_sublevel", "3.2  plus-level moved to cefr_sublevel (cefr_level keeps the band)"),
    ("label_band_only_to_range", "3.2  bare band letter -> cefr_level null, cefr_range set"),
    ("label_missing_to_null", "3.2  missing-label marker -> null, marker kept as reason"),
    ("licence_word_order", "3.3  row licence: same terms, element order differs from card"),
    ("licence_substantive", "3.3  row licence: different terms from card"),
    ("licence_unparseable", "3.3  row licence: not a licence identifier"),
    ("licence_to_spdx", "3.3  row licence string rewritten as an SPDX id"),
    ("collapse_band_expanded", "4.2  rows removed if each text kept once (cople2_pt)"),
    ("collapse_rater_rows", "4.3  rows removed if each text kept once, ratings in a list (elg_cefr_nl)"),
    ("placeholder_none", "4.4  rows whose text is the placeholder 'none' (caes_es)"),
    ("cross_corpus_exact", "4.1  rows whose normalised text also occurs in another corpus"),
]


def report(rows: dict, cards: dict) -> list[dict]:
    # exact cross-corpus sharing (normalised text in >1 corpus)
    where = collections.defaultdict(set)
    for d, rs in rows.items():
        for r in rs:
            where[digest(r["text"])].add(d)
    out = []
    for d in DATASETS:
        rs, card = rows[d], cards[d]["licence"]
        c = collections.Counter()
        texts = collections.Counter(digest(r["text"]) for r in rs)
        for r in rs:
            k = normalise_label(r.get("cefr_level")).kind
            if k == "plus":
                c["label_plus_to_sublevel"] += 1
            elif k == "band_only":
                c["label_band_only_to_range"] += 1
            elif k == "missing":
                c["label_missing_to_null"] += 1
            elif k == "unrecognised":
                c["label_unrecognised"] += 1
            st = licence_status(r.get("license"), card)
            if st in ("word_order", "substantive", "unparseable"):
                c["licence_" + st] += 1
            if r.get("license") != to_spdx(card):
                c["licence_to_spdx"] += 1
            if norm(r["text"]) == "none":
                c["placeholder_none"] += 1
            if len(where[digest(r["text"])]) > 1:
                c["cross_corpus_exact"] += 1
        surplus = len(rs) - len(texts)
        if d == "cople2_pt":
            c["collapse_band_expanded"] = surplus
        if d == "elg_cefr_nl":
            c["collapse_rater_rows"] = surplus
        rec = {"corpus": d, "rows": len(rs), "distinct_texts": len(texts),
               "card_licence": card, "card_sha": (cards[d]["sha"] or "")[:10],
               "row_licence": collections.Counter(r.get("license") for r in rs).most_common(1)[0][0]}
        for key, _ in CHANGES:
            rec[key] = c.get(key, 0)
        rec["label_unrecognised"] = c.get("label_unrecognised", 0)
        out.append(rec)
    return out


def print_report(rep: list[dict]) -> None:
    total = sum(r["rows"] for r in rep)
    print(f"UniversalCEFR proposed fixes: rows affected, {len(rep)} public corpora, {total:,} rows\n")
    print("Label strings found and how they map:")
    seen = collections.Counter()
    for r in ROWS_CACHE:
        seen[r] += 1
    for s, n in sorted(seen.items(), key=lambda x: (normalise_label(x[0]).kind, str(x[0]))):
        l = normalise_label(s)
        print(f"  {s!r:15s} {n:6,d}  -> level={l.cefr_level!s:5s} sublevel={l.cefr_sublevel!s:5s} "
              f"range={l.cefr_range!s:6s} missing_reason={l.label_missing_reason!s}")
    print(f"  ({len(seen)} distinct strings)\n")
    for key, desc in CHANGES:
        hit = [(r["corpus"], r[key]) for r in rep if r[key]]
        n = sum(v for _, v in hit)
        print(f"{desc}\n  {n:,} rows in {len(hit)} {'corpus' if len(hit) == 1 else 'corpora'}" + (":" if hit else ""))
        if hit and len(hit) < len(rep):
            print("   " + ", ".join(f"{d} {v:,}" for d, v in hit))
        print()
    unrec = sum(r["label_unrecognised"] for r in rep)
    print(f"Labels the mapping does not recognise: {unrec}")
    print("\nPer-corpus licence comparison (row value vs card):")
    for r in rep:
        st = licence_status(r["row_licence"], r["card_licence"])
        mark = "" if st in ("same", "format_only") else f"  <- {st}"
        print(f"  {r['corpus']:20s} rows {r['row_licence']!r:28s} card {r['card_licence']!r:18s}{mark}")
    bad = [r for r in rep if licence_status(r["row_licence"], r["card_licence"]) not in ("same", "format_only")]
    print(f"  {len(bad)} of {len(rep)} corpora differ from their card "
          f"({sum(1 for r in bad if licence_status(r['row_licence'], r['card_licence']) == 'word_order')} word order only, "
          f"{sum(1 for r in bad if licence_status(r['row_licence'], r['card_licence']) == 'substantive')} substantive, "
          f"{sum(1 for r in bad if licence_status(r['row_licence'], r['card_licence']) == 'unparseable')} not a licence id)")


ROWS_CACHE: list = []


def print_flags(rows: dict, cards: dict) -> None:
    """Run check_row() over every row and summarise the flags."""
    flags = collections.Counter()
    per = collections.defaultdict(collections.Counter)
    any_flag = 0
    for d, rs in rows.items():
        for r in rs:
            f = [x for x in check_row(r, cards[d]["licence"]) if x != "plus-level"]
            any_flag += bool(f)
            for x in f:
                flags[x] += 1
                per[x][d] += 1
    print("\ncheck_row(): rows outside what the collection and the cards declare")
    for k, n in sorted(flags.items()):
        print(f"  {k:24s} {n:6,d} rows in {len(per[k])} corpora")
    print(f"  rows with at least one flag: {any_flag:,} of {sum(len(v) for v in rows.values()):,}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true", help="fetch the parquet exports and cards")
    ap.add_argument("--dir", default="pq")
    ap.add_argument("--csv", help="write the per-corpus report as CSV")
    a = ap.parse_args()
    if a.download:
        download(a.dir)
        return
    rows, cards = load(a.dir)
    ROWS_CACHE.extend(r.get("cefr_level") for rs in rows.values() for r in rs)
    rep = report(rows, cards)
    print_report(rep)
    print_flags(rows, cards)
    if a.csv:
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rep[0]))
            w.writeheader()
            w.writerows(rep)
        print(f"\nwrote {a.csv}")


if __name__ == "__main__":
    main()
