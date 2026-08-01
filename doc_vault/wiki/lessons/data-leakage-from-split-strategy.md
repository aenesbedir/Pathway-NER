---
type: concept
title: Data leakage from the split strategy
status: evergreen
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - lesson
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - lessons_learned/challenges.md
  - project_tracking.md
last_reviewed: 2026-08-01
---

# Data leakage from the split strategy

**Symptom.** During [[run-005-phase-2-data|Run 005]], validation F1 reached
**0.980 at epoch 13** — against Phase 1's best of ~0.49 on a comparable task.
Training was stopped on suspicion rather than celebrated.

**Cause.** `build_dataset.py` grouped the split on `pathway_ids[0]`, but one
article produces one abstract record plus N full-text window records. Records
from the **same PMID** could therefore land in different splits:

```
PMID 12345, "Glycolysis" → abstract record → train
PMID 12345, "Glycolysis" → ft window 1     → train
PMID 12345, "Glycolysis" → ft window 2     → val    ← same article
```

The model trained on one window of an article and was evaluated on another —
nearly identical text.

**Fix.** Group on `pmid` — [[use-pmid-based-dataset-splitting|the decision]].

**The corroborating detail.** Before the fix, val held only 1,311 records. The
split looked balanced at pathway level while being badly imbalanced at article
level, which is the tell nobody was looking at.

## What generalises

Whenever one source document produces several training records — sliding windows,
multi-span abstracts, augmented views — the split boundary must be drawn at the
**document level**. Splitting at a finer granularity almost always leaks.

And the meta-lesson: an implausibly good validation number is a bug report. The
one habit that worked here was distrusting it immediately.
