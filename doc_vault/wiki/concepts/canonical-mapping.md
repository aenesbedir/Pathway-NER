---
type: concept
title: Canonical mapping
status: developing
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
  - project_tracking.md
  - playground/silver_1k_analyses.md
last_reviewed: 2026-08-01
---

# Canonical mapping

Deciding *which* pathway a surface string names — mapping
`metabolism of androgens` onto the Recon canonical
`androgen and estrogen synthesis and metabolism`. `llm/canonicalize.py` does it
in layers: exact → synonym table → content-phrase overlap → `unmapped`.

**The model never does this.** The tagger is binary, so the canonical name never
becomes a training label. That single fact is why canonicalization has been
deprioritised repeatedly without blocking anything.

## Why it is deliberately deferred

- On the 19 golden spans the canonicalizer commits correctly 16/16 and abstains
  3/19; its abstentions are exactly the string-unbridgeable classes (chemical
  synonym, biochemical hyponym, lipid subtype).
- On the 1k pilot the `unmapped` rate rose to 29%. Inspection of the 353 distinct
  surfaces found mostly **real pathway mentions with no Recon name**
  (`kynurenine pathway`, `lipid metabolism`, umbrella terms) — all valid
  positives for a binary tagger. A minority are cheap vocabulary gaps; a small
  tail is genuine noise for a human to reject.
- 28 of those 353 surfaces are verbatim **KEGG/Reactome** pathway names absent
  from Recon's 98 — independent evidence that the unmapped bucket holds real
  pathways rather than hallucinations.

## Where it does matter

It corrupted analysis once, badly:
[[small-golden-sets-certify-what-they-contain|the direction bug]] mapped
`purine biosynthesis` onto `purine catabolism`. Training labels were unaffected,
but the same error would be serious in the eventual pathway↔disease database —
which is the reason canonicalization cannot be abandoned, only postponed.
