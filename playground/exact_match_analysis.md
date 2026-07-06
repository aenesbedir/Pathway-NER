# Exact Match Quality Analysis

**Script:** `preprocessing/match_exact.py --sources recon`  
**Sample:** 100 randomly selected records (two batches, seed=42 and seed=99)  
**Date:** 2026-07-07

---

## Correction to Earlier Note

A previous note mentioned "KEGG enrichment list context." This was imprecise. We are **not** using KEGG as a source. What was observed is that many papers report KEGG pathway enrichment analysis results, and those results happen to list pathway names that overlap with our Recon names (e.g. "arginine and proline metabolism", "pentose phosphate pathway"). These are legitimate pathway name mentions — the terminology is shared between KEGG and Recon — but they appear in statistical output lists rather than narrative text, making them lower-signal training examples.

---

## Overall Verdict

**~95/100 matches are correct** — the matched text is a genuine pathway name in its proper biochemical sense. The main problems are a small set of Recon3D artifact terms that produce false positives.

---

## Problematic Terms (Blocklist Candidates)

From 100 sampled records, confirmed false positive patterns:

| Pathway name | Span count | Why it's wrong |
|---|---|---|
| `miscellaneous` | 510 | Matches "miscellaneous neurological disorders", "miscellaneous etiologies" — not a pathway |
| `protein formation` | 58 | Matches "amyloid protein formation", "MDA protein formation" — not a metabolic pathway |
| `intracellular demand` | 1 | Matches "responsive to intracellular demand" — Recon3D model artifact |
| `r group synthesis` | 1 | Matches "R Group Synthesis" in a metabolic model paper listing — Recon artifact |
| `biomass and maintenance functions` | ~5 | Appears only in papers discussing metabolic models directly |
| `drug metabolism` | 595 | Mostly correct but also matches "drug metabolism research" (instrument methods) |

These 5 terms (`miscellaneous`, `protein formation`, `intracellular demand`, `r group synthesis`, `biomass and maintenance functions`) should be added to a blocklist in `load_recon()`.

`drug metabolism` is borderline — most of its 595 spans are in legitimate pathway contexts (cytochrome P450, hepatic drug metabolism). Keep but monitor.

---

## Pathways with Zero Matches (13/98)

Root cause analysis: three distinct failure modes.

### Cause 1 — Zero PMIDs in corpus (11/13)

These pathways returned **zero PubMed search hits** during pair fetch, so no articles for them exist in our corpus. No synonym expansion can help here — the data simply isn't there.

Sub-group A — Recon3D model artifacts (already in blocklist):
```
dietary fiber binding
exchange/demand reaction
intracellular source/sink
```

Sub-group B — Niche pathways with insufficient literature coverage:
```
androgen and estrogen synthesis and metabolism
blood group synthesis
hippurate metabolism
keratan sulfate synthesis
lipoate metabolism
n-glycan metabolism
phosphatidylinositol phosphate metabolism
squalene and cholesterol synthesis
vitamin b2 metabolism   (2 PMIDs, but see Cause 3)
```

### Cause 2 — Hyphenated variant in text (1/13): `keratan sulfate degradation`

1 article exists (PMID=31668688). The text reads:
```
"heparan-, chondroitin-, keratan-sulfate degradation"
```
SpaCy tokenizes `keratan-sulfate` as a single token, breaking the three-word phrase match.  
**Fix:** add synonym `"keratan-sulfate degradation"`.

### Cause 3 — Parenthesis breaks phrase (1/13): `vitamin b2 metabolism`

2 articles exist:
- PMID=13415135: 1954 article — no abstract or full text retrieved (too old for PMC/PubMed XML)
- PMID=29298833: Text reads `"riboflavin (vitamin B2) metabolism"` — the closing parenthesis `)` is tokenized between `B2` and `metabolism`, so the three-token phrase never matches.

**Fix:** add synonym `"riboflavin metabolism"`.

### Summary

| Pathway | PMIDs | Fix |
|---|---|---|
| 8 niche pathways | 0 | None possible — no data |
| 3 Recon artifacts | 0 | Add to blocklist |
| keratan sulfate degradation | 1 | Add hyphen synonym |
| vitamin b2 metabolism | 2 (no text / broken phrase) | Add riboflavin synonym |

---

