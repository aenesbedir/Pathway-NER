---
type: concept
title: Phase 1 — original corpus
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
  - analysis/data_summary.md
  - analysis/pubmed_year_distribution.md
last_reviewed: 2026-08-01
---

# Phase 1 — original corpus

The first corpus was built from the articles that **KEGG and Reactome
themselves cite**: 86 KEGG metabolism pathways (524 PMIDs) and 335 Reactome
descendants of the Metabolism root (933 PMIDs), deduplicated to 1,192 unique
PMIDs and fetched from PubMed/PMC.

## Why it produced so few labels

The decisive measurement is in Step 2: SpaCy `PhraseMatcher` over abstract and
full text matched **86 of 1,366 pathway–article pairs (6.3%)**. The reason is
structural and was recorded at the time — *KEGG/Reactome links are gene- and
enzyme-based, not pathway-name based*, so a reference article often never spells
out the pathway it is filed under.

Two more span sources were added to compensate:

- `qwen2.5:7b` via Ollama over the 1,280 unmatched pairs — 178 accepted, **144
  hallucinations dropped** by verbatim re-verification against the source text.
- A pre-built disease-pathway database converted to character offsets — 296
  records.

Total: **560 records with spans, 704 spans, 318 unique span texts.**

## An LLM-prompting result that outlived the phase

Three prompt versions were benchmarked on 450 known pathway↔disease abstracts:
zero-shot with rules **296/450 (65.8%)**, plus a word-order rule 294/450, and
five-shot with an entity definition **198/450 (44.0%)**. The few-shot collapse on
a 7B model is the same failure mode that later killed the vocabulary-guided
prompt in [[guided-prompt-config-selection|Phase 3 config selection]].

## Outcome

Four training runs — [[run-001-baseline|001]], [[run-002-class-weights|002]],
[[run-003-freeze-6-layers|003]], [[run-004-freeze-9-layers|004]] — landed
between F1 0.37 and 0.46 with precision never above 0.40.
[[error-analysis-run-001|Error analysis]] showed the false positives were largely
*real* pathway names the annotation had missed, which redirected the project from
hyperparameters to data. That redirection is what [[phase-2-pubmed-corpus|Phase
2]] is.

Corpus statistics stay canonical in `analysis/data_summary.md` and
`analysis/pubmed_year_distribution.md`.
