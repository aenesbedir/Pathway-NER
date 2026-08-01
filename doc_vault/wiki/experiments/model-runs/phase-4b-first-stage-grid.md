---
type: concept
title: Phase 4b — first-stage grid
status: provisional
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
  - project_tracking.md
last_reviewed: 2026-08-01
---

# Phase 4b — first-stage grid

Paused 2026-07-31. Five encoders × 2 learning rates × 3 seeds = 30 cells on the
fixed gold-004+ recipe. The five were picked for the widest expected spread at
the lowest cost:

| model | role |
|---|---|
| `biomedbert-base` | anchor — every other number is read against it |
| `bert-base` | domain floor (BLURB NER 82.99 vs 86.13) |
| `bio-clinicalbert` | domain mismatch from the opposite side |
| `bioelectra-base` | objective contrast: RTD vs MLM on a byte-identical vocabulary |
| `bio-modernbert-base` | the only architecture / tokenizer / 8192-context change |

The other twelve registry encoders stay in reserve with datasets already built
and validated.

## What was recorded — 7 cells

`biomedbert-base` at lr 5e-05 gives 0.8199 / 0.7947 / 0.8282 (mean 0.8143) and at
3e-05 gives 0.8191 / 0.8125 / 0.8053 (mean 0.8123). The first row reproduces the
[[tier-0-comparison-harness|Tier 0]] measurement exactly — a regression test on
the harness, not a new result. The two learning rates are 0.002 apart against
σ = 0.0175, i.e. indistinguishable at three seeds. `bio-modernbert-base` has one
cell at 0.7857.

## Why 18 cells failed

`bert-base`, `bio-clinicalbert` and `bioelectra-base` aborted immediately:
dataset preparation only ever pulls tokenizer and config, so the weights were
never cached, and `HF_HUB_OFFLINE=1` turned the miss into a hard failure instead
of a download. Resolved — all three are cached and their vocabulary fingerprints
still match the datasets built earlier.

## The finding that outranks the grid

Re-running the oldest cell twice did not reproduce it:
[[training-is-not-reproducible-at-a-fixed-seed|training is not reproducible at a
fixed seed]]. Until that is understood, the grid resolves less than planned.

Resuming is a no-op-safe re-run: `scripts/run_matrix.py` skips any cell that
already holds `test_results.json`, leaving 23 cells (~4 hours). The exact command
stays canonical in `project_tracking.md`.
