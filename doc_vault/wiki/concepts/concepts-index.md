---
type: meta
title: Concepts
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
  - knowledge_base/nlp_concepts.md
last_reviewed: 2026-08-01
---

# Concepts

The vocabulary the rest of the vault assumes. The first three are the NER
mechanics; the rest are this project's own label taxonomy.

- [[span|Span]] — the unit of annotation.
- [[tokenization|Tokenization]] — why character offsets need re-aligning.
- [[bio-labeling|BIO labeling]] — how spans become per-token supervision.
- [[distant-supervision|Distant supervision]] — labels from string matching, and
  what that costs.
- [[silver-labels|Silver labels]] — machine labels awaiting review.
- [[gold-labels|Gold labels]] — review-corrected labels the models train on.
- [[canonical-mapping|Canonical mapping]] — naming a pathway, which the model
  never does.

`knowledge_base/nlp_concepts.md` remains the repository-side glossary.
