---
type: meta
title: Decisions
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

# Decisions

Choices that are still in force, each with the evidence that produced it.

## Data

- [[use-pmid-based-dataset-splitting|Split datasets by PMID]]
- [[freeze-the-gold-split|Freeze the gold split on disk]]
- [[freeze-silver-samples-by-pmid-file|Freeze silver samples as PMID files]]

## Annotation

- [[no-vocab-lenient-prompt|Guided prompt: no vocabulary, lenient rule]]
- [[keep-qwen25-14b-as-annotator|Keep qwen2.5:14b as the annotator model]]
- [[review-phase-3-silver-only|Review Phase 3 silver only]]

## Training

- [[unfreeze-all-encoder-layers|Train all encoder layers]]

Related: [[lessons-index|Lessons]], [[experiments-index|Experiments]].
