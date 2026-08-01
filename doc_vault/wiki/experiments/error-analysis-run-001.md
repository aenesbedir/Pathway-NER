---
type: concept
title: Error analysis of Run 001
status: archived
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - experiment
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - knowledge_base/model_experiments.md
  - project_tracking.md
last_reviewed: 2026-08-01
---

# Error analysis of Run 001

The turning point of the project. [[run-001-baseline|Run 001]]'s predictions were
decoded back to character spans and compared to the test labels
(`analysis/error_analysis.py` → `analysis/error_analysis.json`).

Span counts on the 50 test records: 38 exact true positives, 3 partial (boundary
mismatch), 30 false positives, 23 false negatives. Span-level P 0.559 / R 0.623 /
F1 0.589 under exact scoring.

## The finding that redirected everything

**Many of the false positives are legitimate pathway names** — `heme synthesis`,
`cholesterol metabolism`, `glycolytic pathway` — that the annotation pipeline
never labelled. The model found them; the ground truth did not have them. The
recorded conclusion is unambiguous: *improving the annotation pipeline will have
more impact than further hyperparameter tuning.*

Two other error classes:

- **Partial-term over-generalization** — the model tags components like
  `biosynthesis`, `metabolism`, `sulfate` on their own.
- **A tokenizer artifact** — `dermatan` splits as `dermat` + `##an`, causing a
  cluster of ~10–11 false negatives for the dermatan sulfate pathway. Tier 0
  later measured that this split survives **every** candidate tokenizer, so it is
  not fixable by swapping encoders ([[tokenization|Tokenization]]).

Everything after this point — [[phase-2-pubmed-corpus|Phase 2]],
[[phase-3-silver-labeling|Phase 3]], human review — follows from the first
finding.
