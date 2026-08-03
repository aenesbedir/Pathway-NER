# Model Experiments

Tracking all fine-tuning runs for the Metabolic Pathway NER model.
Base model: `microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext`

---

## Run 001 — Baseline, all layers fine-tuned

**Path:** `models/pathway-ner/`

**Date:** 2026-06-26

### Training Data
| Split | Primary pathways | All pathways | Records | Positive labels |
|---|---|---|---|---|
| Train | 148 | 171 | 502 | 1,708 |
| Val | 18 | 21 | 44 | 224 |
| Test | 19 | 20 | 50 | 153 |

*Primary pathways: the first pathway_id per record, used to control the split. All pathways: every pathway_id including secondary ones on records that cover multiple pathways.*

### Hyperparameters
| Setting | Value |
|---|---|
| Base model | `microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext` |
| Frozen layers | None (all layers fine-tuned) |
| Learning rate | `3e-5` |
| Batch size | `16` |
| Max epochs | `20` |
| Warmup steps | `50` |
| Weight decay | `0.01` |
| Class weights (O / B / I) | `0.1 / 5.0 / 3.0` |
| Early stopping patience | `5 epochs` |
| fp16 | Yes |
| Label scheme | O=0, B-Pathway=1, I-Pathway=2 |

### Results
| Metric | Val (best, epoch 10) | Test |
|---|---|---|
| F1 | 0.4918 | 0.4604 |
| Precision | 0.4412 | 0.3951 |
| Recall | 0.5556 | 0.5517 |

Early stopping triggered at epoch 15 (no val F1 improvement for 5 epochs after epoch 10).

### Notes
- Precision (0.40) is the main weakness — 60% of predicted spans are false positives
- Recall (0.55) is reasonable for a first run with distant supervision labels
- Class weights `[0.1, 5.0, 3.0]` pushed recall up but hurt precision — too aggressive
- Test set is small (50 records, 19 pathways) so metrics have high variance
- No major overfitting: val F1 (0.49) ≈ test F1 (0.46)

### What to try next
- Reduce B/I class weights to `[0.1, 2.0, 1.5]` to improve precision
- Error analysis: inspect false positives to understand what the model mislabels
- Expand training data (biggest lever)
- Human review of a sample of training annotations

---

## Run 002 — Reduced class weights

**Path:** `models/pathway-ner-002/`

**Date:** 2026-06-26

**Change from Run 001:** Class weights reduced from `[0.1, 5.0, 3.0]` to `[0.1, 2.0, 1.5]` to improve precision.

### Hyperparameters
Same as Run 001 except:

| Setting | Value |
|---|---|
| Class weights (O / B / I) | `0.1 / 2.0 / 1.5` |

### Results
| Metric | Val (best) | Test |
|---|---|---|
| F1 | — | 0.4500 |
| Precision | — | 0.3529 |
| Recall | — | 0.6207 |

Early stopping triggered at epoch 14.

### Notes
- Recall increased (0.55 → 0.62) but precision dropped further (0.40 → 0.35) — opposite of intended
- Reducing weights alone does not fix the precision problem
- Root cause: noisy distant supervision labels teach the model to over-predict
- Weight tuning is not the right lever here

---

## Run 003 — Freeze bottom 6 layers

**Path:** `models/pathway-ner-003/`

**Date:** 2026-06-29

**Change from Run 001:** Froze bottom 6 BERT layers (embeddings + layers 0–5). Only top 6 layers + classifier head trained. 101/199 parameter groups frozen.

### Hyperparameters
Same as Run 001 except:

| Setting | Value |
|---|---|
| Frozen layers | Embeddings + encoder layers 0–5 |
| Trainable layers | Encoder layers 6–11 + classifier |

### Results
| Metric | Val (best) | Test |
|---|---|---|
| F1 | — | 0.4177 |
| Precision | — | 0.3300 |
| Recall | — | 0.5690 |

Ran all 20 epochs (no early stopping triggered).

### Notes
- Worst result of the three runs — freezing hurt performance
- Precision dropped further (0.40 → 0.33) despite fewer trainable parameters
- Confirms BiomedBERT lower layers need full adaptation even within the same domain
- Freezing strategy ruled out for this dataset

### Summary across runs

| Run | Change | F1 | Precision | Recall |
|---|---|---|---|---|
| 001 | Baseline, all layers | **0.46** | **0.40** | 0.55 |
| 002 | Reduced weights [0.1/2.0/1.5] | 0.45 | 0.35 | **0.62** |
| 003 | Freeze bottom 6 layers | 0.42 | 0.33 | 0.57 |

Run 001 is the best checkpoint. Precision consistently low across all runs — points to data quality (noisy distant supervision labels) rather than hyperparameters.

---

## Run 004 — Freeze bottom 9 layers

**Path:** `models/pathway-ner-004/`

