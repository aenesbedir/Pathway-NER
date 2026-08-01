---
type: concept
title: Freeze the gold split on disk
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
  - data/processed/gold/README.md
  - knowledge_base/model_experiments.md
last_reviewed: 2026-08-01
---

# Freeze the gold split on disk

**Decision.** `data/processed/gold/splits.json` records the exact train/val/test
assignment (1,076 PMIDs → 860 / 107 / 109) and is **tracked in git**.
`build_dataset.py --splits` assigns by lookup and never shuffles.

**Why.** The split used to be computed after tokenization: documents with no
positive label were dropped (1,083 → 1,076 under BiomedBERT, 7 lost to 512-token
truncation) and the survivors shuffled at `seed=42`. A tokenizer that loses a
different number of documents — a ModernBERT at 8192 tokens loses none — shuffles
a different-length list into an unrelated assignment. Every encoder would have
been scored on a **different test set**, with every log line still reading
"Test: 109".

**The consequence accepted on purpose.** The 7 truncation-killed documents are
excluded for *every* model, including long-context ones that could have kept
them. Reporting that as a separate measurement was judged better than
invalidating eight historical runs.

**Verification.** `data/processed/gold/` holds only tokenizer-independent
artefacts; anything with `input_ids` lives in `data/processed/gold-<slug>/` with
a `meta.json` vocabulary fingerprint that `train.py` refuses to mismatch.

This is what makes [[phase-4-base-encoder-survey|the encoder survey]] a
comparison rather than a set of unrelated numbers. See
[[tier-0-comparison-harness|Tier 0]].
