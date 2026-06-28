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