**Date:** 2026-06-29

**Change from Run 003:** Froze 9 layers instead of 6. Only top 3 layers + classifier head trained. 149/199 parameter groups frozen.

### Hyperparameters
Same as Run 001 except:

| Setting | Value |
|---|---|
| Frozen layers | Embeddings + encoder layers 0–8 |
| Trainable layers | Encoder layers 9–11 + classifier |

### Results
| Metric | Val (best) | Test |
|---|---|---|
| F1 | — | 0.3656 |
| Precision | — | 0.2656 |
| Recall | — | 0.5862 |

Ran all 20 epochs (no early stopping triggered).

### Notes
- Worst result overall — freezing 9 layers significantly hurts all metrics
- Clear trend: more frozen layers → worse F1 and precision
- Freezing strategy definitively ruled out for this dataset and domain

### Full summary across all runs

| Run | Change | F1 | Precision | Recall |
|---|---|---|---|---|
| 001 | All layers, w=[0.1/5.0/3.0] | **0.46** | **0.40** | 0.55 |
| 002 | All layers, w=[0.1/2.0/1.5] | 0.45 | 0.35 | **0.62** |
| 003 | Freeze 6 layers | 0.42 | 0.33 | 0.57 |
| 004 | Freeze 9 layers | 0.37 | 0.27 | 0.59 |

**Conclusion:** Run 001 is the best. Precision is consistently low (0.27–0.40) across all hyperparameter changes — root cause is data quality, not model configuration. Next step: error analysis.

---

## Run 005 — Phase 2 data (PubMed co-occurrence, PMID-based split)

**Path:** `models/pathway-ner-005/`

**Date:** 2026-07-10

**Change from Run 001–004:** Entirely new training data from Phase 2 pipeline. Articles fetched via PubMed co-occurrence search (pathway × disease pairs), annotated with exact string matching. Split changed from pathway-based to **PMID-based** to prevent data leakage (all records from the same article go to the same split).

### Training Data
| Split | PMIDs | Records | Positive labels |
|---|---|---|---|
| Train | 7,085 | 33,328 | 120,761 |
| Val | 885 | 3,970 | 14,087 |
| Test | 887 | 4,403 | 16,180 |

*Records include 1 abstract record + N full-text window records (±500 char context around each annotated span) per PMID.*

### Hyperparameters
Same as Run 001 except:

| Setting | Value |
|---|---|
| Frozen layers | Embeddings + encoder layers 0–8 (149/199 params frozen) |

### Results
| Metric | Val (best, epoch 20) | Test |
|---|---|---|
| F1 | 0.9857 | **0.9812** |
| Precision | 0.9751 | 0.9713 |
| Recall | 0.9966 | 0.9913 |

Ran all 20 epochs (early stopping not triggered — F1 kept slowly improving).

### Notes
- Massive improvement over Phase 1 runs (F1: 0.46 → 0.98) driven entirely by data quality and quantity
- Phase 2 annotations are high-precision: articles were fetched because they co-mention the pathway, so exact string matching yields 93.4% hit rate (vs 6.3% in Phase 1)
- Val/test gap is minimal (0.9857 vs 0.9812) — model generalizes well, no overfitting
- High recall (0.99) suggests the model finds nearly all pathway mentions in the text
- High precision (0.97) suggests very few false positives — opposite of Phase 1 behavior
- First attempt had data leakage (val F1=0.98 at epoch 13 with pathway-based split); fixed by switching to PMID-based split — see `lessons_learned/challenges.md`

### Full summary across all runs

| Run | Data | Change | Weights (O/B/I) | F1 | Precision | Recall |
|---|---|---|---|---|---|---|
| 001 | Phase 1 | All layers | 0.1 / 5.0 / 3.0 | 0.46 | 0.40 | 0.55 |
| 002 | Phase 1 | All layers | 0.1 / 2.0 / 1.5 | 0.45 | 0.35 | 0.62 |
| 003 | Phase 1 | Freeze 6 layers | 0.1 / 5.0 / 3.0 | 0.42 | 0.33 | 0.57 |
| 004 | Phase 1 | Freeze 9 layers | 0.1 / 5.0 / 3.0 | 0.37 | 0.27 | 0.59 |
| **005** | **Phase 2** | **PMID-based split, 33K records** | **0.1 / 5.0 / 3.0** | **0.9812** | **0.9713** | **0.9913** |

**Conclusion:** Data quality and quantity is the dominant factor. Phase 2's co-occurrence-fetched, exact-matched annotations produce a dramatically better model with no architectural changes.

---

## Error Analysis — Run 001

**Script:** `analysis/error_analysis.py`  
**Output:** `analysis/error_analysis.json`

Span text recovered by slicing source text via `offset_mapping` (fixes tokenizer decoding artifact — `"dermat"` → `"dermatan"`). Adjacent predicted spans merged if within 2 chars. Partial TPs: predicted span overlaps true span AND intersection ≥ 50% of predicted span length.

