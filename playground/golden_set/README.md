# Golden Set — variation-aware pathway evaluation

A small, **human-curated** evaluation set that measures whether the model
recognizes pathway mentions in **all their surface variations**, not just the
canonical strings exact matching was built on.

## Why this exists

Training labels come from exact string matching of the 98 canonical Recon names
(+ ~10 synonyms). Across the whole corpus that yields only **105 case-folded
surface forms** for 73k spans (see `../exact_match_analysis.md`). A model trained
on that learns a near-lookup behavior: it tags what it literally saw and labels
paraphrases as `O`. This set was built to **quantify and eventually close** that
gap.

## Versions

- **v1** (5 abstracts): the abstracts richest in *distinct* Recon pathways
  (most-distinct-pathway PMIDs from `exact_matches.jsonl`). Amino-acid/lipid heavy.
- **v2** (+5 abstracts, 10 total): chosen for pathway-*type* diversity to balance
  v1 — energy/central-carbon, carbohydrate, nucleotide, urea cycle, vitamin/cofactor,
  bile acid, drug/xenobiotic. See the articles table below.
- **v3** (in progress, +100 docs): 100 abstracts from the 10k corpus **test split**,
  exported for doccano review as `doccano/golden_100_doccano.jsonl` — the single
  import file for the new golden docs (the 10 curated docs above stay separate, not
  mixed in). Selection (seed 20260818): span-count bands kept varied (9 zero-span
  docs, 33/20/22/16 in 1/2/3-4/5+), greedy max canonical-pathway coverage (61 of 61
  distinct pool pathways), variation-rich docs preferred (186 variation spans).
  Disjoint from all training data (10k train/val, gold-pilot1k, frozen silver).
  PMIDs already excluded from silver (`llm/run_silver.py GOLDEN_PMIDS`,
  `golden_pmids.txt` — 110 entries); not yet merged into `golden_set.json` — merge
  happens after doccano review.

## Headline finding

Hand-annotating every pathway mention in the 10 abstracts, pooling contiguous
spans + shared-head-enumeration parts (per mention; umbrella/abbreviation terms fan
out to each Recon child they denote):

| | Count (v1) | Count (v2, 10 abstracts) | Share (v2) |
|---|---|---|---|
| Recon-resolvable pathway mentions (map to ≥1 of the 98 subsystems) | 38 | 76 | 100% |
| Exact matching **catches** (canonical / synonym) | 14 | 39 | 51% |
| Exact matching **misses** (variations) | **24** | **37** | **49%** |

Plus **9 umbrella mentions** (`amino acid metabolism`, `lipid metabolism`,
`oxidative metabolism`, `energy metabolism`, `neurotransmitter metabolism`, …) —
genuine metabolic-process mentions that don't resolve to any single Recon subsystem,
positive for a binary tagger but not Recon-scored.

The catch rate rose from v1's 37% to 51% in v2: the added central-carbon articles
use many pathway names verbatim (`glycolysis`, `TCA cycle`, `OXPHOS`, `PPP`,
`galactose metabolism`), so exact matching catches more of them — while still
missing ~half. Examples of what it misses:

- `metabolism of androgens` → androgen … metabolism (word-order)
- `cholecalciferol metabolism` → vitamin d metabolism (chemical synonym)
- `cysteine/methionine metabolism` → methionine and cysteine metabolism (order + `/`)
- `histidine and glutathione metabolism` → histidine metabolism (shared head)
- `BCAA … metabolism` → valine, leucine, and isoleucine metabolism (abbreviation)
- `AAA metabolism` → phenylalanine / tyrosine / tryptophan metabolism (abbrev. → 3 children)
- `purine metabolism` → purine synthesis + purine catabolism (umbrella → children)
- `octadecatrienoic acid beta-oxidation` → fatty acid oxidation (specific FA → parent) *(v2)*
- `retinol metabolism` → vitamin a metabolism (chemical synonym) *(v2)*
- `mitochondrial folate metabolism` → folate metabolism (compartment qualifier) *(v2)*
- `pyrimidine metabolism` → pyrimidine synthesis + pyrimidine catabolism (umbrella → children) *(v2)*

## Files

- `build_golden_set.py` — hand annotations encoded as `(surface, occurrence)`; the
  script recomputes/verifies character offsets and validates every `match_type`
  against the Recon vocab + synonym list. Regenerates both outputs.
- `golden_set.json` — machine-readable annotations (the eval artifact).
- `golden_set.md` — human review copy (abstract text + all annotations per PMID).

## Articles

Per-mention (spans + enumeration parts), Recon-resolvable only. `themes` names the
pathway families the article contributes.

**v1** — most distinct Recon pathways, by exact-match count:

