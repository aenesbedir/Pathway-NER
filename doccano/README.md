# doccano — human review of silver pathway spans

Everything needed to get the LLM-generated (silver) pathway spans in front of human
annotators, and to get their corrections back out.

| File | What it is |
|---|---|
| `pilot_1k_doccano.jsonl` | **The import file** — 1,000 abstracts, 1,996 pre-filled `Pathway` spans |
| `ANNOTATION_GUIDE.md` | **Give this to the annotators.** Accept/reject/boundary rules |
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
{"text": "<abstract>", "label": [[74, 90, "Pathway"]], "pmid": "10701848", "model": "qwen2.5:14b", "query_pathways": ["..."], "span_info": [{"text": "purine synthesis", "canonical": "purine synthesis", "match_type": "exact", "source": "llm_silver"}]}
```

- `label` is **singular** on import, and each entry is `[start_offset, end_offset, "Pathway"]`.
  doccano's *export* format uses `labels` (plural) — an asymmetry in their own docs. Do not
  copy the export shape back into an import file.
- Every top-level key other than `text` / `label` is stored by doccano as example metadata,
  so the extras are kept **flat** (not nested under a `meta` object).
- Offsets are character offsets into `text`. The exporter drops any span whose offsets do not
  reproduce its recorded surface exactly — the last run dropped **zero**.

## Import into doccano

1. Install and start doccano (not installed in this repo — see
   <https://doccano.github.io/doccano/>).
2. Create a project with type **Sequence Labeling**.
3. In **Labels**, add a single label named exactly `Pathway`. The import fails on any label
   the project does not define, and this file uses only that one.
4. In **Datasets → Import**, choose file format **JSONL** and upload
   `pilot_1k_doccano.jsonl`. Leave the column settings at their defaults
   (`text` / `label`).
5. Hand the annotators `ANNOTATION_GUIDE.md`.

## What the annotators do

One label type, so the job per span is **accept / reject / fix the boundary**, plus adding
any mention the machine missed. They do **not** assign pathway names — `canonical` in
`span_info` is a machine guess kept for context only, and it is `null` for 29% of spans by
design. The rules and the edge cases are in `ANNOTATION_GUIDE.md`.

## After review

Export the annotated data from doccano (its export uses `labels`, plural) and treat it as
the corrected silver set. It stays separate from the gold set
(`playground/golden_set/`) — the 5 golden PMIDs are deliberately excluded from this file so
that silver never trains on the evaluation set.
