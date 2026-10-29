# Relation Extraction for Pathway–Disease Links — Survey and Design Notes

Date: 2026-08-11
Scope: how to build the pathway–disease relation model and the evidence database
behind it. Covers the task taxonomy, the architecture families, the current
literature with reported numbers, the local data already on disk, and the
decisions taken so far.

All numbers below are reported by the cited sources, not measured here. Nothing in
this repository has been evaluated on a relation extraction task yet.

---

## 1. The constraint that shapes everything

No off-the-shelf model covers the pathway–disease entity pair.

BioRED, BioREx and PubTator 3.0 share one schema: six entity types (gene/protein,
disease, chemical, variant, species, cell line) across eight pairs. Pathway is not
one of them. PubTator 3.0 ships over one billion entity and relation annotations
across ~36M PubMed abstracts and ~6M full-text articles, refreshed weekly, and none
of it answers a pathway–disease question directly.

So the "download and run" option does not exist. Everything below is about which
way to build it.

---

## 2. Four ways to get pathway–disease relations

### Option A — gene-mediated inference

Expand each pathway into its gene set (Recon3D / KEGG / Reactome membership), pull
gene–disease relations from PubTator3 (already precomputed and free), aggregate to
pathway level.

- Works immediately, costs nothing, evidence is already sentence-linked.
- The evidence is a sentence about a *gene*, not about the pathway. An abstract
  saying "glycolysis is upregulated in X" is never captured.
- The aggregation weighting (how many genes, weighted how) has to be invented.
- INDRA does this at mechanism level with belief scores and evidence dedup. iKraph
  processed all of PubMed into ~30M relations (Nature Machine Intelligence 2025) —
  that is simultaneously the baseline and the competitor for this database.

Verdict: keep as a **second channel**, not the main solution.

### Option B — zero/few-shot LLM with ontology-constrained output

Give the model an abstract plus two spans, have it return a predicate. Free-text
output cannot enter a knowledge graph, so the output must be locked to an ontology.

- RELATE (arXiv 2509.19057) does predicate embedding → SapBERT similarity retrieval
  → LLM rerank with explicit negation handling, mapping to Biolink Model predicates.
  52% exact match on ChemProt, 94% accuracy@10, and rejects unrelated associations
  at a 0.4% rate.
- Scenario-based two-stage zero-shot prompting (arXiv 2505.01077) matches supervised
  SOTA on ChemDisGene and CDR with no training data.
- Starts without gold data; adding a relation type is a prompt edit.
- Scanning the whole literature this way is expensive, and without a gold test set
  there is no F1 to report.

### Option C — LLM teacher, encoder student (distillation) — **chosen backbone**

Run a teacher over 10–50k abstracts, produce silver labels, train a
PubMedBERT/BioLinkBERT-class document-level RE model on them, scan millions of
abstracts with the student.

- "Distilling LLMs for Biomedical Knowledge Extraction" (arXiv 2307.06439) shows the
  distilled student beating its teacher at a fraction of the cost.
- KB-refined weak supervision (Database 2023) cleans silver labels against a
  knowledge base — Recon3D/KEGG membership is exactly that resource here.
- The repository is already shaped for this: `train.py`, `encoders.py`,
  `run_matrix.py`, the TRUBA sweep, the frozen split contract. An RE head sits
  alongside the NER pipeline rather than replacing it.
- Encoders remain competitive: BioBERT F1 86.84 vs GPT-4 86.49 on PPI — no clear
  LLM advantage at roughly 1000x the cost.

### Option D — fully supervised document-level RE

Annotate a gold corpus, train an ATLOP/DREEAM-style document-level architecture or
follow BioREx's unified multi-dataset transfer approach.

- 500 abstracts do not train a document-level RE model. The realistic figure is
  2000–5000, depending on positive relation density.
- 4–10x the annotation load, multiple annotators plus adjudication, a calendar
  measured in months.
- In exchange: no teacher bias and a higher ceiling.

