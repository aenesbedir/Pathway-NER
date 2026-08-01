---
type: meta
title: Pipelines
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
  - project_tracking.md
last_reviewed: 2026-08-01
---

# Pipelines

Four phases. Each one changed where the labels come from, not what the model
predicts.

- [[phase-1-original-corpus|Phase 1 — original corpus]] — KEGG/Reactome
  reference articles, three span sources, 596 records.
- [[phase-2-pubmed-corpus|Phase 2 — PubMed corpus]] — pathway × disease
  co-occurrence search, 10,329 articles, exact matching only.
- [[phase-3-silver-labeling|Phase 3 — silver labeling]] — a guided LLM plus a
  deterministic booster, then human review; produced the gold dataset.
- [[phase-4-base-encoder-survey|Phase 4 — base-encoder survey]] — labels held
  fixed, the encoder is the variable.

Related: [[architecture|Pathway-NER architecture]],
[[current-status|Current status]].
