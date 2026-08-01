---
type: meta
title: Lessons
status: evergreen
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - index
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - lessons_learned/challenges.md
  - project_tracking.md
last_reviewed: 2026-08-01
---

# Lessons

Failures that were diagnosed, with the generalisation each one supports.

- [[data-leakage-from-split-strategy|Data leakage from the split strategy]] —
  a metric too good to be true, and why.
- [[small-golden-sets-certify-what-they-contain|Small golden sets certify what
  they contain]] — a gold set that approved a canonicalizer inverting meaning.
- [[silent-llm-failures-cached-forever|Silent LLM failures could be cached
  forever]] — an exception handler that made loss indistinguishable from absence.
- [[cache-keys-must-cover-the-request|Cache keys must cover the request]] —
  a cache keyed on too little.
- [[misconfigured-tokenizers-look-like-weak-encoders|Misconfigured tokenizers look
  like weak encoders]] — a defect the obvious checks could not see.
- [[training-is-not-reproducible-at-a-fixed-seed|Training is not reproducible at a
  fixed seed]] — still open.

A recurring shape: **the check that would have caught it was structurally blind**,
not merely missing. Related: [[decisions-index|Decisions]].
