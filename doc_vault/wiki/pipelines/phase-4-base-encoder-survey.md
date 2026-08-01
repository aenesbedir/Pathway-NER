---
type: concept
title: Phase 4 — base-encoder survey
status: active
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - pipeline
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - project_tracking.md
  - reports/base_model_expansion_analysis_2026-07.md
  - knowledge_base/model_experiments.md
last_reviewed: 2026-08-01
---

# Phase 4 — base-encoder survey

Started 2026-07-29. Hyperparameter tuning had plateaued at `gold-008`
(F1 0.8197) while the teacher LLM sat at 0.864, so two levers remained: more
reviewed data, or a different base encoder. Phase 4 is the encoder axis. It is
independent of [[phase-3-silver-labeling|Phase 3]], which is the annotator axis.

## The honest expectation

`reports/base_model_expansion_analysis_2026-07.md` states the headline as
negative: the whole BLURB NER column spans **86.13 to 86.89** — 0.76 points,
measured on corpora with thousands of documents each. Realistic gain from an
encoder swap is **+0.005 … +0.02 F1** against a measured seed band of ±0.007
(later re-measured much wider — see below). Details in
[[base-encoder-candidates|Base-encoder candidates]].

## Tier 0 — the harness had to come first

Three defects would have made every cross-encoder number meaningless; they are
described in [[tier-0-comparison-harness|Tier 0]]. The one that matters most:
the split was **tokenizer-dependent**, so each encoder would have been scored on
a different test set with every log line still reading "Test: 109".

The gate was byte-identity: the regenerated dataset matches the one
`gold-001…008` used, and the `gold-008` recipe re-run under bf16 gives 0.8199
against the recorded 0.8197.

## The measurement that reframed the phase

Three seeds of the `gold-008` recipe: 0.7947 / 0.8199 / 0.8282 →
**0.8143 ± 0.0175**. The ±0.007 band every earlier conclusion leaned on was
measured at lr 3e-5; at 5e-5 it is 2.5× wider. Consequences: `gold-008`'s 0.8197
was a lucky seed, and resolving a 0.015 difference needs **11 seeds**, not 5.

## Where it stopped

[[phase-4b-first-stage-grid|Phase 4b]] paused on 2026-07-31 with 7 of 30 cells
recorded, and with an unresolved finding that outranks the grid itself:
[[training-is-not-reproducible-at-a-fixed-seed|training is not reproducible at a
fixed seed]].

Two annotation problems surfaced while building the harness and were handed to
the next review wave: **83 nested span pairs** and **12 boundary-error spans**,
both tokenizer-independent (`analysis/alignment_*.json`).
