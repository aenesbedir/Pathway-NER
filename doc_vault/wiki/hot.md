---
type: meta
title: Hot Cache
status: developing
created: 2026-08-01
updated: 2026-08-01
tags:
  - meta
  - hot-cache
---

# Recent Context

## Last Updated

2026-08-01 — re-ingested `project_tracking.md` and
`knowledge_base/model_experiments.md` after the encoder grid completed.

## Key Recent Facts

- Vault now tracks `master` @ `0ddf4f344f423b71999f2d3e0fd7ebd2325fb090`, which
  merged `annotator-model-registry` and recorded the completed grid.
- **[[phase-4b-first-stage-grid|Phase 4b]] finished: 30/30 cells, 0 failures.**
  The result is null — BiomedBERT vs BERT delta −0.0051, 95% CI
  [−0.0354, +0.0275]. The encoder axis is below this experiment's resolution.
- Descriptive leader `bioelectra-base` @ lr 3e-05 = 0.8156 ± 0.0175, inside the
  same band as `gold-008`'s 0.8143 ± 0.0175. Not a better model.
- The sweep used `--no-save-model`, so no deployable checkpoint exists.
- Training still does not reproduce at a fixed seed.

## Recent Changes

- Updated [[current-status|current status]],
  [[phase-4b-first-stage-grid|Phase 4b]],
  [[phase-4-base-encoder-survey|Phase 4]],
  [[base-encoder-candidates|encoder research]] and
  [[training-is-not-reproducible-at-a-fixed-seed|the reproducibility lesson]].
- Two source records superseded; the earlier captured copies are retained, and
  the replicate table dropped from the current `project_tracking.md` survives
  only there.

## Active Threads

- Phase 5 must define which artifact is authoritative before training
  `models/encoders/`: descriptive leader with a fresh saved retrain, or keep the
  BiomedBERT anchor for continuity.
- Wave-3 review and the 25/50/75/100% learning curve now outrank any wider
  encoder ranking.
- GLiNER-biomed and task-adaptive pretraining remain the higher-upside
  directions.
