---
type: concept
title: Cache keys must cover the request
status: evergreen
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - lesson
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - project_tracking.md
last_reviewed: 2026-08-01
---

# Cache keys must cover the request

**The defect.** The silver cache was keyed on **PMID alone**. Swapping the
annotator model would have replayed the previous model's cached answers for every
abstract already seen — a run that looks successful, changes nothing, and cannot
re-label the pilot. The whole point of a model swap would have been silently
cancelled.

**Fix.** The cache path became
`data/raw/llm_cache_silver/<model slug>/<pmid>.json`, and the existing 1,000
files were moved under `qwen2.5_14b/`. Verified: re-running batch 05 reproduces
378 spans from cache with 0 LLM calls.

This was groundwork done *before* any swap, so that
[[annotator-ab-qwen35-vs-qwen25|the A/B]] measured a real difference rather than
an artefact.

## The part still open

The slug derives from the **model tag only**. It does not notice a changed
request shape, and it does not notice a changed **prompt**. Editing
`llm/prompts/pathway_extraction_guided.py` today would silently replay the old
prompt's answers for every cached abstract. Until that changes, altering a
model's request shape or the prompt means deleting that model's cache directory
by hand — recorded as a known sharp edge, deliberately not fixed.

## What generalises

A cache key must cover **everything that can change the answer**, not just the
obvious input. Anything omitted from the key is an assumption that it will never
vary — and prompts vary constantly.

Related: [[keep-qwen25-14b-as-annotator|the annotator decision]],
[[silent-llm-failures-cached-forever|silently cached failures]].
