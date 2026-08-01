---
type: concept
title: Annotator LLM and hardware
status: developing
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - research
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - reports/llm_selection_and_hardware_2026-07.md
last_reviewed: 2026-08-01
---

# Annotator LLM and hardware

A July 2026 literature and web survey answering two questions: is there a better
annotator than `qwen2.5:14b`, and is the hardware the limit. Written in Turkish;
this is an English synthesis.

## Medical-domain LLMs are a trap for this task

Biomedically fine-tuned models do not beat general ones at information extraction
and often lose — `Llama-3-8B-UltraMedical` and `PMC-Llama 13B` fall below base
`Llama-3.1-8B`, and MedGemma's technical report carries no NER/IE benchmark at
all. The reason is that this task needs instruction-following, verbatim spans and
valid JSON, not medical knowledge: the query pathways are already in the prompt
and [[canonical-mapping|canonicalization]] is ours.

## The highest-ROI alternative is not an LLM

**GLiNER-BioMed** — a 434M encoder, MIT licensed. Zero-shot 59.8 F1, **50-shot
76.0**, which is our data scale. It selects spans instead of generating them, so
hallucination is structurally impossible, and it runs in minutes on 8 GB. Its
error profile differs from a decoder's, which makes it a plausible **third**
annotation source next to the LLM and the deterministic booster.

## qwen2.5 is two generations old

Qwen3.5 (Feb–Mar 2026) and Gemma 4 (Apr 2026, Apache 2.0) have shipped, and
`qwen3.5:9b` fits the 8 GB card fully while the current 9.0 GB 14b already runs
partly CPU-offloaded. That was tested and **did not win** —
[[annotator-ab-qwen35-vs-qwen25|the A/B]].

## Hardware is not the bottleneck; the eval set is

15 GB system RAM binds harder than the 8 GB VRAM, and a ~$130 SO-DIMM upgrade
would unlock CPU-offloaded MoE models. But 7b → 14b never moved the deciding
metric (4/6 → 4/6), so the report's own advice is to **buy evidence before
hardware**: a few dollars of cloud GPU or a frontier API measures the ceiling
first, and the full 10k corpus via API costs roughly $3–15.

## The blocking caveat (§7)

The golden set is 10 abstracts / 76 mentions and the deciding metric rests on
**6 cases**. Model comparisons cannot be arbitrated at that size. The report's
first action item is to carve a ~150-abstract hold-out from the human-reviewed
1k before spending anything on model choice — which is what
[[batch-05-review-benchmark|the batch-05 benchmark]] partly answers.
