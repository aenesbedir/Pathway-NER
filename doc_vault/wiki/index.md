---
type: meta
title: Wiki Index
status: evergreen
created: 2026-08-01
updated: 2026-08-01
tags:
  - meta
  - index
---

# Wiki Index

This catalog is updated by completed knowledge operations.

## Projects

- [[pathway-ner|Pathway-NER]] — metabolic pathway NER over biomedical literature
  - [[architecture|Pathway-NER architecture]]
  - [[current-status|Current status]]

## Pipelines

- [[pipelines-index|Pipelines]]
  - [[phase-1-original-corpus|Phase 1 — original corpus]]
  - [[phase-2-pubmed-corpus|Phase 2 — PubMed corpus]]
  - [[phase-3-silver-labeling|Phase 3 — silver labeling]]
  - [[phase-4-base-encoder-survey|Phase 4 — base-encoder survey]]

## Concepts

- [[concepts-index|Concepts]]
  - [[span|Span]] · [[tokenization|Tokenization]] · [[bio-labeling|BIO labeling]]
  - [[distant-supervision|Distant supervision]] ·
    [[canonical-mapping|Canonical mapping]]
  - [[silver-labels|Silver labels]] · [[gold-labels|Gold labels]]

## Experiments

- [[experiments-index|Experiments]]
  - Phase 1: [[run-001-baseline|Run 001]] · [[run-002-class-weights|Run 002]] ·
    [[run-003-freeze-6-layers|Run 003]] · [[run-004-freeze-9-layers|Run 004]] ·
    [[error-analysis-run-001|error analysis]]
  - Phase 2: [[run-005-phase-2-data|Run 005]]
  - Gold: [[gold-001-first-reviewed-labels|gold-001]] ·
    [[gold-002-precision-weights|gold-002]] ·
    [[gold-003-more-epochs|gold-003]] ·
    [[gold-004-unfreeze-all-layers|gold-004]] ·
    [[gold-005-008-seed-and-lr-sweep|gold-005…008]]
  - Encoders: [[tier-0-comparison-harness|Tier 0]] ·
    [[phase-4b-first-stage-grid|Phase 4b grid]]
  - Annotator: [[guided-prompt-config-selection|prompt config]] ·
    [[annotator-ab-qwen35-vs-qwen25|qwen3.5 A/B]]

## Evaluation

- [[evaluation-index|Evaluation]]
  - [[golden-set|Golden set]] ·
    [[batch-05-review-benchmark|batch-05 benchmark]] ·
    [[gold-008-vs-teacher-llm|student vs teacher]] ·
    [[annotation-strategy|annotation strategy]]

## Decisions

- [[decisions-index|Decisions]]
  - [[use-pmid-based-dataset-splitting|split by PMID]] ·
    [[freeze-the-gold-split|freeze the gold split]] ·
    [[freeze-silver-samples-by-pmid-file|freeze silver samples]]
  - [[no-vocab-lenient-prompt|no-vocab lenient prompt]] ·
    [[keep-qwen25-14b-as-annotator|keep qwen2.5:14b]] ·
    [[review-phase-3-silver-only|review Phase 3 only]]
  - [[unfreeze-all-encoder-layers|train all layers]]

## Lessons

- [[lessons-index|Lessons]]
  - [[data-leakage-from-split-strategy|split leakage]] ·
    [[small-golden-sets-certify-what-they-contain|small gold sets]] ·
    [[silent-llm-failures-cached-forever|silent LLM failures]]
  - [[cache-keys-must-cover-the-request|cache keys]] ·
    [[misconfigured-tokenizers-look-like-weak-encoders|misconfigured tokenizers]] ·
    [[training-is-not-reproducible-at-a-fixed-seed|nondeterministic training]]

## Research

- [[research-index|Research]]
  - [[base-encoder-candidates|Base-encoder candidates]] ·
    [[annotator-llm-and-hardware|Annotator LLM and hardware]]

## Sources

- [[sources-index|Sources]] — what was captured, from which commit, and what was
  deliberately left in the repository.
