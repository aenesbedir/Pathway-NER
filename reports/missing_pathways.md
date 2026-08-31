# Missing pathway recovery

Recon3D names 98 metabolic subsystems. Sixteen of them reach neither the 10k
annotated corpus nor the dictionary matcher. This run asks what is actually
behind that gap: a corpus that lacks the literature, a vocabulary that lacks the
name, or a name that was never a pathway to begin with.

Scripts: `scripts/fetch_missing_pathways.py`, `scripts/build_missing_corpus.py`,
`scripts/analyze_missing.py`.
Data (untracked): `data/raw/missing_pathways/`, `data/processed/missing_pathways/`.

## How the 16 were selected

Three independent criteria over the 98 Recon names:

| criterion | test | count |
|---|---|---:|
| A | canonical name absent from the 10k span surface forms (`data/processed/pathway-10k/matches.jsonl`, 2912 unique forms) | 26 |
| B | zero PMIDs from the pathway × disease search (`data/raw/pathway_disease_pairs.json`) | 23 |
| C | zero spans in the dictionary matcher (`data/processed/exact_matches.jsonl`) | 16 |

The target set is **A ∩ C** = 16: thirteen that fail all three (A∩B∩C) plus three
that the search found but neither the dictionary nor the annotation did.

Eight of the sixteen are on `RECON_BLOCKLIST` (`preprocessing/recon_vocab.py`) and
therefore have no curated surface forms — `build_surface_forms()` returns 90 keys,
not 98. They are measured separately throughout, using the canonical name alone,
because `distribute_forms()` produces nonsense for them (`intracellular
source/sink` → `sink`, `exchange/demand reaction` → `exchange`).

## Method

For every surface form of every target — 34 curated forms across 8 pathways, plus
8 bare canonicals for the blocklisted ones — two PubMed searches:

    solo : "<form>"[Title/Abstract]                                  cap 200
    pair : ("<form>"[Title/Abstract]) AND ("<disease>"[Title/Abstract])
           over the 98 curated diseases                              cap 10/pair

4158 ESearch calls. Abstracts fetched for the union of returned PMIDs, then two
checks that the search itself cannot make:

- **text** — does the abstract verbatim contain the form it was retrieved for?
- **model** — does `runs-truba-checkpoints/pathway-10k/biom-electra-large/lr3e-05/seed7`
  (gt_100 seqeval F1 **0.8358**, `doccano/golden_dataset/gt_100_scores.json`)
  predict a span equal to one of the forms? Run with `--no-booster` so the
  dictionary cannot answer its own question.

Corpus: 4160 unique PMIDs, 4150 records, **4102 with an abstract**. Seven golden
PMIDs were dropped by `run_silver.py` (eval data never enters silver), leaving
4095 scored.

## Result 1 — solo and pair are indistinguishable

The question was whether the disease-paired query recovers these pathways better
than the bare one. It does not; the two produce the same quality of document.

| set | abstracts | form in text | % | model predicts form | % |
|---|---:|---:|---:|---:|---:|
| solo only | 2344 | 2238 | 95.5 | 2067 | 88.2 |
| pair only | 690 | 659 | 95.5 | 607 | 88.0 |
| both | 328 | 318 | 97.0 | 303 | 92.4 |

Equal precision, so the choice is about volume, and there the two are
complementary rather than ranked: solo is capped at 200 per form while pair can
return up to 980 (98 diseases × 10), so **pair contributes 690 documents solo's
cap never reached**. Use the union. Neither query is exhaustive — `cholesterol
synthesis` alone reports 6570 hits against the 200 retrieved.

## Result 2 — the corpus is real and mostly new

| | |
|---|---:|
| abstracts | 4102 |
| already in the 10k corpus | 513 |
| of those, carrying a 10k gold record | 131 |
| **not in the 10k corpus** | **3589** |

Model output over 4095 abstracts: **7776 spans in 3243 documents**, 1.9 per
abstract, 1397 unique surface strings. The most frequent predictions are the
target forms themselves — `cholesterol synthesis` (556), `mevalonate pathway`
(420), `estrogen metabolism` (299), `phosphoinositide metabolism` (244).

## Result 3 — per pathway

Curated surface forms. `frm` = forms, `solo+`/`pair+` = forms returning ≥1 hit,
`onlyP` = PMIDs only the pair query found, `hasF` = abstracts containing a form,
`mDoc`/`mSpan` = documents/spans predicted, `mForm` = documents where a
prediction equals a target form.