## Expected vs. Found Pathway Comparison

*Agent analysis: compared `pathway_disease_pairs.json` (expected) vs `exact_matches.jsonl` (found) per PMID.*

### Aggregate Stats

| Category | PMIDs | Pathway hits |
|---|---|---|
| Expected pathway found in text (exact_match) | 9,038 (87.5%) | 9,908 |
| Extra pathways found beyond expected | 3,021 | 6,597 |
| Expected pathway absent from text (missed) | 1,370 (13.3%) | 1,406 |

→ **87.5% of articles contain their expected pathway name in the text.** This is strong recall for an exact-match approach.

### Top 10 Most-Missed Expected Pathways

| Pathway | Miss count | Likely reason |
|---|---|---|
| nad metabolism | 137 | Papers write "NAD+", "NADH", "nicotinamide" — not the full name |
| tryptophan metabolism | 87 | Uses "kynurenine pathway", "serotonin pathway" instead |
| drug metabolism | 86 | Papers use "CYP450", "hepatic clearance", "pharmacokinetics" |
| cholesterol metabolism | 64 | Uses "lipid metabolism", "dyslipidemia" |
| arachidonic acid metabolism | 61 | Uses "eicosanoid", "AA pathway", "prostaglandin synthesis" |
| glycolysis/gluconeogenesis | 61 | Papers write "glycolysis" or "Warburg effect" separately |
| miscellaneous | 58 | Correct to miss — this is a Recon artifact |
| fatty acid oxidation | 58 | Uses "FAO", "beta-oxidation", "β-oxidation" |
| glutathione metabolism | 48 | Uses "GSH", "oxidative stress", "antioxidant pathway" |
| coa synthesis | 42 | Very niche, rarely named directly |

### Top 10 Most Extra-Found Pathways

| Pathway | Extra count | Note |
|---|---|---|
| oxidative phosphorylation | 996 | Extremely common term in metabolic disease papers |
| fatty acid oxidation | 678 | Common across lipid-related diseases |
| fatty acid synthesis | 365 | Common across cancer/metabolic papers |
| pentose phosphate pathway | 319 | Common in metabolomics studies |
| cholesterol metabolism | 306 | Ubiquitous in metabolic disease |
| tryptophan metabolism | 250 | Common in neurological and gut microbiome papers |
| glutamate metabolism | 216 | Common in neurological papers |
| glutathione metabolism | 198 | Common in oxidative stress papers |
| glycerophospholipid metabolism | 197 | Common in lipidomics |
| nucleotide metabolism | 191 | Common in cancer/proliferation papers |

Extra-found pathways are **not errors** — they are genuine pathway mentions in articles that were retrieved for a different reason. They add label diversity to the training set.

---

## Summary of Recommended Actions

### Priority 1 — Add blocklist to `load_recon()`

```python
RECON_BLOCKLIST = {
    "miscellaneous",
    "protein formation",
    "intracellular demand",
    "intracellular source/sink",
    "r group synthesis",
    "biomass and maintenance functions",
    "exchange/demand reaction",
    "dietary fiber binding",
}
```

This removes ~570 false positive spans with minimal recall cost.

### Priority 2 — Add abbreviation synonyms for high-miss pathways

```python
RECON_SYNONYMS = {
    "nad metabolism":              ["NAD+ metabolism", "NADH metabolism", "nicotinamide metabolism"],
    "glycolysis/gluconeogenesis":  ["glycolysis", "gluconeogenesis", "Warburg effect"],
    "fatty acid oxidation":        ["beta-oxidation", "β-oxidation", "FAO"],
    "oxidative phosphorylation":   ["OXPHOS", "electron transport chain"],
    "pentose phosphate pathway":   ["PPP", "hexose monophosphate shunt"],
    "citric acid cycle":           ["TCA cycle", "tricarboxylic acid cycle", "Krebs cycle"],
    "fatty acid synthesis":        ["de novo lipogenesis", "DNL", "fatty acid biosynthesis"],
    "bile acid synthesis":         ["bile acid biosynthesis", "primary bile acid biosynthesis"],
}
```

### Priority 3 (optional) — Flag list-context spans

Spans preceded/followed by another pathway name within 80 chars are likely in a KEGG enrichment table. Tag with `"context": "list"` for downstream filtering.
