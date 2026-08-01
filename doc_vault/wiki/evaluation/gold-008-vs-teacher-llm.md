---
type: comparison
title: gold-008 vs the teacher LLM
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
  - reports/golden_set_gold-008_results.md
last_reviewed: 2026-08-01
---

# gold-008 vs the teacher LLM

The fine-tuned student (`models/pathway-ner-gold-008`) and its teacher
(`qwen2.5:14b` guided extraction) run fresh on the same 10 [[golden-set|golden
set]] abstracts with the same scoring code. 70 gold targets.

| Run | Mentions | TP | FP_neg | Unlabeled | P strict | P lenient | Recall |
|---|---|---|---|---|---|---|---|
| qwen2.5:14b, no booster | 61 | 50 | 1 | 10 | 0.82 | 0.98 | 54/70 (77%) |
| qwen2.5:14b + booster | 63 | 55 | 1 | 7 | 0.87 | 0.98 | 58/70 (83%) |
| **gold-008** | 77 | 71 | 2 | 4 | **0.92** | 0.97 | **69/70 (99%)** |

**Recall is the decisive gap: 99% against 83%.** The student wins or ties on
every target category, including 17/17 contiguous variations and 7/7 variation
enumerations where the teacher lands 13–15/17 and 3–5/7. The near-lookup
behaviour the golden set was built to detect is gone from the student.

## How to read it honestly

The report states its own caveats and they matter more than the headline:

1. **Scoring is overlap-based, not span-exact.** A fragmented prediction still
   counts as a true positive, which is why 77 predictions exceed 70 targets.
2. **The set is tiny** — treat a few points as noise; the 16-point recall gap is
   not.
3. **This is not the held-out metric.** On the 109-document split with span-exact
   scoring the same model gets **F1 0.820 / P 0.783 / R 0.861**. The golden set
   asks an easier question.
4. **No leakage** — the golden abstracts come from the Phase-1 corpus, not from
   the wave-2 / batch-05 data gold-008 trained on.

## A contradiction kept on purpose

`knowledge_base/model_experiments.md` records the teacher **ahead** of the
student (F1 0.864 vs ~0.82) span-exact on the guide-based gold, while this report
puts the student ahead on overlap scoring. Both are true of different questions:
"did you find the mention" versus "did you get its boundaries right". Neither
number replaces the other.

Related: [[gold-005-008-seed-and-lr-sweep|gold-005…008]],
[[batch-05-review-benchmark|batch-05 benchmark]].
