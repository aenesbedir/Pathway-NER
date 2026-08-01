---
type: concept
title: Phase 4b — first-stage grid
status: evergreen
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - experiment
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: master
source_commit: 0ddf4f344f423b71999f2d3e0fd7ebd2325fb090
source_paths:
  - project_tracking.md
  - knowledge_base/model_experiments.md
last_reviewed: 2026-08-01
---

# Phase 4b — first-stage grid

Completed 2026-08-01. Five encoders × 2 registry learning rates × 3 seeds = **30
cells, 0 failures**, on the fixed gold-004+ recipe. The five were picked for the
widest expected spread at the lowest cost:

| model | role |
|---|---|
| `biomedbert-base` | anchor — every other number is read against it |
| `bert-base` | domain floor |
| `bio-clinicalbert` | domain mismatch from the opposite side |
| `bioelectra-base` | objective contrast: RTD vs MLM on a byte-identical vocabulary |
| `bio-modernbert-base` | the only architecture / tokenizer / 8192-context change |

## Run hygiene

The retained grid was run from a **clean tree at commit `5e7e3f1`**, per the
repository rule that a kept number must name a code snapshot. Seven provisional
rows — three of which predated the pipeline commit — were moved to
`runs/_precommit/` before the clean restart, and the two fixed-seed
reproducibility replicates stay in `runs/_recheck/`. Neither archive enters
`runs/summary.jsonl`, which now holds exactly 30 unique model/LR/seed keys, all
stamped with the same SHA.

Result tables are **generated, never hand-maintained** — reproduce them with
`scripts/aggregate_runs.py`, including `--by domain objective arch` and
`--compare biomedbert-base bert-base`.

## What the grid resolved

- The descriptive leader is `bioelectra-base` at lr 3e-05, **0.8156 ± 0.0175**
  test F1. This is a recipe ranking, not evidence that BioELECTRA is superior —
  no paired BioELECTRA-versus-anchor test was specified.
- The **preplanned** contrast: `biomedbert-base` 0.8033 vs `bert-base` 0.7982.
  Paired document bootstrap gives delta (BERT − BiomedBERT) **−0.0051**, 95% CI
  **[−0.0354, +0.0275]**, `P(delta > 0) = 0.382`. The interval contains zero and
  is far wider than the difference: **indistinguishable**.
- Grouped means by domain, objective or architecture differ by a few
  thousandths — descriptive only, because each axis is confounded with model
  identity and run variance exceeds the gaps.
- `bio-clinicalbert` scores 108 effective test documents rather than 109 after
  tokenizer-dependent truncation, so the full ranking is not a common-document
  comparison. Only BiomedBERT vs BERT is scored as one.

## The negative result is the finding

At 860 training and 109 test documents, the base-encoder axis sits **below this
experiment's resolution**. That is evidence against spending the next block of
compute on a wider ranking at the same data size. The learning-curve design and
wave-3 review test whether *supervision*, not encoder identity, is the limiting
variable — and are therefore more informative.

This confirms the prediction in [[base-encoder-candidates|the encoder research]]
from the opposite direction: the literature's +0.005…+0.02 was always inside the
noise band [[tier-0-comparison-harness|Tier 0]] measured, and the grid now shows
it empirically rather than by argument.

## Phase 5 handoff

The sweep ran with `--no-save-model`, so it produced metrics and predictions but
**no deployable checkpoint**. If Phase 5 picks the descriptive leader, it must
save a fresh retrain and treat that artifact plus its own evaluation as
authoritative; a swept mean selects a *recipe* and cannot be assigned to a later
checkpoint. Retaining BiomedBERT is the alternative that keeps continuity without
claiming a significant improvement. That policy decision comes before
`models/encoders/` is populated — and it is forced by
[[training-is-not-reproducible-at-a-fixed-seed|fixed-seed nondeterminism]].
