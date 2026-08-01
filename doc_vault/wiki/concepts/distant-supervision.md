---
type: concept
title: Distant supervision
status: evergreen
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - annotation
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - playground/exact_match_analysis.md
  - playground/golden_set/README.md
last_reviewed: 2026-08-01
---

# Distant supervision

Labelling text automatically by matching a known vocabulary against it, instead
of paying a human to read it. Here the vocabulary is 98 Recon3D pathway names
plus a small synonym list, matched with a SpaCy `PhraseMatcher`.

It is cheap and it is why the project has data at all. It also has one specific,
measured failure.

## The near-lookup problem

Over the whole Phase-2 corpus, 73,096 spans reduce to **256 raw / 105
case-folded unique surface forms** (`playground/exact_match_analysis.md`). A
model trained on that learns to reproduce a lookup table: it tags what it has
literally seen and labels every paraphrase `O`.

Hand annotation quantified the gap. On the ten golden abstracts, **49% of
Recon-resolvable pathway mentions are variations exact matching misses** (v1
alone: 63%). The kinds of miss are systematic, not random:

| Kind | Example |
|---|---|
| word order | `metabolism of androgens` |
| chemical synonym | `cholecalciferol metabolism` = vitamin D |
| separator / order | `cysteine/methionine metabolism` |
| shared head | `histidine and glutathione metabolism` |
| abbreviation | `BCAA metabolism`, `AAA metabolism` |
| umbrella → children | `purine metabolism` → synthesis + catabolism |

## What was done about it

Two answers, in order:

1. **A deterministic booster** for the two purely structural classes
   (`<content> <process>` and `<process> of <content>`) — cheap, precise, and
   model-free.
2. **[[phase-3-silver-labeling|LLM silver labeling]]**, which raised unique
   surface forms on the same 1,000 abstracts from 81 to **532**.

Neither removes the vocabulary problem itself; they widen what counts as a
match. Naming the pathway remains a separate, deferred concern —
[[canonical-mapping|Canonical mapping]].
