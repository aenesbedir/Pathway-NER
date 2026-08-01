---
type: comparison
title: gold-005…008 — seed variance and learning rate
status: active
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
  - knowledge_base/model_experiments.md
last_reviewed: 2026-08-01
---

# gold-005…008 — seed variance and learning rate

2026-07-27. Every gold run so far was a single run at `seed=42` on a
109-document test split. Before trusting [[gold-004-unfreeze-all-layers|gold-004]]
or tuning further, two things had to be measured: the seed noise band, and
whether the hardcoded 3e-5 was still right now that all layers train.

## Seed variance at lr 3e-5

gold-004 (seed 42) 0.8154 · gold-005 (seed 1) 0.8008 · gold-006 (seed 7) 0.8135
→ **0.810 ± 0.007**. Precision is noisier (±0.019), so single-seed precision
comparisons under ~0.04 are meaningless.

## Learning-rate sweep at seed 42

gold-007 (2e-5) 0.7865 · gold-004 (3e-5) 0.8154 · **gold-008 (5e-5) 0.8197**.

2e-5 is clearly worse, outside the band — the hypothesis that full fine-tuning
would want a *lower* learning rate was wrong. 5e-5 beats 3e-5 by +0.004, which is
**inside** the band and therefore not a real difference.

## The conclusion that was later revised

The recorded conclusion was "current best gold-008, statistically tied with
gold-004". [[tier-0-comparison-harness|Tier 0]] then re-measured the band **at
lr 5e-5** and found ±0.0175 — 2.5× wider — with a three-seed mean of 0.8143. So
gold-008's 0.8197 is a lucky draw from a wider distribution, and the +0.004 claim
compared two single seeds from bands of different widths.

Both readings are kept here: the original is what the run log says, the revision
is what the harness measured. The practical rule that survives is the stricter
one — any comparison below ~0.015 F1 needs multi-seed averaging, and at 5e-5 that
means 11 seeds.
