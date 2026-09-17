# universalcefr-check

A provenance and redundancy check over the public
[UniversalCEFR](https://huggingface.co/UniversalCEFR) collection — 24 corpora,
13 languages, 65,037 rows.

It asks five things:

1. **Do any two corpora share texts?** Two resources that declare different
   sources and are not independent cannot corroborate one another, so agreement
   between them is not evidence. Answered exhaustively, not by sampling.
2. **Within a corpus, does the same text carry more than one CEFR level?**
3. **Does the collection contain what its row counts imply?**
4. **Is the label space one scheme?**
5. **Does the licence in each row match the licence on its dataset card?**

```bash
python3 universalcefr_check.py --download   # fetch the parquet exports
python3 universalcefr_check.py              # run the checks (~4 min)
python3 universalcefr_check.py --cards      # also compare each row licence to its card
```

Needs `pyarrow`. Reads the published exports only; redistributes nothing. Each
corpus keeps its own licence (CC BY-NC / CC BY-NC-SA), so use is non-commercial
research with attribution to the original creators.

Results are in [FINDINGS.md](FINDINGS.md). The short version: the field names
are uniform, the `lang` field agrees with the corpus name on every row, and an
exhaustive inversion of every text finds no corpus sharing text with another —
except that `cambridge_exams_en` is 99.7% contained in `elg_cefr_en` while its
card declares a different repository, paper and licence. Beyond that,
`cople2_pt` and `elg_cefr_nl` repeat their own texts structurally under
conflicting levels, the `cefr_level` field holds 17 distinct strings including
four different null markers, and the row-level `license` disagrees with the
dataset card in 13 of the 24 corpora — in three of them stating weaker terms
than the card does.

Every figure in FINDINGS.md is printed by the script; `run_output.txt` is a
committed run.

The method is the one from
[an audit of the open HSK word lists](https://doi.org/10.5281/zenodo.22540154),
where four of the five most used lists turned out to be one artifact circulating
under four names: find what a dataset declares, then test the data against the
declaration instead of trusting it.
