---
type: concept
title: Keep qwen2.5:14b as the annotator model
status: active
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
  - project_tracking.md
last_reviewed: 2026-08-01
---

# Keep qwen2.5:14b as the annotator model

**Decision.** `qwen2.5:14b` (Qwen2.5-14B-Instruct, Q4_K_M via Ollama) stays the
annotation model of record for the wave-2 1k. It is recorded in every silver
record's `model` field.

**Against 7b.** The bigger model does **not** close the variation gap — 4/6 both
ways. What it buys is cleanliness: precision 0.95 vs ~0.90, unadjudicated spans
9 → 3, and run-to-run output that is stable rather than noisy. Less noise for the
human reviewer is the whole argument.

**Against qwen3.5:9b.** Measured on 200 reviewed abstracts, not assumed:
F1 0.783 vs 0.715 span-exact, 0.831 vs 0.815 lenient. Recall is a wash; qwen3.5
simply emits more wrong spans, and its characteristic errors are the annotation
guide's named rejects. Since the annotator workflow is accept/reject, extra false
positives are pure reviewer burden. Qwen3.5's real edge is speed —
~0.4 h per 1k against ~2 h. See [[annotator-ab-qwen35-vs-qwen25|the A/B]].

**Known sharp edge, deliberately unfixed.** The cache slug derives from the model
tag only, so it does not notice a changed request shape *or a changed prompt*.
Editing the prompt today would silently replay the old prompt's cached answers.
Until that changes, altering a model's request shape or the prompt means deleting
that model's cache directory by hand — see
[[cache-keys-must-cover-the-request|the lesson]].

**Open.** `reports/llm_selection_and_hardware_2026-07.md` argues qwen2.5 is two
generations old and that the highest-ROI alternative is not an LLM at all;
[[annotator-llm-and-hardware|the research note]] holds that thread.
