---
type: entity
title: Pathway-NER
status: active
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - project
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - project_tracking.md
  - annotation_handoff.md
last_reviewed: 2026-08-01
---

# Pathway-NER

A named-entity-recognition project that extracts **metabolic pathway** mentions
from biomedical literature. The tagger is binary: a token is either part of a
pathway mention or it is not; pathway *names* are never predicted by the model.

The base encoder is
`microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext`, fine-tuned for
token classification.

## Where it sits in a larger plan

`project_tracking.md` states the wider intent: combine this pathway tagger with
an off-the-shelf disease NER model, then run relation extraction to find
pathway↔disease associations evidenced by literature, ending in a database that
links metabolic pathways to diseases with source PMIDs. **Only the pathway-NER
step is in scope today.**

## How to read this vault

- [[architecture|Architecture]] — the data path from pathway databases to a
  trained tagger.
- [[current-status|Current status]] — what is true on the current branch.
- [[pipelines-index|Pipelines]] — the four phases and what each changed.
- [[experiments-index|Experiments]] — every recorded training run.
- [[evaluation-index|Evaluation]] — how quality is measured, and by what.
- [[decisions-index|Decisions]] — the choices that are still in force.
- [[lessons-index|Lessons]] — the failures worth not repeating.
- [[research-index|Research]] — surveys that have not become code.
- [[concepts-index|Concepts]] — the vocabulary the rest of the notes assume.

## Canonical sources that stay in the repository

Operational documentation is not duplicated here. Setup and run commands,
input/output formats, doccano import steps, dataset README files and generated
statistics remain canonical in the repository and are referenced by locator:
`pubmed_api/PIPELINE.md`, `pubmed_api/STATS.md`, `doccano/README.md`,
`doccano/ANNOTATION_GUIDE.md`, `doccano/ANNOTATOR_STEPS.md`,
`data/silver/README.md`, `data/processed/gold/README.md`.
