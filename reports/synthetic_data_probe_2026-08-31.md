# Synthetic relation data: feasibility probe

Date: 2026-08-31
Status: Throwaway probe. No student was trained; no number here belongs in `runs/summary.jsonl`.

## Question

Can synthetic pathway–disease relation examples be generated at all from the
existing 2k silver corpus and from a metabolic knowledge graph, and what fraction
of what is generated survives a blind re-label by the teacher?

Acceptance rate is the measurement. MedSyn (arXiv 2408.02056) reports 64% for
GPT-4-generated clinical notes and 51% for a fine-tuned LLaMA; those are the
reference points.

## Two methods

**Counterfactual direction flip.** Take the `upregulation` and `downregulation`
rows of `data/processed/relation/silver_2k/relations_llm_opus.jsonl`, find the one
polarity term in the evidence sentence, replace it with its opposite, shift the
entity offsets, and flip the expected label. No model writes anything; the text is
real PubMed prose with one word changed.

**KG-seeded generation.** Take a (disease, pathway) pair from SMPDB, name a target
relation class, and have the teacher write an abstract-like paragraph expressing
it. The knowledge graph decides *which pair* is discussed. The target class
decides *what is claimed*. Neither becomes the label.

Both methods write a `candidates.jsonl` in the shape `run_teacher.py` already
consumes, so the acceptance filter is the existing teacher run over new text — no
second judging path to keep in sync.

## Knowledge graph selection

PrimeKG was the starting proposal and does not fit:

- It has no disease–pathway edge. It carries `disease_protein` and
  `pathway_protein`, so a link is a two-hop inference through a gene: high recall,
  low precision.
- Its pathways are Reactome, which is signalling-heavy. The v1 scope of this
  project is metabolic pathways only.
- Its edges are undirected associations. The schema needs `upregulation` /
  `downregulation`, and that information is not in the graph at all. The most a
  KG could supply is `association`, which is already the second most common label
  in the silver corpus.

HumanCyc/BioCyc data files are behind a paid subscription (≥ $5,000) and were not
used. SMPDB is free, human, and metabolic, and carries a `Disease` pathway subject
whose members are inborn errors of metabolism drawn as perturbations of a named
metabolic pathway — a disease–pathway pairing without the gene hop.

The mapping from SMPDB to this project's tag set is lossy and is recorded as such:
37 SMPDB metabolic pathways match 35 of the 98 Recon pathway names by token
Jaccard, and 20,244 SMPDB disease pathways yield 144 seed pairs over 135 diseases
at a metabolite-Jaccard floor of 0.30. The name match is a string heuristic and
produces visible noise (`nucleotide metabolism` ← `Nucleotide Sugars Metabolism`;
`d-alanine metabolism` ← `Alanine Metabolism`).

## Results

| Method | generated | re-labelled | acceptance |
|---|---|---|---|
| Counterfactual flip | 150 (of 308 available) | 129 | **0.400** |
| KG-seeded generation | 97 (of 100 requests) | 96 | **0.979** |

Per class:

| Class | counterfactual | KG-seeded |
|---|---|---|
| upregulation | 0.254 (n=63) | 1.000 (n=20) |
| downregulation | 0.506 (n=87) | 0.950 (n=20) |
| association | – | 0.947 (n=19) |
| no_association_stated | – | 1.000 (n=18) |
| none | – | 1.000 (n=20) |

### The counterfactual failure is systematic, not noise

Of 129 re-labelled flips, **44 came back with the label the row had before the
flip**. The text changed; the claim did not. Two causes, both observed:

1. The flipped word qualifies a *metabolite*, not the pathway. In
   `... leads to the accumulation of glycosphingolipids ...` the flip to
   `depletion` changes the metabolite's direction, and the pathway's direction
   does not follow from it — the teacher's original reading survives the edit.
2. The sentence carries more than one polarity signal and the flip makes it
   contradict itself: `... taking up lactate at decreased levels ... whilst also
   increasing NADPH levels ...`.

The method's premise — that word polarity equals relation polarity — is false for
roughly a third of the corpus it applies to. A further 21 of 150 were lost to
`evidence_not_verbatim` at re-labelling.

Generation itself rejected 556 of 864 signed rows before any model was called: 326
evidence sentences contain no polarity term from the lexicon, 230 contain more
than one and were refused as ambiguous.

### The KG-seeded number is inflated and should not be read as quality

97.9% acceptance is agreement between a generator and a judge from the same model
family, on text the generator was told what to claim. It measures that the
generator can be steered, not that the text is realistic. Two pieces of evidence
that it is not:

- Synthetic abstracts run to a median 177 words against 224 for the real
  candidate pool.
- Hedging is thinner: 4.8 hedge terms per 1,000 words against 7.8 in the real
  pool.

Hedged and unsigned claims are exactly what the schema notes (`relation_extraction/schema.py`)
identify as the hard cases. Synthetic text that hedges less than real text trains
a student on the easy half of the problem.

## What this says about the next step

- The KG-seeded route produces balanced examples of the rare classes on demand:
  20 `none`, 18 `no_association_stated`, 20 each of the signed classes from 100
  requests, against 34 `no_association_stated` in the entire 4,982-row silver
  corpus. That is the one thing sampling real abstracts cannot do.
- The acceptance filter as run here is close to worthless, because generator and
  judge are the same family. A real filter needs a different judge — a second
  model family, or gold-panel humans on a sample.
- The counterfactual route as specified should not be scaled. If it is kept, the
  lexicon has to be restricted to terms that modify the pathway mention itself,
  and sentences with more than one polarity signal have to stay excluded.
- Nothing here establishes that synthetic data helps the student. That question
  needs a training run against the locked `gt_100` panel and was explicitly out of
  scope for this probe.

## Reproducing

```
python3 relation_extraction/synth_kg_seed.py
python3 relation_extraction/synth_generate.py --n-seeds 20
python3 relation_extraction/synth_counterfactual.py
python3 relation_extraction/run_teacher.py --candidates <dir>/candidates.jsonl \
    --out <dir>/relabelled.jsonl --mode single
python3 relation_extraction/synth_probe_report.py --expected <dir>/expected.jsonl \
    --relabelled <dir>/relabelled.jsonl
```

Outputs land in `data/processed/relation/synth_probe/`, which is not tracked.
