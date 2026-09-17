# A provenance and redundancy check over the public UniversalCEFR collection

Run 17 September 2026 against the 24 public parquet exports at
`huggingface.co/UniversalCEFR`. Reproduce with `universalcefr_check.py`
(`--download` first, `--cards` to add the checks that need network). 65,037 rows;
nothing private, nothing redistributed.

Gathering resources into one collection is what makes cross-resource checking
possible: separately published corpora cannot be compared against each other
until someone puts them in the same place and the same format. UniversalCEFR
does that, and this is one such check run against it.

**Every number below is printed by the script.** If a figure here is not in
`run_output.txt`, it is a defect in this document; please report it.

---

## What is clean

Worth stating first, because it is the larger part of the answer.

- **One schema across all 24 corpora.** The same eight fields throughout —
  `category, cefr_level, format, lang, license, source_name, text, title` —
  with `cefr_level` as a plain string. This compares field *names*, not Arrow
  types. No row has empty or missing text.
- **`lang` agrees with the corpus name on all 65,037 rows.** Not one disagrees.
  This is a metadata-consistency check, not language identification — no
  language identifier was run over the text.
- **No cross-corpus text sharing except one pair, established exhaustively.** Every
  text in every corpus was normalised (NFKC, case-folded, whitespace collapsed)
  and inverted to the set of corpora holding it: no sampling, no threshold, no
  length floor. **131 texts occur in more than one corpus.** 130 are the pair in
  Finding 1; the remaining one is the single character `!`, in `caes_es` and
  `readme_en`, which is a degenerate row rather than a shared text.

  This is exhaustive for *string identity under that normalisation*, which is
  what it claims and no more. It will not catch a text that was reformatted,
  re-hyphenated or lightly edited between corpora — that is what the approximate
  sweep below is for.
- **Each of the 24 datasets exposes exactly one parquet file**, so reading
  `train/0.parquet` per dataset reads all of it. The script checks this against
  the hub's parquet listing under `--cards` rather than assuming it; a sharded
  dataset would otherwise be silently under-read.
- Every corpus carries a `source_name` field — the declaration convention is
  already implemented. What has not been done is testing it against the data.

An approximate MinHash sweep (5-gram Jaccard ≥ 0.5) is also included, and finds
the same pair and nothing else. It is reported as a secondary result because it
cannot support a negative claim on its own: it skips texts under 80 characters
(16.7% of rows) and, at K=64 over 16 bands, surfaces a true pair at the
threshold only about 64% of the time. The exhaustive pass above is what the
"nothing else is shared" claim rests on.

## Finding 1 — two corpora that declare different sources are the same texts

`cambridge_exams_en` and `elg_cefr_en` are separate entries in the collection.
Their dataset cards declare different repositories, different papers and
different licences:

| | `cambridge_exams_en` | `elg_cefr_en` |
| --- | --- | --- |
| repository | ilexir.co.uk | edia.nl ELG |
| paper | Xia, Kochmar & Briscoe 2016 | Breuker 2023 |
| card licence | CC BY-NC-SA 4.0 | CC BY-NC 4.0 |
| unique texts | 325 | 706 |

**130 of the 325 Cambridge texts are identical to an `elg_cefr_en` text** after
NFKC, case and whitespace normalisation. **324 of the 325 — 99.7% — have a match
at 5-gram Jaccard ≥ 0.5, and the CEFR labels agree on 324 of 324.**

The obvious objection to the 324 is that a weak threshold could be matching
shared exam boilerplate rather than shared documents. It is not:

- the match is **one-to-one** — the 324 Cambridge texts map to 324 *distinct*
  ELG texts, with no ELG text claimed twice
- the similarity distribution is not sitting at the threshold: median 0.97,
  minimum 0.55, and of the 324 matches **130 are identical, 98 fall in
  0.9–1.0, 80 in 0.7–0.9, and only 16 in 0.5–0.7**

The containment figure is computed exhaustively over all 325 × 706 pairs and is
exact. If only the 130 exact matches are admitted, the finding stands on those
alone.

**Why it matters for this collection specifically.** These two entries look like
independent corroboration of each other and are not. Checking a label in one
against the other and finding agreement is not evidence, and the agreement rate
between them — 100% — is exactly what a reader would take as strong mutual
confirmation.

## Finding 2 — `cople2_pt`: every text carries two contradictory levels

942 rows, **471 unique texts, each appearing exactly twice**, and every one of
the 471 carries two different CEFR levels. The pairing is perfectly regular:

```
('A1','A2') x236    ('B1','B2') x163    ('C1','C2') x72
```

Every other field is identical between the two rows, and this is checked rather
than asserted: across the 471 repeated texts, `title`, `lang`, `source_name`,
`format`, `category` and `license` differ in **zero** of them. `cefr_level` is
the only field that differs, in all 471.

The regularity is consistent with a band being expanded into one row per
sub-level rather than genuine disagreement: a text labelled at the A band became
one A1 row and one A2 row. This is an inference from the pattern, not something
the exports establish.

## Finding 3 — `elg_cefr_nl`: ratings stored as texts

3,596 rows, **1,195 unique texts**. The multiplicity distribution is exactly
`{2: 1, 3: 1190, 6: 4}` — 1,190 texts appear three times. 1,126 carry
conflicting levels across 142 distinct combinations. The tuples run over
adjacent bands, sometimes with a level repeated rather than three distinct ones
— `('B1','B1+','B2')` and `('B1+','B2','B2+')`, but also `('B1','B1','B1+')`
and `('B1','B1+','B1+')`.

