---
type: concept
title: Run 004 — freeze 9 layers
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

# Run 004 — freeze 9 layers

2026-06-29. Embeddings and encoder layers 0–8 frozen (149 of 199 parameter
groups); only layers 9–11 and the classifier train.

**Test F1 0.3656 · P 0.2656 · R 0.5862** — the worst result of the Phase-1
series.

With [[run-003-freeze-6-layers|Run 003]] this gives a clean monotone trend: more
frozen layers, worse F1 and worse precision. Freezing was ruled out for this
dataset and domain.

The whole Phase-1 series spans F1 0.37–0.46 with precision never above 0.40. That
consistency across four different hyperparameter settings is what pointed at the
labels rather than the configuration, and produced
[[error-analysis-run-001|the error analysis]] and then
[[phase-2-pubmed-corpus|Phase 2]].

Ironically, the 9-frozen-layer setting persisted as the default into
[[run-005-phase-2-data|Run 005]] and the early gold runs, and was only undone at
[[gold-004-unfreeze-all-layers|gold-004]].
