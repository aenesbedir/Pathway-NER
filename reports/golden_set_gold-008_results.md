# gold-008 vs the guided LLM on the golden set

The fine-tuned student model (`models/pathway-ner-gold-008`) and its teacher
(`qwen2.5:14b` guided extraction) evaluated on the hand-curated golden set
(`playground/golden_set/golden_set.json`, v2 — 10 abstracts).

Both were run **fresh, on the same 10 abstracts, with the same scoring code**, so
the numbers are directly comparable.

- Student script: `playground/golden_set/eval_bert_model.py`
- LLM script: `playground/golden_set/eval_llm_guided.py`
- Raw reports: `analysis/golden_set_gold-008.json`,
  `analysis/golden_set_qwen14b_booster_rerun.json`,
  `analysis/golden_set_qwen14b_nobooster_rerun.json`

## How to read these numbers

The golden set is a **hand-annotated answer key**. For each abstract a human marked:

- **gold targets** — every real pathway mention the model *should* find: the
  `spans` (contiguous mentions) plus the `shared_head_enumerations` (umbrella
  phrases like *"steroid synthesis and metabolism"*). Across the 10 abstracts
  there are **70**.
- **negatives** — things that look tempting but must **not** be tagged
  (metabolites, hormones, out-of-vocabulary terms), e.g. `cortisol`.

Each predicted span is then compared to that key by **character-offset overlap**:

| Column | Meaning |
|---|---|
| **Run** | which model / configuration was evaluated |
| **Mentions** | how many spans the **model predicted** in total (its output, not the answer key) |
| **TP** | a prediction that overlaps a real gold mention → correct |
| **FP_neg** | a prediction that overlaps an annotated **negative** → a definite precision error |
| **Unlabeled** | a prediction that overlaps neither → **unjudged**: either a genuine pathway the annotator did not mark, or a false positive |
| **P (strict)** | `TP / all predictions` — counts every Unlabeled as *wrong* (pessimistic bound) |
| **P (lenient)** | `TP / (TP + FP_neg)` — ignores Unlabeled entirely (optimistic bound) |
| **Recall** | how many of the 70 gold targets the model found |

True precision sits between the strict and lenient bounds; both exist because
Unlabeled predictions were never adjudicated.

## Headline

**The student model finds 99% of the annotated pathway mentions versus the
teacher's 83%, at equal-or-better precision.**

## Head-to-head — all 10 abstracts, 70 gold targets

| Run | Mentions | TP | FP_neg | Unlabeled | P (strict) | P (lenient) | Recall |
|---|---|---|---|---|---|---|---|
| qwen2.5:14b (no booster) | 61 | 50 | 1 | 10 | 0.82 | **0.98** | 54/70 (77%) |
| qwen2.5:14b + booster | 63 | 55 | 1 | 7 | 0.87 | **0.98** | 58/70 (83%) |
| **gold-008 (BERT student)** | 77 | 71 | 2 | 4 | **0.92** | 0.97 | **69/70 (99%)** |

- **Recall is the decisive gap**: 99% vs 83%. The student misses one mention; the
  teacher misses twelve.
- **Strict precision favours the student** (0.92 vs 0.87) — it produces fewer
  unadjudicated spans relative to its output.
- **Lenient precision is a tie** (0.97 vs 0.98) — when a prediction is judged at
  all, both are right ~97–98% of the time.
- The deterministic booster helps the LLM (+6 pts recall) but does not close the gap.

## Recall by gold target type

This is what the golden set was built to expose: `exact` mentions are the ones
plain string matching already catches; `variation` / `synonym` / `umbrella` are the
paraphrases, word-order reversals and factored enumerations it misses.

| Target type | qwen2.5:14b | + booster | **gold-008** |
|---|---|---|---|
| span:exact | 22/25 | 24/25 | **25/25** |
| span:variation | 13/17 | 15/17 | **17/17** |
| span:synonym | 9/11 | 8/11 | **10/11** |
| span:umbrella | 4/5 | 4/5 | **5/5** |
| enum:variation | 3/7 | 5/7 | **7/7** |
| enum:exact+umbrella | 1/1 | 1/1 | 1/1 |
| enum:exact+variation | 1/1 | 1/1 | 1/1 |
| enum:synonym+variation | 1/1 | 0/1 | 1/1 |
| enum:umbrella | 0/1 | 0/1 | **1/1** |
| enum:umbrella+variation | 0/1 | 0/1 | **1/1** |

**The student wins or ties on every single category.** It is perfect on the hard
ones — 17/17 contiguous variations and 7/7 variation enumerations — where the LLM
lands 13–15/17 and 3–5/7. The near-lookup behaviour the golden set was created to
detect is gone.

The 2 FP_neg cases for gold-008: `Biosynthesis of unsaturated fatty acids`
(PMID 40225847) and `mitochondrial metabolism` (PMID 36294866) — both annotated as
out-of-vocab / non-pathway, both arguably defensible tags.

## Caveats — read before presenting

1. **Scoring is overlap-based, not span-exact.** A prediction counts as a TP if it
   overlaps a gold interval at all. Some student predictions are fragmented
   (`atr` / `acid` / `oxidation` for one mention; `lipid and` + `nucleotide
   metabolism` split) and still score TP. This is why the student's 77 predictions
   exceed the 70 targets. Both models are measured with the same yardstick so the
   comparison is fair, but the absolute precision is not span-exact.
2. **The golden set is tiny** — 10 abstracts, 70 targets. Treat differences of a
   few points as noise; the 16-point recall gap is well outside that.
3. **Different from the held-out test metric.** On the 109-document held-out split
   with strict span-exact scoring, gold-008 gets **F1 0.820 / P 0.783 / R 0.861**.
   The golden set answers an easier question (did it find the mention at all?).
4. **No leakage**: the golden set abstracts come from the Phase-1 exact-match
   corpus, not from the wave-2 / pilot-batch-05 data gold-008 was trained on.
5. The teacher is not disadvantaged by prompt choice — the booster variant shown is
   its strongest configuration from the earlier model sweep.

## Superseded numbers

Earlier LLM reports in `data/silver/eval_qwen*.json` (2026-07-20, commit `03a84cd`)
were scored on golden set **v1 — only 5 of these abstracts (29 targets)** and with
pre-`c1946fb` extraction code. They are kept for history but the table above
replaces them. For reference the old best was qwen2.5:14b+booster at
P_strict 0.83 / recall 21/29 (72%); the re-run on the same 5 abstracts with current
code is better, so the comparison here is against an *improved* teacher.

## Reproduce

```bash
# student
/home/enes/sci-usage/venv310/bin/python3 playground/golden_set/eval_bert_model.py \
    --model-dir models/pathway-ner-gold-008 \
    --report analysis/golden_set_gold-008.json

# teacher (needs `ollama serve` and the qwen2.5:14b model pulled)
venv310/bin/python3 playground/golden_set/eval_llm_guided.py \
    --model qwen2.5:14b --booster \
    --report analysis/golden_set_qwen14b_booster_rerun.json

venv310/bin/python3 playground/golden_set/eval_llm_guided.py \
    --model qwen2.5:14b \
    --report analysis/golden_set_qwen14b_nobooster_rerun.json
```