**Span counts (test set, 50 records):**

| Category | Count |
|---|---|
| True Positives (exact match) | 38 |
| Partial True Positives (boundary mismatch) | 3 |
| False Positives | 30 |
| False Negatives | 23 |
| Total predicted spans | 71 |
| Total true spans | 64 |

**Metrics:**

| Scheme | P | R | F1 |
|---|---|---|---|
| Exact only | 0.559 | 0.623 | 0.589 |
| Partial TPs full credit | 0.578 | 0.641 | 0.607 |
| nervaluate strict | 0.412 | 0.509 | 0.455 |
| nervaluate partial | 0.456 | 0.564 | 0.504 |
| nervaluate type | 0.500 | 0.618 | 0.553 |

**Key findings:**
- Many FPs are legitimate pathway names missed by distant supervision (`"heme synthesis"`, `"cholesterol metabolism"`, `"glycolytic pathway"`) — data quality is the root cause
- 3 partial TPs are boundary errors: model extends or truncates span slightly (e.g. `"dermatan sulfate biosynthesis"` vs `"dermatan sulfate"`)
- Tokenizer artifact: `"dermatan"` → `"dermat" + "##an"` causes 10 FNs for dermatan sulfate pathway
- Conclusion: improving the annotation pipeline will have more impact than further hyperparameter tuning

---

## Run gold-001 — First model on review-corrected gold data

**Path:** `models/pathway-ner-gold-001/`

**Date:** 2026-07-27

**Change from prior runs:** New dataset. Trained on the review-corrected **gold**
labels (`data/processed/gold/`, see `data/processed/gold/README.md`) instead of
Phase-1/2 distant-supervision silver. Gold spans = reviewed `tp + fn` from
wave-2 silver (qwen2.5:14b) + pilot-1k batch 05. Architecture/hyperparameters
identical to Run 001.

### Training Data
| Split | PMIDs | Records | Positive tokens (B+I) |
|---|---|---|---|
| Train | 860 | 860 | 5,943 |
| Val | 107 | 107 | 673 |
| Test | 109 | 109 | 709 |

*1200 gold docs → 1083 with ≥1 span → 1076 with B/I tokens after 512-token
truncation → PMID-stratified 80/10/10 split (seed 42).*

### Hyperparameters
Same as Run 001 (frozen embeddings + encoder layers 0–8 → 149/199 params frozen;
lr 3e-5; batch 16; 20 epochs; warmup 50; weight decay 0.01; class weights
`0.1 / 5.0 / 3.0`; early stopping patience 5; fp16).

### Results
| Metric | Val (best, epoch 8) | Test |
|---|---|---|
| F1 | 0.6965 | 0.6734 |
| Precision | — | 0.5809 |
| Recall | — | 0.8008 |

Early stopping triggered at epoch 13. Train runtime ~125 s on RTX 4060 Laptop.

### Notes
- Large jump over Phase-1/2 silver models (test F1 0.37–0.46 → **0.67**): cleaner
  labels dominate, as expected.
- Not comparable to Run 005 (F1 0.98) — that was a different, exact-match test set
  with trivial string-match leakage.
- Precision (0.58) is the weakness; recall (0.80) is strong → model over-tags.
  Likely driven by umbrella/coordination gold spans (`lipid metabolism`, long
  coordinated names) that push aggressive tagging.
- Teacher (qwen2.5:14b) span-exact on the same guide-gold: P 0.906 / R 0.825 /
  F1 0.864. Student underperforms on 860 abstracts — precision is the gap.

### What to try next
- Raise O weight / lower B/I weights to curb over-tagging (precision lever).
- Error analysis on gold test FPs (`analysis/error_analysis.py`).
- More reviewed data (wave-3) — biggest lever.

## Run gold-002 — Precision tuning via class weights

**Path:** `models/pathway-ner-gold-002/`

**Date:** 2026-07-27

**Change from gold-001:** Class weights `0.1 / 5.0 / 3.0` → **`0.3 / 2.0 / 1.5`**.
Raise the O weight (penalise entity over-prediction) and lower B/I to curb the
over-tagging seen in gold-001. Everything else identical. Class weights are now a
CLI arg (`train.py --class-weights O B I`).

### Results
| Metric | gold-001 | gold-002 | Δ |
|---|---|---|---|
| Test F1 | 0.6734 | **0.7227** | +0.049 |
| Test Precision | 0.5809 | **0.6558** | +0.075 |
| Test Recall | 0.8008 | 0.8048 | +0.004 |

Best val F1 0.7625 (epoch 18). Ran the full 20 epochs — early stopping did **not**
trigger (val F1 still climbing), so the run may be epoch-limited. Train runtime
~193 s on RTX 4060 Laptop.

