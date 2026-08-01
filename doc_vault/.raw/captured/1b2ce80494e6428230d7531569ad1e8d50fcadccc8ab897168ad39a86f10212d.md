# Annotation Handoff — Doccano Session

## Goal of this session
Manually review and correct NER annotations in Doccano to improve training data quality for a metabolic pathway NER model.

## Project one-liner
Fine-tune `microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext` to extract metabolic pathway names from biomedical abstracts/full-text. Part of a larger pipeline: pathway NER → disease NER → relation extraction → pathway↔disease database.

**Repo:** `/home/enes/NER-pipeline`  
**Full tracking doc:** `project_tracking.md`

---

## Why annotation work is needed

We trained a baseline NER model (Run 001) and ran error analysis. Results:

| Metric | Value |
|---|---|
| Test F1 | 0.46 |
| Precision | 0.40 |
| Recall | 0.55 |

**Root cause (from `analysis/error_analysis.json`):**
- Many false positives are *legitimate* pathway names (e.g. `"heme synthesis"`, `"cholesterol metabolism"`, `"glycolytic pathway"`) that were simply missed by the distant supervision pipeline — model found them, ground truth didn't label them
- Partial-term false positives: model over-generalizes on pathway name components (`"biosynthesis"`, `"metabolism"`, `"sulfate"`)
- Conclusion: **annotation quality, not hyperparameters, is the bottleneck**

---

## Current data

### Annotation source
All training annotations were produced automatically (no human review):
- **Step 2:** SpaCy PhraseMatcher on KEGG/Reactome names
- **Step 3:** `qwen2.5:7b` via Ollama, verbatim-verified
- **Source 3:** DB dataset spans

### Key files
| File | Description |
|---|---|
| `data/processed/all_matches.jsonl` | 1,662 records; 560 with spans; 704 spans total |
| `data/processed/bio_tags.jsonl` | 597 tokenized+labeled records (BIO format) |
| `data/processed/train.jsonl` | 502 training records |
| `data/processed/val.jsonl` | 44 validation records |
| `data/processed/test.jsonl` | 50 test records |
| `analysis/error_analysis.json` | TP/FP/FN breakdown per test record |

### Record structure in `all_matches.jsonl`
```json
{
  "pmid": "12345678",
  "pathway_ids": ["hsa00010"],
  "source": "kegg",
  "abstract": "Full abstract text...",
  "full_text": "Full paper text or null",
  "spans": [
    {"start": 42, "end": 60, "text": "glycolytic pathway", "source": "abstract"}
  ]
}
```

---

## What to do in Doccano

1. **Export** `all_matches.jsonl` spans into Doccano-compatible format (text + span annotations)
2. **Review** each annotated span — confirm, remove, or correct the label
3. **Add missing annotations** — flag pathway names the pipeline missed (false negatives)
4. **Re-export** corrected annotations back to span format
5. **Re-run** Steps 4–6 (`tag_bio.py` → `build_dataset.py` → `train.py`) with corrected data

### Priority: review test set FPs first
The 41 false positives from error analysis are the highest-leverage items. Their PMIDs are in `analysis/error_analysis.json`.

---

## Venv and model
```bash
# Python environment
/home/enes/sci-usage/venv310/bin/python3

# BiomedBERT tokenizer/model
microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext

# Best trained checkpoint (Run 001)
/home/enes/NER-pipeline/models/pathway-ner/
```

---

## Not in scope for this session
- Re-running the LLM extraction (Step 3) — data already collected
- Hyperparameter tuning — ruled out; annotation quality is the bottleneck
- Disease NER / relation extraction — future steps
