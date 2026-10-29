# `opus_prediction` vs. biom-electra-large vs. KEGG CSV — 50 PMC Full Texts

Three-way comparison on the same 50 open-access PMC full texts used in `fulltext_50_analysis.md`.

| Source | What it is | File |
|---|---|---|
| `opus_prediction` | LLM annotator (Opus) reading each full text end-to-end and listing distinct pathway surface forms | `data/processed/kegg_recon3d/opus_prediction_fulltext_50.jsonl` |
| model | `runs-truba-checkpoints/pathway-10k/biom-electra-large/lr3e-05/seed7`, windowed inference (`max_length=512`, `stride=64`) | `data/processed/kegg_recon3d/pathway-10k-biom-electra-large-seed7_fulltext_50_direct.jsonl` |
| CSV | curated KEGG–Recon3D disease→pathway link for that PMID | `data/raw/kegg_recon3d/kegg_recon3d_matched_pathways.csv` |

Method: the 50 articles were split into 10 balanced chunks and annotated by 10 parallel Opus agents, each instructed to read its 5 articles in full (no grep-substitution) and emit distinct pathway surface forms with mention counts, using the same PATHWAY entity definition the model was trained on (metabolic/signaling pathway names, including abbreviations; excluding gene, protein, enzyme, and disease names). Comparison uses the same normalization as the earlier reports: lowercase, punctuation stripped, trailing `pathway(s)` removed; "partial" = one normalized string contains the other.

## Volume

| | `opus_prediction` | model |
|---|---|---|
| Documents with ≥1 pathway | 43 / 50 (86%) | 37 / 50 (74%) |
| Distinct pathway surface forms | 391 | 238 (from 480 raw spans) |
| Total mentions | 942 | 480 |

## `opus_prediction` vs. CSV

| Level | Exact | Partial | No string match |
|---|---|---|---|
| Surface-form level (391) | 5 (1%) | 17 (4%) | 369 (94%) |
| Document level (43 positive docs) | 5 (12%) | 15 (35%) | 23 (53%) |

Nearly identical to the model's CSV agreement (model: 1% / 15% / 84% at span level, 14% / 38% / 49% at doc level). Both annotators diverge from the CSV in the same way and for the same reason documented in `fulltext_50_analysis.md`: the CSV encodes one curated disease→pathway link per row, while a full text legitimately names many other real pathways. The CSV is therefore not a usable ceiling for either — it measures link coverage, not annotation quality.

## `opus_prediction` vs. model — the informative comparison

Distinct normalized names per document, set-compared:

| | Count |
|---|---|
| Agreed (both found) | 173 |
| `opus_prediction` only | 210 |
| model only | 65 |
| Overlap (Jaccard) | 0.386 |
| Doc-level positive/negative agreement | 44 / 50 |

**Agreed core** — the canonical KEGG-style names both find reliably:

```
10 lipid metabolism      9 oxidative phosphorylation   7 OXPHOS
 5 glycolysis            4 glycogenolysis              4 gluconeogenesis
 3 fatty acid metabolism 3 fatty acid oxidation        3 glycogen metabolism
 3 Krebs cycle           3 citric acid cycle           3 TCA cycle
 3 cholesterol biosynthesis  3 cholesterol metabolism   2 FAO
```

**`opus_prediction` only (210)** — dominated by two categories the model systematically does not tag:

```
9 respiratory chain              6 electron transport chain   5 mitochondrial respiratory chain
4 nonsense-mediated decay        3 mitophagy                  3 mitochondrial biogenesis
3 intermediary metabolism        3 proteasomal degradation     3 ERAD
2 N-linked glycosylation         2 carbohydrate metabolism     2 anaplerosis
```

1. *Non-KEGG-metabolic processes* — ERAD, mitophagy, NMD, proteasomal degradation, DNA-repair pathways (HR/NHEJ/NER/BER), ESCRT, signaling cascades. These fall outside the pathway-10k training distribution, so the model's silence here is a training-scope difference, not a plain recall failure. Whether they *should* count as PATHWAY depends on the annotation guideline; the `gt_100` convention leans toward metabolic pathway names.
2. *Respiratory-chain family* — `respiratory chain`, `electron transport chain`, `ETC`, `mitochondrial respiratory chain`. These *are* core bioenergetics and closely adjacent to `oxidative phosphorylation`, which the model does tag. This looks like a genuine model recall gap on a specific naming family.

**Model only (65)** — mostly long descriptive noun phrases rather than canonical pathway names:

