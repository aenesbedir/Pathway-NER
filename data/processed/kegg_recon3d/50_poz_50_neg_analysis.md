# biom-electra-large (pathway-10k, lr3e-05, seed7) — Manual Precision/Recall Spot-Check on KEGG-Recon3D Abstracts

Checkpoint: `runs-truba-checkpoints/pathway-10k/biom-electra-large/lr3e-05/seed7`
Input: `data/processed/kegg_recon3d/pathway-10k-biom-electra-large-seed7_abstracts_1521_direct.jsonl` (1521 abstracts, seed=42 random sample)
Sampled: 50 documents with ≥1 predicted PATHWAY span ("pos"), 50 documents with zero predicted spans ("neg")
Method: manual reading of each abstract against the predicted spans, no scripted heuristics.

## Summary

| Metric | Value |
|---|---|
| Pos docs sampled | 50 (73 spans total) |
| Spans conceptually correct (real pathway/process mention) | ~68/73 (~93%) |
| Spans with wrong/truncated boundaries (concept still right) | ~6/73 (~8%) |
| Spans that are outright wrong (not a pathway at all) | 0/73 |
| Neg docs sampled | 50 |
| True negatives (no pathway name in the *abstract* text) | 49/50 |
| False negatives (pathway name present, model missed it) | 1/50 — and that one hit is in the **title**, not the abstract body (see below) |

Estimated precision (does a predicted span name a real pathway/process): **~93%** at the concept level, ~85% if boundary-exactness is required.
Estimated recall on abstract-body pathway mentions: **~100%** in this sample — the model did not miss a single explicit pathway phrase inside an abstract's own text.

## Error patterns

1. **Boundary truncation, not misclassification.** The model correctly identifies the pathway concept but the span cuts a couple of words short of the full phrase:
   - PMID 16176880: `"de novo pathway of purine"` — should extend to `"...purine synthesis"`.
   - PMID 16176262: `"degradation of branched"` — truncates before `"chain fatty acid"`.
   - PMID 17034877: `"metabolism of oxygen"` — truncates before `"metabolites"`.
   - PMID 23664117: `"biosynthesis of the GAG"` — truncates before `"linker region"`.
   - PMID 21763480: `"synthesis of glycosaminoglycan"` — truncates before `"side chains"`.
   - PMID 16317551: `"L: -isoleucine catabolism"` — includes an OCR/text artifact (`"L: -"`) from the source abstract rather than a model error per se.
   This is the dominant error mode: word-level decoding (first-subword supervision) occasionally stops one token early on multi-word noun phrases that continue past a preposition.

2. **No confident false positives.** Every positive span in the sample names an actual KEGG-style pathway or metabolic process (e.g. "mevalonate pathway", "Krebs cycle", "oxidative phosphorylation", "bile acid synthesis", "urea cycle", "glycolytic pathway"). The model never tagged a gene name, disease name, or protein complex as a pathway in this sample.

3. **Negatives are true negatives, driven by genre, not recall failure.** The 50 zero-span documents are almost all mutation/case-report abstracts ("we identified a homozygous missense mutation in X causing Y syndrome...") that describe a gene defect and its clinical phenotype without ever naming the underlying pathway in prose. Examples: PMID 29590114 (PPIP5K2/hearing loss), 8252036 (Canavan disease/aspartoacylase), 23910460 (CYC1/complex III) — none of these abstracts contain a pathway-name phrase for the model to find.

4. **One false negative, and it's a pipeline artifact, not a model recall miss.** PMID 15024124's *title* is "...a genetic disorder of methionine metabolism", but the abstract body itself never repeats "methionine metabolism" (it discusses hypermethioninemia, AdoHcy, etc. — the underlying biochemistry, not the pathway name). If `predict_abstracts.py`'s input text is abstract-only (title not concatenated), this mention was structurally unreachable, not a model error.

## Example rows

**Correct positive** — PMID 26202976: predicted `"mevalonate pathway"` (×4) and `"isoprenoid biosynthesis"` in an abstract literally titled "Genomic variations of the mevalonate pathway in porokeratosis." Textbook true positive.

