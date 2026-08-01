---
type: concept
title: gold-004 — unfreeze all layers
status: active
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

# gold-004 — unfreeze all layers

2026-07-27. One change from [[gold-003-more-epochs|gold-003]]:
`--frozen-layers 9` → `0`. The whole network trains, embeddings included.

**Test F1 0.8154 (+0.072) · P 0.7881 (+0.108) · R 0.8446 (+0.024).**

## Why it matters more than its size

Freezing had been the default since [[run-004-freeze-9-layers|Run 004]] — a
setting inherited from a Phase-1 experiment that had *already been ruled a
failure*, carried forward unquestioned into every subsequent run. Removing it was
the single largest lever in the project, larger than every class-weight and epoch
change combined.

The +0.072 jump is far outside the ±0.007 seed band measured at this learning
rate, so unlike most differences in this project it is unambiguously real.

The recipe becomes the standard for everything after it —
`--class-weights 0.5 1.5 1.0 --epochs 40 --patience 8 --frozen-layers 0` — and is
what [[gold-005-008-seed-and-lr-sweep|gold-005…008]] and the Phase 4 grid vary
around. See [[unfreeze-all-encoder-layers|the decision]].
