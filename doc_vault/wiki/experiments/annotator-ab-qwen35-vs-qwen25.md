---
type: comparison
title: qwen3.5:9b vs qwen2.5:14b
status: active
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - experiment
  - annotation
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - project_tracking.md
last_reviewed: 2026-08-01
---

# qwen3.5:9b vs qwen2.5:14b

First use of the [[batch-05-review-benchmark|batch-05 harness]]: 200 abstracts,
483 gold spans.

| run | spans | P | R | F1 | lenient P/R/F1 |
|---|---|---|---|---|---|
| `qwen2.5:14b` | 378 | 0.892 | 0.698 | **0.783** | 0.934 / 0.748 / **0.831** |
| `qwen3.5:9b` | 398 | 0.791 | 0.652 | 0.715 | 0.889 / 0.752 / 0.815 |

**Recall is a wash; the whole gap is precision.** qwen3.5 emits more spans and
more of them are wrong. Its characteristic errors are the guide's named rejects:
`mitochondrial metabolism`, `mitochondrial respiration`, `glucose turnover`.

## Read span-exact with suspicion

The gold is seeded by qwen2.5 — for documents 51–200 the gold true positives
*are* qwen2.5's accepted spans, so it has a home-field advantage on boundaries.
Boundary-only false positives are 39/83 for qwen3.5 against 16/41 for qwen2.5,
and some of them (`pentose phosphate pathway`) are arguably better spans than the
recorded gold. Lenient scoring is the fairer read — and qwen2.5 still wins there.

## Two engineering findings

- **`think: false` is not sufficient.** On one PMID qwen3.5 deterministically
  breaks the JSON contract by reasoning *inside* the array. Disabling the
  thinking channel does not stop inline chain-of-thought. `think: true` is
  unusable outright: ~45× slower and it never emits a final answer.
- **A response schema fixes the format, not the judgement.** With a schema,
  200/200 abstracts complete at 1.3 s each (was 199/200 at 1.8), but F1 moves
  0.715 → 0.715. On `qwen2.5:14b` the schema is a strict no-op — byte-identical
  span output over the same 200. It was kept for every registry entry because it
  makes that failure class structurally impossible at zero cost.

The prompt already said "Return ONLY a JSON object… Do not explain." The model
read that and violated it anyway — the fix belongs at the decoding layer.

**Outcome:** [[keep-qwen25-14b-as-annotator|keep qwen2.5:14b]].
