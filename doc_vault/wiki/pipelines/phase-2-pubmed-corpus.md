---
type: concept
title: Phase 2 — PubMed corpus
status: archived
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - pipeline
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - project_tracking.md
  - playground/exact_match_analysis.md
  - analysis/data_summary.md
last_reviewed: 2026-08-01
---

# Phase 2 — PubMed corpus

Phase 1 failed on data, not on model capacity, so Phase 2 replaced the corpus
rather than the architecture. Instead of asking a pathway database which articles
to read, it asks PubMed which articles mention a pathway **and** a disease
together.

## The retrieval idea

834 MeSH disease descriptors were fetched from three subtrees (C18 metabolic,
C04 neoplasms, C10.574 neurodegenerative) and curated down to **98 diseases**.
Each was crossed with 98 Recon3D pathways:

```
("pathway name"[Title/Abstract]) AND ("disease name"[Title/Abstract])
```

9,604 searched pairs → 1,959 with a hit (20.4%) → **10,329 unique PMIDs**, of
which 5,837 have PMC full text.

## Why exact matching now works

The corpus was *selected* by co-occurrence, so the pathway name is usually
present verbatim. The Phase-1 hit rate of 6.3% became **93.4%** at the article
level, and matching produced **22,017 records / 73,096 spans**
(`playground/exact_match_analysis.md`, which also samples ~95/100 matches as
correct).

## The measurement that ends the phase

The same analysis counts **256 raw / 105 case-folded unique surface forms** for
those 73,096 spans. A model trained on that learns a near-lookup: it tags the
strings it literally saw. That number is the reason
[[phase-3-silver-labeling|Phase 3]] exists — see
[[distant-supervision|Distant supervision]].

## What went wrong first

[[run-005-phase-2-data|Run 005]] initially reported val F1 0.98 with a
pathway-based split. That was [[data-leakage-from-split-strategy|leakage]]:
several records share one PMID, so windows of the same article landed on both
sides of the split. The fix became a standing rule —
[[use-pmid-based-dataset-splitting|split by PMID]].

## Canonical operational sources

Run order, commands and per-step counts stay in `pubmed_api/PIPELINE.md` and
`pubmed_api/STATS.md`; corpus shape in `analysis/data_summary.md`.
