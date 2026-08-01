---
type: concept
title: Annotation strategy
status: active
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
  - doccano/ANNOTATION_GUIDE.md
  - project_tracking.md
  - annotation_handoff.md
last_reviewed: 2026-08-01
---

# Annotation strategy

Human review is **accept / reject / fix boundary**, plus adding spans the machine
missed. Annotators never assign pathway names: that is expert work and
irrelevant to a binary tagger ([[canonical-mapping|Canonical mapping]]).

## The rule the corpus is annotated under

> Does this string name a metabolic process?

Everything else in `doccano/ANNOTATION_GUIDE.md` is that rule applied to
recurring cases. Accepts include word-order variants, chemical synonyms,
subtypes, umbrella terms and non-"metabolism" process words. Rejects are bare
metabolites, enzymes and genes, non-metabolic processes
(`aminoacyl-tRNA biosynthesis` is translation), compartment terms
(`mitochondrial metabolism`) and diseases. The most common machine error is the
bare metabolite — the same compound *with* a process word is an accept.

## One deliberate divergence from the golden set

The [[golden-set|golden set]] files `biosynthesis of unsaturated fatty acids`
under `out_of_vocab_pathways` because it does not map onto a Recon name. That is
a **vocabulary** concern, not a "is this a pathway mention" concern. Since the
trained model is binary, such subtype names are **accepts** for review. The two
documents disagree on purpose and both are right for their own job.

## Workflow decisions in force

- **Annotators review Phase 3 silver only.** The older Phase-1 doccano export
  (488 documents) is ignored — zero review was done on it, it shares 3 PMIDs with
  Phase 3, and it is a different corpus and vocabulary. See
  [[review-phase-3-silver-only|the decision]].
- **Local install, per-annotator batches.** `doccano/split_batches.py` cuts the
  import file into verbatim 200-document slices; each annotator gets a batch plus
  `ANNOTATOR_STEPS.md` (Turkish) and `ANNOTATION_GUIDE.md` (English).
- The label is `PATHWAY`, matching the pre-existing annotation workspace's
  convention. The string never reaches the model.

`annotation_handoff.md` describes the earlier Phase-1 review session and is kept
as history only.

## Still open

A round-trip script that merges annotators' doccano exports back into a corrected
silver set does not exist yet for this schema. Policy for non-English abstract
bodies (two observed) is undecided.
