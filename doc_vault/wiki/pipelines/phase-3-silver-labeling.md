---
type: concept
title: Phase 3 — silver labeling
status: active
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
  - playground/silver_1k_analyses.md
last_reviewed: 2026-08-01
---

# Phase 3 — silver labeling

Phase 3 answers the surface-form problem that [[phase-2-pubmed-corpus|Phase 2]]
measured: an LLM reads a whole abstract, is told which pathways the article was
retrieved for, and returns **surface strings only**. Canonical mapping stays on
our side, never the model's — see [[canonical-mapping|Canonical mapping]].

The output is [[silver-labels|silver]]: machine labels that must pass human
review before being trusted.

## Design rules that were fixed up front

- Precision is measured on the [[golden-set|golden set]] *before* anything is
  scaled.
- Feasibility ladder: golden benchmark → 1k pilot → 10k full corpus.
- Silver and gold never mix (`data/silver/` vs `playground/golden_set/`).
- Every returned string is grounded to character offsets verbatim; anything that
  is not found in the source text is dropped as a hallucination.

## The two annotation sources

1. **Guided LLM extraction** — configuration chosen by measurement, see
   [[guided-prompt-config-selection|Guided prompt config selection]] and
   [[keep-qwen25-14b-as-annotator|the model decision]].
2. **A deterministic booster** (`llm/booster.py`) — strips process words from
   each Recon canonical to get content phrases, then scans for
   `<content> <process>` and `<process> of <content>`. Requiring an adjacent
   process word is what preserves precision: a bare metabolite never matches.
   On the golden set it lifted `span:variation` from 4/6 to **5/6 with zero new
   false positives**, and it contributes ~9% of the pilot's spans.

The booster scans **all 90 Recon names, not just the article's query pathways**,
because a measured case (PMID 11469814, `metabolism of androgens`) proved query
pathways are an incomplete hint.

## The 1k pilot

1,000 abstracts, `qwen2.5:14b`, 39 minutes (2.4 s/abstract), **1,996 spans**.
The pilot's ten golden PMIDs were excluded so that silver never trains on the
evaluation set.

The payoff is in the composition: `variation` + `synonym` = **425 spans (21%)**
are mentions exact matching would miss outright. The descriptive analysis
(`playground/silver_1k_analyses.md`, which states plainly it is *not* an
evaluation) counts **532 unique surface forms against exact matching's 81 on the
same 1,000 abstracts — 6.6×**, with 457 of them new.

29% of spans are `unmapped` — mostly real pathway mentions with no Recon name,
which is harmless because the canonical never becomes a training label.

## Review and what it produced

Spans are exported to doccano and split into per-annotator batches; the
accept/reject policy is [[annotation-strategy|the annotation strategy]].
Reviewed output becomes [[gold-labels|gold]], which is what every `gold-00N` run
trains on.

Two bugs found in this phase are recorded as lessons:
[[small-golden-sets-certify-what-they-contain|the direction bug]] and
[[silent-llm-failures-cached-forever|silently cached LLM failures]].
Reproducibility is handled by
[[freeze-silver-samples-by-pmid-file|freezing the sample as a PMID file]].

Operational detail — import steps, the JSONL format, batch splitting — stays in
`doccano/README.md` and `data/silver/README.md`.