### Notes
- Precision lever worked as intended: +7.5 pts precision, recall held → +5 pts F1.
- Contrast with Run 002 (Phase-1 silver), where lowering B/I weights *hurt*
  precision — on clean gold the weight lever behaves as expected.
- Teacher (qwen2.5:14b) still ahead: P 0.906 / R 0.825 / F1 0.864.

### What to try next
- More epochs (val F1 not yet plateaued at 20) or higher early-stopping patience.
- Push O weight further (e.g. `0.5 / 1.5 / 1.0`) to trade a little recall for more
  precision.
- Error analysis on remaining gold-test FPs.

## Run gold-003 — More epochs + balanced weights

**Path:** `models/pathway-ner-gold-003/`

**Date:** 2026-07-27

**Change from gold-002:** Class weights `0.3 / 2.0 / 1.5` → **`0.5 / 1.5 / 1.0`**
(push O further, flatten B/I); max epochs 20 → **40**, early-stopping patience
5 → **8**. `--epochs` and `--patience` are now CLI args.

### Results
| Metric | gold-001 | gold-002 | gold-003 |
|---|---|---|---|
| Test F1 | 0.6734 | 0.7227 | **0.7437** |
| Test Precision | 0.5809 | 0.6558 | **0.6799** |
| Test Recall | 0.8008 | 0.8048 | **0.8207** |

Best val F1 0.7713. Early stopping fired (~epoch 25); best checkpoint epoch 17.
Train runtime ~164 s on RTX 4060 Laptop.

### Notes
- Both precision (+2.4) and recall (+1.6) rose over gold-002 — no trade-off this
  time; the extra epochs let the balanced weights fit better.
- Cumulative gain over gold-001: F1 +0.070, precision +0.099.
- Still below teacher qwen2.5:14b (F1 0.864). Remaining gap is mostly the small
  training set (860 abstracts); weight/epoch tuning looks near its ceiling.

### What to try next
- More reviewed data (wave-3) — now the dominant lever.
- Error analysis on gold-003 test FPs to confirm what is left.

## Run gold-004 — Unfreeze all layers (biggest lever so far)

**Path:** `models/pathway-ner-gold-004/`

**Date:** 2026-07-27

**Change from gold-003:** `--frozen-layers 9` → **`0`** (train the whole network,
embeddings included). Weights `0.5 / 1.5 / 1.0`, epochs 40, patience 8 unchanged.
`--frozen-layers` is now a CLI arg.

### Results
| Metric | gold-003 (9 frozen) | gold-004 (0 frozen) | Δ |
|---|---|---|---|
| Test F1 | 0.7437 | **0.8154** | +0.072 |
| Test Precision | 0.6799 | **0.7881** | +0.108 |
| Test Recall | 0.8207 | **0.8446** | +0.024 |

Best val F1 0.8229 (epoch 23); early stopping fired ~epoch 31. Train runtime
~452 s on RTX 4060 Laptop (all params trainable → slower).

### Notes
- **Freezing was the dominant lever, not class weights.** Full fine-tuning jumped
  F1 +7 pts and precision +11 pts over the best frozen run.
- Now close to teacher qwen2.5:14b (F1 0.864 vs 0.815) — the distilled student
  nearly matches the LLM at a fraction of inference cost.
- Precision and recall both balanced (~0.79 / 0.84); no obvious over/under-tagging.
- gold-004 is the current best model.

### What to try next
- Inference post-processing (merge adjacent spans, repair `I`-without-`B`) for a
  cheap precision bump.
- More reviewed data (wave-3) to close the last gap to the teacher.

## Runs gold-005 … gold-008 — Seed variance and learning-rate sweep

**Paths:** `models/pathway-ner-gold-005` … `-008`

**Date:** 2026-07-27

**Why:** every gold run so far was a single run at HF's default `seed=42`, on a
109-document test split. Before trusting gold-004's 0.815 or tuning further, we
needed (a) the seed noise band and (b) whether the hardcoded `3e-5` was right now
that all layers train. `--lr` and `--seed` are now CLI args (`set_seed()` is called
before model init so the classifier head is reproducible). The data split is
untouched — `--seed` only affects head init, batch shuffling and dropout.

All runs use the gold-004 recipe: `--class-weights 0.5 1.5 1.0 --epochs 40
--patience 8 --frozen-layers 0`.

### Seed variance (lr 3e-5)
| Run | Seed | Test F1 | Test P | Test R | Best epoch |
|---|---|---|---|---|---|
| gold-004 | 42 | 0.8154 | 0.7881 | 0.8446 | 23 |
| gold-005 | 1 | 0.8008 | 0.7645 | 0.8406 | 30 |
| gold-006 | 7 | 0.8135 | 0.8103 | 0.8167 | 21 |
| **mean ± std** | | **0.810 ± 0.007** | 0.788 ± 0.019 | 0.834 ± 0.012 | |

