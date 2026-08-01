---
type: concept
title: "Guided prompt: no vocabulary, lenient rule"
status: evergreen
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - decision
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - project_tracking.md
last_reviewed: 2026-08-01
---

# Guided prompt: no vocabulary, lenient rule

**Decision.** The guided extraction prompt hints the article's query pathways but
**does not** supply the 98-name Recon vocabulary, and uses the lenient
compound-name rule plus the word "synonyms" in the task line. Baked as the
default in `extract_guided()`; `--strict` reproduces the old baseline.

**Why no vocabulary.** Supplying the 98 names makes a 7B model over-conservative:
precision reaches 1.00 while variation recall collapses to 0–17%. Query-pathway
hints alone give the best balance. This is the same failure mode as the Phase-1
five-shot prompt, which dropped from 65.8% to 44.0% on the same model class.

**Why lenient.** The strict rule ("do not return metabolite or compound names")
was suppressing pathway phrases *built from* a compound name. The lenient rule
excludes a **bare** metabolite but keeps
`<compound> metabolism / biosynthesis / synthesis of <compound>`. Measured
effect: variation recall 33% → 67%, precision unchanged, zero new false
positives.

**Cost, stated.** Precision remains ~0.90 lenient on the golden set; the two
scored false positives (`aminoacyl-tRNA biosynthesis`, `mitochondrial
metabolism`) are terms deliberately scoped out — a scope disagreement, not
hallucination.

Evidence: [[guided-prompt-config-selection|Guided prompt config selection]].
The remaining variation misses are structural and were answered by the
deterministic booster in [[phase-3-silver-labeling|Phase 3]].
