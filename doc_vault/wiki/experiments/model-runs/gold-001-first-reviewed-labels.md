---
type: concept
title: gold-001 — first reviewed labels
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

# gold-001 — first reviewed labels

2026-07-27. First model trained on [[gold-labels|gold]] — review-corrected
labels — instead of raw distant supervision. Architecture and hyperparameters
identical to [[run-001-baseline|Run 001]] (still 9 frozen layers). Data:
860 / 107 / 109 documents.

**Test F1 0.6734 · P 0.5809 · R 0.8008.**

## Reading

- A large jump over the Phase-1 silver models (0.37–0.46 → 0.67) attributable to
  label quality alone; nothing else changed.
- **Not comparable to [[run-005-phase-2-data|Run 005]]'s 0.98** — that was a
  different, exact-match test set with trivial string-match leakage.
- Precision 0.58 against recall 0.80: the model over-tags. The recorded
  hypothesis is that umbrella and coordinated gold spans push aggressive tagging.
- The teacher `qwen2.5:14b` scores P 0.906 / R 0.825 / F1 0.864 on the same
  guide-based gold, so the student starts 0.19 F1 behind.

Next lever taken: the precision knob, in
[[gold-002-precision-weights|gold-002]].
