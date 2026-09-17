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
    schemas = {tuple(sorted(k for k in r.keys() if k != "_ds")) for r in rows}
    print(f"distinct schemas across {len(DATASETS)} corpora: {len(schemas)}")
    for sc in schemas:
        print(f"  {len(sc)} fields: {', '.join(sc)}")
    empty = sum(1 for r in rows if not (r.get("text") or "").strip())
    print(f"rows with empty or missing text: {empty}")
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
    print(f"{'corpus':22s} {'rows':>7s} {'unique':>7s} {'dup rows':>9s} {'x':>6s}  conflicting-level texts")
    nconf = 0
    dups = {}
    for d in sorted(tot, key=lambda x: -(tot[x] / max(len(uniq[x]), 1))):
        g = collections.defaultdict(set)
        for r in rows:
            if r["_ds"] == d:
                g[digest(r["text"])].add(r["cefr_level"])
        conf = sum(1 for v in g.values() if len(v) > 1)
        nconf += conf > 0
        dups[d] = tot[d] - len(uniq[d])
        if tot[d] != len(uniq[d]):
            print(f"{d:22s} {tot[d]:7d} {len(uniq[d]):7d} {dups[d]:9d} "
                  f"{tot[d]/len(uniq[d]):5.2f}x  {conf:6d}")
    allu = set().union(*uniq.values())
    total_dup = sum(tot.values()) - len(allu)
    within = sum(dups.values())
    print(f"\ncollection: {sum(tot.values())} rows, {len(allu)} unique texts, "
          f"{total_dup} rows duplicate another row")
    print(f"  of those, {within} duplicate within a corpus and {total_dup - within} across corpora")
    top = max(dups, key=lambda d: dups[d])
    print(f"  largest single contributor: {top} with {dups[top]} rows "
          f"({dups[top] / total_dup * 100:.0f}% of the total)")
    print(f"  corpora holding at least one text with more than one level: {nconf}")


