---
type: concept
title: Tier 0 — comparison harness
status: active
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - experiment
  - infrastructure
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - knowledge_base/model_experiments.md
  - reports/base_model_expansion_analysis_2026-07.md
last_reviewed: 2026-08-01
---

# Tier 0 — comparison harness

2026-07-29. Infrastructure only, no modelling change. Its purpose was to make
cross-encoder numbers mean anything at all.

## Three defects that would have invalidated the survey

1. **The split was tokenizer-dependent.** `build_dataset.py` dropped label-free
   records *after* tokenization (1083 → 1076 under BiomedBERT, 7 lost to
   512-token truncation) and shuffled the survivors. A ModernBERT at 8192 tokens
   loses none of the 7 and would shuffle a different-length list into an
   unrelated assignment — every encoder scored on a different test set, with
   every log line still reading "Test: 109".
2. **The model name was hardcoded in two files** with nothing linking the
   `input_ids` on disk to the model consuming them. Vocabularies overlap in
   range, so a mismatch trains silently on nonsense.
3. **`train.py` could only load BERT**, and used fp16 — a known NaN source for
   ModernBERT, which was pretrained in bf16.

## What was built

`encoders.py` (a registry shaped like `llm/models.py`),
`preprocessing/make_splits.py`, `preprocessing/check_alignment.py`,
`scripts/run_matrix.py`, `scripts/aggregate_runs.py`, and the tracked
`data/processed/gold/splits.json` — see [[freeze-the-gold-split|the decision]].

## The gate

The regenerated dataset is **byte-identical** to the one gold-001…008 used, and
the gold-008 recipe re-run under bf16 and transformers 5.10.2 gives **F1 0.8199**
against the recorded 0.8197. The historical series is continuous.

## What it measured that changed the plan

- **The seed band at lr 5e-5 is ±0.0175**, 2.5× the ±0.007 every earlier
  conclusion leaned on — see [[gold-005-008-seed-and-lr-sweep|the sweep]].
  Resolving 0.015 F1 needs 11 seeds.
- **Long context buys 0.000 F1 on this split.** ModernBERT truncates 0 of 2,817
  gold spans against 29–33 for the 512-token candidates, but *all* those losses
  fall in train/val — the test split loses none. Its only effect is 33 extra
  training spans.
- Tokenizer findings are collected in [[tokenization|Tokenization]].
- **`biomedbert-large` is not the size-only control it was chosen to be** — its
  vocabulary differs from `biomedbert-base`'s, so base → large changes the
  tokenizer too. `biolinkbert-base` → `-large` is the confound-free pair.

Two annotation problems were also handed to the next review wave: 83 nested span
pairs and 12 boundary-error spans (`analysis/alignment_*.json`).
