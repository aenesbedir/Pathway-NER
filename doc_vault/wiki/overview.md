---
type: overview
title: Vault Overview
status: developing
created: 2026-08-01
updated: 2026-08-01
tags:
  - overview
---

# Vault Overview

This vault holds the **knowledge-level** record of [[pathway-ner|Pathway-NER]] —
a project that trains a binary tagger to find metabolic pathway mentions in
biomedical abstracts.

## Division of labour with the repository

The code repository stays canonical for anything operational: setup and run
commands, script input/output formats, reproduce instructions, doccano import
steps, dataset README files, and generated statistics. Those must change in the
same commit as the code they describe.

The vault is canonical for what does not belong next to a script: the conceptual
description of the project, architectural synthesis, why each experiment was run
and what it implies, technical decisions and their evidence, lessons from
diagnosed failures, and research syntheses.

Nothing was deleted or rewritten in the repository to build this vault.

## The shape of the story

Four phases, each of which changed **where labels come from**, never what the
model predicts:

[[phase-1-original-corpus|Phase 1]] showed the model's false positives were
mostly real pathway names the annotation had missed — so the bottleneck was data.
[[phase-2-pubmed-corpus|Phase 2]] built a far larger corpus by co-occurrence
search, and measured that its 73,096 spans reduce to 105 case-folded surface
forms — a near-lookup problem. [[phase-3-silver-labeling|Phase 3]] answered that
with LLM silver labelling plus a deterministic booster, then human review, which
produced the [[gold-labels|gold]] dataset every current model trains on.
[[phase-4-base-encoder-survey|Phase 4]] holds the labels fixed and asks whether
the encoder matters — and mostly finds that the measurement apparatus needed
fixing first.

## What is true now

Best model F1 ~0.82 on a 109-document held-out split; the teacher LLM sits at
0.864 span-exact. The encoder grid is paused on an unresolved reproducibility
problem. More reviewed data remains the dominant lever. See
[[current-status|Current status]].

Start at [[index|the index]].
