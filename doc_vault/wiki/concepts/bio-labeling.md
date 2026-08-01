---
type: concept
title: BIO labeling
status: evergreen
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - nlp
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - knowledge_base/nlp_concepts.md
  - project_tracking.md
last_reviewed: 2026-08-01
---

# BIO labeling

Token classification needs one label per token. This project uses three classes
plus an ignore value:

| Value | Name | Meaning |
|---|---|---|
| `0` | O | outside any entity |
| `1` | B-Pathway | first token of a pathway mention |
| `2` | I-Pathway | continuation of a pathway mention |
| `-100` | ignore | special tokens and subword continuations |

`-100` is a HuggingFace convention: PyTorch's `CrossEntropyLoss` skips those
positions. Only the **first subword of each word** carries a real label; the rest
are masked, so the model is never trained to predict a label for `##lytic`
independently.

## Two consequences that shaped the project

- **Class imbalance is normal.** In Phase 1 the tag distribution was 98.6% `O`.
  This motivated weighted loss, and the weight lever behaved differently on noisy
  and on clean labels — compare [[run-002-class-weights|Run 002]] with
  [[gold-002-precision-weights|gold-002]].
- **Flat BIO cannot represent nesting.** When a shared-head enumeration is
  annotated both whole and in parts, the inner span's start opens a new `B` and
  truncates the outer mention. 83 such pairs are recorded in
  `analysis/alignment_*.json` and handed to the next review wave.

The label strings never leave the training code: `train.py` hardcodes
`{"O", "B-Pathway", "I-Pathway"}` while doccano uses the label name `PATHWAY`,
and the two only have to agree inside the annotation tool.