```
3 energy metabolism                      2 synthesis of glycogen
2 fatty acid synthesis                   1 mitochondrial oxidation of long-chain fatty acids (LCFA)
1 triglyceride and phospholipid biosynthesis  1 muscle carbohydrate metabolism
1 metabolism of neuroprotective steroids  1 biotin carboxylation domain
1 transcarboxylation domain               1 glycogen breakdown
```

Two sub-patterns: (a) the model captures prose paraphrases (`"synthesis of glycogen"`, `"glycogen breakdown"`) where the LLM normalized to the canonical name (`glycogenesis`, `glycogenolysis`) — an overlap the set comparison under-counts; (b) a small number of true false positives — `"biotin carboxylation domain"` and `"transcarboxylation domain"` are protein domains, not pathways. That is the clearest model error class visible in this comparison, and it is rare.

**Document-level disagreement (6 docs)** — all in the same direction, `opus_prediction` positive / model zero spans:

```
31636353 (opus 13)   25855803 (opus 7)   17054399 (opus 4)
22927827 (opus 4)    11949934 (opus 1)   26005867 (opus 1)
```

Spot-checking the largest of these (31636353, 25855803, 17054399) against the per-chunk agent notes: these are genetics/clinical papers whose pathway content is signaling and degradation cascades (PI3K-AKT-mTOR, MAPK, ERAD, IP3/Ca²⁺) rather than named metabolic pathways — i.e. the same out-of-training-scope category as pattern 1 above. There were no documents where the model fired and `opus_prediction` found nothing.

## Per-PMID agreement with the CSV (expandable)

Only PMIDs with at least one agreeing name are listed; a name counts once per (name, CSV pathway) pair. `exact` = normalized string equality, `partial` = one normalized string contains the other.

### model ∩ CSV — 19 / 50 PMIDs, 22 agreeing names

<details>
<summary>**PMID 11949935** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycolysis / Gluconeogenesis; Glycolysis/gluconeogenesis; Starch and sucrose metabolism

| Found by model | CSV pathway | Match |
|---|---|---|
| `glycolysis` | Glycolysis / Gluconeogenesis | partial |

</details>

<details>
<summary>**PMID 35718349** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycerophospholipid metabolism; Oxidative phosphorylation; Purine catabolism; Purine metabolism

| Found by model | CSV pathway | Match |
|---|---|---|
| `phospholipid metabolism` | Glycerophospholipid metabolism | partial |

</details>

<details>
<summary>**PMID 1634041** — 1 agreeing name(s), 1 exact</summary>

CSV links for this PMID: Oxidative phosphorylation

| Found by model | CSV pathway | Match |
|---|---|---|
| `oxidative phosphorylation` | Oxidative phosphorylation | exact |

</details>

<details>
<summary>**PMID 34489854** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycerophospholipid metabolism; Oxidative phosphorylation; Purine catabolism; Purine metabolism

| Found by model | CSV pathway | Match |
|---|---|---|
| `lipid metabolism` | Glycerophospholipid metabolism | partial |

</details>

<details>
<summary>**PMID 28052917** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycerophospholipid metabolism; Oxidative phosphorylation; Purine catabolism; Purine metabolism

| Found by model | CSV pathway | Match |
|---|---|---|
| `lipid metabolism` | Glycerophospholipid metabolism | partial |

</details>

<details>
<summary>**PMID 11949932** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycolysis / Gluconeogenesis; Glycolysis/gluconeogenesis; Starch and sucrose metabolism

| Found by model | CSV pathway | Match |
|---|---|---|
| `glycolysis` | Glycolysis / Gluconeogenesis | partial |

</details>

<details>
<summary>**PMID 18614015** — 1 agreeing name(s), 1 exact</summary>

CSV links for this PMID: Oxidative phosphorylation

| Found by model | CSV pathway | Match |
|---|---|---|
| `oxidative phosphorylation` | Oxidative phosphorylation | exact |

</details>

<details>
<summary>**PMID 34415322** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycerophospholipid metabolism; Oxidative phosphorylation; Purine catabolism; Purine metabolism

| Found by model | CSV pathway | Match |
|---|---|---|
| `lipid metabolism` | Glycerophospholipid metabolism | partial |

</details>

<details>
<summary>**PMID 11949937** — 2 agreeing name(s)</summary>

CSV links for this PMID: Glycolysis / Gluconeogenesis; Glycolysis/gluconeogenesis; Starch and sucrose metabolism

| Found by model | CSV pathway | Match |
|---|---|---|
| `glycolysis` | Glycolysis / Gluconeogenesis | partial |
| `gluconeogenesis` | Glycolysis / Gluconeogenesis | partial |

</details>

<details>
<summary>**PMID 3201231** — 1 agreeing name(s), 1 exact</summary>

