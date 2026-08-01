---
type: concept
title: Tokenization
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
  - knowledge_base/model_experiments.md
last_reviewed: 2026-08-01
---

# Tokenization

Converting raw text into the integer IDs a model consumes, using the exact
vocabulary the model was pretrained with. A different tokenizer produces
meaningless input, which is why the pipeline stores a vocabulary fingerprint
next to every tokenized dataset and refuses a mismatch.

For NER the important output is `offset_mapping`: it maps each token back to its
character range, which is how a [[span|span]] becomes token labels. Without it
the character offsets and the token sequence no longer correspond.

## Measurements this project made

Tokenization turned out to be a live variable in
[[phase-4-base-encoder-survey|Phase 4]], and several intuitions were wrong:

- **A larger, newer vocabulary fragments biomedical terms *more*.** Bio-ModernBERT
  masks 14.8% of positions as continuation subwords against BiomedBERT's 7.4%,
  because its 50k vocabulary is general-domain while BiomedBERT's 30k WordPiece
  was built on PubMed.
- **Vocabulary quality costs documents, not just tokens.** At a fixed 512-token
  budget, tokens-per-word rises from 1.377 (BiomedBERT) to 1.825 (BioBERT /
  Bio_ClinicalBERT) and truncated gold spans rise from 29 to 127 of 2,817. Part
  of any measured "domain effect" is therefore tokenizer efficiency.
- **Five of seven candidates share one vocabulary** (fingerprint `595e0ac36d19`,
  28895 tokens), so differences among them are purely pretrained weights. In
  contrast `bert-base` and `biomedbert-base` are both 30522 tokens and
  *different* vocabularies — the pairing that fails silently rather than raising.
- **`trim_offsets: true` does not exclude the leading space**: `Ġfatty` reports
  offsets covering `' fatty'`, so label lookup must test a token's whole range.
- **A tokenizer can be silently misconfigured** — see
  [[misconfigured-tokenizers-look-like-weak-encoders|the lesson]].

The `dermatan` → `dermat` + `##an` split that causes a false-negative cluster
survives **every** candidate tokenizer, so that error class is not addressable by
swapping encoders.
