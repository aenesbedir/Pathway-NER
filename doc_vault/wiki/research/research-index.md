---
type: meta
title: Research
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
  - reports/base_model_expansion_analysis_2026-07.md
  - reports/llm_selection_and_hardware_2026-07.md
last_reviewed: 2026-08-01
---

# Research

Surveys that have not become code. Both are literature and vendor-documentation
work, not measurements on this corpus — the distinction matters when reading
their numbers.

- [[base-encoder-candidates|Base-encoder candidates]] — which encoder should
  replace BiomedBERT-base, if any.
- [[annotator-llm-and-hardware|Annotator LLM and hardware]] — is there a better
  annotator than `qwen2.5:14b`, and is the hardware the limit.

They converge on the same recommendation from opposite directions: the highest
expected-value candidate is **GLiNER-BioMed**, a span-scoring encoder rather than
a generative model.
