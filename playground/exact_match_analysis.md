# Exact Match Quality Analysis

## Inputs & Related Files

**Analysis inputs:**
- `unique_pathways_from_recon.json` — 98 canonical Recon3D pathways (the label vocabulary)
- `preprocessing/match_exact.py` — matcher config (`RECON_BLOCKLIST`, `RECON_SYNONYMS`)
- `data/processed/exact_matches.jsonl` — matched spans (22,017 records) ← **the file this analysis is about**
- `data/raw/articles.json` — article corpus (10,329 articles, ~236M chars)

**Scripts (reproducible):**
- `playground/phase_2_label_coverage.py` — full-corpus label coverage; `--markdown` emits the tables below
- `playground/phase_2_synonym_candidates.py` — corpus grep for candidate synonyms of zero-match pathways

**Related docs:**
- `pubmed_api/STATS.md` — corpus & pair-search statistics
- `knowledge_base/model_experiments.md` — Run 005 was trained on this exact-match data

---

## Overall Verdict

**~95/100 sampled matches are correct** — the matched text is a genuine pathway name in its proper biochemical sense. The main problems are a small set of Recon3D artifact terms that produce false positives (now blocklisted).

---

## Label Coverage Summary (full corpus, 2026-07-10)

Computed over the entire `exact_matches.jsonl` (not a sample).

| Category | Count |
|---|---|
| Recon3D pathways total | 98 |
| Blocklisted (never enter matcher) | 8 |
| Eligible for matching | 90 |
| **Labeled** (≥1 span) | **82** |
| Unlabeled eligible (zero match) | 8 |
| Labeled pathway_ids outside the 98 Recon names | **0** |

**Every `pathway_id` in `exact_matches.jsonl` is a canonical Recon name.** The pipeline uses only the `recon` source (`match_exact.py`), so no "extra" pathway can appear. Synonyms (e.g. "NAD+ metabolism", "TCA cycle") are folded into their canonical `pathway_id` at match time, so the 82 count is already synonym-deduped — no double counting.

---

## Blocklisted Recon Subsystems (8) — why excluded

These are Recon3D metabolic-**model** subsystem/boundary labels, not pathway names used in the literature. Matching them against free text produces false positives, so `RECON_BLOCKLIST` removes them before the matcher is built.

| Blocklisted term | Reason |
|---|---|
| `miscellaneous` | Generic Recon bucket; matches "miscellaneous neurological disorders", "miscellaneous etiologies" (~510 FP spans in sample). Not a pathway. |
| `protein formation` | Matches "amyloid protein formation", "MDA protein formation". A reaction label, not a metabolic pathway. |
| `intracellular demand` | Recon3D model boundary artifact ("responsive to intracellular demand"). Not literature terminology. |
| `intracellular source/sink` | Recon3D source/sink pseudo-reaction — a modeling node, not a biological pathway. |
| `r group synthesis` | Recon3D model listing artifact ("R Group Synthesis"); appears only in metabolic-model papers. |
| `biomass and maintenance functions` | Recon3D biomass objective / maintenance reaction — a flux-balance modeling construct, not a pathway. |
| `exchange/demand reaction` | Recon3D boundary reaction class — not a metabolic pathway. |
| `dietary fiber binding` | Recon3D pseudo-reaction for dietary uptake — not a pathway. |

---

## Unlabeled Eligible Pathways (8) — corrected analysis

⚠️ **Correction to an earlier note.** A previous version of this document claimed these 8 pathways had "zero PMIDs in corpus — the data simply isn't there." **That is wrong.** Full-corpus grep (`phase_2_synonym_candidates.py`) shows their common surface forms appear in the corpus. The real reason for zero matches is that the **canonical Recon name is never written verbatim** in the literature.

**Synonym validity rule (important).** A synonym may only be added if it **denotes the process** — i.e. it contains `metabolism` / `synthesis` / `biosynthesis` / `oxidation` / `cycle` / `pathway`, or is an established process name (`glycolysis`, `steroidogenesis`, `lipogenesis`, `Warburg effect`). A **bare metabolite/chemical name** (`lipoic acid`, `hippurate`, `squalene`) is a **Chemical entity, not a Pathway entity** — labeling it as `Pathway` is a type error that teaches the model to tag every metabolite as a pathway and destroys precision. Every existing `RECON_SYNONYMS` entry already obeys this rule (note it is `nicotinamide metabolism`, not bare `nicotinamide`).

