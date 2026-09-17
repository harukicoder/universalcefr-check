# universalcefr-check

A provenance and redundancy check over the public
[UniversalCEFR](https://huggingface.co/UniversalCEFR) collection — 24 corpora,
13 languages, 65,037 rows.

It asks three things:

1. **Do any two corpora share texts?** Two resources that declare different
   sources and are not independent cannot corroborate one another, so agreement
   between them is not evidence.
2. **Within a corpus, does the same text carry more than one CEFR level?**
3. **Does the collection contain what its row counts imply?**

```bash
python3 universalcefr_check.py --download   # fetch the parquet exports
python3 universalcefr_check.py              # run the checks (~4 min)
```

Needs `pyarrow`. Reads the published exports only; redistributes nothing. Each
corpus keeps its own licence (CC BY-NC / CC BY-NC-SA), so use is non-commercial
research with attribution to the original creators.

Results are in [FINDINGS.md](FINDINGS.md). The short version: the schema is
uniform, `lang` is correct on every row, and there is no cross-corpus overlap
anywhere in thirteen languages — except that `cambridge_exams_en` is 99.7%
contained in `elg_cefr_en` while declaring a different repository, paper and
licence. Three corpora also repeat their own texts under conflicting levels.

The method is the one from
[an audit of the open HSK word lists](https://doi.org/10.5281/zenodo.22540154),
where four of the five most used lists turned out to be one artifact circulating
under four names: find what a dataset declares, then test the data against the
declaration instead of trusting it.
