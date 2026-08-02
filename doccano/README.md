# doccano — human review of silver pathway spans

Everything needed to get the LLM-generated (silver) pathway spans in front of human
annotators, and to get their corrections back out.

Wave-3 and wave-4 review is complete. Their final canonical training annotations
are tracked as `wave3_1k_gold.jsonl` and `wave4_1k_gold.jsonl`; detailed review JSONs
remain local audit material.

| File | What it is |
|---|---|
| `pilot_1k_doccano.jsonl` | **The import file** — 1,000 abstracts, 1,996 pre-filled `PATHWAY` spans |
| `ANNOTATION_GUIDE.md` | **Give this to the annotators.** Accept/reject/boundary rules (EN) |
| `ANNOTATOR_STEPS.md` | **Give this to the annotators.** Post-install doccano steps (TR) |
| `split_batches.py` → `batches/` | Splits the import file into per-annotator batches |
| `export_doccano.py` | Regenerates the import file from `data/silver/pilot_1k.jsonl` |
| `preview.py` → `preview.html` | Static preview of the spans — check them **without** installing doccano |

Upstream: `llm/run_silver.py` produces `data/silver/pilot_1k.jsonl`; this folder only
reshapes it for doccano. Provenance and analysis: `project_tracking.md` (P3-1c/d/e),
`playground/silver_1k_analyses.md`.

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
