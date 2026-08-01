---
type: concept
title: Batch-05 review benchmark
status: active
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - evaluation
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - project_tracking.md
last_reviewed: 2026-08-01
---

# Batch-05 review benchmark

200 fully reviewed abstracts (483 gold spans) that replaced the
[[golden-set|golden set]] as the metric for choosing an annotator model. The
reason is stated plainly in the model report: 10 abstracts / 76 mentions cannot
arbitrate a model choice when the deciding metric rests on 6 cases.

## Provenance — two halves, deliberately labelled

- **Docs 1–50**: a human annotator's doccano export, with 16 assistant-applied
  corrections; its final labels are the gold standard there.
- **Docs 51–200**: the assistant's own review against the annotation guide.

Every span is classified TP / FP / FN, boundary errors are recorded as an FP plus
a corrected FN so span-exact metrics stay honest, and all offsets are
machine-verified.

## The numbers

All 200 documents: 378 machine spans → 337 TP, 41 FP, 146 FN →
**P 0.892 / R 0.698 / F1 0.783**. By half: human 0.854 / 0.800 / 0.826;
assistant 0.906 / 0.668 / 0.769.

The recall difference between halves is a **sweep-depth** difference, not a model
difference — the assistant half counted umbrella terms and repeat mentions the
human half largely left alone. Absolute recall is therefore pessimistic by
construction, but equally so for every model, which is what an A/B needs.

## What the errors are

- **False positives**: bare metabolites, disease names, signalling pathways, the
  guide's own named rejects, and boundary slips.
- **False negatives**: umbrella terms dominate, then a spelled-out first mention
  when the later abbreviation was caught, then whole zero-span documents that do
  contain a mention.

## Conventions applied but not written into the guide

Four coordination and boundary rules were recorded in the review JSON only —
deliberately not added to `doccano/ANNOTATION_GUIDE.md`, on the reasoning that
they are edge cases annotators can derive from the existing rules. See
[[annotation-strategy|Annotation strategy]].

A cross-check against an independent Gemini pass corroborated 16 of 26 false
positives verbatim and produced 6 genuine conflicts, all resolvable from the
guide's own text.

The harness that scores any silver run against this reference is
`analysis/score_against_review.py`; its first use is
[[annotator-ab-qwen35-vs-qwen25|the qwen3.5 A/B]].
