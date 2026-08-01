---
type: concept
title: gold-003 — more epochs, balanced weights
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

# gold-003 — more epochs, balanced weights

2026-07-27. Class weights `0.3 / 2.0 / 1.5` → `0.5 / 1.5 / 1.0`, max epochs
20 → 40, patience 5 → 8.

**Test F1 0.7437 · P 0.6799 · R 0.8207.**

Both precision (+2.4) and recall (+1.6) rose over
[[gold-002-precision-weights|gold-002]] — no trade-off this time; the extra
epochs let the flatter weights fit. Cumulative gain over
[[gold-001-first-reviewed-labels|gold-001]]: F1 +0.070, precision +0.099.

The note's own read at this point was that weight and epoch tuning were near
their ceiling and that more reviewed data was the dominant lever. That turned out
to be premature — one untried architectural knob was still worth +0.072 on its
own: [[gold-004-unfreeze-all-layers|gold-004]].
