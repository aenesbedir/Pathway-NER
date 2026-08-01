---
type: concept
title: Span
status: evergreen
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - nlp
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - knowledge_base/nlp_concepts.md
  - playground/golden_set/README.md
last_reviewed: 2026-08-01
---

# Span

A contiguous segment of text identified by its **character** start and end
positions in a source string, so that `text[start:end]` always reproduces the
matched string exactly.

```json
{"start": 42, "end": 61, "text": "glycolytic pathway", "source": "abstract"}
```

Spans are the unit everything else is built on: they are what annotators accept
or reject, what evaluation compares, and what must be re-aligned to tokens before
a model can consume them ([[tokenization|Tokenization]],
[[bio-labeling|BIO labeling]]).

## What a span carries in this project

Beyond the offsets, a span records where it came from — `source="abstract"` or
`"full_text"` for match provenance, and for silver spans additionally
`source="llm_silver"`, `model`, `match_type` and `canonical`
(`data/silver/README.md`). This is what makes silver separable from gold after
the fact.

## Where spans get hard

- **Nesting.** The golden set annotates shared-head enumerations both as the
  whole phrase and as their parts, which flat BIO cannot represent — 83 such
  pairs were counted in `analysis/alignment_*.json`.
- **Boundaries.** A span that starts mid-word (`biopterin metabolism` inside
  `tetrahydrobiopterin metabolism`) produces a dangling `I` with no `B`; 12 such
  spans were found.
- **Coordination.** Review adopted an explicit test:
  `calcium and vitamin D metabolism` is one span because deleting a conjunct
  leaves something that is not a pathway name, while
  `glycolysis and the pentose phosphate pathway` is two.
