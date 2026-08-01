---
type: concept
title: gold-002 — precision weights
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

# gold-002 — precision weights

2026-07-27. Class weights `0.1 / 5.0 / 3.0` → `0.3 / 2.0 / 1.5`: raise the `O`
weight to penalise over-prediction, lower `B`/`I`. Everything else identical to
[[gold-001-first-reviewed-labels|gold-001]].

**Test F1 0.7227 (+0.049) · P 0.6558 (+0.075) · R 0.8048 (+0.004).**

The lever worked exactly as intended — and that is the interesting part. The
*same* lever in [[run-002-class-weights|Run 002]] moved precision the wrong way.
On clean labels it behaves; on noisy ones it cannot, because the model's "false"
positives were partly correct.

Best val F1 0.7625 at epoch 18, with early stopping never firing — so the run is
epoch-limited, which is what [[gold-003-more-epochs|gold-003]] tests.
