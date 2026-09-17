#!/usr/bin/env python3
"""Provenance and redundancy check over the public UniversalCEFR collection.

    python3 universalcefr_check.py --download   # fetch the 24 public parquet files
    python3 universalcefr_check.py              # run the checks

Three questions, in the order they matter:

1. Do any two corpora in the collection share texts? Two resources that declare
   different sources and are not independent cannot corroborate each other, so
   agreement between them is not evidence.
2. Within a corpus, does the same text carry more than one CEFR level?
3. Does the collection contain what its row counts imply?

Everything is computed from the published parquet files. No private data.
Licences are per-dataset (CC BY-NC / CC BY-NC-SA); this reads, never redistributes.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, random, re, sys, unicodedata, urllib.request

DATASETS = [
    "caes_es","hablacultura_es","kwiqiz_es","cople2_pt","peapl2_pt","readme_en",
    "readme_fr","readme_ru","readme_ar","readme_hi","merlin_cs","merlin_de",
    "merlin_it","elg_cefr_de","elg_cefr_en","elg_cefr_nl","elle_et","icle500_en",
    "kwiqiz_fr","learn_welsh_cy","cefr_sp_en","cefr_asag_en","cambridge_exams_en",
    "zaebuc_ar",
]
# listed in the org but carrying no loadable data files as of 2026-09-12
NO_DATA = ["ComplexityMT"]
PQ = "https://huggingface.co/api/datasets/UniversalCEFR/{d}/parquet/default/train/0.parquet"


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", t or "")).strip().lower()


def digest(t: str) -> str:
    return hashlib.sha256(norm(t).encode()).hexdigest()


def _h(s: str) -> int:
    """Stable 64-bit hash. Python's built-in hash() is salted per process, which
    would make the shingle signatures — and so the pair counts — differ between
    runs. Blake2b keeps the result reproducible."""
    return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "big")


def shingles(t: str, n: int = 5) -> set[int]:
    w = t.split()
    if len(w) < n:
        return {_h(t)}
    return {_h(" ".join(w[i : i + n])) for i in range(len(w) - n + 1)}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a or b) else 0.0


def download(dest: str) -> None:
    os.makedirs(dest, exist_ok=True)
    for d in DATASETS:
        out = os.path.join(dest, d + ".parquet")
        if os.path.exists(out):
            continue
        print(f"  fetching {d}", file=sys.stderr)
        urllib.request.urlretrieve(PQ.format(d=d), out)


def load(src: str) -> list[dict]:
    import pyarrow.parquet as pq
    rows = []
    for d in DATASETS:
        t = pq.read_table(os.path.join(src, d + ".parquet")).to_pylist()
        for r in t:
            r["_ds"] = d
        rows += t
    return rows


def check_schema(rows) -> None:
    schemas = {tuple(sorted(r.keys())) for r in rows}
    print(f"distinct schemas across {len(DATASETS)} corpora: {len(schemas)}")
    bad = sum(
        1
        for r in rows
        if r["_ds"].rsplit("_", 1)[-1] in {"es","pt","en","fr","ru","ar","hi","cs","de","it","nl","et","cy"}
        and str(r["lang"]).lower() != r["_ds"].rsplit("_", 1)[-1]
    )
    print(f"rows whose lang disagrees with the corpus name: {bad}")


def check_redundancy(rows) -> None:
    print("\n--- redundancy within each corpus ---")
    tot = collections.Counter(r["_ds"] for r in rows)
    uniq = collections.defaultdict(set)
    for r in rows:
        uniq[r["_ds"]].add(digest(r["text"]))
    print(f"{'corpus':22s} {'rows':>7s} {'unique':>7s} {'x':>6s}  conflicting-level texts")
    for d in sorted(tot, key=lambda x: -(tot[x] / max(len(uniq[x]), 1))):
        g = collections.defaultdict(set)
        for r in rows:
            if r["_ds"] == d:
                g[digest(r["text"])].add(r["cefr_level"])
        conf = sum(1 for v in g.values() if len(v) > 1)
        if tot[d] != len(uniq[d]):
            print(f"{d:22s} {tot[d]:7d} {len(uniq[d]):7d} {tot[d]/len(uniq[d]):5.2f}x  {conf:6d}")
    allu = set().union(*uniq.values())
    print(f"\ncollection: {sum(tot.values())} rows, {len(allu)} unique texts, "
          f"{sum(tot.values()) - len(allu)} rows duplicate another row")


def check_level_structure(rows, ds: str) -> None:
    g = collections.defaultdict(list)
    for r in rows:
        if r["_ds"] == ds:
            g[digest(r["text"])].append(r["cefr_level"])
    tup = collections.Counter(tuple(sorted(v)) for v in g.values())
    print(f"\n--- {ds}: level tuples per unique text ---")
    for t, c in tup.most_common(8):
        print(f"  {t}  x{c}")
    if len(tup) > 8:
        print(f"  ... {len(tup)} distinct tuples")


def check_cross_overlap(rows, threshold: float = 0.5) -> None:
    print(f"\n--- cross-corpus overlap (5-gram Jaccard >= {threshold}) ---")
    random.seed(7)
    K, BANDS = 64, 16
    perm = [(random.getrandbits(32) | 1, random.getrandbits(32)) for _ in range(K)]
    M = (1 << 32) - 1
    bylang = collections.defaultdict(list)
    seen = set()
    for r in rows:
        n = norm(r["text"])
        if len(n) < 80:
            continue
        k = (r["_ds"], digest(r["text"]))
        if k in seen:
            continue
        seen.add(k)
        bylang[r["lang"]].append((r["_ds"], n, r["cefr_level"]))

    found = collections.Counter()
    for lang, items in bylang.items():
        if len({d for d, _, _ in items}) < 2:
            continue
        shs = [shingles(t) for _, t, _ in items]
        sigs = [tuple(min(((a * x + b) & M) for x in sh) for a, b in perm) for sh in shs]
        buckets = collections.defaultdict(list)
        rpb = K // BANDS
        for i, s in enumerate(sigs):
            for b in range(BANDS):
                buckets[(b, s[b * rpb : (b + 1) * rpb])].append(i)
        cand = set()
        for v in buckets.values():
            if 1 < len(v) <= 40:
                for i in range(len(v)):
                    for j in range(i + 1, len(v)):
                        if items[v[i]][0] != items[v[j]][0]:
                            cand.add((min(v[i], v[j]), max(v[i], v[j])))
        for i, j in cand:
            if jaccard(shs[i], shs[j]) >= threshold:
                found[tuple(sorted((items[i][0], items[j][0])))] += 1
    if not found:
        print("  none")
    for p, c in found.most_common():
        print(f"  {c:5d} near-duplicate pairs  {p[0]} <-> {p[1]}")


def check_containment(rows, a: str, b: str, threshold: float = 0.5) -> None:
    A, B = {}, {}
    for r in rows:
        if r["_ds"] == a:
            A.setdefault(norm(r["text"]), set()).add(r["cefr_level"])
        if r["_ds"] == b:
            B.setdefault(norm(r["text"]), set()).add(r["cefr_level"])
    bs = [(shingles(t), lv) for t, lv in B.items()]
    hit = agree = 0
    for t, lv in A.items():
        sh_a = shingles(t)
        best, blv = 0.0, None
        for sh_b, lv_b in bs:
            j = jaccard(sh_a, sh_b)
            if j > best:
                best, blv = j, lv_b
        if best >= threshold:
            hit += 1
            agree += lv == blv
    print(f"\n--- containment: {a} in {b} ---")
    print(f"  {a}: {len(A)} unique texts; {b}: {len(B)} unique texts")
    print(f"  with a near-duplicate in {b}: {hit} = {hit/len(A)*100:.1f}%")
    if hit:
        print(f"  label agreement on those: {agree}/{hit} = {agree/hit*100:.1f}%")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--dir", default="pq")
    a = ap.parse_args()
    if a.download:
        download(a.dir)
        return
    rows = load(a.dir)
    print(f"loaded {len(rows)} rows from {len(DATASETS)} public corpora "
          f"({', '.join(NO_DATA)} has no loadable data files)")
    check_schema(rows)
    check_redundancy(rows)
    for d in ("cople2_pt", "elg_cefr_nl"):
        check_level_structure(rows, d)
    check_cross_overlap(rows)
    check_containment(rows, "cambridge_exams_en", "elg_cefr_en")


if __name__ == "__main__":
    main()