- F1 noise band is small (±0.007, full range 0.801–0.815). The gold-003 → gold-004
  jump (+0.072) is **far outside** the noise — unfreezing is a real effect.
- Precision is the noisier metric (±0.019); precision-only comparisons below
  ~0.04 should not be trusted from a single seed.

### Learning-rate sweep (seed 42)
| Run | lr | Test F1 | Test P | Test R | Best epoch |
|---|---|---|---|---|---|
| gold-007 | 2e-5 | 0.7865 | 0.7420 | 0.8367 | 15 |
| gold-004 | 3e-5 | 0.8154 | 0.7881 | 0.8446 | 23 |
| gold-008 | 5e-5 | **0.8197** | 0.7826 | **0.8606** | 21 |

- 2e-5 is clearly worse (−0.029 F1, outside the noise band) — the hypothesis that
  full fine-tuning wanted a *lower* lr was wrong.
- 5e-5 edges out 3e-5 by +0.004 F1, which is **inside** the ±0.007 seed band —
  not a distinguishable difference on one seed. Recall is higher (+0.016),
  precision marginally lower.

### Conclusion
- **Current best: gold-008 (lr 5e-5, F1 0.8197)**, but statistically tied with
  gold-004; treat 3e-5 and 5e-5 as equivalent and prefer 5e-5 for the recall edge.
- lr tuning is exhausted: the 2e-5→5e-5 span moves F1 by ~0.03, and the top half of
  that range is flat.
- Teacher qwen2.5:14b remains ahead (F1 0.864 vs 0.820), gap now ~0.044.
- Any future comparison smaller than ~0.015 F1 needs multi-seed averaging to mean
  anything.

### What to try next
- More reviewed data (wave-3) — the only lever left with real headroom.
- Inference post-processing (BIO repair, adjacent-span merge) for cheap precision.

---

## Tier 0 — comparison harness (no modelling change)

**Date:** 2026-07-29

Infrastructure only, in preparation for the encoder survey in
`reports/base_model_expansion_analysis_2026-07.md`. No hyperparameter or data
change; the gate was that the regenerated dataset must be byte-identical to the
one gold-001…008 used, and it is.

### What was wrong

1. **The split was tokenizer-dependent.** `build_dataset.py` dropped records with
   no positive label *after* tokenization (1083 → 1076 under BiomedBERT, 7 lost to
   512-token truncation) and then shuffled the survivors at `seed=42`. A tokenizer
   that loses a different number of documents — a ModernBERT at 8192 tokens loses
   none — shuffles a different-length list into an unrelated assignment. Every
   encoder would have been scored on a different test set, with every log line
   still reading "Test: 109".
2. **The model name was hardcoded twice** (`tag_bio.py`, `train.py`) with no link
   between the `input_ids` on disk and the model consuming them.
3. **`train.py` could only load BERT**, and used fp16 — a known NaN source for
   ModernBERT, which was pretrained in bf16.

### What changed

| file | change |
|---|---|
| `preprocessing/make_splits.py` *(new)* | snapshots the gold-001…008 assignment into `data/processed/gold/splits.json`, now a tracked contract |
| `preprocessing/build_dataset.py` | `--splits` assigns by lookup, no shuffle; logs `n_assigned / n_kept / n_unassigned / n_missing` |
| `preprocessing/tag_bio.py` | `--model`; range-based label alignment; writes `meta.json` with a vocabulary fingerprint |
| `preprocessing/check_alignment.py` *(new)* | decodes BIO back to character spans and fails on any unexplained loss |
| `encoders.py` *(new)* | encoder registry, shaped like `llm/models.py`: 10 entries with ctx, precision, batch size, lr grid, layer-name pattern |
| `train.py` | `--model`, `AutoModelForTokenClassification`, bf16 autodetect, vocabulary guard, `test_predictions.jsonl`, `--no-save-model` |
| `scripts/run_matrix.py`, `scripts/aggregate_runs.py` *(new)* | model × lr × seed sweep; mean ± std and a document-level paired bootstrap |

### Verification

| check | result |
|---|---|
| `splits.json` | 1076 PMIDs, 860/107/109, the 7 truncation-killed PMIDs listed |
| byte-identity gate | `bio_tags.jsonl` and `{train,val,test}.jsonl` identical to the pre-change files |
| `check_alignment.py`, 7 tokenizers | 0 unexplained span losses on all of them |
| vocabulary guard | rejects BiomedBERT-base data for a BioLinkBERT model; allows it where the vocabularies are byte-identical |
| **bf16 re-run of the gold-008 recipe** | **F1 0.8199** vs gold-008's 0.8197 (Δ +0.0002) — the precision flip and the transformers 4.x → 5.10.2 upgrade are both harmless |

### The seed band at lr 5e-5 is 2.5x wider than assumed