### Decision

**C.** The extra ceiling of D does not justify the extra annotation months, and C
already contains D's first step (the gold set). If the silver ceiling turns out to
be too low, D is reached by adding annotation. The reverse direction does not exist.

C and D share the first four steps, so the choice does not have to be final until
the gold set is annotated:

1. Freeze the schema
2. Build candidate pair generation
3. Annotate ~500 abstracts, double-annotated, with IAA reported
4. Write `train_re.py` and the split contract

Only step 5 diverges: C treats the gold as a test set and scales with silver, D
treats it as training data and scales by annotating more.

---

## 3. Taxonomy — how relation extraction gets implemented

"Relation Extraction" is a task name, not an architecture. Four independent axes
determine an implementation; each can be chosen separately.

### Axis 1 — what is given and what is found

| Formulation | Input | Output |
|---|---|---|
| Relation Classification (RC) | Text **plus two entity spans** | One label for that pair |
| Pipeline RE | Text | Entities first, then a label per pair |
| Joint / end-to-end RE | Text | Entities **and** relations in one pass |
| Seq2seq triplet generation | Text | A serialized triplet string, parsed afterwards |
| Open IE | Text | Schema-free `(subject, predicate, object)`, predicate is surface text |

This project is fixed at **RC**: pathway spans come from the existing NER model and
disease spans from PubTator3, so entities arrive from upstream. Moving to a joint
model would discard the existing NER investment.

### Axis 2 — scope

| Scope | Where the relation is sought |
|---|---|
| Sentence-level | One sentence (TACRED, ChemProt) |
| Document-level (DocRE) | Whole abstract; entities may be in different sentences |
| Cross-document | Multiple articles — handled here as database-side aggregation |

This project is **document-level**. This axis, more than model quality, explains
most of the spread in reported numbers (see §5).

Note: graph-based document-level models (GAIN, GEGA) build an entity/sentence graph
and run a GNN over it. ATLOP won with simple localized attention pooling instead, so
the graph branch is not the main line today.

### Axis 3 — how the label is represented

**This axis alone decides whether zero-shot is possible.**

| Method | Where the label lives | Zero-shot | Examples |
|---|---|---|---|
| Fixed softmax head | An `R`-dimensional output layer; meaning learned from scratch | No | Entity-marker BERT, ATLOP, DREEAM |
| Label-as-text (bi-encoder) | Label is text, embedded by a second encoder, matched by similarity | Yes | GLiREL, GLiDRE, GLiNER-Relex |
| Entailment / NLI | Label becomes a hypothesis sentence: "X increases Y" | Yes | Sainz et al. 2021, Ask2Transformers |
| QA | Label becomes a question; the answer span is the entity | Yes | Levy et al. 2017 |
| Cloze / prompt | Label is a `[MASK]` in a template, filled via the MLM head | Yes | PTR, KnowPrompt |
| Generative | Label is generated as free text, then mapped to the schema | Yes | LLM prompting, REBEL, RELATE |

Everything except the fixed softmax head uses the same trick: move the label out of
the output axis and into the input. Once the label is text, the model's language
understanding extends to labels it never trained on.

### Axis 4 — where the labels come from

Zero/one/few-shot belongs **here**. It is a data regime, not an architecture.

| Regime | Labeled examples | Weights change |
|---|---|---|
| Zero-shot | 0 | No |
| One-shot | 1 (or 1 per label) | Depends |
| Few-shot | ~1–100 | Depends |
| Distant supervision | 0 human labels; KB triples aligned to text | Yes |
| Weak / silver supervision | 0 human labels; a teacher model produces them | Yes |
| Fully supervised | Thousands | Yes |

### "Classic RE" defined

Classic RE is one specific point in this space:

> Axis 1: RC · Axis 2: sentence-level · Axis 3: fixed softmax · Axis 4: fully supervised

Input is marker-annotated text, `"@PATHWAY$ ... @DISEASE$"`; output is a softmax over
`K` classes. Each modern variant changes exactly one coordinate:

