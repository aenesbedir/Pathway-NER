---
type: concept
title: Run 003 — freeze 6 layers
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

# Run 003 — freeze 6 layers

2026-06-29. Embeddings and encoder layers 0–5 frozen (101 of 199 parameter
groups); only layers 6–11 and the classifier train.

**Test F1 0.4177 · P 0.3300 · R 0.5690.** Ran all 20 epochs without early
stopping.

The reasoning behind freezing was that BiomedBERT is already pretrained on the
same domain, so the lower layers should transfer unchanged. The measurement says
otherwise: precision dropped despite fewer trainable parameters.

Continued in [[run-004-freeze-9-layers|Run 004]], and finally reversed by
[[gold-004-unfreeze-all-layers|gold-004]], where unfreezing everything turned out
to be the single biggest lever in the project.