That pattern is consistent with several raters per text, which is a good thing
to have, stored as separate texts, which is not. Again an inference from shape.
Unlike `cople2_pt` the repeats are not quite field-identical: `title` differs in
2 of the 1,195 and the raw `text` in 1, so a small number are not pure
duplicates.

## Finding 4 — the label space is not one scheme

The premise of a multilingual CEFR benchmark is a shared label space. The
`cefr_level` field holds **17 distinct strings** across the collection:

- the six bands `A1 A2 B1 B2 C1 C2`
- sub-band `+` levels in three corpora — `A1+ A2+ B1+ B2+` in `elg_cefr_en`,
  `A1+` through `C2+` in `elg_cefr_nl`, `B1+ B2+` in `icle500_en`
- a bare `B`, in `hablacultura_es`
- and four different ways of recording no label, one per corpus that needs one:
  `EMPTY` (`merlin_cs`, `merlin_it`), `NA` (`icle500_en`), `unrated`
  (`merlin_it`), `Unassessable` (`zaebuc_ar`)

A consumer filtering on the six canonical bands silently drops every plus-level;
one testing for missing labels has to know all four null markers, and `merlin_it`
alone uses two of them.

## Finding 5 — the row `license` field disagrees with the dataset card

Each row carries a `license` string, and each dataset has a card declaring a
licence. They disagree in **13 of the 24 corpora**. Seven are only word order
(`CC BY-SA-NC 4.0` in the rows against `cc-by-nc-sa-4.0` on the card) and are
cosmetic, though they do mean the field is not machine-readable. Six differ
substantively:

| corpus | rows say | card says |
| --- | --- | --- |
| `icle500_en` | `CC0 1.0 (Public Domain)` | `cc-by-nc-4.0` |
| `learn_welsh_cy` | `public` | `cc-by-nc-sa-4.0` |
| `zaebuc_ar` | `CC BY-SA 4.0` | `cc-by-nc-sa-4.0` |
| `elg_cefr_de` | `CC BY-NC-SA 4.0` | `cc-by-nc-4.0` |
| `elg_cefr_en` | `CC BY-NC-SA 4.0` | `cc-by-nc-4.0` |
| `elg_cefr_nl` | `CC BY-NC-SA 4.0` | `cc-by-nc-4.0` |

The first three matter most: in each, the row field states **weaker**
restrictions than the card. A user filtering on the row field would conclude
that `icle500_en` is public domain and that `zaebuc_ar` permits commercial use.
Which of the two declarations is right is not determinable from the exports.

## Finding 6 — `caes_es`: placeholder rows

1.51× redundancy, 31,149 rows over 20,629 unique texts. Most of it is short
learner utterances that genuinely coincide, so the inflation is **not** itself a
defect and is excluded from the collection-wide reading below. Two things are:

- the string `none` appears **214 times**, carrying five different CEFR levels
  (A2 ×123, A1 ×60, B1 ×17, C1 ×11, B2 ×3)
- 310 rows are under 20 characters, including `!` at A1 (×15), `hola` at A1 and
  A2, and `buenas tardes adios` at A1 (×7)

`caes_es` is not alone in this: `learn_welsh_cy` has 223 rows under 20
characters out of 1,372.

## Finding 7 — `ComplexityMT` has no data

Listed in the organisation; the datasets server reports *"No (supported) data
files found"*. Zero rows.

## Collection-wide

**65,037 rows over 51,426 unique texts. 13,611 rows duplicate another row** —
13,480 within a corpus and 131 across corpora.

That total should not be read as a leakage figure for the collection. **10,520
of it, 77%, is `caes_es` alone**, where short learner utterances genuinely
coincide. The structural duplication is `elg_cefr_nl` (2,401 rows) and
`cople2_pt` (471). In those two, a random row-wise split puts the same text,
under two different labels, on both sides of the cut.

Ten corpora contain at least one text carrying more than one level; in eight of
them it is a handful of rows, and only `cople2_pt` (471 of 471) and
`elg_cefr_nl` (1,126 of 1,195) are structural.

---

## What this check cannot determine

Whether any of this originates upstream or in the conversion to the
UniversalCEFR format. From outside, the two are indistinguishable: an upstream
corpus that ships band labels and a converter that expands bands produce
identical output. The people who built the conversion can answer it
immediately; nobody else can. The same applies to Finding 5 — the card and the
field disagree, and which one reflects the source is not visible from here.

The dataset cards do not help. All 24 carry the same boilerplate — licence,
repository, citation — and none records row counts, multiplicity, or annotator
structure. A user has no way to learn from the card that every text in
`cople2_pt` appears twice with two levels.

## Reproducing

```bash
python3 universalcefr_check.py --download
python3 universalcefr_check.py            # all checks except the licence comparison
python3 universalcefr_check.py --cards    # adds parquet listing + card licences
```

`--cards` needs network. Some Python builds ship without usable root
certificates, so it falls back to `curl`; if a card cannot be read the run says
so and draws no conclusion for it, rather than counting silence as agreement.

Roughly four minutes. Hashing is Blake2b rather than Python's built-in `hash()`,
which is salted per process and made the pair counts drift between runs.
