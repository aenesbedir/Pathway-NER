# doccano — human review of silver pathway spans

Everything needed to get the LLM-generated (silver) pathway spans in front of human
annotators, and to get their corrections back out.

The full 1,000-document pilot review is complete. Batches 01-03 have auditable
review decisions in `analysis/pilot_batchNN_review.json`; batches 04-05 retain
their existing reviewed gold. The combined canonical output is
`pilot_1k_gold.jsonl`.

Wave-3 and wave-4 review is complete. Their final canonical training annotations
are tracked as `wave3_1k_gold.jsonl` and `wave4_1k_gold.jsonl`; detailed review JSONs
remain local audit material.

Pilot batch 04's final labels are tracked as
`pilot_1k_batch04_gold.jsonl`: the 200 documents of
`batches/pilot_1k_doccano_batch_04_5.jsonl` after review, changing the spans of 81
documents and taking the batch from 413 to 508 spans. Unlike batch 05, it has no
separate review JSON — this file is the only record of those corrections.

| File | What it is |
|---|---|
| `pilot_1k_doccano.jsonl` | **The import file** — 1,000 abstracts, 1,996 pre-filled `PATHWAY` spans |
| `golden_100_doccano.jsonl` | **Golden-set expansion import (single file)** — 100 docs from the 10k corpus *test* split, 261 `PATHWAY` + 865 `DISEASE` pre-filled spans |
| `golden_100_test_pmids.txt` | Selection record of the 100 PMIDs (seed 20260818) |
| `ANNOTATION_GUIDE.md` | **Give this to the annotators.** Accept/reject/boundary rules (EN) |
| `ANNOTATOR_STEPS.md` | **Give this to the annotators.** Post-install doccano steps (TR) |
| `split_batches.py` → `batches/` | Splits the import file into per-annotator batches |
| `export_doccano.py` | Regenerates the import file from `data/silver/pilot_1k.jsonl` |
| `preview.py` → `preview.html` | Static preview of the spans — check them **without** installing doccano |

Upstream: `llm/run_silver.py` produces `data/silver/pilot_1k.jsonl`; this folder only
reshapes it for doccano. Provenance and analysis: `project_tracking.md` (P3-1c/d/e),
`playground/silver_1k_analyses.md`.

## Golden-set expansion (100 test-split docs, single import file)

`golden_100_doccano.jsonl` is the one file the new golden-set docs move through —
**all 100 from the 10k corpus test split**, nothing else (the 10 curated docs of
`playground/golden_set/golden_set.json` stay separate and are not mixed in).

Selection (record: `golden_100_test_pmids.txt`, seed 20260818), from the 609
test-split docs that are disjoint from all training data (10k train/val,
gold-pilot1k wave2/3/4+pilot, frozen silver — 404 of 1013 test docs were
contaminated and excluded):

- **Span-count distribution kept varied** — 9 docs with 0 pathways, 33 with 1,
  20 with 2, 22 with 3-4, 16 with 5+ (mirrors the test split).
- **Pathway diversity maximized** — greedy selection by marginal new canonical
  coverage; the 100 cover **61 of 61** distinct Recon pathways present in the pool.
- **Variation preference** — tie-breaking prefers docs whose gold spans are
  paraphrase forms (word-order, chemical synonyms, abbreviations, umbrellas);
  the 100 contain **186 variation-type** spans (vs 75 exact/synonym).

The pre-filled labels come from the 10125-corpus gold — **both `PATHWAY` (261) and
`DISEASE` (865) spans are included** — the job is verify/correct, exactly like the
pilot batches. The doccano project must define **both** labels (`PATHWAY` and
`DISEASE`); the import fails on any label the project does not define.

- The 100 PMIDs are **already excluded from silver** (`GOLDEN_PMIDS` in
  `llm/run_silver.py` + `playground/golden_set/golden_pmids.txt` — 110 entries with
  the 10 curated v1/v2) so review time cannot leak eval data into training. Do not
  remove them.
- After review, convert with `build_gold_from_review.py` and merge into the golden set.

## Preview before you import

```bash
venv310/bin/python3 doccano/preview.py                 # first 40 documents
venv310/bin/python3 doccano/preview.py --limit 200
```

Then open `doccano/preview.html`. It renders straight from the import file using the
exact offsets doccano will read, so it shows what doccano will show. Blue = LLM span,
orange = booster span. Hover any span for its canonical / match_type / source.

## Format