CSV links for this PMID: Oxidative phosphorylation

| Found by model | CSV pathway | Match |
|---|---|---|
| `oxidative phosphorylation` | Oxidative phosphorylation | exact |

</details>

<details>
<summary>**PMID 25751282** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycerophospholipid metabolism; Oxidative phosphorylation; Purine catabolism; Purine metabolism

| Found by model | CSV pathway | Match |
|---|---|---|
| `lipid metabolism` | Glycerophospholipid metabolism | partial |

</details>

<details>
<summary>**PMID 18067674** — 1 agreeing name(s), 1 exact</summary>

CSV links for this PMID: Purine catabolism; Purine metabolism

| Found by model | CSV pathway | Match |
|---|---|---|
| `purine metabolism` | Purine metabolism | exact |

</details>

<details>
<summary>**PMID 31637422** — 3 agreeing name(s)</summary>

CSV links for this PMID: Glycerophospholipid metabolism; Oxidative phosphorylation; Purine catabolism; Purine metabolism

| Found by model | CSV pathway | Match |
|---|---|---|
| `metabolism` | Glycerophospholipid metabolism | partial |
| `phospholipid metabolism` | Glycerophospholipid metabolism | partial |
| `lipid metabolism` | Glycerophospholipid metabolism | partial |

</details>

<details>
<summary>**PMID 37119330** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycerophospholipid metabolism; Oxidative phosphorylation; Purine catabolism; Purine metabolism

| Found by model | CSV pathway | Match |
|---|---|---|
| `lipid metabolism` | Glycerophospholipid metabolism | partial |

</details>

<details>
<summary>**PMID 27217339** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycerophospholipid metabolism; Oxidative phosphorylation; Purine catabolism; Purine metabolism

| Found by model | CSV pathway | Match |
|---|---|---|
| `lipid metabolism` | Glycerophospholipid metabolism | partial |

</details>

<details>
<summary>**PMID 18782459** — 1 agreeing name(s), 1 exact</summary>

CSV links for this PMID: Cholesterol metabolism

| Found by model | CSV pathway | Match |
|---|---|---|
| `cholesterol metabolism` | Cholesterol metabolism | exact |

</details>

<details>
<summary>**PMID 11949931** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycolysis / Gluconeogenesis; Glycolysis/gluconeogenesis; Starch and sucrose metabolism

| Found by model | CSV pathway | Match |
|---|---|---|
| `gluconeogenesis` | Glycolysis / Gluconeogenesis | partial |

</details>

<details>
<summary>**PMID 8655128** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycolysis / Gluconeogenesis; Glycolysis/gluconeogenesis; Starch and sucrose metabolism

| Found by model | CSV pathway | Match |
|---|---|---|
| `gluconeogenesis` | Glycolysis / Gluconeogenesis | partial |

</details>

<details>
<summary>**PMID 24482476** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycerophospholipid metabolism; Oxidative phosphorylation; Purine catabolism; Purine metabolism

| Found by model | CSV pathway | Match |
|---|---|---|
| `lipid metabolism` | Glycerophospholipid metabolism | partial |

</details>

### `opus_prediction` ∩ CSV — 20 / 50 PMIDs, 22 agreeing names

<details>
<summary>**PMID 11949935** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycolysis / Gluconeogenesis; Glycolysis/gluconeogenesis; Starch and sucrose metabolism

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `glycolysis` | Glycolysis / Gluconeogenesis | partial |

</details>

<details>
<summary>**PMID 35718349** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycerophospholipid metabolism; Oxidative phosphorylation; Purine catabolism; Purine metabolism

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `phospholipid metabolism` | Glycerophospholipid metabolism | partial |

</details>

<details>
<summary>**PMID 1634041** — 1 agreeing name(s), 1 exact</summary>

CSV links for this PMID: Oxidative phosphorylation

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `oxidative phosphorylation` | Oxidative phosphorylation | exact |

</details>

<details>
<summary>**PMID 34489854** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycerophospholipid metabolism; Oxidative phosphorylation; Purine catabolism; Purine metabolism

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `lipid metabolism` | Glycerophospholipid metabolism | partial |

</details>

<details>
<summary>**PMID 28052917** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycerophospholipid metabolism; Oxidative phosphorylation; Purine catabolism; Purine metabolism

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `lipid metabolism` | Glycerophospholipid metabolism | partial |

</details>

<details>
<summary>**PMID 11949932** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycolysis / Gluconeogenesis; Glycolysis/gluconeogenesis; Starch and sucrose metabolism

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `glycolysis` | Glycolysis / Gluconeogenesis | partial |

</details>

