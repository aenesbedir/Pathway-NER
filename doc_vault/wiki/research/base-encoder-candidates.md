---
type: concept
title: Base-encoder candidates
status: developing
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - research
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - reports/base_model_expansion_analysis_2026-07.md
  - reports/base_model_survey_2026-07.md
last_reviewed: 2026-08-01
---

# Base-encoder candidates

Two reports exist and the later one **overrules** the earlier on two candidates.
Both are captured; the disagreement is preserved rather than resolved.

## The headline, stated negatively

The whole BLURB NER column spans **86.13** (the current base) to **86.89** (the
leaderboard's best) — 0.76 points, averaged over six corpora with thousands of
training documents each. A 2026 paper measures a 396M 8192-context
bio-ModernBERT at **parity with 110M PubMedBERT** on BC5CDR / JNLPBA / NCBI /
AnatEM. Realistic gain from an encoder swap: **+0.005 … +0.02 F1**, against a
measured seed band of ±0.007 — later re-measured at ±0.0175 at lr 5e-5, which
puts the predicted gain *inside* the noise.

## Dropped on evidence

- **BioClinical-ModernBERT**, ranked second by the earlier survey
  (`base_model_survey_2026-07.md`), is **1.0–4.1 points below** 110M PubMedBERT
  on literature NER. Its SOTA is on clinical notes; this corpus is PubMed
  abstracts.
- **Decoder LLMs with a token-classification head** — the teacher is already an
  LLM; the point of a student is to be cheap.

The earlier survey's ranking (BioLinkBERT-large, then Bio-ModernBERT-large, then
BiomedBERT-large) still reflects the BLURB leaderboard correctly; what changed is
the reading of what a leaderboard difference buys on 860 documents.

## The two candidates that clear the noise band

- **GLiNER-biomed** (arXiv 2504.00676) — LLM annotation ability distilled into a
  span-scoring model: 10-shot 70.4 → **50-shot 76.0** → full-supervision ~84.9
  F1. It selects spans rather than generating them, so hallucination is
  structurally impossible. This project's 860 documents sit inside that curve,
  and it is structurally the same idea as this project at a scale we cannot
  reach.
- **Task-adaptive pretraining** (OpenMed NER, arXiv 2508.01630) — SOTA on 10 of
  12 biomedical NER benchmarks from ordinary backbones plus DAPT and LoRA, under
  12 GPU-hours. A large unlabelled on-topic corpus already exists in `data/raw/`.

## Measured outcome (2026-08-01)

The first stage of this survey has now run and **confirmed the negative
prediction**: 30 cells over five encoders, and the preplanned
BiomedBERT-vs-BERT contrast lands at delta −0.0051 with a 95% CI of
[−0.0354, +0.0275]. See [[phase-4b-first-stage-grid|Phase 4b]].

That does not falsify the two candidates above — neither GLiNER-biomed nor
task-adaptive pretraining was in the grid, and both are different *kinds* of
change rather than another backbone swap. What it does settle is the ranking
question: widening the leaderboard at 860 documents is not worth the compute.

## Standing caveat

Every conclusion here is a paper number on other corpora. The project's own
measurements ([[tier-0-comparison-harness|Tier 0]]) contradicted several
assumptions the earlier survey made — notably that long context and a newer
tokenizer would help. Treat this note as a hypothesis list, not a result.

Related: [[phase-4-base-encoder-survey|Phase 4]],
[[annotator-llm-and-hardware|Annotator LLM and hardware]].