Verified against doccano's importer (`backend/data_import/pipeline/catalog.py`, whose
`ArgColumn` defaults are `column_data="text"`, `column_label="label"`):

```json
{"text": "<abstract>", "label": [[74, 90, "PATHWAY"]], "meta": {"pmid": "10701848", "model": "qwen2.5:14b", "query_pathways": ["..."], "spans": [{"text": "purine synthesis", "canonical": "purine synthesis", "match_type": "exact", "source": "llm_silver"}]}}
```

- `label` is **singular** on import, and each entry is `[start_offset, end_offset, "PATHWAY"]`.
  doccano's *export* format uses `labels` (plural) — an asymmetry in their own docs. Do not
  copy the export shape back into an import file.
- `meta` is nested. The doccano workspace at `/home/enes/annotations` has imported 488
  records in exactly this shape, so it is the proven one; a flattened variant is untested.
- The label string never reaches the model — `train.py` hardcodes
  `{"O", "B-Pathway", "I-Pathway"}` and `tag_bio.py` derives BIO from the spans, not from
  this name. It only has to match the label defined in the doccano project. `PATHWAY` is
  what `/home/enes/annotations/DOCCANO_GUIDE.md` already prescribes.
- Offsets are character offsets into `text`. The exporter drops any span whose offsets do not
  reproduce its recorded surface exactly — the last run dropped **zero**.

## Import into doccano

doccano is already installed and runnable at `/home/enes/annotations` (its own venv +
`doccano-home/db.sqlite3`); see that folder's `DOCCANO_GUIDE.md` §1–2 for start/stop.

1. Start the server, log in at `http://localhost:8000`.
2. **Create a new project**, type **Sequence Labeling**. Do not reuse the existing
   *"Pathway-disease relation project"* — that one holds the 488-document **Phase 1**
   import, which is out of scope here (see below).
3. In **Labels**, add a single label named exactly `PATHWAY`. The import fails on any label
   the project does not define, and this file uses only that one.
4. In **Datasets → Import**, choose file format **JSONL** and upload
   `pilot_1k_doccano.jsonl`. Leave the column settings at their defaults (`text` / `label`).
   You should see 1,000 documents.
5. Hand the annotators `ANNOTATION_GUIDE.md`.

## Splitting into per-annotator batches (local-install workflow)

Annotators install doccano locally and each imports one slice. Split the import file:

```bash
venv310/bin/python3 doccano/split_batches.py            # 200 docs per batch → 5 files
venv310/bin/python3 doccano/split_batches.py --size 100 # smaller batches
```

Output in `doccano/batches/`, named `pilot_1k_doccano_batch_NN_TOTAL.jsonl` (so it is
always clear which file was split and which slice this is), e.g.
`pilot_1k_doccano_batch_01_5.jsonl`. Each batch is a verbatim slice — self-contained and
directly importable, exactly like the full file.

Send each annotator **their batch file + `ANNOTATOR_STEPS.md` (TR, post-install steps) +
`ANNOTATION_GUIDE.md` (the accept/reject rules)**. In `ANNOTATOR_STEPS.md` step 4 the doc
count to expect is the batch size (200), not 1,000.

### Phase 1 is out of scope
`/home/enes/annotations` also contains a Phase-1 pathway export (488 docs, from
`all_matches.jsonl`) and its own `DOCCANO_GUIDE.md`, written before Phase 2/3 existed. That
project has **zero human review done** (556 spans, all machine pre-fill; 0 documents marked
complete), and it shares just **3 PMIDs** with this Phase 3 silver — different corpus,
different vocabulary. Nothing is lost by leaving it alone.

## What the annotators do

One label type, so the job per span is **accept / reject / fix the boundary**, plus adding
any mention the machine missed. They do **not** assign pathway names — `canonical` in
`span_info` is a machine guess kept for context only, and it is `null` for 29% of spans by
design. The rules and the edge cases are in `ANNOTATION_GUIDE.md`.

## After review

Export the annotated data from doccano (its export uses `labels`, plural) and convert
the corrections into reviewed training gold with `build_gold_from_review.py`. This
training gold remains separate from the external golden set under
`playground/golden_set/`: its 10 PMIDs are deliberately excluded so evaluation data
never enters training.

The default converter rebuilds only sources whose review inputs are tracked. On the
machine holding the local wave-3/4 review audit files, pass
`--include-local-reviews` to rebuild their tracked canonical gold JSONL files.
