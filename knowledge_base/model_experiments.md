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
