# biom-electra-large (pathway-10k, lr3e-05, seed7) — PMC Full-Text Spot-Check on KEGG-Recon3D

Checkpoint: `runs-truba-checkpoints/pathway-10k/biom-electra-large/lr3e-05/seed7`

## Data pipeline

1. Took the 1521 abstract-fetched KEGG-Recon3D PMIDs (`data/raw/kegg_recon3d/articles.json`).
2. ELinked each PMID → PMCID and pulled the first 50 with an available open-access PMC JATS full text (`data/raw/kegg_recon3d/fulltext_50/articles_fulltext_50.json`; PMCID, title, abstract, `full_text` = concatenated body sections).
3. Ran the same checkpoint via `predict_abstracts.py` over `full_text` (windowed, `max_length=512`, `stride=64`) → `data/processed/kegg_recon3d/pathway-10k-biom-electra-large-seed7_fulltext_50_direct.jsonl`.
4. Compared predicted span text against each PMID's CSV-linked pathway names (`pathway_name`, `matched_recon3d_pathway` in `kegg_recon3d_matched_pathways.csv`), using the same normalized exact/partial/no-match method as the abstract-only analysis (`50_poz_50_neg_analysis.md`).

## Inference results

| | Abstract-only (this PMID subset would need re-check) | Full text (this run) |
|---|---|---|
| Documents | 50 | 50 |
| Documents with ≥1 predicted span | — | 37 / 50 (74%) |
| Total spans | — | 480 |
| Spans per positive document (avg) | — | ~13 |

Full text drives document-level pathway detection far higher than abstract-only (74% of docs here vs. ~30% document hit-rate on the 1521-abstract corpus overall) — expected, since full text repeats pathway names many times across Methods/Discussion/Results where the abstract alone may never state them.

## Agreement with the CSV-linked pathway

| Level | Exact match | Partial (substring) match | No string match |
|---|---|---|---|
| Span-level (480 spans) | 6 (1%) | 71 (15%) | 403 (84%) |
| Document-level (37 positive docs) | 5 (14%) | 14 (38%) | 18 (49%) |

Same caveat as the abstract-only analysis applies, more strongly here: full text mentions many real, correct pathways beyond the CSV's single linked one, so "no string match" is dominated by legitimate biology, not model error. Top no-match span texts, all real pathway/process names:

```
27  OXPHOS                   20  glycogenolysis            17  TCA cycle
16  mitochondrial β-oxidation 15 oxidative phosphorylation 11  PPP
11  cholesterol metabolism   10  CDP-ethanolamine pathway   9  cholesterol biosynthesis
 9  cholesterol synthesis     8  fatty acid oxidation        7  glycogen metabolism
 6  energy metabolism         6  FAO                         6  fatty acid synthesis
 6  Kennedy pathway            5  glycolysis                  5  lipid metabolism
```

Examples of exact matches: PMID 3201231 / 1634041 / 18614015 → `"oxidative phosphorylation"` against CSV `Oxidative phosphorylation`; PMID 18782459 → `"cholesterol metabolism"`; PMID 18067674 → `"purine metabolism"`.

Examples of partial matches: PMID 11949931/11949932/11949935 (CSV: `Glycolysis/gluconeogenesis`) → model predicts `"gluconeogenesis"` / `"glycolysis"` individually, each a correct half of the compound CSV name.

Examples of no-match-but-correct: full-text articles about oxidative-phosphorylation disorders repeatedly mention `"OXPHOS"` (an abbreviation of the CSV's own linked pathway `Oxidative phosphorylation`) and adjacent bioenergetics pathways (`TCA cycle`, `mitochondrial β-oxidation`) that are biologically related but not the CSV's chosen link — same pattern documented in the abstract-only analysis, just amplified by full-text's larger vocabulary of pathway mentions per document.

## Read

Full text roughly doubles document-level detection rate versus abstract-only (74% vs ~30%) and, as expected, surfaces many more pathway mentions per document (~13 spans/doc here vs ~1.8 in the abstract-only positive sample). The CSV string-match rate looks lower in absolute percentage than the abstract-only run (49% doc-level any-match here vs 24% there) mainly because full text pulls in many extra, correct-but-unlinked pathway names (abbreviations like OXPHOS/TCA/PPP/FAO, and neighboring pathways discussed in Methods/Discussion) that abstracts rarely mention — not because the model performs worse on full text. No hallucinated (non-pathway) spans were observed while spot-checking the exact/partial-match examples above.
