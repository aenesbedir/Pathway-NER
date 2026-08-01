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
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - project_tracking.md
  - knowledge_base/model_experiments.md
last_reviewed: 2026-08-01
---

# Current status

State of branch `annotator-model-registry` at commit
`5e7e3f1145d7625855ce8c4fd120a0baba1184a3`. History lives in the phase notes;
this page holds only what is true now.

## Best model

`gold-008` — test F1 **0.8197** on the frozen 109-document split. The Tier 0
re-run of the same recipe under bf16 gives **0.8199**, and three seeds of it give
**0.8143 ± 0.0175**, so the recorded 0.8197 is a lucky draw from that band rather
than a separate result.

## Last completed work

- **Phase 4b first-stage grid, paused 2026-07-31.** 7 of 30 cells recorded in
  `runs/summary.jsonl`. See [[phase-4b-first-stage-grid|Phase 4b grid]].
- **Annotator model registry** (`llm/models.py`) with per-model caches and
  automatic sample freezing.
- **Annotator A/B**: `qwen3.5:9b` was measured against `qwen2.5:14b` and did not
  replace it — see [[annotator-ab-qwen35-vs-qwen25|the A/B]] and
  [[keep-qwen25-14b-as-annotator|the decision]].
- **Golden set v2**, grown 5 → 10 abstracts.

## Active blockers

- **Training is not reproducible at a fixed seed.** Re-running the oldest grid
  cell twice gave 0.7662 and 0.7736 against a recorded 0.8199. This is unresolved
  and it weakens every swept comparison — see
  [[training-is-not-reproducible-at-a-fixed-seed|the lesson]].
- **Statistical power.** At σ = 0.0175 an 11-seed sweep is needed to resolve
  0.015 F1, which is the size of the gain an encoder swap is predicted to give.
- **Ten of seventeen registry encoders have no weights cached**, and disk is at
  89% with 15 GB free. Check before launching a sweep that includes them.

## Next verified steps

Taken from the *Next* section of `project_tracking.md`:

1. **Tier 1** locally (~7.3 GPU-hours): `bioelectra-base`, `biolinkbert-base`,
   `bio-modernbert-base`, `modernbert-bio-base` against the baseline at 11 seeds.
2. **Tier 2** on TRUBA: the 340–396M candidates, only if Tier 1 separates.
3. **Tier 3**: fine-tune GLiNER-biomed on the same 860 documents; task-adaptive
   pretraining on the unlabelled corpus.
4. **Wave-3 review** remains the dominant lever; an encoder swap is a complement
   to more data, not a substitute.

## Deferred, deliberately

- A round-trip script that merges annotators' doccano exports back into a
  corrected silver set.
- Canonicalizer coverage gaps (29% `unmapped` in the pilot): the canonical never
  becomes a training label, so this is analysis-only.
- Policy for non-English abstract bodies in the review corpus (two documents
  observed).
