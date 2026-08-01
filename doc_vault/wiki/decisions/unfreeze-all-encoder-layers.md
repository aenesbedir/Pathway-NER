---
type: concept
title: Train all encoder layers
status: evergreen
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - decision
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - knowledge_base/model_experiments.md
last_reviewed: 2026-08-01
---

# Train all encoder layers

**Decision.** `--frozen-layers 0`. No layer freezing, embeddings included. This
is part of the standard recipe every later run varies around:
`--class-weights 0.5 1.5 1.0 --epochs 40 --patience 8 --frozen-layers 0`.

**Evidence.** Twice, independently:

- Phase 1, on noisy labels: freezing 6 layers gave F1 0.4177 and freezing 9 gave
  0.3656 against 0.4604 unfrozen — a monotone trend in the wrong direction.
- Phase 3 gold data: [[gold-004-unfreeze-all-layers|gold-004]] lifted F1 0.7437 →
  **0.8154** and precision 0.6799 → **0.7881** over the identical 9-frozen
  recipe. Far outside the ±0.007 band, so unambiguously real.

**Why it took so long.** The 9-frozen setting was inherited from
[[run-004-freeze-9-layers|Run 004]] — an experiment that had *already been
recorded as a failure* — and carried into Run 005 and gold-001…003 unquestioned.
Three class-weight and epoch experiments were spent tuning around a known-bad
default.

**Cost.** Training time roughly triples (about 164 s → 452 s per run on the RTX
4060 Laptop), which is affordable at this data scale.

The stated interpretation is that BiomedBERT's lower layers need full adaptation
**even within the same pretraining domain**, contradicting the intuition that
made freezing look sensible.
