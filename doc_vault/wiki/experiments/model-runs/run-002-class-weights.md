---
type: concept
title: Run 002 — reduced class weights
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
last_reviewed: 2026-08-01
---

# Run 002 — reduced class weights

2026-06-26. One change from [[run-001-baseline|Run 001]]: class weights
`0.1 / 5.0 / 3.0` → `0.1 / 2.0 / 1.5`, intended to raise precision.

**Test F1 0.4500 · P 0.3529 · R 0.6207.**

## The result is the opposite of the hypothesis

Precision fell (0.40 → 0.35) while recall rose (0.55 → 0.62). The recorded
conclusion: weight tuning is not the right lever here, because the model is
over-predicting for a different reason — noisy [[distant-supervision|distant
supervision]] labels teach it that unlabelled pathway names are negatives.

Worth contrasting with [[gold-002-precision-weights|gold-002]], where the *same*
lever on clean labels moved precision +7.5 points exactly as intended. The lever
was never broken; the labels were.
