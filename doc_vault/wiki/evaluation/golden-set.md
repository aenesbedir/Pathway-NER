---
type: concept
title: Golden set
status: active
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - evaluation
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - playground/golden_set/README.md
  - project_tracking.md
last_reviewed: 2026-08-01
---

# Golden set

A small, hand-curated evaluation set built to answer one question: does the model
recognise pathway mentions **in all their surface variations**, or only in the
canonical strings [[distant-supervision|exact matching]] was built on.

It is for measurement, never for training. Its ten PMIDs are excluded from silver
generation by an explicit list.

## Versions

- **v1** — 5 abstracts, the ones richest in distinct Recon pathways;
  amino-acid/lipid heavy.
- **v2** — +5 abstracts chosen for pathway-*type* diversity: energy/central
  carbon, carbohydrate, nucleotide, urea cycle, vitamin/cofactor, bile acid,
  drug/xenobiotic.

Growing it moved Recon-resolvable mentions 38 → **76** and the exact-match catch
rate 37% → **51%** — the added central-carbon articles name pathways verbatim.
Roughly half the mentions are still variations that exact matching misses.

## Annotation schema

Four buckets per article: `spans` (contiguous mentions, typed `exact` /
`synonym` / `variation` / `umbrella`), `shared_head_enumerations` (factored
phrases and umbrella terms fanned out to their Recon children),
`out_of_vocab_pathways` (recorded but not scored) and
`metabolites_not_pathways` (precision negatives that must not be tagged).

## Its limits, stated by its own documentation

- **Abstract-level only.** The ten articles have long full texts; only abstracts
  are annotated.
- **Small by design** — 10 abstracts / 76 Recon-resolvable mentions (+9
  umbrella). Enough to detect a real generalization gap, not a tight benchmark.
- **It certifies only what it contains.** The 19 golden spans contain no
  synthesis/catabolism pair, which is exactly how they certified a canonicalizer
  that inverted meaning — see
  [[small-golden-sets-certify-what-they-contain|the lesson]].
- **It cannot arbitrate a model choice.** The deciding variation metric rests on
  6 cases, which is why [[batch-05-review-benchmark|the batch-05 review]]
  replaced it for A/B work.

Schema, the per-article table and the reproduce command stay canonical in
`playground/golden_set/README.md`; the annotated text lives in
`playground/golden_set/golden_set.md`.
