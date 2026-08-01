---
type: comparison
title: Guided prompt config selection
status: active
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - experiment
  - annotation
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - project_tracking.md
last_reviewed: 2026-08-01
---

# Guided prompt config selection

How the [[phase-3-silver-labeling|Phase 3]] extraction configuration was chosen —
a 2×2 grid on the [[golden-set|golden set]], vocabulary hint × rule strictness,
run with `qwen2.5:7b`.

| Variant | Precision | span:exact | span:variation | Verdict |
|---|---|---|---|---|
| no-vocab, strict | 0.82 / 0.90 | 11/11 | 2/6 (33%) | superseded |
| **no-vocab, lenient** | 0.82 / 0.90 | 11/11 | **4/6 (67%)** | **chosen** |
| with-vocab, strict | 1.00 | 11/11 | 0/6 | too conservative |
| with-vocab, lenient | 1.00 | 11/11 | 1/6 | too conservative |

## Two findings

**The 98-name vocabulary is the dominant recall killer.** Supplying it buys
precision 1.00 at the cost of near-zero variation recall — the same
over-conservatism the Phase-1 few-shot prompt showed on a 7B model. Query-pathway
hints alone give the best balance.

**The strict rule was suppressing the wrong thing.** "Do not return metabolite or
compound names" was killing pathway phrases *built from* a compound name. The
lenient rule still excludes a bare metabolite but explicitly keeps
`<compound> metabolism / biosynthesis / synthesis of <compound>`. Effect:
variation recall 33% → 67%, **no precision change, zero new false positives**.

Adding the word "synonyms" to the task line recovered the synonym case and lifted
span-level catch 15 → 17/19 with precision flat.

## A caveat recorded at the same time

Ollama is **not** deterministic run to run even at `temperature=0, seed=42`
(GPU batching). The same configuration varies by ±1–2 mentions, so single-mention
category deltas are run noise. Large-margin conclusions (no-vocab ≫ with-vocab,
lenient > strict) hold; the 5-abstract set cannot arbitrate the rest. This is why
reproducibility is handled by
[[freeze-silver-samples-by-pmid-file|frozen artefacts]], not by seeds.

A 7B vs 14B comparison followed and is recorded in
[[keep-qwen25-14b-as-annotator|the annotator decision]]: the bigger model did
**not** close the variation gap (4/6 either way), but it was cleaner and far more
stable.
