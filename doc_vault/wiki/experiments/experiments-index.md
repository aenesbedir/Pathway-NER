---
type: meta
title: Experiments
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
  - knowledge_base/model_experiments.md
last_reviewed: 2026-08-01
---

# Experiments

Every recorded training run, in order. Numbers quoted in these notes are the ones
`knowledge_base/model_experiments.md` reports; per repository policy no vault
note maintains a results table — `runs/summary.jsonl` and each run's
`test_results.json` are the source of truth.

## Phase 1 — noisy distant supervision

- [[run-001-baseline|Run 001 — baseline]] · F1 0.4604
- [[run-002-class-weights|Run 002 — reduced class weights]] · F1 0.4500
- [[run-003-freeze-6-layers|Run 003 — freeze 6 layers]] · F1 0.4177
- [[run-004-freeze-9-layers|Run 004 — freeze 9 layers]] · F1 0.3656
- [[error-analysis-run-001|Error analysis of Run 001]]

## Phase 2 — exact-matched corpus

- [[run-005-phase-2-data|Run 005 — Phase 2 data]] · F1 0.9812, and why that
  number does not mean what it looks like

## Gold runs — reviewed labels

- [[gold-001-first-reviewed-labels|gold-001]] · F1 0.6734
- [[gold-002-precision-weights|gold-002]] · F1 0.7227
- [[gold-003-more-epochs|gold-003]] · F1 0.7437
- [[gold-004-unfreeze-all-layers|gold-004]] · F1 0.8154 — the biggest single lever
- [[gold-005-008-seed-and-lr-sweep|gold-005…008]] · seed band and learning rate

## Infrastructure and encoder work

- [[tier-0-comparison-harness|Tier 0 — comparison harness]]
- [[phase-4b-first-stage-grid|Phase 4b — first-stage grid]]

## Annotator-side experiments

- [[guided-prompt-config-selection|Guided prompt config selection]]
- [[annotator-ab-qwen35-vs-qwen25|qwen3.5:9b vs qwen2.5:14b]]