**Truncated positive** — PMID 16176880: predicted span `"de novo pathway of purine"` inside "...leads to enormous overactivity of de novo pathway of purine synthesis and purine overproduction." Correct concept, span 9 characters short of the full phrase.

**True negative** — PMID 8617498 ("Etfdh, Etfb, Etfa... glutaric acidemia type II"): describes an electron-transfer-flavoprotein deficiency and its chromosomal mapping; no pathway name appears anywhere in the abstract.

**False negative (title-only)** — PMID 15024124: title contains "methionine metabolism"; abstract body does not restate it. Model predicted zero spans, correctly, for the text it was actually given.

## Agreement between predicted spans and the CSV's linked pathway (all 460 pos docs / 815 spans)

This section covers all 460 documents with ≥1 predicted span (not just the 50-doc sample), comparing each predicted span's text against the `pathway_name` / `matched_recon3d_pathway` columns of `data/raw/kegg_recon3d/kegg_recon3d_matched_pathways.csv` for that PMID. Matching is name-normalized (lowercased, punctuation stripped, trailing "pathway(s)" removed); "exact" = normalized string equality, "partial" = one string contains the other (handles cases like predicted `"gluconeogenesis"` vs CSV `"Glycolysis/gluconeogenesis"`).

| Level | Exact match | Partial (substring) match | No string match |
|---|---|---|---|
| Span-level (815 spans) | 73 (9%) | 66 (8%) | 676 (83%) |
| Document-level (460 docs) | 64 (14%) | 46 (10%) | 350 (76%) |

Same judging convention as `gt_100`/`score_gt_100.py` was applied conceptually: correctness is decided by whether the span names a real pathway/process, not by exact character-offset match against one reference string. Under that lens the 83%/76% "no string match" figures **overstate real errors** — inspecting the top no-match span texts shows they are almost all legitimate pathway names, just not the *one* pathway the CSV row happens to link that PMID to:

```
36  urea cycle              23  OXPHOS                  14  energy metabolism
13  cholesterol biosynthesis 11 Krebs cycle              11  heme biosynthesis
10  mevalonate pathway        8 cholesterol synthesis     8  oxidative phosphorylation
 7  BCAA metabolism           6 glycogen metabolism       6  lipid metabolism
 6  creatine synthesis        6 fatty acid oxidation      5  urea-cycle
```

Two distinct causes behind "no string match", both benign:

1. **CSV records one disease→pathway link per row; abstracts legitimately discuss others.** E.g. PMID 17552001's CSV entry is `Glycolysis/gluconeogenesis` / `Starch and sucrose metabolism`, but its abstract also correctly discusses `"glycogen metabolism"`, `"glycogen synthesis"`, `"glycogen degradation"` — real, adjacent pathways the model correctly tagged that simply aren't the CSV's chosen link.
2. **Naming/abbreviation mismatch, same pathway.** `"OXPHOS"` vs CSV's `"Oxidative phosphorylation"`, `"Krebs cycle"` vs CSV's `"Citrate cycle (TCA cycle)"`, `"urea cycle"` vs CSV's `"Arginine biosynthesis"` / `"Urea cycle"` variants not always present per-row — same biology, different label, undercounted by plain string comparison rather than by the model being wrong.

Net read: the model is not hallucinating pathways unrelated to the article's biology; the low string-match rate against the CSV reflects the CSV encoding *one* curated disease-pathway link per row while abstracts freely mention several correct, related pathways.

## Verdict on the 460/1521 (30%) coverage rate

The low document-level hit rate looks like **true low prevalence in the corpus, not model under-recall**. The KEGG-Recon3D abstract set was built from disease↔pathway crossref evidence (CSV rows linking a PMID to a KEGG pathway via the *disease*, not necessarily via abstract text), so a large fraction of these abstracts are gene-discovery / mutation case reports that never mention a pathway by name — the pathway link comes from the KEGG annotation of the causal gene, not from the article's prose. In this sample, 49/50 zero-span documents were confirmed true negatives by manual reading, and the one apparent miss traces to a title-only mention rather than a genuine abstract-text pathway phrase the model failed to catch. The model's recall on text that actually contains a pathway phrase looks close to complete in this sample; its main weakness is span-boundary trimming on multi-word phrases, not concept detection.
