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
