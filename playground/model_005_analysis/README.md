# Run 005 — Abstract Prediction Analysis

Applies the **Run 005** pathway-NER model to a held-out set of abstracts and
records, per PMID, every pathway span the model detected with its character
offsets.

## Files

- `predict_abstracts.py` — inference script (sliding-window, word-level span reconstruction)
- `model_005_abstract_predictions.json` — output (450 records)

## Input / Output

**Input:** `data/raw/extracted_disease_pathway_db_disease_pathway_just_abstracts.json`
(450 records: disease, expected pathway, abstract, pmid, mesh_descriptors)

**Model:** `models/pathway-ner-005/` — see `knowledge_base/model_experiments.md`

**Output record shape:**
```json
{
  "pmid": "35713123",
  "disease": "Breast Cancer",
  "expected_pathway": "Taurine and hypotaurine metabolism",
  "num_detected": 7,
  "detected_pathways": [
    {"start": 2633, "end": 2667, "text": "taurine and hypotaurine metabolism"}
  ]
}
```
`detected_pathways` are the character spans (into the abstract) the model
tagged as `Pathway`. Note the model is a binary B/I/O pathway tagger — it does
not classify which of the 98 Recon pathways a span is; `expected_pathway` is
carried over from the input only for comparison.

## Method notes

- **Sliding window** (`max_length=512`, `stride=64`, overflow) so long
  abstracts (34/450 exceed 512 tokens) lose no spans to truncation.
- **Word-level span reconstruction**: subword tokens are collapsed to whole
  words (each word takes its first subword's predicted label, matching how
  training assigned labels) so a span can never break mid-word. This fixes the
  known subword artifact (e.g. `glycer` + `ophospholipid metabolism` →
  `glycerophospholipid metabolism`).
- Spans fully contained in a longer span are dropped (`keep_longest`).

## Summary (this run)

| Metric | Value |
|---|---|
| Records | 450 |
| Records with ≥1 detected span | 270 (60.0%) |
| Records with zero spans | 180 |
| Total spans | 514 |
| Avg spans / record | 1.14 |
| Max spans in one record | 11 |

**Top detected surface forms:** glycolysis (42), oxidative phosphorylation
(21), pentose phosphate pathway (16), folate metabolism (15), arginine and
proline metabolism (14), sphingolipid metabolism (14), glycerophospholipid
metabolism (14), pyruvate metabolism (14).

## Reproduce

```bash
# from repo root, with the training venv
<venv>/bin/python3 playground/model_005_analysis/predict_abstracts.py
```

## Related

- `knowledge_base/model_experiments.md` — Run 005 training results
- `playground/exact_match_analysis.md` — analysis of the training labels