Three seeds of the gold-008 recipe on the frozen split:

| seed | test F1 | P | R |
|---|---|---|---|
| 42 | 0.8199 | 0.7897 | 0.8526 |
| 1 | 0.7947 | 0.7600 | 0.8327 |
| 7 | 0.8282 | 0.7949 | 0.8645 |
| **mean ± std** | **0.8143 ± 0.0175** | 0.7815 ± 0.0188 | 0.8499 ± 0.0161 |

The ±0.007 band every earlier conclusion leaned on came from gold-004/005/006 at
**lr 3e-5**. At 5e-5 it is **±0.0175**, range 0.0335. Higher learning rate, more
variance — which is ordinary, but it was never measured until now.

Consequences:

- **gold-008's 0.8197 was a lucky seed.** The recipe's actual mean is 0.8143, and
  gold-004's 0.8154 at 3e-5 is indistinguishable from it. The earlier note that
  "5e-5 edges out 3e-5 by +0.004" compared two single seeds and means nothing.
- **The 0.015 decision margin was calibrated on the wrong number.** With σ = 0.0175,
  two 5-seed configurations differ detectably only at ≈ **0.022 F1** — the very top
  of the +0.005…+0.02 range the literature predicts for an encoder swap.

| seeds / config | SEM | smallest detectable difference |
|---|---|---|
| 3 | 0.0101 | 0.029 |
| 5 | 0.0078 | 0.022 |
| 8 | 0.0062 | 0.018 |
| **11** | 0.0053 | **0.015** |
| 15 | 0.0045 | 0.013 |

- **Tier 1 needs 11 seeds, not 5.** That is ~7.3 GPU-hours for five configurations
  on the 4060 — an overnight run, so the fix is affordable rather than blocking.
- Whether lr 3e-5 is the more *stable* choice is now an open question worth one
  cheap experiment: its band was measured at ±0.007 on three seeds, half of 5e-5's.

### Measurements worth keeping

- **Bio-ModernBERT fragments biomedical terms *more*, not less.** 14.8% of its
  positions are masked continuation subwords against BiomedBERT's 7.4%. Its 50k
  vocabulary is general-domain; BiomedBERT's 30k WordPiece was built on PubMed.
  Whatever a ModernBERT wins here, it will not be through tokenization.
- **At 8192 tokens ModernBERT truncates 0 of 2817 gold spans**, against 29–33 for
  every 512-token candidate — but **all of those losses fall in train/val: the test
  split loses 0 of its 254 spans to truncation.** So long context can buy exactly
  **0.000 F1** on the current test set. Its only effect is 33 extra training spans
  (+1.5%). The long-context argument for ModernBERT is, on this split, worthless.
- **`dermatan` fragments worse under ModernBERT, not better**: `dermat`+`##an`
  (2 pieces) under both WordPiece vocabularies, `der`+`mat`+`an` (3) under the
  ByteLevel BPE. No candidate tokenizer keeps it whole, so the FN cluster in
  `analysis/error_analysis.json` is not addressable by an encoder swap at all.
- **Long context is not free.** Bio-ModernBERT-*base* (150M) OOMs at batch 16 on
  the 8 GB card: a 512-token model pads a batch to 512, an 8192-token one pads to
  the longest document in it (~2750 tokens here). It needs batch 2 × grad-accum 8.
- **Five of seven candidates share one vocabulary.** BioLinkBERT base *and* large,
  BiomedBERT-large-abstract, BioM-ELECTRA-large and BioELECTRA all ship
  byte-identical 28895-token PubMedBERT `vocab.txt` files (fingerprint
  `595e0ac36d19`). BiomedBERT-*base*-abstract-fulltext has its own 30522-token
  vocabulary (`c6e31067b526`) — a different vocabulary of a similar size, exactly
  the pairing that fails silently. The guard compares fingerprints for this reason.

  Two consequences for the survey design:
  - among those five, any F1 difference is **purely the pretrained weights** — the
    inputs are bit-identical, which is as clean as a comparison gets;
  - **`biomedbert-large` is not the size-only control it was chosen to be.** Its
    vocabulary is the 28895 one, not `biomedbert-base`'s 30522, so base → large
    changes the tokenizer as well as the size. `biolinkbert-base` → `-large` does
    that job with the confound removed.
- **The `dermatan` → `dermat` + `##an` split survives every candidate tokenizer**,
  so the FN cluster in `analysis/error_analysis.json` is not addressable by an
  encoder swap.

### Findings for wave-3 review

`analysis/alignment_*.json` records two annotation problems, both
tokenizer-independent:

- **83 nested span pairs** — shared-head enumerations annotated twice
  (`cholesterol and fatty acid synthesis` *and* `fatty acid synthesis`). Flat BIO
  cannot represent nesting: the inner span's start opens a new `B`, truncating the
  outer mention. This plausibly contributes to the boundary errors already logged
  in the error analysis and deserves its own investigation.