| System | Deviation from classic |
|---|---|
| ATLOP / DREEAM | Axis 2 → document-level (plus adaptive thresholding, evidence supervision) |
| GLiDRE / GLiREL | Axis 3 → label-as-text (which in turn opens Axis 4 → zero/few-shot) |
| REBEL | Axis 1 → seq2seq triplets, Axis 3 → generative |
| GLiNER-Relex | Axis 1 → joint, Axis 3 → label-as-text |
| NLI-based | Axis 3 → entailment |
| BioREx | Axis 4 → transfer by unifying heterogeneous datasets |
| LLM prompting | Axis 3 → generative, Axis 4 → in-context |

---

## 4. Architectures — and why NER is not one

Two things are routinely conflated. Architecture and task are separate.

### Architecture families

| Family | Attention | Examples | Can | Cannot |
|---|---|---|---|---|
| Encoder-only | Bidirectional — each token sees both sides | BERT, RoBERTa, DeBERTaV3, PubMedBERT, BioLinkBERT | Understand text, emit a vector per token | Generate text |
| Decoder-only | Causal — each token sees only its left | GPT, Llama, Mistral, Qwen, Claude | Predict the next token, i.e. generate | Be bidirectional by construction |
| Encoder-decoder | Bidirectional encoder, causal decoder plus cross-attention | T5, BART, SciFive | Map text to text | — (two stacks, heavier) |

The only real difference is the attention mask. "LLM" in current usage almost always
means decoder-only.

A secondary axis: **cross-encoder** (both inputs concatenated and encoded together —
ATLOP, DREEAM, classic RE) versus **bi-encoder** (inputs encoded separately, vectors
compared — GLiDRE, GLiREL, GLiNER). GLiDRE is encoder-only but runs *two* of them:
one over the document, one over the label text.

### Tasks, and where NER sits

| Task | Technical name | Output shape | Typical architecture |
|---|---|---|---|
| NER | Token classification | A label per token (B-PATHWAY, I-PATHWAY, O) | Encoder-only |
| Relation Extraction | Sequence classification | One label per text or per pair | Encoder-only |
| Extractive QA | Span prediction | Start and end index | Encoder-only |
| Summarization, translation | Seq2seq / generation | Free text | Decoder-only or encoder-decoder |
| Semantic search | Embedding / retrieval | A single vector | Encoder-only |

NER and RE are in the **same column**. Both are the natural work of an encoder-only
model; they differ only in the output head. `train.py` uses
`AutoModelForTokenClassification` (NER); an RE trainer would use
`AutoModelForSequenceClassification`. Same body, different top layer.

### The four input/output formulations in concrete terms

**1. Pair classification with entity markers** — the classic encoder route:

```
Input:  "Upregulated @PATHWAY$glutaminolysis$@ drives tumor
         proliferation in @DISEASE$glioblastoma$@."
Output: positive_regulation   (softmax over K classes)
```

Entities are given; the model only answers "what holds between these two". Three
pathways and two diseases in one abstract means six forward passes.

**2. All-pairs / table filling** — the ATLOP and DREEAM line:

```
Input:  the whole abstract plus the entity list (spans and types)
Output: an N x N x R score matrix over (entity_i, entity_j, relation_r)
```

One forward pass for every pair. ATLOP contributes localized context pooling and
adaptive thresholding (a learned per-pair threshold instead of a fixed 0.5, so one
pair can carry several relations). DREEAM adds evidence-sentence supervision.

**3. Generative / multiple-choice** — the LLM route:

```
Input:  abstract plus "Which relation holds between Gene X and Disease Y?
         (a) causative mutation (b) increased expression (c) therapeutic target ..."
Output: free text, parsed back into a label
```

Unconstrained output does not land on an ontology; this is why RELATE pins its
output to Biolink predicates.

**4. Bi-encoder label matching** — GLiREL / GLiDRE / GLiNER-Relex:

