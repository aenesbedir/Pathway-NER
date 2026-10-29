# Seed sources compared: SMPDB metabolite overlap vs PrimeKG two-hop

Date: 2026-09-03
Status: Throwaway probe, follow-up to `synthetic_data_probe_2026-08-31.md`. No
student was trained; no number here belongs in `runs/summary.jsonl`.

## Question

The KG-seeded generator uses a knowledge graph for exactly one job: choosing
which (disease, pathway) pair gets written about. The first probe used SMPDB and
rejected PrimeKG, but the rejection argued that PrimeKG cannot supply a
*direction* — which is true, and irrelevant to the job the KG actually does.
SMPDB does not supply direction either.

So the open question was never answered: for pair selection, is PrimeKG's
two-hop walk through genes better or worse than SMPDB's metabolite overlap?

## Why acceptance rate cannot answer it

The obvious comparison is to generate from both and score the blind re-label.
That measures whether the generator can be steered to a requested class, and it
saturated at 0.979 on the SMPDB seeds. A generator told to write
`downregulation` about an absurd pair still writes `downregulation`, the filter
passes it, and the number says nothing about the pair.

## The measurement used instead

A seed source proposes pairs a paper might plausibly be written about. That is
checkable against the 10,125 real abstracts in
`data/processed/pathway-10k/articles.jsonl`: how often do both names of a
proposed pair appear in the same abstract?

Raw co-occurrence confounds pairing quality with disease commonness — a source
drawing on rare inborn errors of metabolism is penalised for its vocabulary, not
its pairing. Two corrections are applied:

- rates are conditioned on both names appearing in the corpus at all;
- each source is scored against its own permutation — the same diseases and the
  same pathways, re-paired at random, averaged over 20 shuffles.

**Lift** is the difference between the real pairing and its permutation. It is
the part attributable to the pairing rather than to the vocabulary.

Matching is case-folded substring, minus a trailing parenthetical. Crude, and
applied identically to every source.

## Results

| | smpdb | primekg | primekg_ms2 | primekg_shared | primekg_top3 |
|---|---|---|---|---|---|
| pairs | 144 | 80 | 211 | 80 | 102 |
| diseases | 134 | 80 | 210 | 80 | 80 |
| Recon pathways | 28 | 11 | 21 | 11 | 12 |
| disease name in corpus | 0.410 | 0.425 | 0.498 | 0.425 | 0.431 |
| pairs with both names present | 48 | 29 | 96 | 29 | 39 |
| co-occur, given both present | **0.417** | 0.345 | 0.344 | 0.345 | 0.308 |
| same, permuted | 0.052 | 0.238 | 0.200 | 0.255 | 0.275 |
| **lift** | **+0.365** | +0.107 | +0.144 | +0.090 | +0.033 |

PrimeKG variants: `ms2` lowers the shared-gene minimum from 3 to 2; `shared`
ranks candidate pathways by raw intersection size instead of gene-set Jaccard;
`top3` keeps three pathways per disease instead of one.

Overlap between the two sources is near zero: 0 shared pairs, 2 shared diseases.

## Reading

**SMPDB's pairing carries real signal.** Its pairs co-occur eight times more
often than the same diseases and pathways re-paired at random. This is the first
direct evidence that the metabolite-overlap heuristic picks pairs literature
actually discusses, rather than merely pairs that pass a threshold.

**PrimeKG's two-hop pairing is weak, and the reason is visible in the control.**
Its raw co-occurrence (0.345) is not far below SMPDB's (0.417), which on its own
looks competitive. But its permuted control sits at 0.238, because the walk
collapses onto very few pathways — 11 Recon names, with `citric acid cycle` and
`heme degradation` taking 41 of 80 pairs. When a source proposes the same handful
of common pathways for every disease, shuffling the assignment barely changes
anything, and most of the apparent co-occurrence is the pathway's popularity
rather than the pairing. The lift of +0.107 is what survives that correction, and
it drops to +0.033 when the walk is widened to three pathways per disease.

**PrimeKG is nevertheless broader where SMPDB is narrow.** At the looser
threshold it proposes 210 diseases against SMPDB's 134, and a higher fraction of
them appear in the corpus at all (0.498 vs 0.410). SMPDB's ceiling is structural:
its only disease–pathway pairing comes from the `Disease` pathway subject, which
is inborn errors of metabolism, and 59% of those names never occur in 10k
abstracts.

**The two sources are disjoint.** Zero shared pairs. They are not competing
estimates of the same thing; they select from different regions of the disease
space.

## What this changes

- The first probe's rejection of PrimeKG was right for the wrong reason. The
  correct reason is not that its edges are undirected — SMPDB's are too — but
  that its gene-mediated pairing concentrates on a few large pathways and adds
  little over a random assignment among them.
- SMPDB stays the seed source. Nothing here argues for replacing it.
- Coverage remains an unsolved problem. Neither source reaches the common
  diseases that dominate PubMed with a pairing that survives its own permutation
  control. If synthetic generation is scaled, the pair source is the part that
  needs work, not the generator.
- A weighted combination was not tried. Given zero overlap, a union is available
  at no cost and would inherit both the coverage and the weak pairing.

## Reproducing

```
python3 relation_extraction/synth_kg_seed_primekg.py
python3 relation_extraction/synth_seed_compare.py \
    --source smpdb=data/processed/relation/synth_probe/kg_seeds.jsonl \
    --source primekg=data/processed/relation/synth_probe/kg_seeds_primekg.jsonl
```

PrimeKG is a 937 MB `kg.csv` from Harvard Dataverse (datafile 6180620); the
builder does not download it. Outputs land in
`data/processed/relation/synth_probe/`, which is not tracked.
