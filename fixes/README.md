# UniversalCEFR proposed fixes, as code

Code for three of the fixes proposed in *UniversalCEFR public collection:
observations and proposed fixes* (A. Serrano, 30 September 2026), for the
UniversalCEFR conversion or dataset cards to run. MIT licence.

| Function | What it does | Document section |
|---|---|---|
| `normalise_label()` | Maps the 17 `cefr_level` strings onto the six CEFR bands. Plus-levels go to `cefr_sublevel`, a bare band letter to `cefr_range`, and the missing-label markers to `null` with the marker kept in `label_missing_reason`. Unknown strings are reported, never guessed. | 3.2, 4.5 |
| `check_row()` | Flags a row whose label is outside the six-band scheme, or whose row `license` differs from its dataset card (word order only, different terms, or not a licence id). | 3.2, 3.3, 4.6 |
| `report()` | Counts, per corpus, how many rows each proposed change touches, including the 4.1 to 4.4 de-duplication fixes. | 3, 4 |

```bash
pip install pyarrow pandas            # pandas only for the notebook
python3 universalcefr_fixes.py --download --dir pq   # 24 parquet exports + cards, ~26 MB
python3 universalcefr_fixes.py --dir pq --csv report.csv
python3 -m pytest -q fixes/            # 8 unit tests
```

`universalcefr_fixes.ipynb` runs the same steps with the output saved.
`run_output.txt` and `report.csv` are the committed run (12 November 2026).

## Results on the public data (run 12 November 2026)

All 24 exports were at the revisions pinned in the document's Appendix A
(none had changed), so the counts reproduce the document's.

* 65,037 rows; 17 distinct label strings, all recognised by the mapping.
* Plus-levels moved to `cefr_sublevel`: **1,823 rows** (elg_cefr_en 114,
  elg_cefr_nl 1,505, icle500_en 204).
* Bare "B" to `cefr_range` B1-B2: **18 rows** (hablacultura_es).
* Missing-label markers to `null` with reason: **22 rows** (merlin_cs 2,
  merlin_it 7, icle500_en 7, zaebuc_ar 6). Together with the 18, that is the
  document's 40 rows outside the six bands.
* Row licence against the card: **13 of 24 corpora differ**. 7 differ only in
  word order (11,108 rows), 5 state different terms (5,527 rows: the three
  elg_cefr corpora add ShareAlike, icle500_en says CC0, zaebuc_ar drops
  NonCommercial), and learn_welsh_cy says "public" (1,372 rows). Writing SPDX ids
  would touch every row (65,037), since none is an SPDX string today.
* Keeping each text once: cople2_pt **471** rows fewer, elg_cefr_nl **2,401**
  rows fewer. caes_es has **214** placeholder rows reading "none".
* `check_row()` flags 18,034 of 65,037 rows, almost all for the licence string.

## Interpretation notes

* The dataset cards declare a licence but no label set, so labels are checked
  against the collection's six CEFR levels, with plus-levels kept as valid
  sub-levels.
* The code proposes; it applies nothing. Whether each issue starts upstream or
  in the conversion is the providers' call, as the document says.

## Data and licences

This folder holds no UniversalCEFR data. Each corpus keeps its own licence
(mostly CC BY-NC or CC BY-NC-SA); `--download` fetches the published exports
from huggingface.co/UniversalCEFR. Related: universalcefr-check,
doi:10.5281/zenodo.22821029.
