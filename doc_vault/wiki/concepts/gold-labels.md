---
type: concept
title: Gold labels
status: evergreen
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - annotation
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - data/processed/gold/README.md
  - knowledge_base/model_experiments.md
last_reviewed: 2026-08-01
---

# Gold labels

Review-corrected labels: for each document, gold = the accepted true positives
plus the false negatives the reviewer added, with rejected spans dropped. This is
what every `gold-00N` run trains on.

Two review batches feed it, with no PMID overlap: wave-2 silver (1,000
documents) and pilot-1k batch 05 (200 documents).

## Two different things are called "gold"

They are not interchangeable and mixing them produces wrong conclusions:

| | purpose | size |
|---|---|---|
| `data/processed/gold/` | **training** dataset from reviewed silver | 1,200 documents |
| [[golden-set\|golden set]] | **evaluation** answer key, hand-annotated | 10 abstracts |

## Shape of the training dataset

1,200 documents → 1,083 with at least one span → 1,076 with B/I tokens after
512-token truncation → an 80/10/10 PMID-stratified split of **860 / 107 / 109**.
The seven documents lost to truncation are excluded for every encoder, including
long-context ones, so historical runs stay comparable —
[[freeze-the-gold-split|Freeze the gold split]].

The directory holds only tokenizer-independent artefacts; anything containing
`input_ids` lives in a per-model directory. The provenance chain and the six
regeneration commands stay canonical in `data/processed/gold/README.md`.

## Quality ceiling

The teacher `qwen2.5:14b` scores P 0.906 / R 0.825 / F1 0.864 span-exact against
this same guide-based gold, and the best student sits at F1 ~0.82 — see
[[experiments-index|Experiments]].