Applying that rule, the recoverability picture changes: only pathways whose **process forms** are common are recoverable.

| Unlabeled pathway | Process-form synonyms in corpus (valid) | Bare chemical forms (NOT usable) | Verdict |
|---|---|---|---|
| `androgen and estrogen synthesis and metabolism` | "steroidogenesis" ×237, "steroid biosynthesis" ×188, "estrogen metabolism" ×52, "androgen metabolism" ×19 | — | ✅ Recoverable |
| `squalene and cholesterol synthesis` | "sterol synthesis" ×1580, "cholesterol biosynthesis" ×982, "mevalonate pathway" ×215 | "squalene" ×206 | ✅ Recoverable (avoid bare "cholesterol synthesis" — overlaps `cholesterol metabolism`) |
| `lipoate metabolism` | "lipoic acid metabolism" ×14, "lipoic acid biosynthesis" ×4 | "lipoic acid" ×177 | ⚠️ Marginal — process form too rare to be worth it |
| `hippurate metabolism` | "hippurate metabolism" ×1 | "hippurate" ×128, "hippuric acid" ×125 | ❌ Leave — only the chemical form is common |
| `n-glycan metabolism` | "n-glycosylation" ×130 | "n-glycan" ×212 | ⚠️ Risky — separate `n-glycan synthesis`/`degradation` exist; umbrella term |
| `phosphatidylinositol phosphate metabolism` | — | "pi3k" ×3564, "phosphatidylinositol" ×776 | ❌ No — "PI3K" is signaling, high FP risk |
| `blood group synthesis` | — | "abo blood group" ×1 | ❌ No — genuinely absent |
| `keratan sulfate synthesis` | "keratan sulfate biosynthesis" ×1 | — | ❌ No — genuinely absent |

**Bottom line:** only **2 of the 8** (`androgen and estrogen synthesis and metabolism`, `squalene and cholesterol synthesis`) can be cleanly recovered with process-denoting synonyms. The rest stay unlabeled — either the only common surface form is a bare chemical (which must not be labeled as a pathway), the term is too ambiguous, or it is genuinely absent.

---

## Full Labeled Pathway Table (82)

Sorted by span count. Generated by `phase_2_label_coverage.py --markdown`.

<details>
<summary>All 82 labeled pathways (span / PMID counts)</summary>