| pathway | frm | solo+ | pair+ | pmid | solo | pair | onlyP | abs | hasF | mDoc | mSpan | mForm |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| androgen and estrogen synthesis and metabolism | 10 | 8 | 7 | 1478 | 1248 | 383 | 230 | 1474 | 1414 | 1394 | 2524 | 1310 |
| squalene and cholesterol synthesis | 7 | 6 | 6 | 1459 | 1045 | 553 | 414 | 1457 | 1384 | 1407 | 4307 | 1315 |
| phosphatidylinositol phosphate metabolism | 3 | 3 | 2 | 271 | 224 | 74 | 47 | 270 | 264 | 247 | 377 | 226 |
| lipoate metabolism | 4 | 3 | 2 | 108 | 108 | 10 | 0 | 108 | 100 | 97 | 331 | 86 |
| keratan sulfate synthesis | 4 | 4 | 1 | 36 | 36 | 1 | 0 | 36 | 36 | 30 | 88 | 27 |
| n-glycan metabolism | 1 | 1 | 0 | 7 | 7 | 0 | 0 | 7 | 7 | 7 | 28 | 7 |
| blood group synthesis | 3 | 1 | 0 | 5 | 5 | 0 | 0 | 5 | 5 | 2 | 2 | 2 |
| hippurate metabolism | 2 | 1 | 1 | 5 | 5 | 1 | 0 | 5 | 5 | 5 | 9 | 4 |

Totals: 3369 PMIDs (2347 solo-only, 691 pair-only), 3362 abstracts, 3215 with a
form present, 3189 with a model span, 7666 spans.

Blocklisted, canonical name only:

| pathway | pmid | solo | pair | abs | hasF | mDoc | mSpan | mForm |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| miscellaneous | 547 | 200 | 370 | 544 | 526 | 20 | 39 | **0** |
| protein formation | 238 | 200 | 68 | 238 | 224 | 32 | 74 | **0** |
| intracellular demand | 8 | 8 | 1 | 8 | 8 | 4 | 5 | **0** |
| biomass and maintenance functions | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| dietary fiber binding | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| exchange/demand reaction | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| intracellular source/sink | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| r group synthesis | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Totals: 793 PMIDs, 790 abstracts, 758 with the string present, 56 with any model
span, 118 spans.

**The blocklist is confirmed by measurement.** Five names return nothing at all.
The three that do — `miscellaneous`, `protein formation`, `intracellular demand` —
match because they are ordinary English: the string is in 758 of 790 abstracts,
yet the model predicts the name as a pathway in **zero** of them. A model trained
on 10k pathway spans does not consider "protein formation" a pathway. Unblocking
them would have added 758 false positives.

## Result 4 — "missing from 10k" was partly an artifact of the canonical name

Criterion A tested the Recon canonical string against the 10k span surface forms.
Tested against the curated surface forms instead, four of the eight are already
annotated in the 10k corpus:

| pathway | 10k spans under its forms | which |
|---|---:|---|
| squalene and cholesterol synthesis | 154 | `cholesterol synthesis` 140, `mevalonate pathway` 8, `cholesterol biosynthetic pathway` 4 |
| androgen and estrogen synthesis and metabolism | 17 | `androgen metabolism` 5, `estrogen metabolism` 4, `sex steroid metabolism` 3 |
| lipoate metabolism | 3 | `lipoic acid metabolism` |
| phosphatidylinositol phosphate metabolism | 1 | `phosphoinositide metabolism` |
| blood group synthesis | 0 | — |
| hippurate metabolism | 0 | — |
| keratan sulfate synthesis | 0 | — |
| n-glycan metabolism | 0 | — |

Confirmed on the 506 documents this corpus shares with the 10k: 102 contain a
target form and the 10k gold already labels **100** of them. The annotation was
not failing; it wrote the form the author used. Only four pathways are genuinely
unrepresented, and all four are marginal in the literature (best form: 36, 7, 5
and 5 abstracts).

## Result 5 — the surface-form dictionary is not wired into the matcher

For all 34 curated forms, `exact_matches.jsonl` holds **zero** spans. The reason
is upstream of the data: `preprocessing/match_exact.py` builds its vocabulary from
`recon_vocab.RECON_SYNONYMS`, which covers 10 pathways, and never imports
`preprocessing/pathway_surface_forms.py`. Nothing in this branch's pipeline does —
`llm/booster.py` here imports `recon_vocab` only.

The main working tree is ahead of this branch on exactly that point: its
`llm/booster.py` has `boost_surface()` built from `build_surface_forms()`, and its
`run_silver.py` calls it. That work is uncommitted. The dictionary matcher does
not use the surface forms in either tree.

## What this changes

1. **`match_exact.py` should read `pathway_surface_forms.py`.** The vocabulary
   exists, is curated with a stated trust order, and the matcher ignores it. This
   is the single highest-value change here and it needs no new data.
2. **Union of solo and pair, not one of them.** Equal precision, disjoint volume,
   both capped well below the true hit count.
3. **Leave the blocklist alone.** Its three literature-frequent names produce zero
   model-confirmed pathway spans in 758 abstracts.
4. **Four pathways stay unrepresented** — blood group synthesis, hippurate
   metabolism, keratan sulfate synthesis, n-glycan metabolism. Between 5 and 36
   abstracts each; this is scarcity in the literature, not a pipeline defect.
5. **3589 new abstracts** with 7776 model spans are available as annotation
   candidates. They are silver: machine-labeled, unreviewed, and the model that
   produced them scores 0.8358 on gt_100, so roughly one span in six is wrong.
