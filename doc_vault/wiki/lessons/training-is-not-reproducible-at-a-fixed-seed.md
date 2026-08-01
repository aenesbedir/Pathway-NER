---
type: concept
title: Training is not reproducible at a fixed seed
status: contested
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - lesson
  - open
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - project_tracking.md
  - CLAUDE.md
last_reviewed: 2026-08-01
---

# Training is not reproducible at a fixed seed

**Unresolved.** Re-running the oldest grid cell (`biomedbert-base`, lr 5e-05,
seed 42) twice did not reproduce its recorded 0.8199:

| run | test F1 | best epoch | epochs run |
|---|---|---|---|
| 29 Jul (recorded) | 0.8199 | — | — |
| replicate 1 | 0.7662 | 7 | 15 |
| replicate 2 | 0.7736 | 16 | 24 |

The replicates differ from each other as well as from the original, so the
pipeline is nondeterministic at a fixed seed. Every configuration field in
`test_results.json` was compared and is identical; the dataset has not changed
since 29 July.

**Mechanism.** `set_seed` is called but `torch.use_deterministic_algorithms` is
not, so cuDNN kernel selection and atomic accumulation order vary between runs.
Early stopping then turns those small numeric differences into a *discrete*
decision — which epoch is best — and the trajectories diverge from there.

## Why it matters beyond one cell

- The σ = 0.0175 recorded as **seed** variance is really seed plus run-to-run
  noise, so [[phase-4b-first-stage-grid|the grid]] resolves less than planned.
- The assumption that retraining a best configuration reproduces its swept number
  is **false**. Phase 5 needs a different rule for which checkpoint is
  authoritative.

## What is genuinely unknown

Both replicates fall below all three recorded lr 5e-05 runs. Two samples cannot
separate an unlucky draw from a systematic shift. Arguing *against* a shift: the
three lr 3e-05 cells ran on 31 July under the current code and are not depressed,
and the only intervening `train.py` edit is a no-op for this uncased model. The
question is open; the replicates live in `runs/_recheck/` and are excluded from
`summary.jsonl`.

## What it forces on Phase 5

The completed [[phase-4b-first-stage-grid|grid]] ran with `--no-save-model`, so
it holds metrics and predictions but no deployable checkpoint. Combined with this
finding, that produces a standing rule: **a swept mean selects a recipe and can
never be assigned to a later retrain**. If Phase 5 adopts the descriptive leader,
the saved retrain and its own evaluation become the authoritative artifact.

## Provenance note

The replicate table above was recorded in `project_tracking.md` at commit
`5e7e3f1`. The current `master` text condenses that section into
*"Reproducibility and the Phase 5 checkpoint decision"* and no longer prints the
individual replicate numbers. They survive in this vault's captured copy of the
earlier file — which is what content-addressed capture is for.

## The rule it produced

This incident is the reason `CLAUDE.md` requires a clean working tree before any
run whose numbers will be kept: diagnosing it meant comparing file mtimes,
because the changes between the two dates had never been committed. A clean tree
would have answered it with one `git diff`.
