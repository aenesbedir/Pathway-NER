---
type: concept
title: Pathway-NER architecture
status: developing
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - architecture
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - project_tracking.md
  - data/processed/gold/README.md
last_reviewed: 2026-08-01
---

# Pathway-NER architecture

The project has never had a single pipeline; it has had **four generations of the
same shape**. The shape is stable, the annotation source is what changes.

## The invariant shape

1. **Get a pathway vocabulary.** KEGG, Reactome and Recon3D supply canonical
   pathway names plus synonyms.
2. **Get text.** PubMed abstracts and PMC full text, fetched by PMID and cached
   to disk.
3. **Produce character spans.** This is the axis that changes per phase — see
   [[distant-supervision|Distant supervision]] and
   [[silver-labels|Silver labels]].
4. **Align spans to tokens.** A HuggingFace fast tokenizer maps character
   offsets to token positions; see [[tokenization|Tokenization]] and
   [[bio-labeling|BIO labeling]].
5. **Split, then train.** Split at the document level, then fine-tune a token
   classification head.

## What changed per generation

| Generation | Span source | Note |
|---|---|---|
| [[phase-1-original-corpus\|Phase 1]] | SpaCy PhraseMatcher + `qwen2.5:7b` + a pre-built disease-pathway DB | 560 records with spans |
| [[phase-2-pubmed-corpus\|Phase 2]] | exact matching over a 10,329-article co-occurrence corpus | 22,017 records |
| [[phase-3-silver-labeling\|Phase 3]] | guided `qwen2.5:14b` extraction + a deterministic booster, then human review | produced the gold dataset |
| [[phase-4-base-encoder-survey\|Phase 4]] | unchanged labels; the *encoder* is the variable | infrastructure and a survey |

## Structural facts worth knowing

- **A record is not an article.** In the Phase-2 exact-match data a record is a
  `(pmid, pathway_id)` pair, so one article that names 21 pathways produces 21
  records. Abstract and full-text spans live inside the *same* record,
  distinguished by a per-span `source` field
  (`playground/exact_match_analysis.md`).
- **The split boundary is the document.** Splitting on anything finer leaked;
  see [[use-pmid-based-dataset-splitting|PMID-based dataset splitting]].
- **The split is frozen on disk.** `data/processed/gold/splits.json` is tracked
  in git so that two encoders are scored on the same test set; see
  [[freeze-the-gold-split|Freeze the gold split]].
- **The label vocabulary never reaches the model.** `train.py` works with
  `O / B-Pathway / I-Pathway` only. Canonical pathway names exist for analysis
  and for the eventual pathway↔disease database — see
  [[canonical-mapping|Canonical mapping]].

## Runtime

Local training and local LLM annotation both run on one RTX 4060 Laptop with
8 GB VRAM; `reports/llm_selection_and_hardware_2026-07.md` measures 15 GB system
RAM as the tighter constraint of the two.
