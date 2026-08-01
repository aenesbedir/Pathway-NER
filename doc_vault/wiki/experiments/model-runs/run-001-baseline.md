---
type: concept
title: Run 001 — baseline
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

# Run 001 — baseline

2026-06-26. The first fine-tune: all layers trainable, on
[[phase-1-original-corpus|Phase 1]] data (502 / 44 / 50 records), with weighted
cross-entropy `0.1 / 5.0 / 3.0` to counter the 98.6% `O` imbalance.

**Test F1 0.4604 · P 0.3951 · R 0.5517.** Best val at epoch 10, early stopping at
15.

## What it established

- Precision is the weakness, not recall — 60% of predicted spans were false
  positives.
- No overfitting: val F1 0.4918 ≈ test 0.4604.
- The test set is 50 records over 19 pathways, so every metric has high variance.

The stated next moves were to lower the class weights ([[run-002-class-weights|Run
002]]), run [[error-analysis-run-001|error analysis]], and expand the training
data — which the note already calls the biggest lever.

This remained the best Phase-1 checkpoint.