- **12 boundary-error spans** — 6 starting mid-word (`biopterin metabolism` inside
  `tetrahydrobiopterin metabolism`), 6 dropping a plural (`kynurenine pathway`
  where the text reads `kynurenine pathways`). The 6 mid-word starts produce a
  dangling `I` with no `B`.

### What to try next
- Tier 1: the base-size sweep (`bioelectra-base`, `biolinkbert-base`,
  `bio-modernbert-base`, `modernbert-bio-base`) at **11 seeds**, locally — ~7 GPU-hours.
- Re-measure the lr 3e-5 band on the frozen split; if it really is half of 5e-5's,
  the sweep should run at 3e-5 to buy statistical power for free.
- Wave-3 data remains the dominant lever, and the variance measurement strengthens
  that: the encoder axis is now known to sit at the edge of what 109 test documents
  can resolve at all.

---

## Phase 4b prep — two silently misconfigured tokenizers

**Date:** 2026-07-30

Found while checking whether the pipeline accepts every candidate's input format.
It does — 17/17 fast tokenizers, all with a token-classification head and
`max_position_embeddings` ≥ the registry's context. No format work was needed.
But two entries were quietly broken, and both would have read as "this encoder is
weak" rather than "this encoder was misconfigured".

### BioBERT and Bio_ClinicalBERT were being decapitalised

Neither `dmis-lab/biobert-base-cased-v1.2` nor `emilyalsentzer/Bio_ClinicalBERT`
ships a `tokenizer_config.json` (both 404). `AutoTokenizer` therefore falls back
to `do_lower_case=True` — on **cased** checkpoints whose shared 28996-token
vocabulary (fingerprint `d480c5ef3e08`) has 8373 capitalised entries.

```
default                'Alzheimer' -> ['al', '##z', '##heimer']
do_lower_case=False    'Alzheimer' -> ['Alzheimer']
```

Every capitalised entry the models were pretrained on was unreachable. Fixed with
a new `EncoderSpec.tokenizer_kwargs` field; `spec.load_tokenizer()` is now the
single construction point, so the override cannot be applied in one script and
forgotten in another.

### The alignment check was structurally blind to it

Broken BioBERT passed `check_alignment.py` at **95.8% exact**. Offsets stay
correct no matter how badly text is tokenized, so span recovery cannot see
tokenization quality at all. Worse, the obvious proxies barely move:

| | broken | fixed |
|---|---|---|
| `[UNK]` rate | 1.57% | 1.55% |
| tokens per word | 1.811 | 1.836 |

Only a direct test catches it: capitals present in the vocabulary while
`do_lower_case=True`. `check_alignment.py` now runs that check, plus UNK-rate and
tokens-per-word bounds, and exits non-zero on any of them.

The UNK threshold is set at 5%, deliberately loose: a general-domain vocabulary
on biomedical text legitimately produces more UNKs, and that penalty is part of
what the domain axis is meant to measure, not a defect to reject.

### Measured tokenizer properties across the grid

Seven distinct vocabularies across the 14 built datasets:

| fingerprint | size | models |
|---|---|---|
| `595e0ac36d19` | 28895 | BioLinkBERT base/large, BiomedBERT-large, BioM-ELECTRA-large, BioELECTRA |
| `54655758a902` | 50280 | Bio-ModernBERT, ModernBERT-bio, ModernBERT, BioClinical-ModernBERT (base) |
| `d480c5ef3e08` | 28996 | BioBERT, Bio_ClinicalBERT |
| `c6e31067b526` | 30522 | BiomedBERT-base |
| `92f70256e884` | 30522 | bert-base-uncased |
| `ce8694c0d5e3` | 31090 | SciBERT |
| `7fbefd3cb7a7` | 50265 | BioMed-RoBERTa |

`bert-base` and `biomedbert-base` are both 30522 tokens and **different
vocabularies** — the exact pairing that produces in-range nonsense rather than an
exception, and the reason the guard compares fingerprints.

### Vocabulary quality costs documents, not just tokens

At a fixed 512-token context, a worse-fitting vocabulary produces more tokens per
document and therefore truncates more gold spans:

| model | tokens/word | spans truncated (of 2817) | exact recovery |
|---|---|---|---|
| BiomedBERT-base | 1.377 | 29 | 95.9% |
| SciBERT | 1.437 | 42 | 95.4% |
| BioMed-RoBERTa | 1.640 | 63 | 94.1% |
| bert-base | 1.694 | 80 | 94.0% |
| BioBERT / Bio_ClinicalBERT | 1.825 | 127 | 92.4% |
| ModernBERT family (8192 ctx) | 1.503 | **0** | 96.3% |

