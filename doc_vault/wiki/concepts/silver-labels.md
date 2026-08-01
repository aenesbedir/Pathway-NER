---
type: concept
title: Silver labels
status: evergreen
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - annotation
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - data/silver/README.md
  - project_tracking.md
last_reviewed: 2026-08-01
---

# Silver labels

Machine-generated pathway spans that are **training-label candidates, not ground
truth**. In this project silver means the output of the guided extraction
pipeline: an LLM plus the deterministic booster, grounded to verbatim character
offsets.

Silver must pass human review before it is trusted for training. Reviewed silver
becomes [[gold-labels|gold]].

## Separation is enforced by construction

- Silver lives in `data/silver/`, gold in `playground/golden_set/` and
  `data/processed/gold/`; they are never mixed.
- Every silver span carries `source="llm_silver"`, `model`, `match_type` and
  `canonical`, so its origin survives every later transformation.
- The ten golden PMIDs are excluded from silver by an explicit list, on both the
  sampling path and the `--pmids` path — an eval abstract must not reach training
  data by either route.

## Composition of the 1k pilot

1,996 spans: `exact` 1,012 · `unmapped` 572 · `variation` 238 · `synonym` 174
(counts after the direction-bug fix). 1,824 came from the LLM and 172 from the
booster.

The `variation` + `synonym` share is the part that justifies the whole approach:
those mentions are invisible to [[distant-supervision|distant supervision]].

## Known qualifications

- Silver precision was assumed at ~0.90 from the golden set; the batch-05 review
  measured **0.892** on 200 abstracts and recall **0.698** — see
  [[batch-05-review-benchmark|the batch-05 benchmark]].
- Silver is reproducible by frozen artefacts, not by determinism —
  [[freeze-silver-samples-by-pmid-file|the freezing decision]].