```
Input:  text plus the relation labels themselves as text
        ("causes", "treats", "positively regulates")
Output: similarity between the entity-pair vector and the label vector
```

The label set is supplied at inference, not frozen at training. New predicates need
no retraining. GLiNER-Relex extends this to entities as well, returning entities and
triplets in a single call.

### Few-shot means two different things

| | In-context few-shot | Gradient few-shot |
|---|---|---|
| Where the examples go | Into the prompt | Into a training loop |
| Weights | Unchanged | Updated |
| Persistent | No — resent on every call | Yes — a checkpoint is produced |
| Who does it | Decoder-only LLM | Encoder-only model (GLiDRE, ATLOP), NLI model |
| Cost | Context consumed on every inference | One-off, minutes on a single GPU |

The "1 / 10 / 100 / 1000 examples" rows in §5 are the right-hand column: actual
gradient descent on that many annotated documents.

Two evaluation protocols are also easily confused:

- **N-way K-shot** (FewRel): N candidate relations at test time, K examples each.
- **ZS-RE `m`** (Wiki-ZSL / FewRel zero-shot setup): `m` is the number of *unseen*
  relations offered at test time. Larger `m` is harder.

Finally: zero-shot never means "never trained". The NLI route uses an entailment
engine trained on MNLI; GLiDRE was pretrained on 136k synthetic documents. What is
zero is the number of labels *in our schema*.

---

## 5. Current landscape, with reported numbers

### PubTator 3.0 + BioREx — the only thing available ready-made

BioREx is a unified model extracting 12 relation types across 8 entity-type pairs,
gene/protein–disease included. Precomputed over ~36M abstracts and ~6M full texts,
updated weekly, queryable via API. For protein–disease questions no training is
needed. For pathway–disease it offers nothing.

### BioTriplex (Bioinformatics, 2026) — closest published analogue

The freshest gold corpus in this area and the study whose design most resembles this
project.

Corpus: 100 **full-text** papers, 604 subsections, 21,745 sentences, 586,781 words.
15,056 gene mentions, 7,133 disease mentions, 781 relation instances across 21
subtypes, 1,217 linked triplets. Schema: five categories — disease causing, disease
modulating, gene expression, diagnosis, therapy — with fine-grained subtypes such as
"causative mutation", "increased expression", "therapeutic target".

Task format: input is text with pre-identified gene and disease entities; output is
the relation type, formulated generatively as a multiple-choice question.

| Approach | Relation F1 |
|---|---|
| Fine-tuned LLaMA 3.1 8B | 0.63 (subtypes) / 0.68 (groups) |
| BioBERT, supervised | 0.57 |
| Claude 3.7, few-shot | 0.54 |
| GPT-4, few-shot | 0.40 |
| LLaMA 3.1, zero-shot | 0.22 |

Entity NER F1 in the same study: genes 0.90, diseases 0.81.

Three readings, all relevant to the C-versus-D decision:

1. Zero-shot alone is not usable (0.22); few-shot is a large jump (0.54).
2. A fine-tuned small model beats a prompted large one — the core bet behind C.
3. The absolute numbers are low. Relation F1 of 0.63 sits far below the NER F1 of
   0.90/0.81 in the same corpus. RE is structurally harder than NER; expecting RE
   numbers comparable to the existing pathway NER scores would be a mistake.

### GLiDRE (arXiv 2508.00757, 2025) — document-level, low-resource

Compact bi-encoder recasting document-level RE as representation matching.
Backbone: DeBERTaV3-Large for the document, BGE-Large V1.5 for labels, ~800M
parameters total. Pretrained on 136,404 documents with 76,497 unique relation types,
synthetically annotated by Mistral-Small-24B-Instruct-2501 over FineWeb samples.

