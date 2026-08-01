---
type: meta
title: Current status
status: active
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - status
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: master
source_commit: 0ddf4f344f423b71999f2d3e0fd7ebd2325fb090
source_paths:
  - project_tracking.md
  - knowledge_base/model_experiments.md
last_reviewed: 2026-08-01
---

# Current status

State of `master` at commit `0ddf4f344f423b71999f2d3e0fd7ebd2325fb090`, which
merged `annotator-model-registry` and then recorded the completed encoder grid.
History lives in the phase notes; this page holds only what is true now.

## Best model

`gold-008` — test F1 **0.8197** on the frozen 109-document split, with a
three-seed mean of **0.8143 ± 0.0175** for the same recipe. The encoder grid's
descriptive leader, `bioelectra-base` at lr 3e-05, reaches **0.8156 ± 0.0175** —
the same band, not a better model.

## Last completed work

- **[[phase-4b-first-stage-grid|Phase 4b grid]] finished: 30/30 cells, 0
  failures**, run from a clean tree at `5e7e3f1`. Its outcome is a **null
  result** — the preplanned BiomedBERT-vs-BERT contrast gives delta −0.0051 with
  95% CI [−0.0354, +0.0275], i.e. indistinguishable.
- Annotator model registry (`llm/models.py`), per-model caches, automatic sample
  freezing.
- Annotator A/B: `qwen3.5:9b` did not replace `qwen2.5:14b`.
- Golden set v2, grown 5 → 10 abstracts.

## What the null result changes

The encoder axis is below this experiment's resolution at 860 training
documents, so a **wider encoder leaderboard is no longer the next move**.
Supervision, not encoder identity, is the variable worth testing.

## Active blockers

- **Phase 5 has no authoritative checkpoint.** The sweep ran with
  `--no-save-model`: metrics and predictions exist, a deployable model does not.
  A swept mean selects a recipe and cannot be attached to a later retrain, so
  Phase 5 must first decide what counts as authoritative.
- **Training is not reproducible at a fixed seed** — CUDA nondeterminism plus
  early stopping. Reported standard deviations combine seed and run-to-run
  variance. See [[training-is-not-reproducible-at-a-fixed-seed|the lesson]].

## Next verified steps

From the *Next* section of `project_tracking.md`:

1. Decide whether Phase 5 uses the descriptive leader (`bioelectra-base`,
   lr 3e-05) or keeps the BiomedBERT anchor for continuity — then record the
   saved retrain as a new measured artifact.
2. Prioritise wave-3 review or the 25/50/75/100% learning-curve design over a
   wider encoder leaderboard.
3. Keep the large-model / TRUBA tier **conditional** on evidence that the
   encoder axis separates. The completed grid does not provide that evidence.
4. GLiNER-biomed and task-adaptive pretraining remain higher-upside directions
   than another base-encoder ranking on the same 860 documents.

## Deferred, deliberately

- A round-trip script merging annotators' doccano exports into corrected silver.
- Canonicalizer coverage gaps (29% `unmapped` in the pilot) — analysis-only,
  since the canonical never becomes a training label.
- Policy for non-English abstract bodies in the review corpus.
