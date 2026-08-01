---
type: concept
title: Run 005 — Phase 2 data
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

# Run 005 — Phase 2 data

2026-07-10. Same architecture as [[run-001-baseline|Run 001]], entirely new data:
the [[phase-2-pubmed-corpus|Phase 2]] corpus, 7,085 / 885 / 887 PMIDs
(33,328 / 3,970 / 4,403 records), split by PMID.

**Test F1 0.9812 · P 0.9713 · R 0.9913.**

## Read that number carefully

It is not a 0.46 → 0.98 modelling improvement. Two things produced it:

1. **A first attempt with a pathway-based split leaked** — val F1 hit 0.98 at
   epoch 13 and training was stopped on suspicion. The fix was
   [[use-pmid-based-dataset-splitting|splitting by PMID]]; see
   [[data-leakage-from-split-strategy|the lesson]].
2. **Even after the fix the task is easy.** The corpus was retrieved *because*
   articles co-mention the pathway, so exact matching hits 93.4% of articles and
   the test labels are the same literal strings as the training labels. The later
   note on [[gold-001-first-reviewed-labels|gold-001]] states it directly: Run
   005 is *not comparable*, it was scored on an exact-match test set with trivial
   string-match leakage.

So the honest reading is that Run 005 measured how well a model can memorise a
lookup table — which is exactly the near-lookup problem
[[distant-supervision|distant supervision]] creates, and the reason
[[phase-3-silver-labeling|Phase 3]] followed instead of a victory lap.

Prediction analyses for this model live in `playground/model_005_analysis/` and
`playground/model_005_ground_truth_compare/`.
