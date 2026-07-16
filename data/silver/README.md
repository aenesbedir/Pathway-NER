# Silver labels (LLM-generated)

LLM-generated, **noisy** pathway span annotations produced by the guided-extraction
pipeline (`llm/extract_guided.py`). These are training-label *candidates*, not
ground truth.

- **Silver** = machine-labeled here. Must go through human review (doccano) before
  being trusted for training.
- **Gold** = human-curated, in `playground/golden_set/`. Never mixed with silver.

Every span carries provenance: `source="llm_silver"`, `model`, `match_type`,
`canonical`, so silver spans can always be traced and separated.

Contents (filled in as phases run):
- `pilot_1k.jsonl` — Phase 1 pilot output (1k abstracts)
- `pilot_1k_doccano.jsonl` — doccano import for the pilot
- `all.jsonl` — Phase 2 full-corpus output
