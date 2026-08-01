---
type: meta
title: Wiki Log
status: evergreen
created: 2026-08-01
updated: 2026-08-01
tags:
  - meta
  - log
---

# Wiki Log

Newest completed operations appear first.

## 2026-08-01 — `ingest-encoder-grid-20260801` (ingest)

Re-ingest after `master` advanced to
`0ddf4f344f423b71999f2d3e0fd7ebd2325fb090` (merge of
`annotator-model-registry`, then `docs: record completed encoder grid`).

- **Sources**: new revisions of `project_tracking.md` and
  `knowledge_base/model_experiments.md`, captured create-only by operation
  `capture-encoder-grid`. The earlier revisions are retained and their ledger
  records marked `superseded`.
- **Pages updated**: [[phase-4b-first-stage-grid|Phase 4b]] (paused at 7 cells →
  completed 30/30 with a null result), [[current-status|current status]],
  [[phase-4-base-encoder-survey|Phase 4]],
  [[base-encoder-candidates|encoder research]],
  [[training-is-not-reproducible-at-a-fixed-seed|reproducibility lesson]],
  overview and hot cache.
- **Outcome**: the grid's conclusion is negative — the preplanned contrast gives
  delta −0.0051, 95% CI [−0.0354, +0.0275]. Recorded as a result, not a failure.
  The replicate table that the new `project_tracking.md` no longer prints
  survives in this vault's captured copy of the earlier revision.

## 2026-08-01 — `ingest-pathway-ner-docs-20260801` (ingest)

Initial documentation migration for `aenesbedir/Pathway-NER`
@ `5e7e3f1145d7625855ce8c4fd120a0baba1184a3` (branch
`annotator-model-registry`).

- **Sources**: 13 repository Markdown documents, captured create-only under
  `.raw/captured/` by operation `capture-reviewed` and recorded in the source
  ledger. Listed in [[sources-index|Sources]].
- **Principal pages**: [[pathway-ner|Pathway-NER]],
  [[architecture|architecture]], [[current-status|current status]], four pipeline
  phase notes, 12 experiment notes, 4 evaluation notes, 7 concept notes, 7
  decision notes, 6 lesson notes, 2 research notes, plus domain indexes.
- **Outcome**: every note is grounded in a captured source; contradictions
  between sources (student-vs-teacher scoring, the two encoder surveys, the
  revised seed band) are preserved side by side rather than resolved. No
  repository file was modified, moved or deleted.

## 2026-08-01 — `capture-reviewed` (capture)

13 create-only content-addressed payloads under `.raw/captured/`, 256 KB total,
all UTF-8 Markdown. No datasets, model files, caches or binaries were captured.

## 2026-08-01 — `init-reviewed` (setup)

Vault created at `doc_vault/` from the v2.1.0 template: workspace config,
privacy-safe `.gitignore`, `inbox/`, `.raw/`, `wiki/` core pages, ledgers and
minimal Obsidian defaults.