<details>
<summary>**PMID 18614015** — 1 agreeing name(s), 1 exact</summary>

CSV links for this PMID: Oxidative phosphorylation

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `oxidative phosphorylation` | Oxidative phosphorylation | exact |

</details>

<details>
<summary>**PMID 34415322** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycerophospholipid metabolism; Oxidative phosphorylation; Purine catabolism; Purine metabolism

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `lipid metabolism` | Glycerophospholipid metabolism | partial |

</details>

<details>
<summary>**PMID 11949937** — 2 agreeing name(s)</summary>

CSV links for this PMID: Glycolysis / Gluconeogenesis; Glycolysis/gluconeogenesis; Starch and sucrose metabolism

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `glycolysis` | Glycolysis / Gluconeogenesis | partial |
| `gluconeogenesis` | Glycolysis / Gluconeogenesis | partial |

</details>

<details>
<summary>**PMID 3201231** — 1 agreeing name(s), 1 exact</summary>

CSV links for this PMID: Oxidative phosphorylation

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `oxidative phosphorylation` | Oxidative phosphorylation | exact |

</details>

<details>
<summary>**PMID 25751282** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycerophospholipid metabolism; Oxidative phosphorylation; Purine catabolism; Purine metabolism

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `lipid metabolism` | Glycerophospholipid metabolism | partial |

</details>

<details>
<summary>**PMID 18067674** — 1 agreeing name(s), 1 exact</summary>

CSV links for this PMID: Purine catabolism; Purine metabolism

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `purine metabolism` | Purine metabolism | exact |

</details>

<details>
<summary>**PMID 31637422** — 2 agreeing name(s)</summary>

CSV links for this PMID: Glycerophospholipid metabolism; Oxidative phosphorylation; Purine catabolism; Purine metabolism

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `phospholipid metabolism` | Glycerophospholipid metabolism | partial |
| `lipid metabolism` | Glycerophospholipid metabolism | partial |

</details>

<details>
<summary>**PMID 39230499** — 1 agreeing name(s)</summary>

CSV links for this PMID: Nucleotide metabolism; Nucleotide salvage pathway

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `salvage pathways` | Nucleotide salvage pathway | partial |

</details>

<details>
<summary>**PMID 37119330** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycerophospholipid metabolism; Oxidative phosphorylation; Purine catabolism; Purine metabolism

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `lipid metabolism` | Glycerophospholipid metabolism | partial |

</details>

<details>
<summary>**PMID 27217339** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycerophospholipid metabolism; Oxidative phosphorylation; Purine catabolism; Purine metabolism

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `lipid metabolism` | Glycerophospholipid metabolism | partial |

</details>

<details>
<summary>**PMID 18782459** — 1 agreeing name(s), 1 exact</summary>

CSV links for this PMID: Cholesterol metabolism

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `cholesterol metabolism` | Cholesterol metabolism | exact |

</details>

<details>
<summary>**PMID 11949931** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycolysis / Gluconeogenesis; Glycolysis/gluconeogenesis; Starch and sucrose metabolism

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `gluconeogenesis` | Glycolysis / Gluconeogenesis | partial |

</details>

<details>
<summary>**PMID 8655128** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycolysis / Gluconeogenesis; Glycolysis/gluconeogenesis; Starch and sucrose metabolism

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `gluconeogenesis` | Glycolysis / Gluconeogenesis | partial |

</details>

<details>
<summary>**PMID 24482476** — 1 agreeing name(s)</summary>

CSV links for this PMID: Glycerophospholipid metabolism; Oxidative phosphorylation; Purine catabolism; Purine metabolism

| Found by `opus_prediction` | CSV pathway | Match |
|---|---|---|
| `lipid metabolism` | Glycerophospholipid metabolism | partial |

</details>

## Read

- The two annotators agree on the canonical metabolic core (173 shared names, including all the high-frequency KEGG-style ones), and agree on 44/50 documents at the positive/negative level.
- The 0.386 overlap is driven almost entirely by **scope**, not accuracy: `opus_prediction` includes non-metabolic cellular processes and signaling cascades the pathway-10k model was never trained to tag. Restricted to metabolic pathway names, the two track closely.
- The one substantive model recall gap worth acting on is the **respiratory-chain / electron-transport-chain family**, which is squarely metabolic, adjacent to a pathway the model already knows (`oxidative phosphorylation`), and missed in 20 distinct-name instances.
- Model false positives are rare and confined to protein-domain phrases (2 instances observed).
- Against the CSV both sources score similarly low (~1% exact at surface-form level), confirming the CSV's single-link structure — not annotation quality — is what caps that metric.
