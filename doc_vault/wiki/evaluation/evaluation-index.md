---
type: meta
title: Evaluation
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
  - reports/golden_set_gold-008_results.md
  - project_tracking.md
last_reviewed: 2026-08-01
---

# Evaluation

Three different yardsticks are in use, and confusing them produces wrong
conclusions.

| Instrument | What it answers | Size |
|---|---|---|
| held-out test split | span-exact F1 on unseen documents | 109 documents |
| [[golden-set\|golden set]] | did the model find the mention at all (overlap) | 10 abstracts, 70 targets |
| [[batch-05-review-benchmark\|batch-05 review]] | model-selection A/B for annotators | 200 abstracts, 483 spans |

- [[golden-set|Golden set]] — the variation-aware answer key.
- [[gold-008-vs-teacher-llm|gold-008 vs the teacher LLM]] — student and teacher
  on the same 10 abstracts.
- [[batch-05-review-benchmark|Batch-05 review benchmark]] — why the golden set
  stopped being the model-selection metric.
- [[annotation-strategy|Annotation strategy]] — the accept/reject rule the whole
  corpus is annotated under.

Related: [[gold-labels|Gold labels]], [[silver-labels|Silver labels]].