Zero-shot on Re-DocRED: **17.32 F1** (Ign F1 16.41), against Llama 3.3 70B at 15.81,
Mistral-Small 24B at 14.38, Qwen 2.5 72B at 18.00, Mistral-Large 123B at 18.61.
"Competitive with large LLMs" is accurate but is not praise — everything is weak in
that regime.

Few-shot on Re-DocRED:

| Training examples | GLiDRE | ATLOP | DREEAM |
|---|---|---|---|
| 1 | 24.45 | 4.32 | 4.27 |
| 10 | 41.73 | 29.48 | 27.07 |
| 100 | 60.04 | 57.17 | 58.14 |
| 1000 | 72.09 | 71.70 | 71.67 |

Fully supervised: GLiDRE 77.83, TTM-RE 79.95, DREEAM 80.20.

Two things follow. First, the shape of the curve: the first 100 examples move the
model from 17 to 60; the next 900 move it from 60 to 72. Second, GLiDRE's advantage
is confined to the low-data regime — by 1000 examples it has converged to ATLOP.
The reason ATLOP scores 4.32 at one example is that its output layer is randomly
initialized: the meaning of each relation neuron must be learned from data. GLiDRE
starts from a pretrained matching ability, so a handful of examples *calibrate*
rather than teach.

Stated limitations: quadratic growth of negative pairs with entity density; ~512
token maximum sequence length; independent entity-pair scoring with no inter-label
interaction; and it assumes gold entities and coreference chains, requiring upstream
modules.

### GLiREL (arXiv 2501.03172) — sentence-level, zero-shot

Trained on 63,493 synthetic texts with 25,619,624 annotated relations generated by
Mistral 7B-Instruct over FineWeb, with any label intersecting a benchmark label
discarded to preserve the zero-shot setting.

| Benchmark | m=5 | m=15 |
|---|---|---|
| FewRel | 94.20 | 84.48 |
| Wiki-ZSL | 83.28 | 73.91 |

Outperforms GPT-4o at every value of `m`. Requires entity spans as input. Operates
at sentence level; a document-level extension via windowing and coreference
clustering appears in the appendix.

Limitations: the number of labels per instance is bounded by DeBERTa's 512-token
limit; performance is sensitive to the order and number of labels supplied.

**The 17 versus 94 gap is the single most important comparison in this document.**
Same model family, same idea, an order of magnitude apart. The difference is not
model quality — it is how constrained the task is. Document-level with DocRED's 96
relation types gives 17; sentence-level with 5 candidates gives 94.

### GLiNER-Relex (arXiv 2605.10108, 2026) — joint NER and RE

A shared bidirectional transformer encoder jointly represents text, entity type
labels and relation type labels; entity-pair representations are built from
recognized spans and scored by a dedicated relation module. Entity and relation
types are specified at inference; entities and triplets are returned in one call.
Evaluated on CoNLL04, DocRED, FewRel and CrossRE. Open source, with a Python package.

### Entailment-based RE (Sainz et al., EMNLP 2021)

Relations are verbalized into hypothesis templates and scored by a pretrained
textual entailment engine, used as-is or fine-tuned.

On TACRED: **63 F1 zero-shot**, **69 F1 with 16 examples per relation** — 17 points
above the best supervised system under the same conditions, and 4 points short of
SOTA, which uses 20x more training data. Verbalizations take under 15 minutes per
relation to write.

Note the same trap as above: TACRED is sentence-level. Most of the gap to GLiDRE's
17.32 comes from Axis 2, not Axis 3.

### Others worth knowing

- **REBEL** — BART-based seq2seq triplet extraction over 200+ relation types,
  trained on a large distantly supervised dataset. BioGPT reports an 8.28%
  improvement over it on biomedical RE.
- **Zero-shot doc-level biomedical RE via scenario-based prompting**
  (arXiv 2505.01077) — matches supervised SOTA on ChemDisGene and CDR with no
  training data. The most current reference for Option B.
- **iKraph** (Nature Machine Intelligence 2025) — all of PubMed processed into ~30M
  relations with probabilistic semantic reasoning. Both baseline and competitor.
