# Annotation guide — Pathway span review (doccano)

You are reviewing **machine-generated (silver)** pathway spans. One label type: `PATHWAY`.

Your job per span: **accept**, **reject**, or **fix its boundary**. You may also **add** a
pathway mention the machine missed. **You do not assign pathway names** — the `canonical`
field in the metadata is machine-guessed context only; ignore it if it looks wrong, and
never let it drive your decision.

## The one question

> Does this string **name a metabolic process**?

If yes → accept. If no → reject. That is the whole rule; everything below is that rule
applied to the cases that actually come up.

## Accept

| Case | Example |
|---|---|
| Canonical name | `butanoate metabolism` |
| Known synonym | `TCA cycle`, `nicotinamide metabolism` |
| Word-order variant | `metabolism of androgens` |
| Alternative/chemical name | `cholecalciferol metabolism` (= vitamin D) |
| Subtype of a broader pathway | `biosynthesis of unsaturated fatty acids`, `lysophospholipid metabolism` |
| Umbrella term | `lipid metabolism`, `energy metabolism`, `amino acid metabolism` |
| Process word other than "metabolism" | `arginine biosynthesis`, `leukotriene production`, `fatty acid oxidation` |

## Reject

| Case | Example | Why |
|---|---|---|
| Bare metabolite / compound | `carnitine`, `arachidonic acid`, `tryptophan-derived metabolite` | a molecule, not a process |
| Enzyme / protein / gene | `5alpha-reductase`, `FLT3` | not a process |
| **Non-metabolic** process | `aminoacyl-tRNA biosynthesis` | that is translation, not metabolism |
| Compartment / location term | `mitochondrial metabolism` | names where, not which process |
| Disease / phenotype | `insulin resistance syndrome` | not a pathway |

The metabolite case is the most common machine error — a compound name alone is always a
reject, but the same compound **with a process word** (`arachidonic acid metabolism`) is an
accept.

## Boundaries

- Include the whole phrase, process word included: `arginine biosynthesis`, not `arginine`.
- In a list, each item is its own span: in `glycolysis, gluconeogenesis, and fatty acid
  oxidation` that is three spans, not one.
- Modifiers that are part of the pathway name stay in: `de novo pyrimidine synthesis`.
  Modifiers that are not do not: in `carnitine mediated fatty acid oxidation`, the pathway
  is `fatty acid oxidation`.

## Worked examples

`playground/golden_set/golden_set.md` is 5 abstracts annotated by hand under this rule —
use it as the reference when a case is unclear.

## Note — one deliberate difference from the golden set

The golden set files `biosynthesis of unsaturated fatty acids` under
`out_of_vocab_pathways` because it does not map cleanly onto a Recon subsystem name. That is
a **vocabulary-mapping** concern, not a "is this a pathway mention" concern. The model we
train is a **binary** tagger (pathway / not-pathway), so here such subtype names are
**accepts**. Only genuinely non-metabolic items (`aminoacyl-tRNA biosynthesis`,
`mitochondrial metabolism`) are rejects.
