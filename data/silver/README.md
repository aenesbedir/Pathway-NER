# Silver labels (LLM-generated)

LLM-generated, **noisy** pathway span annotations produced by the guided-extraction
pipeline (`llm/extract_guided.py`). These are training-label *candidates*, not
ground truth.

- **Silver** = machine-labeled here. It must go through review before being trusted
  for training.
- **Reviewed training gold** = corrected training annotations under `doccano/`.
- **External golden set** = the separate 10-PMID evaluation set under
  `playground/golden_set/`; it is never mixed into training.

Every span carries provenance: `source="llm_silver"`, `model`, `match_type`,
`canonical`, so silver spans can always be traced and separated.

Contents (filled in as phases run):
- `pilot_1k.jsonl` — Phase 1 pilot output (1k abstracts)
- `pilot_1k_doccano.jsonl` — doccano import for the pilot
- `wave2_1k.jsonl` — wave-2 sample output (1k abstracts, qwen2.5:14b), frozen by
  `wave2_1k_pmids.txt`
- `wave3_1k.jsonl` — wave-3 sample output (1k abstracts, qwen2.5:14b), frozen by
  `wave3_1k_pmids.txt`
- `wave4_1k.jsonl` — wave-4 sample output (1k abstracts, qwen2.5:14b), frozen by
  `wave4_1k_pmids.txt`
- `all.jsonl` — Phase 2 full-corpus output

Once reviewed, silver → gold: see `data/processed/gold/README.md` for the
review-correction chain and the derived train/val/test dataset. The final wave-3
and wave-4 gold JSONL files are tracked as canonical records; their local review
JSONs are audit material and are not tracked.