A general-domain tokenizer costs ~4x the truncation of a domain one. This is a
confound to name in any write-up: part of the domain effect measured on a
512-token budget is tokenizer efficiency, not representation quality.

---

## Phase 4b — clean five-encoder grid

**Date completed:** 2026-08-01

**Pipeline snapshot:** `5e7e3f1`

**Design:** 5 encoders × 2 registry learning rates × 3 seeds = 30 cells

The clean grid completed all 30 cells with no failures. The earlier seven-row
partial table is archived under `runs/_precommit/`, and the two reproducibility
replicates remain isolated under `runs/_recheck/`. The retained
`runs/summary.jsonl` has one unique row per cell, all stamped with the same Git
SHA and backed by a canonical `test_results.json` in the ignored run directories.

### Reproduce the results

The result table is generated, not maintained by hand:

```bash
venv310/bin/python3 scripts/aggregate_runs.py
venv310/bin/python3 scripts/aggregate_runs.py --by domain objective arch
venv310/bin/python3 scripts/aggregate_runs.py \
  --compare biomedbert-base bert-base
```

### Findings

- `bioelectra-base` at lr 3e-05 has the highest descriptive mean,
  **0.8156 ± 0.0175** test F1. No paired BioELECTRA-versus-anchor test was
  specified, so this is not a statistically established win.
- The preplanned anchor contrast compares each model's best mean-LR group:
  BiomedBERT 0.8033 versus general BERT 0.7982. The paired document bootstrap
  estimates delta (BERT - BiomedBERT) at **-0.0051**, with 95% CI
  **[-0.0354, +0.0275]** and `P(delta > 0) = 0.382`.
- The interval includes zero and is much wider than the observed difference.
  The encoder-domain contrast is therefore **indistinguishable** on this split.
- Grouping the same runs by domain, pretraining objective or architecture yields
  differences of only a few thousandths. Those summaries are descriptive because
  each axis is confounded with model identity and the run variance is larger than
  the gaps.
- BioClinicalBERT evaluates 108 effective test documents rather than 109 after
  tokenizer-dependent truncation. Only the BiomedBERT/BERT comparison is scored
  as a paired common-document contrast here.

### Interpretation

The grid answered its intended first question: at 860 training documents, the
base-encoder axis is below the current experiment's resolution. This is not a
failed sweep. It is evidence against spending the next block of compute on a
wider ranking at the same data size. The learning-curve design and wave-3 review
are more informative because they test whether supervision, rather than encoder
identity, is the limiting variable.

The fixed-seed rechecks also showed that CUDA nondeterminism plus early stopping
changes the selected trajectory. Reported standard deviations combine seed and
run-to-run variation; a future retrain must never inherit a swept F1 by name.

### Phase 5 handoff

The sweep ran with `--no-save-model`, so it produced no deployable checkpoint.
If Phase 5 chooses the descriptive leader (`bioelectra-base`, lr 3e-05), it must
save a new retrain and treat that concrete artifact and its own evaluation as
authoritative. Alternatively, retaining BiomedBERT preserves continuity without
claiming the grid found a significant improvement. That policy decision belongs
before `models/encoders/` is populated.

---

## Expanded reviewed-data carry-forward

**Prepared:** 2026-08-02

Wave-3 and wave-4 are now fully human-reviewed. Their tracked canonical gold files
contain 2000 documents and 4645 pathway spans; together with wave-2 and pilot batch
05, the available corpus contains 3200 documents, 2887 positive documents and 7462
spans. The detailed wave-3/4 review JSONs remain local audit material, so the final
gold JSONL files are the Git-tracked annotation records.

The historical Phase 4b dataset remains frozen. The expanded snapshot is built
under `data/processed/gold-wave4/`: its 107 validation and 109 test PMIDs are reused
unchanged, and all 1804 new positive wave-3/4 documents are assigned to training.
The five tokenizer-specific validation/test files are byte-identical to their
Phase 4b counterparts, and alignment validation reports zero unexplained span
losses. This isolates the supervision change and keeps every new score comparable
with the completed grid.

The follow-up does not repeat learning-rate selection. It carries forward each
model's best Phase 4b mean-LR group and repeats it at seeds 42, 1 and 7:

| model | carried learning rate | Phase 4b mean F1 |
|---|---:|---:|
| `biomedbert-base` | 3e-05 | 0.8033 |
| `bert-base` | 3e-05 | 0.7982 |
| `bio-clinicalbert` | 5e-05 | 0.8032 |
| `bioelectra-base` | 3e-05 | 0.8156 |
| `bio-modernbert-base` | 8e-05 | 0.8031 |

The resulting 15 cells measure how the previously selected recipes respond to
roughly three times as much positive training supervision. They do not establish
that those learning rates remain optimal on the expanded corpus. The run has not
started: a separate summary namespace and explicit per-model learning-rate and
versioned-data support in `run_matrix.py` are still required first.
