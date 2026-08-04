# Pathway–Disease Relation Schema

Annotation schema for pathway–disease relation extraction. A unit of annotation is
one **(pathway, disease) pair within one abstract** — not one mention pair. If the
same pair is mentioned several times in an abstract, it receives a single label.

This schema is frozen before annotation starts. Changing a label definition or the
direction rules invalidates every abstract annotated under the old version, because
neither can be recovered from the stored answer.

Three fields are annotated: `label` (section A), `direction` (section B) and
`negated` (section C).

---

## A. `label` — predicate set

Four mutually exclusive values.

### `no_relation`

Both entities occur in the abstract, but the text makes no claim connecting them.
Expect this to be the majority of candidate pairs.

> Patients with type 2 diabetes were enrolled. Glycolysis was measured in muscle
> biopsies.

### `association`

A connection is claimed, but the text does not say which way it points or whether
the effect is an increase or a decrease. Typical cues: *linked to*, *implicated in*,
*role in*, *correlated with*, *associated with*.

> Aberrant fatty acid oxidation has been implicated in hepatocellular carcinoma.

### `positive_regulation`

One entity increases, activates, promotes or triggers the other.

> Upregulated glutaminolysis drives tumor proliferation in glioblastoma.

### `negative_regulation`

One entity decreases, suppresses, inhibits or protects against the other.

> Enhanced oxidative phosphorylation suppresses metastatic progression.

### Decision rules

1. If the sign of the effect is not explicit, fall back to `association`. Do not
   infer the sign from background knowledge — only from this abstract.
2. `positive_regulation` and `negative_regulation` are subsets of "a relation
   exists". Coarse evaluation may collapse all three non-null labels into a single
   positive class; the annotation stays fine-grained.
3. A relation reported as absent is still a claim. Label it with the predicate the
   sentence denies (usually `association`) and set `negated` (section C), not
   `no_relation`. `no_relation` means *no claim was made*, not *a claim of no
   effect*.

---

## B. `direction`

Three values. Annotated only when `label != no_relation`; otherwise `null`.

- `pathway_to_disease` — the pathway acts on the disease
- `disease_to_pathway` — the disease acts on the pathway
- `undirected` — the sentence does not commit to a direction

### Decision rules

1. **Default is `undirected`.** A direction is assigned only when the sentence has a
   regulatory or causal verb with an unambiguous subject. When in doubt, the answer
   is `undirected`.

2. **The subject of the regulatory verb determines the direction.**

   | Sentence | Direction |
   |---|---|
   | Glycolysis **drives** tumor growth. | `pathway_to_disease` |
   | Tumor hypoxia **induces** glycolysis. | `disease_to_pathway` |
   | Glycolysis **is elevated in** tumors. | `undirected` |

3. **Observational phrasing is `undirected`.** Constructions such as *is elevated
   in*, *is reduced in*, *levels differ between*, *is dysregulated in* report a
   measurement, not a causal claim. This is the most frequent pattern in abstracts
   and the most common source of annotator disagreement — it is `undirected` even
   though the disease is grammatically the context.

4. A high share of `undirected` is expected and correct. It is not a sign that the
   schema is failing.

---

## C. `negated`

Boolean. `true` when the abstract asserts that the relation does **not** hold.
Annotated only when `label != no_relation`; otherwise `null`.

> No association was found between the urea cycle and Alzheimer's disease.

is `association` + `negated: true`.

### Decision rules

1. **Negation marks the claim, it does not erase it.** A denied relation keeps the
   predicate the sentence denies. `no_relation` and `negated: true` are different
   outcomes: the first means the abstract is silent about the pair, the second means
   the abstract makes an explicit claim of absence. Both are useful in the database
   and collapsing them loses evidence.

2. **The negation must scope over the relation itself.** Only a denial of the
   pathway–disease link counts.

   | Sentence | `negated` |
   |---|---|
   | Glycolysis was **not** associated with tumor stage. | `true` |
   | **No** effect of the urea cycle on disease progression was detected. | `true` |
   | Glycolysis is elevated in **non**-small cell lung cancer. | `false` |
   | Patients who did **not** respond showed elevated glycolysis. | `false` |

   The last two negate an entity or a subgroup, not the relation.

3. **Hedging is not negation.** *May contribute*, *suggests*, *a potential role*
   weaken a claim without denying it — they stay `negated: false`. Hedging is not
   annotated as a separate field in this version of the schema.

4. **Direction is annotated as if the claim were positive.** A denied directed
   claim keeps the direction of the verb it denies: *glycolysis does not drive
   tumor growth* is `pathway_to_disease` + `negated: true`.

---

## Record format

```json
{
  "pmid": "12345678",
  "pathway_id": "...",
  "disease_id": "...",
  "label": "positive_regulation",
  "direction": "pathway_to_disease",
  "negated": false
}
```

`pathway_id` and `disease_id` are normalized identifiers (Recon3D / KEGG for
pathways, MeSH for diseases), not surface strings. An unnormalized pair cannot enter
the database.

---

## Modelling note

`label`, `direction` and `negated` are separate prediction targets sharing one
encoder, not a single cross-product label. A cross-product would produce twenty-four
sparse classes, several of which would never accumulate enough examples to train or
evaluate. `negated` in particular is a rare positive class and needs its own head to
be measured at all.

---

## Pilot requirement

Compute inter-annotator agreement separately for `label` and for `direction` on the
first 50 doubly annotated abstracts. If the `direction` kappa falls below 0.6, the
direction rules are underspecified and must be repaired before annotating at scale.

For `negated`, report the raw count of disagreements rather than kappa: the positive
class is rare enough that kappa is unstable at this sample size. Every disagreement
is read individually — at these counts the cause is a rule gap, not annotator noise.
