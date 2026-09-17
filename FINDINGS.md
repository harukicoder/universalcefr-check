# A provenance and redundancy check over the public UniversalCEFR collection

Run 12 September 2026 against the 24 public parquet exports at
`huggingface.co/UniversalCEFR`. Reproduce with `universalcefr_check.py`
(`--download` first). 65,037 rows; nothing private, nothing redistributed.

Gathering resources into one collection is what makes cross-resource checking
possible: separately published corpora cannot be compared against each other
until someone puts them in the same place and the same format. UniversalCEFR
does that. So far as its EMNLP 2025 paper records, the check itself had not been
run. This is it.

---

## What is clean

Worth stating first, because it is the larger part of the answer.

- **One schema across all 24 corpora.** Identical eight fields, `cefr_level` as a
  plain string. No mixed granularities, no silent scheme drift.
- **`lang` is correct on all 65,037 rows.** Not one disagrees with its corpus.
- **No cross-corpus overlap anywhere except a single pair.** Thirteen languages,
  24 corpora, swept at 5-gram Jaccard ≥ 0.5. Everything except the pair below is
  genuinely independent of everything else.
- Every corpus carries a `source_name` field — the declaration convention is
  already implemented. What has not been done is testing it against the data.

## Finding 1 — two corpora that declare different sources are the same texts

`cambridge_exams_en` and `elg_cefr_en` are separate entries in the collection.
They declare different repositories, different papers, different authors and
different licences:

| | `cambridge_exams_en` | `elg_cefr_en` |
| --- | --- | --- |
| repository | ilexir.co.uk | edia.nl ELG |
| paper | Xia, Kochmar & Briscoe 2016 | Breuker 2023 |
| licence | CC BY-NC-SA 4.0 | CC BY-NC 4.0 |
| unique texts | 325 | 706 |

**324 of the 325 Cambridge texts — 99.7% — have a near-duplicate in
`elg_cefr_en`, and the CEFR labels agree on 324 of 324.** 130 of those are
byte-identical after whitespace and case normalisation.

The containment figure is computed exhaustively and is exact. The LSH sweep,
which is approximate and therefore a lower bound, independently surfaces 328
near-duplicate pairs between the two and none anywhere else.

**Why it matters for this collection specifically.** These two entries look like
independent corroboration of each other and are not. Checking a label in one
against the other and finding agreement is not evidence, and the agreement rate
between them — 100% — is exactly what a reader would take as strong mutual
confirmation. This is the same failure the HSK word-list audit found, where four
of five widely used lists turned out to be one artifact under four names:
agreement across sources that are not independent.

## Finding 2 — `cople2_pt`: every text carries two contradictory levels

942 rows, **471 unique texts, each appearing exactly twice**, and every one of
the 471 carries two different CEFR levels. The pairing is perfectly regular:

```
('A1','A2') x236    ('B1','B2') x163    ('C1','C2') x72
```

Every other field — `title`, `lang`, `source_name`, `format`, `category`,
`license` — is identical between the two rows. The regularity says this is a
band being expanded into one row per sub-level rather than genuine disagreement:
a text labelled at the A band became one A1 row and one A2 row. The corpus
therefore reports twice the texts it has, and every label in it is contradicted
by another row.

## Finding 3 — `elg_cefr_nl`: ratings stored as texts

3,596 rows, **1,195 unique texts**, 1,190 of them appearing three times.
1,126 carry conflicting levels, and the tuples run over contiguous bands —
`('B1','B1+','B2')`, `('B1+','B2','B2+')` — across 142 distinct combinations.
That pattern is consistent with several raters per text, which is a good thing
to have, stored as separate texts, which is not. The corpus is 3.01× its own
size and its labels contradict each other by construction.

## Finding 4 — `caes_es`: placeholder rows

1.51× redundancy, 31,149 rows over 20,629 unique texts. Most of it is short
learner utterances that genuinely coincide, so the inflation is not itself a
defect. Two things are:

- the string `none` appears **214 times**, carrying five different CEFR levels
  (A2 ×123, A1 ×60, B1 ×17, C1 ×11, B2 ×3)
- 673 rows are under 20 characters, including `!` at A1

## Finding 5 — `ComplexityMT` has no data

Listed in the organisation; the datasets server reports *"No (supported) data
files found"*. Zero rows.

## Collection-wide

**65,037 rows over 51,426 unique texts. 13,611 rows — 20.9% — duplicate another
row.** Anyone splitting the collection at random has leakage across the split
in three corpora, two of which leak contradictory labels.

---

## What this check cannot determine

Whether any of this originates upstream or in the conversion to the
UniversalCEFR format. From outside, the two are indistinguishable: an upstream
corpus that ships band labels and a converter that expands bands produce
identical output. The people who built the conversion can answer it immediately;
nobody else can.

The dataset cards do not help. All five inspected carry the same boilerplate —
licence, repository, citation — and none records row counts, multiplicity, or
annotator structure. A user has no way to learn from the card that every text in
`cople2_pt` appears twice with two levels.

## Reproducing

```bash
python3 universalcefr_check.py --download
python3 universalcefr_check.py
```

Roughly four minutes. Hashing is Blake2b rather than Python's built-in `hash()`,
which is salted per process and made the pair counts drift between runs.
