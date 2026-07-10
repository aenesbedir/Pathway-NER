# Run 005 vs Curated Ground Truth

Compares the **Run 005** pathway-NER model against the curated Excel
**"Pathway-Disease Relationship Example Data.xlsx"** (treated as ground truth).

## TL;DR

| Metric | Value | Meaning |
|---|---|---|
| GT pathway–article associations (in-scope) | 87 | pathway ↔ evidence-article links, mapped to Recon pathways |
| …of which the pathway is **named in the article text** | **4** | the only ones a name-based NER model could possibly detect |
| Model detected (of those 4) | **4** | **recall vs named-in-text = 100%** |
| Recall vs *all* GT | 4.6% | **misleading** — see below |
| Detected surface forms hallucinated (not in text) | 0 / 96 | every model detection genuinely appears in the text |

**Key finding:** the ground truth is **not** a per-article pathway annotation.
It is a per-Recon-pathway **evidence bibliography** — each pathway is linked to
one supporting article, and a handful of broad **genome-scale metabolic-model /
omics papers** (e.g. *Pan-Cancer genome-scale metabolic network analysis*,
PMID 39001365) are cited as blanket evidence for 13–16 pathways each. Those
Recon **subsystem labels never appear as prose** in the articles, so **83 of 87**
associations are undetectable by any name-based NER. When a pathway *is* written
by name (4 cases), the model detected it every time.

The model also correctly detected the pathways that *are* named in these papers
(glycolysis, oxidative phosphorylation, TCA, pentose phosphate pathway, fatty
acid biosynthesis, …) — they simply aren't the specific subsystem labels the
Excel assigned to that article, so they show up as "extra" rather than "matched".

## Files

- `build_ground_truth.py` — parse the Excel → per-article GT pathway set; resolve PMC→PMID; fetch abstract + full text from NCBI
- `ground_truth_articles.json` — 21 unique articles with GT pathways + fetched text
- `compare_model.py` — run Run 005, map detections to Recon pathways, compare
- `model_005_vs_ground_truth.json` — per-article results + summary

## How the ground truth was parsed

The Excel's columns 5–6 hold entries like
`"Alanine and aspartate metabolism — https://pmc.ncbi.nlm.nih.gov/articles/PMC11240338/"`.
These are inverted to `article → {pathways it is evidence for}`. Pathway names
are normalized to the 98 Recon canonical names (with a small manual override map
for slash/ampersand variants). Names that are **not** Recon metabolic pathways
are excluded from the in-scope GT:
- **Transport subsystems** (`Transport, mitochondrial`, …) — not in the 98 pathways
- **Blocklisted Recon artifacts** (`miscellaneous`, `biomass and maintenance functions`, `exchange/demand reaction`, …) — model is designed never to detect them

22 article references merged into **21 unique articles** (one PMC and one PMID
ref were the same paper).

## Method

- **Fetch:** PMC→PMID via NCBI ID converter; abstract via EFetch (PubMed);
  full text via EFetch (PMC, `<body>` paragraphs).
- **Model:** `models/pathway-ner-005/`, run on `abstract + full_text` with the
  sliding-window / word-level reconstruction from
  `playground/model_005_analysis/predict_abstracts.py`.
- **Detection → pathway:** each detected span's lowercased text is mapped to a
  Recon canonical pathway via the same vocabulary as `match_exact.py`
  (canonical names + `RECON_SYNONYMS`).
- **`gt_present_in_text`:** GT pathways whose canonical name or a synonym
  literally appears in the text — the subset a name-based model could detect.
- **`recall_vs_named_gt`** (= matched / named) is the honest model metric;
  **`recall_vs_all_gt`** is reported only to show the blanket-citation drag.

## Caveats

- The "named-in-text" subset is tiny (**n = 4**), so 100% is illustrative, not
  statistically robust.
- Precision against this GT is not computed: the GT is a per-pathway
  bibliography, not an exhaustive per-article annotation, so a detected pathway
  outside the GT set is an "extra", not necessarily an error (all extras were
  verified to genuinely appear in the text).
- This exposes a **task-definition gap**: the model recognizes pathways *named*
  in text, whereas this ground truth encodes *pathway-disease relationships*
  supported by evidence — which often require reading tables/figures or
  reasoning over metabolites, not just surface-name matching.

## Reproduce

```bash
# from repo root, with the venv that has torch + transformers + openpyxl
VENV=/home/enes/sci-usage/venv310/bin/python3
$VENV playground/model_005_ground_truth_compare/build_ground_truth.py
$VENV playground/model_005_ground_truth_compare/compare_model.py
```

## Related

- `knowledge_base/model_experiments.md` — Run 005 training
- `playground/model_005_analysis/` — Run 005 predictions on the abstract DB
- `playground/exact_match_analysis.md` — training-label / Recon-vocabulary analysis