def check_level_structure(rows, ds: str) -> None:
    g = collections.defaultdict(list)
    for r in rows:
        if r["_ds"] == ds:
            g[digest(r["text"])].append(r["cefr_level"])
    mult = collections.Counter(len(v) for v in g.values())
    tup = collections.Counter(tuple(sorted(v)) for v in g.values())
    print(f"\n--- {ds}: level tuples per unique text ---")
    print(f"  multiplicity (how many rows per unique text): {dict(sorted(mult.items()))}")
    print(f"  unique texts: {len(g)}; carrying more than one level: "
          f"{sum(1 for v in g.values() if len(set(v)) > 1)}")
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
    short = 0
    for r in rows:
        n = norm(r["text"])
        if len(n) < 80:
            short += 1
            continue
        k = (r["_ds"], digest(r["text"]))
        if k in seen:
            continue
        seen.add(k)
        bylang[r["lang"]].append((r["_ds"], n, r["cefr_level"]))

    # State what the sweep can and cannot see. A negative result is only as strong
    # as the sensitivity of the search that failed to find anything.
    multi = {l for l, v in bylang.items() if len({d for d, _, _ in v}) >= 2}
    single = {l: sorted({d for d, _, _ in v}) for l, v in bylang.items() if l not in multi}
    rpb = K // BANDS
    sens = lambda s: 1 - (1 - s ** rpb) ** BANDS
    print(f"  coverage: {short} of {len(rows)} rows ({short / len(rows) * 100:.1f}%) are under "
          f"80 characters and are not swept")
    print(f"  compared: {len(multi)} of {len(bylang)} languages hold more than one corpus "
          f"({', '.join(sorted(multi))})")
    if single:
        names = ", ".join(f"{d} ({l})" for l, ds in sorted(single.items()) for d in ds)
        print(f"  not tested: {len(single)} languages hold a single corpus, so cross-corpus "
              f"overlap is impossible there by construction — {names}")
    print(f"  sensitivity: K={K}, {BANDS} bands of {rpb}; a true pair at Jaccard {threshold} "
          f"surfaces with probability {sens(threshold):.2f}, at 0.7 with {sens(0.7):.2f}. "
          f"Counts below are a lower bound.")

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
        dropped = sum(len(v) * (len(v) - 1) // 2 for v in buckets.values() if len(v) > 40)
        if dropped:
            print(f"  note: {lang} has oversized LSH buckets; "
                  f"~{dropped} candidate comparisons skipped by the cap")
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
    exact = len(set(A) & set(B))
    bs = [(t, shingles(t), lv) for t, lv in B.items()]
    hit = agree = 0
    targets, sims = [], []
    for t, lv in A.items():
        sh_a = shingles(t)
        best, blv, bt = 0.0, None, None
        for t_b, sh_b, lv_b in bs:
            j = jaccard(sh_a, sh_b)
            if j > best:
                best, blv, bt = j, lv_b, t_b
        if best >= threshold:
            hit += 1
            agree += lv == blv
            targets.append(bt)
            sims.append(best)
    print(f"\n--- containment: {a} in {b} ---")
    print(f"  {a}: {len(A)} unique texts; {b}: {len(B)} unique texts")
    print(f"  with a near-duplicate in {b}: {hit} = {hit/len(A)*100:.1f}%")
    if hit:
        print(f"  label agreement on those: {agree}/{hit} = {agree/hit*100:.1f}%")
    print(f"  identical after whitespace/case normalisation: {exact}")
    if hit:
        # Is the match one-to-one? Many-to-one would mean shared boilerplate rather
        # than shared documents, which is the obvious objection to this finding.
        uniq_t = len(set(targets))
        print(f"  distinct {b} texts matched: {uniq_t}"
              f"{'  (one-to-one)' if uniq_t == hit else f'  ({hit - uniq_t} collisions)'}")
        band = collections.Counter()
        for j in sims:
            band["identical" if j == 1.0 else "0.9-1.0" if j >= 0.9
                 else "0.7-0.9" if j >= 0.7 else f"{threshold}-0.7"] += 1
        sims_sorted = sorted(sims)
        med = sims_sorted[len(sims_sorted) // 2]
        print(f"  similarity of the matches: min {min(sims):.2f}, median {med:.2f}")
        for k in ("identical", "0.9-1.0", "0.7-0.9", f"{threshold}-0.7"):
            if band.get(k):
                print(f"    {k:12s} {band[k]:4d}")


def check_level_inventory(rows) -> None:
    """The collection's label space. A shared CEFR scheme is the premise of the
    benchmark, so the set of strings actually used is worth stating."""
    print("\n--- cefr_level inventory ---")
    per = collections.defaultdict(set)
    for r in rows:
        per[r["_ds"]].add(str(r["cefr_level"]))
    allv = set().union(*per.values())
    core = {"A1", "A2", "B1", "B2", "C1", "C2"}
    plus = {v for v in allv if v.endswith("+")}
    other = allv - core - plus
    print(f"  {len(allv)} distinct level strings collection-wide")
    print(f"  the six CEFR bands: {sorted(core & allv)}")
    if plus:
        print(f"  sub-band '+' levels: {sorted(plus)}")
        for d in sorted(per):
            p = sorted(per[d] & plus)
            if p:
                print(f"    {d:22s} {p}")
    if other:
        print(f"  outside the CEFR scheme: {sorted(other)}")
        for d in sorted(per):
            o = sorted(per[d] & other)
            if o:
                print(f"    {d:22s} {o}")


def check_cross_exact(rows) -> None:
    """Exhaustive and deterministic: invert normalised text -> corpora. Unlike the
    LSH sweep this has no length floor, no threshold and no false negatives, so a
    null result here is a real null result."""
    print("\n--- cross-corpus exact duplicates (exhaustive) ---")
    where = collections.defaultdict(set)
    lv = collections.defaultdict(set)
    for r in rows:
        h = digest(r["text"])
        where[h].add(r["_ds"])
        lv[h].add(r["cefr_level"])
    cross = {h: ds for h, ds in where.items() if len(ds) > 1}
    pairs = collections.Counter()
    for h, ds in cross.items():
        s = sorted(ds)
        for i in range(len(s)):
            for j in range(i + 1, len(s)):
                pairs[(s[i], s[j])] += 1
    print(f"  texts present in more than one corpus: {len(cross)}")
    for (a, b), c in pairs.most_common():
        print(f"    {c:6d}  {a} <-> {b}")
    disagree = sum(1 for h in cross if len(lv[h]) > 1)
    print(f"  of those, carrying different levels in different corpora: {disagree}")
    # Print any shared text short enough to be degenerate rather than a real overlap.
    sample = {}
    for r in rows:
        h = digest(r["text"])
        if h in cross and len(norm(r["text"])) < 80:
            sample[h] = norm(r["text"])
    if sample:
        print(f"  {len(sample)} of the shared texts are under 80 characters "
              f"(degenerate rather than genuine overlap):")
        for h, t in list(sample.items())[:5]:
            print(f"    {t!r:20s} in {sorted(where[h])}")


def check_placeholders(rows, floor: int = 20) -> None:
    """Rows whose text is too short to carry a CEFR judgement, and repeated
    placeholder strings."""
    print(f"\n--- short and placeholder rows (under {floor} characters) ---")
    short = collections.Counter()
    for r in rows:
        if len(norm(r["text"])) < floor:
            short[r["_ds"]] += 1
    for d, c in short.most_common():
        print(f"  {d:22s} {c:6d} rows")
    rep = collections.defaultdict(collections.Counter)
    for r in rows:
        n = norm(r["text"])
        if len(n) < floor:
            rep[(r["_ds"], n)][r["cefr_level"]] += 1
    worst = sorted(rep.items(), key=lambda kv: -sum(kv[1].values()))[:5]
    print("  most repeated short strings, with the levels they carry:")
    for (d, t), c in worst:
        if sum(c.values()) > 1:
            print(f"    {d:16s} {t!r:12s} x{sum(c.values()):4d}  {dict(c.most_common())}")


def _fetch_json(url: str):
    """urllib first; fall back to curl, which uses the system trust store. Some
    Python builds ship without usable root certificates and urllib then fails on
    every request — which must not be mistaken for every card agreeing."""
    try:
        with urllib.request.urlopen(url, timeout=30) as fh:
            return json.load(fh)
    except Exception:
        import subprocess
        out = subprocess.run(["curl", "-s", "--max-time", "30", url],
                             capture_output=True, text=True)
        if out.returncode != 0 or not out.stdout.strip():
            raise RuntimeError(f"curl failed ({out.returncode})")
        return json.loads(out.stdout)


def check_field_identity(rows, ds: str) -> None:
    """For a corpus whose texts repeat, report which other fields differ between the
    repeated rows. Claiming "every other field is identical" requires checking it."""
    g = collections.defaultdict(list)
    for r in rows:
        if r["_ds"] == ds:
            g[digest(r["text"])].append(r)
    fields = [f for f in next(iter(g.values()))[0] if f not in ("_ds",)]
    diff = collections.Counter()
    rep = 0
    for v in g.values():
        if len(v) < 2:
            continue
        rep += 1
        for f in fields:
            if len({str(x.get(f)) for x in v}) > 1:
                diff[f] += 1
    print(f"\n--- {ds}: fields that differ between repeated rows ---")
    print(f"  {rep} texts appear more than once")
    for f in fields:
        print(f"    {f:14s} differs in {diff.get(f, 0):5d} of them")


def check_shards() -> None:
    """The loader reads train/0.parquet per dataset. That is only complete if each
    dataset exposes exactly one parquet file, which is checked here rather than
    assumed."""
    print("\n--- parquet file count per dataset ---")
    multi, failed = [], []
    for d in DATASETS:
        try:
            j = _fetch_json(f"https://huggingface.co/api/datasets/UniversalCEFR/{d}/parquet")
        except Exception as e:
            failed.append(d)
            continue
        n = sum(len(urls) for cfg in j.values() for urls in cfg.values()) if isinstance(j, dict) else 0
        if n != 1:
            multi.append((d, n))
            print(f"  {d:22s} {n} files — train/0.parquet is NOT the whole dataset")
    if failed:
        print(f"  INCOMPLETE: could not list {len(failed)} datasets ({', '.join(failed)})")
    if not multi:
        print(f"  all {len(DATASETS) - len(failed)} datasets checked expose exactly one "
              f"parquet file; reading train/0.parquet reads all of it")


def check_declared_licence(rows) -> None:
    """The row-level `license` field against the dataset card that publishes it.
    Needs network. The card is the licence a user sees on the hub; the field is
    the licence a user sees after loading the data."""
    print("\n--- row `license` field vs dataset card ---")
    seen = {}
    for r in rows:
        seen.setdefault(r["_ds"], collections.Counter())[str(r.get("license"))] += 1
    key = lambda s: (s or "").lower().replace(" ", "-").replace("_", "-").strip()
    bad, failed = [], []
    for d in DATASETS:
        rowlic = seen[d].most_common(1)[0][0] if seen.get(d) else "(none)"
        try:
            j = _fetch_json(f"https://huggingface.co/api/datasets/UniversalCEFR/{d}")
            card = j.get("license") or (j.get("cardData") or {}).get("license") or "?"
        except Exception as e:
            failed.append(d)
            print(f"  {d:22s} card unreachable ({type(e).__name__})")
            continue
        if key(rowlic) != key(card):
            bad.append((d, rowlic, card))
            print(f"  {d:22s} rows {rowlic!r} != card {card!r}")
    checked = len(DATASETS) - len(failed)
    if failed:
        # A network failure is not a clean result. Say so instead of counting it as agreement.
        print(f"  INCOMPLETE: {len(failed)} of {len(DATASETS)} cards could not be read "
              f"({', '.join(failed)}); no conclusion is drawn for those.")
    print(f"  {len(bad)} of the {checked} corpora actually checked disagree with their own card")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--dir", default="pq")
    ap.add_argument("--cards", action="store_true",
                    help="also run the checks that need network: parquet file counts, "
                         "and each dataset card's licence against the rows")
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
        check_field_identity(rows, d)
    check_level_inventory(rows)
    check_cross_exact(rows)
    check_cross_overlap(rows)
    check_containment(rows, "cambridge_exams_en", "elg_cefr_en")
    check_placeholders(rows)
    if a.cards:
        check_shards()
        check_declared_licence(rows)


if __name__ == "__main__":
    main()