- **INDRA** — mechanism-level assembly with belief scores and evidence dedup; the
  reference model for the evidence-database design in §8.

---

## 6. Local data already on disk

Scanned `/home/enes/projects/yl` (1.1 GB) on 2026-08-11.

### Directly usable: a candidate-pair corpus

`pubmed_api/extracted_disease_pathway_db_disease_pathway_just_abstracts.json`

450 records with fields `disease, pathway, abstract, pubmed_link, pmid,
mesh_descriptors`. 413 unique PMIDs, 75 distinct pathways, one empty abstract.

| Disease | Records |
|---|---|
| Breast Cancer | 205 |
| Colon Cancer | 171 |
| Clear Cell Carcinoma | 54 |
| Pancreas Cancer | 20 |

This is a candidate-pair generator output, not a curated positive set. Per
`pubmed_api/fetch_article.py`, pairs were produced by the PubMed query
`"{pathway}"[ab] AND "{disease}"[ab]` with at most 3 articles per pathway×disease
pair. Co-occurrence is guaranteed; a relation claim is not. `no_relation` instances
are therefore naturally present, which is the correct distribution shape for
annotation.

The seven-record file `..._disease_pathway.json` is an earlier pilot of the same
schema. `fetch_article.py` also contains a mock LLM stub for UP/DOWN extraction that
was never implemented — an unbuilt sketch of Option B.

**Known bias.** The retrieval query matches the Recon3D subsystem name verbatim, so
in these 450 abstracts the pathway is always mentioned in canonical form. The point
of the NER model is to catch non-canonical mentions. A gold set drawn only from here
would measure RE on a slice where grounding is already solved, while the deployed
pipeline will feed it NER spans from a different distribution. This hurts C more
than D: if the teacher also runs on this corpus, the entire silver set inherits the
bias and the student learns it permanently.

### Grounding resources

- `useful_scripts/recon3d_processed.csv` — Reaction_ID, Reaction_Name, Pathway,
  Genes, Metabolites, Equation. The pathway normalization table.
- `pubmed_api/grouped_pathways.json` — 98 pathways mapped to reaction IDs and names.
  The input side of Option A.
- `process_recon/`, `process_human2_gem/` — Recon3D and Human-GEM subsystem
  extraction; the two subsystem lists differ.

### Disease grounding is not solved by this data

`mesh_descriptors` is non-empty in 332 of 450 records, but it holds **article-level
MeSH headings** ("Humans", "Female", "*Midazolam/pharmacokinetics/...") — not
span-linked disease annotations. There is no mapping from a MeSH term to the disease
mention in the sentence, so `disease_id` cannot be derived from it. Disease NER plus
normalization remains open; PubTator3 supplies offsets and MeSH IDs together and is
the preferred source.

### Other contents

`NER/bert_model` (config, safetensors, tokenizer), `NER/pathway_ner/scispacy.py`,
`NER/ner_results*.json`, and `process_xml/` (562 MB of PubMed XML plus per-pathway
result files).

---

## 7. Schema

Frozen in `doccano/RELATION_SCHEMA.md` (commit `6944b98`). Three annotated fields.

**`label`** — `no_relation`, `association`, `positive_regulation`,
`negative_regulation`. Fall back to `association` when the sign is not explicit; do
not infer sign from background knowledge.

**`direction`** — `pathway_to_disease`, `disease_to_pathway`, `undirected`. Default
is `undirected`; a direction is assigned only when a regulatory or causal verb has an
unambiguous subject. Observational phrasing ("is elevated in", "is dysregulated in")
is `undirected` by rule — the most frequent pattern in abstracts and the biggest
source of annotator disagreement. A high `undirected` share (50–70%) is expected and
correct.

