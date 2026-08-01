---
type: concept
title: Misconfigured tokenizers look like weak encoders
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
  - knowledge_base/model_experiments.md
last_reviewed: 2026-08-01
---

# Misconfigured tokenizers look like weak encoders

2026-07-30, found while checking whether the pipeline accepts every candidate's
input format. It did — 17/17 fast tokenizers. But two registry entries were
quietly broken, and **both would have read as "this encoder is weak" rather than
"this encoder was misconfigured"**.

**The defect.** Neither `dmis-lab/biobert-base-cased-v1.2` nor
`emilyalsentzer/Bio_ClinicalBERT` ships a `tokenizer_config.json`, so
`AutoTokenizer` falls back to `do_lower_case=True` — on **cased** checkpoints
whose shared vocabulary has 8,373 capitalised entries.

```
default                'Alzheimer' -> ['al', '##z', '##heimer']
do_lower_case=False    'Alzheimer' -> ['Alzheimer']
```

Every capitalised entry the models were pretrained on was unreachable.

**Fix.** An `EncoderSpec.tokenizer_kwargs` field, applied inside
`spec.load_tokenizer()` — one construction point, so the override cannot be set
in one script and forgotten in another.

## Why the existing check could not see it

Broken BioBERT passed `check_alignment.py` at **95.8% exact**. Span recovery uses
character offsets, which stay correct no matter how badly the text is tokenized,
so the check is *structurally blind* to tokenization quality. The obvious proxies
barely move either: `[UNK]` rate 1.57% → 1.55%, tokens per word 1.811 → 1.836.

Only a direct test catches it: capitals present in the vocabulary while
`do_lower_case=True`. That check now runs, alongside deliberately loose UNK-rate
and tokens-per-word bounds — loose because a general-domain vocabulary on
biomedical text legitimately produces more UNKs, and that penalty is part of what
the domain axis is meant to measure.

## What generalises

When a validation passes, ask what it is *capable* of observing. A check that
measures a downstream invariant (offsets recover) can be perfectly satisfied by
input that is upstream garbage.

Related: [[tokenization|Tokenization]],
[[tier-0-comparison-harness|Tier 0]].