| spans | PMIDs | pathway |
|---|---|---|
| 13,671 | 2265 | glycolysis/gluconeogenesis |
| 9,705 | 1939 | oxidative phosphorylation |
| 5,651 | 1453 | citric acid cycle |
| 5,512 | 1568 | fatty acid oxidation |
| 4,655 | 1263 | fatty acid synthesis |
| 2,918 | 818 | cholesterol metabolism |
| 2,269 | 623 | sphingolipid metabolism |
| 2,268 | 622 | tryptophan metabolism |
| 2,121 | 572 | urea cycle |
| 1,622 | 489 | bile acid synthesis |
| 1,522 | 713 | pentose phosphate pathway |
| 1,488 | 480 | glycerophospholipid metabolism |
| 1,371 | 525 | glutathione metabolism |
| 1,327 | 595 | drug metabolism |
| 1,306 | 467 | nucleotide metabolism |
| 1,207 | 522 | glutamate metabolism |
| 1,135 | 361 | folate metabolism |
| 1,004 | 462 | arachidonic acid metabolism |
| 932 | 353 | pyruvate metabolism |
| 916 | 277 | nad metabolism |
| 855 | 246 | purine synthesis |
| 776 | 206 | pyrimidine synthesis |
| 732 | 257 | vitamin d metabolism |
| 690 | 294 | arginine and proline metabolism |
| 626 | 271 | tyrosine metabolism |
| 561 | 172 | histidine metabolism |
| 547 | 220 | phenylalanine metabolism |
| 510 | 154 | heme synthesis |
| 375 | 165 | galactose metabolism |
| 315 | 96 | vitamin b6 metabolism |
| 300 | 111 | glyoxylate and dicarboxylate metabolism |
| 288 | 188 | steroid metabolism |
| 268 | 121 | butanoate metabolism |
| 263 | 112 | heme degradation |
| 248 | 90 | propanoate metabolism |
| 238 | 98 | purine catabolism |
| 234 | 60 | lysine metabolism |
| 217 | 120 | starch and sucrose metabolism |
| 209 | 60 | vitamin a metabolism |
| 207 | 107 | taurine and hypotaurine metabolism |
| 201 | 84 | inositol phosphate metabolism |
| 190 | 92 | nucleotide sugar metabolism |
| 173 | 83 | beta-alanine metabolism |
| 159 | 80 | eicosanoid metabolism |
| 150 | 73 | ros detoxification |
| 146 | 75 | fructose and mannose metabolism |
| 143 | 96 | glycosphingolipid metabolism |
| 131 | 57 | thiamine metabolism |
| 88 | 48 | vitamin b12 metabolism |
| 86 | 66 | triacylglycerol synthesis |
| 81 | 35 | biotin metabolism |
| 71 | 42 | vitamin b2 metabolism |
| 65 | 24 | coa synthesis |
| 45 | 21 | hyaluronan metabolism |
| 34 | 30 | peptide metabolism |
| 30 | 19 | nucleotide salvage pathway |
| 29 | 14 | heparan sulfate degradation |
| 27 | 3 | nucleotide interconversion |
| 21 | 11 | pyrimidine catabolism |
| 20 | 10 | vitamin e metabolism |
| 15 | 5 | n-glycan degradation |
| 14 | 10 | leukotriene metabolism |
| 13 | 9 | c5-branched dibasic acid metabolism |
| 12 | 7 | alanine and aspartate metabolism |
| 11 | 10 | vitamin c metabolism |
| 11 | 6 | linoleate metabolism |
| 9 | 6 | ubiquinone synthesis |
| 9 | 5 | chondroitin sulfate degradation |
| 8 | 6 | tetrahydrobiopterin metabolism |
| 8 | 1 | o-glycan metabolism |
| 6 | 5 | d-alanine metabolism |
| 5 | 5 | valine, leucine, and isoleucine metabolism |
| 4 | 4 | glycine, serine, alanine, and threonine metabolism |
| 4 | 4 | aminosugar metabolism |
| 4 | 3 | n-glycan synthesis |
| 4 | 3 | cytochrome metabolism |
| 3 | 1 | keratan sulfate degradation |
| 3 | 2 | methionine and cysteine metabolism |
| 1 | 1 | limonene and pinene degradation |
| 1 | 1 | alkaloid synthesis |
| 1 | 1 | coa catabolism |
| 1 | 1 | chondroitin synthesis |

</details>

---

## Synonym Surface Forms (surface → canonical)

Which matched texts differ from the canonical `pathway_id`. Format: `surface form (canonical pathway)`. Case variants folded. These are the spans recovered thanks to `RECON_SYNONYMS`.

<details>
<summary>Synonym surface forms and their span counts</summary>

| matched surface form (canonical pathway) | spans |
|---|---|
| glycolysis (glycolysis/gluconeogenesis) | 10,481 |
| OXPHOS (oxidative phosphorylation) | 4,266 |
| TCA cycle (citric acid cycle) | 3,937 |
| gluconeogenesis (glycolysis/gluconeogenesis) | 1,696 |
| lipogenesis (fatty acid synthesis) | 1,530 |
| β-oxidation (fatty acid oxidation) | 1,495 |
| Warburg effect (glycolysis/gluconeogenesis) | 968 |
| electron transport chain (oxidative phosphorylation) | 918 |
| de novo lipogenesis (fatty acid synthesis) | 719 |
| fatty acid β-oxidation (fatty acid oxidation) | 534 |
| tricarboxylic acid cycle (citric acid cycle) | 507 |
| fatty acid biosynthesis (fatty acid synthesis) | 484 |
| NAD+ metabolism (nad metabolism) | 442 |
| Krebs cycle (citric acid cycle) | 351 |
| beta-oxidation (fatty acid oxidation) | 278 |
| primary bile acid biosynthesis (bile acid synthesis) | 244 |
| nicotinamide metabolism (nad metabolism) | 235 |
| bile acid biosynthesis (bile acid synthesis) | 181 |
| bile acid production (bile acid synthesis) | 95 |
| fatty acid beta-oxidation (fatty acid oxidation) | 83 |
| riboflavin metabolism (vitamin b2 metabolism) | 71 |
| pentose phosphate shunt (pentose phosphate pathway) | 15 |
| hexose monophosphate shunt (pentose phosphate pathway) | 7 |
| NADH metabolism (nad metabolism) | 4 |
| keratan-sulfate degradation (keratan sulfate degradation) | 3 |

