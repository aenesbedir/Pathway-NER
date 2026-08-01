---
type: concept
title: Review Phase 3 silver only
status: active
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
  - annotation_handoff.md
last_reviewed: 2026-08-01
---

# Review Phase 3 silver only

**Decision (user).** Annotators review [[phase-3-silver-labeling|Phase 3]] silver
in a **new** doccano project. The pre-existing Phase-1 export is ignored and its
project is left untouched.

**Why.** The Phase-1 export in the separate annotation workspace holds 488
documents whose 556 spans are all machine pre-fill with **zero review completed**.
It shares just 3 PMIDs with Phase 3 and is a different corpus (KEGG/Reactome
reference articles versus the PubMed co-occurrence corpus), different vocabulary,
1.1 versus 2.0 spans per document. Merging them would mix two annotation regimes
for no gain.

## What was reconciled with the existing workspace

An established doccano workspace already existed outside this repository, and
some of `doccano/` had been reinvented before it was found. Two things were
changed to match it:

- **Label `Pathway` → `PATHWAY`**, the convention that workspace already uses.
  The string never reaches the model.
- **`meta` un-flattened back to nested.** The earlier flattening was reasoned
  from doccano's source; the nested shape is the *proven* one — 488 records
  imported with it. Untested theory should not override working precedent.

`annotation_handoff.md` documents the Phase-1 review session and is kept as
history. The live policy is [[annotation-strategy|the annotation strategy]].

**Still open.** The round-trip script that merges doccano exports back into a
corrected silver set targets the Phase-1 schema, not this one; a Phase-3
equivalent is deferred until review returns.
