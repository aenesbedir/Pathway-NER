---
type: concept
title: Split datasets by PMID
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
  - lessons_learned/challenges.md
  - project_tracking.md
last_reviewed: 2026-08-01
---

# Split datasets by PMID

**Decision.** Train/val/test assignment groups on `pmid`, never on
`pathway_ids[0]`. Every record derived from one article lands in one split.

**Why.** A single article produces one abstract record plus N full-text window
records. Grouping by pathway put windows of the *same* article on both sides of
the split, and the model was evaluated on text it had effectively trained on —
[[data-leakage-from-split-strategy|the leakage incident]].

**The change** is one line in `preprocessing/build_dataset.py`: the grouping key
becomes `r["pmid"]`.

**Evidence it was real.** Before the fix, val held 1,311 records — suspiciously
small, balanced at pathway level but not at article level. After it: 7,085 / 885
/ 887 PMIDs.

**Scope.** The rule generalises beyond this dataset: whenever one source document
produces several training records — sliding windows, multi-span abstracts,
augmented views — the split boundary is the document. It still governs the gold
dataset, which is PMID-stratified and additionally
[[freeze-the-gold-split|frozen on disk]].
