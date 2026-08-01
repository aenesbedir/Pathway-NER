---
type: concept
title: Small golden sets certify what they contain
status: evergreen
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - lesson
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - project_tracking.md
  - playground/silver_1k_analyses.md
last_reviewed: 2026-08-01
---

# Small golden sets certify what they contain

**The bug.** The 1k pilot analysis surfaced semantically **opposite** mappings:
`purine biosynthesis` → `purine catabolism`, `heme catabolism` → `heme synthesis`,
`pyrimidine biosynthesis` → `pyrimidine catabolism`.

**Cause.** Both `canonicalize.py` and `booster.py` strip the process word and
match on content phrases alone, so `purine biosynthesis` → `{purine}` ties
against *both* `purine synthesis` and `purine catabolism`; whichever came first
in the vocabulary won. Recon distinguishes them — the information was being
thrown away. The same surface even resolved differently depending on which code
path produced it, which is how it was localised to two places.

**Fix.** `process_class()` / `direction_ok()` classify a phrase as anabolic,
catabolic or neutral by its process word; a non-neutral surface may never match a
canonical of the opposite direction. Defined once in `booster.py` and imported by
`canonicalize.py`.

**Impact.** **Zero on training labels** — the canonical never enters a `0/1/2`
label. It corrupted the *analysis*, and would have been a serious error in the
future pathway↔disease database. After the fix, `exact` 999 → 1,012 and
`variation` 251 → 238; golden gates re-run with no regression.

## The lesson

The 19-span golden set contains **no synthesis/catabolism pair**, so it certified
a canonicalizer that inverted meaning. A gold set certifies exactly the phenomena
it contains and silently approves everything it does not.

A claim recorded earlier — "the failure mode is abstention, not error; it never
maps to a wrong canonical" — was **false**, and is struck through in the source
rather than deleted. Preserving the retracted claim next to its refutation is why
this was catchable at all.

Related: [[golden-set|Golden set]], [[canonical-mapping|Canonical mapping]],
[[batch-05-review-benchmark|the larger benchmark that replaced it]].
