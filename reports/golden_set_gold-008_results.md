# gold-008 on the golden set — results

The fine-tuned student model (`models/pathway-ner-gold-008`) evaluated on the
hand-curated golden set (`playground/golden_set/golden_set.json`), scored with the
**same offset-overlap methodology** as the guided-LLM runs so the numbers are
directly comparable.

- Script: `playground/golden_set/eval_bert_model.py`
- Raw reports: `analysis/golden_set_gold-008.json` (all 10 abstracts),
  `analysis/golden_set_gold-008_v1subset.json` (the 5 abstracts the LLM runs used)

## How to read these numbers

The golden set is a **hand-annotated answer key**. For each abstract a human marked:

- **gold targets** — every real pathway mention the model *should* find. These are
  the `spans` (contiguous mentions) plus the `shared_head_enumerations` (umbrella
  phrases like *"steroid synthesis and metabolism"*). Across all 10 abstracts there
  are **70** of them.
- **negatives** — things that look tempting but must **not** be tagged
  (metabolites, hormones, out-of-vocabulary terms), e.g. `cortisol`.

The model is then run over the same abstracts and every predicted span is compared
against that key by **character-offset overlap**:

| Column | Meaning |
|---|---|
| **Run** | which model / configuration was evaluated |
| **Mentions** | how many spans the **model predicted** in total (its output, not the answer key) |
| **TP** | a prediction that overlaps a real gold mention → correct |
| **FP_neg** | a prediction that overlaps an annotated **negative** → a definite precision error |
| **Unlabeled** | a prediction that overlaps neither → **unjudged**: either a genuine pathway the annotator did not mark, or a false positive |
| **P (strict)** | `TP / all predictions` — counts every Unlabeled as *wrong* (pessimistic bound) |
| **P (lenient)** | `TP / (TP + FP_neg)` — ignores Unlabeled entirely (optimistic bound) |
| **Recall** | how many of the gold targets the model found |

True precision sits between the strict and lenient numbers; the two bounds exist
because Unlabeled predictions were never adjudicated.

## Headline

**On the identical 5 abstracts the guided LLM was scored on, the student model
matches the teacher's precision and lifts recall from 72% to 100%.**

## Like-for-like comparison (v1 subset — 5 abstracts, 29 gold targets)

| Run | Mentions | TP | FP_neg | Unlabeled | P (strict) | P (lenient) | Recall |
|---|---|---|---|---|---|---|---|
| qwen2.5:14b + booster | 24 | 20 | 1 | 3 | 0.83 | **0.95** | 21/29 (72%) |
| qwen2.5:14b no-vocab | 20 | 16 | 1 | 3 | 0.80 | 0.94 | 17/29 (59%) |
| qwen2.5:7b no-vocab lenient | 34 | 22 | 2 | 10 | 0.65 | 0.92 | 22/29 (76%) |
| qwen2.5:7b with-vocab lenient | 14 | 14 | 0 | 0 | **1.00** | **1.00** | 15/29 (52%) |
| **gold-008 (BERT student)** | 36 | 31 | 2 | 3 | **0.86** | 0.94 | **29/29 (100%)** |

The 7b with-vocab variant reaches perfect precision only by being extremely
conservative — it finds barely half the mentions.

## Full golden set — all 10 abstracts, 70 gold targets

This is gold-008 measured on the **whole** answer key, not just the 5-abstract
subset above. The LLM was never scored on these 10, so there is no teacher column
here — this section answers *"how good is the student in absolute terms?"*, while
the previous section answers *"student vs teacher, same data"*.

Read it as: the model was shown 10 abstracts containing **70 pathway mentions it
should find**. It produced **77 predictions**, of which **71 landed on a real gold
mention**. Only **2** predictions hit something explicitly annotated as *not* a
pathway. **4** predictions fell outside the answer key entirely and were left
unjudged. It found **69 of the 70** targets.

| Metric | Value | Reading |
|---|---|---|
| Gold targets (the answer key) | 70 | what the model *should* find |
| Predicted mentions | 77 | what the model *did* output |
| True positives | 71 | predictions that hit a real mention |
| FP_neg (tagged a known negative) | 2 | definite errors |
| Unlabeled (not in gold, not a negative) | 4 | unjudged — possibly valid, possibly wrong |
| **Precision (strict)** | **0.92** | 71/77 — treats all 4 Unlabeled as wrong |
| **Precision (lenient)** | **0.97** | 71/73 — excludes the 4 Unlabeled |
| **Recall** | **69/70 (99%)** | only one gold mention missed |

Predictions (77) exceed gold targets (70) partly because a few mentions are split
into several predicted fragments — see caveat 1.

### Recall by gold target type

| Target type | Hit / total | % |
|---|---|---|
| span:exact | 25/25 | 100% |
| span:variation | 17/17 | 100% |
| span:synonym | 10/11 | 91% |
| span:umbrella | 5/5 | 100% |
| enum:variation | 7/7 | 100% |
| enum:exact+umbrella | 1/1 | 100% |
| enum:exact+variation | 1/1 | 100% |
| enum:synonym+variation | 1/1 | 100% |
| enum:umbrella | 1/1 | 100% |
| enum:umbrella+variation | 1/1 | 100% |

**`variation` recall is the point of this set** — those are real pathway mentions
that exact string matching misses (word-order reversals, plurals, paraphrases).
The model gets **17/17 contiguous variations and 7/7 variation enumerations**,
i.e. it has moved well past the near-lookup behaviour the golden set was built to
expose.

The 2 FP_neg cases: `Biosynthesis of unsaturated fatty acids` (PMID 40225847) and
`mitochondrial metabolism` (PMID 36294866) — both annotated as out-of-vocab /
non-pathway in the gold, both arguably defensible tags.

## Caveats — read before presenting

1. **Scoring is overlap-based, not span-exact.** A prediction counts as a TP if it
   overlaps a gold interval at all. Some predictions are fragmented
   (`atr` / `acid` / `oxidation` for one mention; `lipid and` + `nucleotide
   metabolism` split) and still score as TP. Precision here is therefore *lenient
   by construction* — this is the same yardstick the LLM was measured with, so the
   comparison is fair, but the absolute number is not a span-exact precision.
2. **The golden set is tiny** — 10 abstracts, 70 targets. Treat differences of a
   few points as noise.
3. **Different from the held-out test metric.** On the 109-document held-out split
   with strict span-exact scoring, gold-008 gets **F1 0.820 / P 0.783 / R 0.861**.
   The golden set measures a different, easier-to-satisfy question (did the model
   find the mention at all?).
4. The golden set abstracts are **not** in the training data (they come from the
   Phase-1 exact-match corpus, not the wave-2 / pilot-batch-05 gold set).

## Reproduce

```bash
# full golden set
/home/enes/sci-usage/venv310/bin/python3 playground/golden_set/eval_bert_model.py \
    --model-dir models/pathway-ner-gold-008 \
    --report analysis/golden_set_gold-008.json

# the 5-abstract subset the guided-LLM runs were scored on
/home/enes/sci-usage/venv310/bin/python3 playground/golden_set/eval_bert_model.py \
    --model-dir models/pathway-ner-gold-008 \
    --pmids 11469814 39934780 40225847 29615816 36294866 \
    --report analysis/golden_set_gold-008_v1subset.json
```
