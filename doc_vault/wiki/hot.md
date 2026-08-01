---
type: meta
title: Hot Cache
status: developing
created: 2026-08-01
updated: 2026-08-01
tags:
  - meta
  - hot-cache
---

# Recent Context

## Last Updated

2026-08-01 — initial ingest of the Pathway-NER documentation set (13 sources,
one batch).

## Key Recent Facts

- Vault covers repository `aenesbedir/Pathway-NER`, branch
  `annotator-model-registry`, commit `5e7e3f1145d7625855ce8c4fd120a0baba1184a3`.
- Best model is `gold-008` at test F1 0.8197; three seeds of the same recipe give
  0.8143 ± 0.0175, so that figure is a lucky draw from a wide band.
- The encoder grid ([[phase-4b-first-stage-grid|Phase 4b]]) is paused at 7 of 30
  cells.
- Training does not reproduce at a fixed seed — open, and it weakens every swept
  comparison.

## Recent Changes

- Created the vault foundation and captured 13 repository documents.
- Wrote the initial knowledge graph: project, four pipeline phases, 12 experiment
  notes, 4 evaluation notes, 7 concepts, 7 decisions, 6 lessons, 2 research
  syntheses.
- Added `documentation-migration-map.yaml` classifying all 25 Markdown files.

## Active Threads

- Wave-3 review is the dominant lever on model quality; a doccano round-trip
  script for the Phase-3 schema does not exist yet.
- Tier 1 encoder sweep needs 11 seeds per configuration, not 5.
- Ten of seventeen registry encoders have no cached weights; disk at 89%.