</details>

---

## Sample-Based Notes (100 records, seed=42 & 99, 2026-07-07)

Point-in-time manual review of 100 randomly sampled records. `drug metabolism` (1,327 spans total) is borderline — most spans are legitimate (cytochrome P450, hepatic drug metabolism) but a few match instrument/method contexts ("drug metabolism research"). Kept but worth monitoring.

Many papers report **KEGG pathway enrichment** results whose pathway names overlap with Recon names (e.g. "arginine and proline metabolism", "pentose phosphate pathway"). These are legitimate mentions but appear in statistical output lists rather than narrative text — lower-signal training examples.

---

## Expected vs. Found Pathway Comparison

*Compared `pathway_disease_pairs.json` (expected, per PMID) vs `exact_matches.jsonl` (found, per PMID).*

| Category | PMIDs | Pathway hits |
|---|---|---|
| Expected pathway found in text | 9,038 (87.5%) | 9,908 |
| Extra pathways found beyond expected | 3,021 | 6,597 |
| Expected pathway absent from text (missed) | 1,370 (13.3%) | 1,406 |

→ **87.5% of articles contain their expected pathway name in the text** — strong recall for exact matching. "Extra pathways found beyond expected" are still Recon pathways (just not the one the article was fetched for); they add label diversity, not errors.

### Top 10 Most-Missed Expected Pathways

| Pathway | Miss count | Likely reason |
|---|---|---|
| nad metabolism | 137 | Papers write "NAD+", "NADH", "nicotinamide" |
| tryptophan metabolism | 87 | Uses "kynurenine pathway", "serotonin pathway" |
| drug metabolism | 86 | Uses "CYP450", "hepatic clearance", "pharmacokinetics" |
| cholesterol metabolism | 64 | Uses "lipid metabolism", "dyslipidemia" |
| arachidonic acid metabolism | 61 | Uses "eicosanoid", "AA pathway", "prostaglandin synthesis" |
| glycolysis/gluconeogenesis | 61 | Papers write "glycolysis"/"Warburg effect" separately |
| miscellaneous | 58 | Correct to miss — Recon artifact |
| fatty acid oxidation | 58 | Uses "FAO", "beta-oxidation", "β-oxidation" |
| glutathione metabolism | 48 | Uses "GSH", "oxidative stress", "antioxidant pathway" |
| coa synthesis | 42 | Very niche, rarely named directly |

---

## Recommended Actions

### Applied (in `match_exact.py`)
- **Blocklist (8 terms)** — removes Recon model-artifact false positives.
- **`RECON_SYNONYMS`** — abbreviation/variant coverage for 10 pathways (TCA, glycolysis, OXPHOS, PPP, FAO, FAS, bile acid, NAD, keratan-sulfate degradation, riboflavin). These recover tens of thousands of spans (see synonym table).

### Pending (new candidates from this analysis)
Add **process-denoting** synonyms to recover 2 currently-unlabeled pathways:
```python
"androgen and estrogen synthesis and metabolism": [
    "steroidogenesis", "steroid biosynthesis",
    "androgen metabolism", "estrogen metabolism",
    "androgen synthesis", "estrogen synthesis",
],
"squalene and cholesterol synthesis": [
    "cholesterol biosynthesis", "sterol synthesis",
    "sterol biosynthesis", "mevalonate pathway",
],
```
Do **not** add:
- Bare chemical/metabolite names — `lipoic acid`, `hippurate`, `hippuric acid`, `squalene` — these are Chemical entities, not Pathway entities (violates the synonym validity rule above).
- `cholesterol synthesis` bare — overlaps the separate `cholesterol metabolism` pathway.
- `pi3k` / `phosphatidylinositol` — signaling terms, high false-positive risk.
- bare `n-glycan` — overlaps `n-glycan synthesis` / `n-glycan degradation`.

`lipoate metabolism` and `hippurate metabolism` cannot be recovered without labeling bare chemical names, so they remain unlabeled.