| PMID | Title | catches | variations | umbrella |
|---|---|---|---|---|
| 11469814 | Steroid metabolism in metabolic syndrome X | 2 | 2 | 0 |
| 39934780 | Metabolic perturbations, liver steatosis & CVD | 3 | 4 | 2 |
| 40225847 | Biomarkers for schizophrenia (metabolomics review) | 2 | 1 | 0 |
| 29615816 | Metabolic features of FLT3-ITD AML | 2 | 4 | 0 |
| 36294866 | Metabolomic signatures of ASD | 5 | 13 | 2 |

**v2** — chosen for pathway-type diversity:

| PMID | Title | catches | variations | umbrella | themes |
|---|---|---|---|---|---|
| 34376485 | HPV vs smoking HNSCC plasma phenotypes | 7 | 2 | 0 | energy (OXPHOS/glycolysis), bile acid, FA oxidation, galactose, vitamin B6 |
| 42299101 | Posttranscriptional regulation in glioblastoma | 5 | 5 | 5 | Warburg/glycolysis, PPP, nucleotide, folate, glutamine |
| 28587170 | Arginine deprivation + 5-FU in HCC | 3 | 2 | 0 | urea cycle, pyrimidine, TCA |
| 38669820 | Goose astrovirus RNA-seq | 5 | 4 | 0 | drug/cytochrome-P450, vitamin A (retinol), vitamin C (ascorbate), carbohydrate |
| 37807318 | Central-carbon biomarkers in colon cancer | 5 | 0 | 0 | glycolysis, TCA, PPP, galactose, butanoate |

## Annotation schema

Each article has four buckets:

- **`spans`** — contiguous character spans of a pathway mention.
  `match_type`: `exact` / `synonym` (exact matching catches), `variation`
  (exact matching misses but resolves to ≥1 Recon subsystem — the primary eval
  target), or `umbrella` (a real metabolic-process mention that resolves to **no**
  single Recon subsystem, e.g. `amino acid metabolism`; positive for a binary
  tagger, reported separately, not Recon-scored).
- **`shared_head_enumerations`** — factored phrases like
  `"glycine, serine and threonine, BCAA and AAA metabolism"`, **or** umbrella terms
  that fan out to several Recon children (`purine metabolism` → purine synthesis +
  catabolism), decomposed into the pathways a reader intends. Where distant
  supervision breaks down most.
- **`out_of_vocab_pathways`** — mentions that are **not** in-scope Pathway spans at
  all: non-metabolic processes (`aminoacyl-tRNA biosynthesis` = translation,
  `mitochondrial metabolism` = compartment) and narrow subtype specifications whose
  subtype word is absent from the parent Recon name (`biosynthesis of unsaturated
  fatty acids`). Recorded for transparency; not scored.
- **`metabolites_not_pathways`** — salient metabolite names (`arachidonic acid`,
  `carnitine`, …) that must **not** be tagged. Precision negatives.

**Scope rule.** A span is an in-scope Pathway if it denotes a metabolic process and
either (a) maps to ≥1 Recon subsystem (specific process → parent pathway; umbrella
term → its Recon children) → `variation`, or (b) is a generic metabolic-process
umbrella term → `umbrella`. Non-metabolic processes and off-name subtypes are
excluded (`out_of_vocab_pathways`).

## Scope & caveats

- **Abstract-level.** These 10 articles have long full texts; only the abstracts are
  annotated (exhaustively, and trustworthy). Full-text annotation is a future extension.
- **Small by design.** A gold set is for measurement, not training. 10 abstracts /
  76 Recon-resolvable mentions (+9 umbrella) is enough to detect a real
  generalization gap; it is not a statistically tight benchmark. Grow it before
  drawing fine-grained conclusions.
- **Per-mention counting.** Umbrella/abbreviation terms fan out (`AAA metabolism` →
  3 aromatic-aa subsystems; `purine metabolism` → 2), so one surface can add several
  mentions. Unique (article, pathway) recall will be lower than the per-mention rate.
- **Scope decision resolved** (see the scope rule above): specific processes and
  umbrella terms that map to Recon subsystems are in-scope `variation`s; generic
  metabolic umbrellas are flagged `umbrella` (positive-for-tagger, non-Recon);
  non-metabolic processes and off-name subtypes are excluded.

## How it will be used

1. Run the current Run 005 model over each abstract; align detections to these
   spans. Expected: high recall on `exact`/`synonym`, low on `variation` — the
   measured baseline gap.
2. After any label-enrichment step (rule-based `metabolism of X` / shared-head
   expansion, or LLM annotation), re-run and check whether `variation` recall
   improves **without** hurting `exact` recall or tagging the metabolite negatives.

## Reproduce

```bash
# from repo root
/home/enes/sci-usage/venv310/bin/python3 playground/golden_set/build_golden_set.py
```

## Related

- `../exact_match_analysis.md` — the 105-surface-form / distant-supervision analysis
- `../model_005_analysis/` — Run 005 predictions on the abstract DB
- `knowledge_base/model_experiments.md` — Run 005 training