**`negated`** — boolean, true when the abstract asserts the relation does *not*
hold. Negation marks the claim rather than erasing it: `no_relation` means the
abstract is silent, `negated: true` means it makes an explicit claim of absence, and
both are useful evidence. Negation must scope over the relation itself, not over an
entity ("non-small cell lung cancer") or a subgroup ("patients who did not respond").
Hedging (*may contribute*, *suggests*) is not negation and is not a separate field in
this version.

`direction` and `negated` are annotated only when `label != no_relation`.

### Why direction was included

It is not in the original target statement — `project_tracking.md:6` says
"pathway↔disease associations" and `annotation_handoff.md:7` says "pathway↔disease
database", both undirected. Adding it widens the scope deliberately, for three
reasons:

1. The asymmetry is real and says different things to a user. "Glycolysis drives
   tumor growth" is a mechanism claim and a drug-target candidate; "glycolysis is
   elevated in tumor tissue" is a biomarker observation. Collapsing them leaves the
   product saying only "this pathway is mentioned in this disease" — which is what a
   PubMed co-occurrence query already returns.
2. Cost asymmetry. At annotation time direction is one extra decision on a sentence
   already read. Added later it means re-annotating all gold, because it cannot be
   recovered from the stored answer. BioRED fell into exactly this trap and needed a
   later directionality study (PMC12261447) to repair it.
3. Downstream fit. Biolink predicates are subject–object typed; undirected data
   would force the direction to be invented at mapping time.

The counter-argument is honest: direction is the field that lowers IAA. The three
rules above (default undirected, subject-of-verb, observational-is-undirected) exist
to contain that.

### Modelling consequence

`label`, `direction` and `negated` are three separate prediction targets sharing one
encoder — not one cross-product label. A cross-product would produce 24 sparse
classes, several of which would never see enough examples. `negated` in particular is
a rare positive class and needs its own head to be measurable at all.

This is worth noting against Axis 3: label-as-text methods (NLI, generative,
bi-encoder) express all three fields for free, as separate hypothesis strings
("X increases Y" / "Y increases X" / "X does not increase Y"). A fixed softmax head
must either cross-product or carry three heads. The three-field schema fits
label-as-text architectures more naturally.

### Pilot requirement

Compute IAA separately for `label` and `direction` on the first 50 doubly annotated
abstracts. A `direction` kappa below 0.6 means the rules are underspecified and must
be repaired before scaling. For `negated`, report the raw disagreement count instead
of kappa — the positive class is too rare for kappa to be stable at that sample size.

---

## 8. Evidence database design

One row is one *statement* with many *evidence* records. Following INDRA: merge
repetitions of the same claim, attach PMID, sentence and confidence to each
occurrence, and compute a statement-level belief score from the number of
independent sources and reader confidence. iKraph does the same at scale with
probabilistic semantic reasoning.

A claim supported by one paper and a claim repeated across forty cannot occupy
equivalent rows, or the database is unusable.

Two fields are non-negotiable for this to work: `evidence_sentence` (character
offsets of the sentence carrying the relation — this *is* the "show the evidence"
part of the product) and normalized `pathway_id` / `disease_id`. An unnormalized
pair cannot enter the database; linking accuracy, not NER F1, sets the ceiling on
database quality.

---

## 9. Applicable configurations for this project

Axes 1 and 2 are fixed (RC, document-level). Axes 3 and 4 remain open:

| Configuration | Axis 3 | Axis 4 | When it makes sense |
|---|---|---|---|
| Entity markers + 3 heads | Fixed softmax | Silver + gold | The C student; the eventual scanning model |
| GLiDRE few-shot | Label-as-text | 100–500 gold | Early signal, local, cheap; also a teacher candidate |
| NLI / verbalization | Entailment | 0–16 per label | Cheapest baseline to write — 4 labels, 4 templates, ~1 hour |
| LLM few-shot, ontology-constrained | Generative | In-context | Silver teacher; expensive but most flexible |
| Distant supervision | Any | Recon3D/KEGG membership | An additional silver channel; Option A facing RE |

