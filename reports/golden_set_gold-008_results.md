# gold-008 on the golden set — results

The fine-tuned student model (`models/pathway-ner-gold-008`) evaluated on the
hand-curated golden set (`playground/golden_set/golden_set.json`), scored with the
**same offset-overlap methodology** as the guided-LLM runs so the numbers are
directly comparable.

- Script: `playground/golden_set/eval_bert_model.py`
- Raw reports: `analysis/golden_set_gold-008.json` (all 10 abstracts),
  `analysis/golden_set_gold-008_v1subset.json` (the 5 abstracts the LLM runs used)

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

## Full golden set (all 10 abstracts, 70 gold targets)

| Metric | Value |
|---|---|
| Predicted mentions | 77 |
| True positives | 71 |
| FP_neg (tagged a known negative) | 2 |
| Unlabeled (not in gold, not a negative) | 4 |
| **Precision (strict)** | **0.92** |
| **Precision (lenient)** | **0.97** |
| **Recall** | **69/70 (99%)** |

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