On expectations: this project sits between the two extremes of §5. Document-level
counts against it. In its favour: four labels rather than 96, and a single entity-type
pair rather than every combination. Against it again: both GLiREL and GLiDRE were
pretrained on FineWeb web text and benchmarked on Wikipedia. PubMed abstracts are
neither that language nor that entity distribution, and Recon3D pathway names are
effectively absent from their pretraining. Whether zero-shot lands nearer 17 or 60
cannot be predicted — and measuring it requires the gold set anyway. Zero-shot is
not a way to avoid annotation; the gold set was always needed for *measurement*.

---

## 10. Open decisions

1. **Candidate pair source for the gold set.** The existing 450 pairs, or running
   the NER model over abstracts and taking the resulting spans? The second is more
   work but measures what the pipeline will actually see (§6).
2. **Disease coverage.** Keep the four cancers, or widen the gold set to more
   diseases from the start?
3. **Disease NER source.** PubTator3 API (offsets plus MeSH IDs, ready) or a local
   model?
4. **Pathway grounding scope.** Recon3D metabolic subsystems only, or do signalling
   pathways (`PI3K/AKT signaling`) count? The annotation guide needs the boundary
   written down.
5. **`runs/summary.jsonl` collision.** RE results in the same append-only file as
   NER results will conflict on merge between branches. Separate summary file, or
   keep merges one-directional?

---

## Sources

- [BioTriplex: a full-text annotated corpus for gene–disease relation extraction (Bioinformatics 2026)](https://academic.oup.com/bioinformatics/article/42/2/btag037/8435810)
- [GLiDRE: Generalist Lightweight model for Document-level Relation Extraction](https://arxiv.org/abs/2508.00757)
- [GLiREL: Generalist Model for Zero-Shot Relation Extraction](https://arxiv.org/abs/2501.03172)
- [GLiNER-Relex: A Unified Framework for Joint NER and Relation Extraction](https://arxiv.org/abs/2605.10108)
- [Label Verbalization and Entailment for Zero- and Few-Shot Relation Extraction (Sainz et al., EMNLP 2021)](https://aclanthology.org/2021.emnlp-main.92/)
- [REBEL: Relation Extraction By End-to-end Language generation](https://aclanthology.org/2021.findings-emnlp.204/)
- [ZS4IE: Zero-Shot Information Extraction with simple Verbalizations](https://arxiv.org/pdf/2203.13602)
- [Revisiting Relation Extraction in the era of Large Language Models](https://arxiv.org/pdf/2305.05003)
- [RELATE: Relation Extraction in Biomedical Abstracts with LLMs and Ontology Constraints](https://arxiv.org/abs/2509.19057)
- [Zero-Shot Document-Level Biomedical RE via Scenario-based Prompt Design](https://arxiv.org/pdf/2505.01077)
- [BioREx: Improving Biomedical Relation Extraction by Leveraging Heterogeneous Datasets](https://arxiv.org/abs/2306.11189)
- [BioRED: A Rich Biomedical Relation Extraction Dataset](https://arxiv.org/pdf/2204.04263)
- [PubTator 3.0: an AI-powered Literature Resource](https://arxiv.org/pdf/2401.11048)
- [Enhancing biomedical relation extraction with directionality (PMC12261447)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12261447/)
- [iKraph (Nature Machine Intelligence 2025)](https://www.nature.com/articles/s42256-025-01014-w)
- [INDRA — automated assembly of molecular mechanisms at scale](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10167483/)
- [Distilling LLMs for Biomedical Knowledge Extraction](https://arxiv.org/pdf/2307.06439)
- [Biomedical RE with knowledge base–refined weak supervision](https://academic.oup.com/database/article/doi/10.1093/database/baad054/7238699)
- [GPT vs BERT for PPI identification](https://academic.oup.com/bioinformaticsadvances/article/4/1/vbae133/7755482)
- [Document-Level RE with Global Relations (ACL Findings 2025)](https://aclanthology.org/2025.findings-acl.1002.pdf)
