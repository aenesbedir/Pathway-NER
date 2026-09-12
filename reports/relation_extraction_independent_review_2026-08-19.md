# Pathway–Disease Relation Extraction — Independent Review

**Schema revision, 2026-08-20.** The label set was cut to three mutually exclusive
classes — `upregulation`, `downregulation`, `no_relation`. `association` is removed,
`direction` is removed. See §2.0 for what this changes; passages elsewhere in this
document were written against the four-label schema and are updated in place.

Date: 2026-08-19. Written independently of
`reports/relation_extraction_survey_2026-08-11.md`; overlaps are noted, and the
places where this review disagrees with it are marked explicitly.

Assumption for the whole document: disease NER and pathway NER are solved, and the
pipeline hands us abstracts with typed, offset-annotated spans. The open problem is
what to do with a `(pathway span, disease span, abstract)` triple.

---

## 0. What the product actually is, and why that changes the model choice

The deliverable is not a benchmark score. It is a database row:

    pathway_id, disease_id, label, pmid, evidence_sentence, confidence

with `label ∈ {upregulation, downregulation, no_relation}`.

A database that a biologist will read as a claim about the literature. That has one
consequence that dominates every design decision below:

**This is a precision-first, abstain-allowed task, not a balanced-F1 task.**

A wrong row is worse than a missing row, because a missing row is invisible while a
wrong row is cited. The literature is large enough (10k abstracts here, ~37M in
PubMed) that recall lost on one abstract is usually recovered from another abstract
making the same claim. Redundancy is the property that a corpus-scale extraction
task has and a benchmark does not.

Practical form of this: every design below must produce a calibrated score and an
`uncertain` bucket, and the reported quality metric should be
**precision at a fixed recall / coverage point**, not micro-F1. A system at P=0.90
covering 40% of candidate pairs is a shippable database. A system at F1=0.62 with
unknown precision is not.

The 2026-08-11 survey settled on micro/macro-F1 framing throughout. That is the main
methodological disagreement in this document.

Second consequence: **aggregation across abstracts is part of the model, not a
post-processing detail.** A pathway–disease pair supported by 9 abstracts with
consistent sign is a different object from a pair supported by 1 hedged sentence.
Per-pair confidence should be computed from the evidence set (count, sign agreement,
per-instance calibrated probability), and that aggregation absorbs a lot of
per-instance error. A per-instance model that is only mediocre can still yield a
high-precision pair-level database. Design the schema so this is possible: store
instances, derive pairs.

---

## 1. Can we reuse an existing model? (Q1)

Three different meanings of "reuse", with three different answers.

### 1a. Reuse a trained drug–disease / gene–disease RE model as-is — **no**

The blocker is not domain, it is the schema. BioRED / BioREx / PubTator 3.0 are all
built over the same closed set of six entity types — gene/protein, disease,
chemical, variant, species, cell line — and a fixed inventory of typed pairs.
`pathway` is not an entity type in any of them, and the classification head is a
fixed softmax over that inventory. Feeding it a pathway span means feeding it an
out-of-schema entity; the output is not wrong so much as undefined.

The same holds for the newest specialised work: `Drug-ACE` (arXiv 2606.14031)
annotates 1,119 drug–disease pairs with *applicability conditions* and improves LoRA
to exploit the drug–disease relation — a good paper, and a completely different
entity pair with a completely different label space. There is nothing to transfer
but the recipe.

So: no drop-in model exists. This agrees with the earlier survey's §1.

### 1a-bis. Feed the pathway span to a gene–disease model as a *surrogate gene* — **testable, and worth one hour**

The obvious follow-up to "no drop-in model exists" is: can we not simply put the
pathway span where the drug or gene span is supposed to go, and let the model run?
Mechanically, yes — and it deserves a measurement rather than a dismissal.

**Why it is mechanically possible.** BioREx input is already entity-masked: spans are
replaced with type placeholders such as `@GENE$` and `@DISEASE$` before encoding.
Nothing validates that the text under `@GENE$` is biologically a gene. The model
receives tensors and never checks the semantics of the type string.

The label space also lines up better than expected. BioREx shares one relation
inventory across all eight entity pairs — `Association`, `Positive_Correlation`,
`Negative_Correlation`, `Bind`, `Drug_Interaction`, `Cotreatment`, `Comparison`,
`Conversion`. Under the three-label schema the mapping is now exact rather than
partial: `upregulation` → `Positive_Correlation`, `downregulation` →
`Negative_Correlation`, everything else → `no_relation`. BioREx's `Association` class,
which previously absorbed our `association` label, now folds into `no_relation` —
which makes the surrogate probe a **cleaner** experiment than it was, since a mapping
that discards a class is easier to interpret than one that splits it.

**Four independent reasons it still degrades.**

1. **The type token is a feature, not decoration.** The model is conditioned on gene
   semantics in the `@GENE$` slot: a short uppercase symbol, surrounded by
   "expression of", "mutation in", "knockdown of". Pathways are multi-word noun
   phrases appearing with different verbs ("flux through X", "X is dysregulated in").
   Masking hides the span but **does not hide the surrounding context** — that is
   where the loss happens, and masking cannot repair it.
2. **Calibration collapses.** Probabilities produced under distribution shift are not
   meaningful, and §0 requires a calibrated score to write a database row at all.
3. ~~It supplies one head out of three.~~ **No longer an objection.** With `direction`
   and `negated` gone, the schema is a single 3-way label, and BioREx's
   `Positive_Correlation` / `Negative_Correlation` distinction is exactly that label.
   The surrogate probe now covers the whole task rather than a third of it, which
   raises its expected value and is a direct argument for running it in Step 1.
4. **PubTator 3.0's precomputed relations are unusable for this.** They are keyed at
   concept-ID level and pathways have no MeSH/NCBI identifier. The model has to be
   run locally on our own masked text; there is no annotation to download.

**Practical choice.** Use `@GENE$` as the surrogate type, not `@CHEMICAL$`:
gene–disease is BioRED's most densely trained pair, and the regulation verbs we care
about (upregulate, inhibit, activate) occur most often in gene context.

Add this as a **fourth baseline in the Step 1 probe** (§5), alongside NLI, GLiDRE and
LLM few-shot. Cost is roughly an hour, and it yields one precision number directly
comparable with the other three on the same 100 items. If it lands well it is a free
silver channel; if not it is eliminated in a day. Expectation — a prediction, not a
measurement — is tolerable on `Association` and weak on the
`Positive_Correlation` / `Negative_Correlation` distinction, which is exactly the
distinction the product needs.

**The less deceptive variant, using the same model.** Instead of masking a pathway as
a gene, expand the pathway into its member genes, run the real gene–disease model on
real genes, and aggregate to pathway level. No schema violation, model stays inside
its own distribution. This is §1c seen from the model side rather than the KB side.
Running both on the same 100 probe items is more informative than either alone: where
they diverge shows directly what the masking trick loses.

### 1b. Reuse *pair-agnostic* zero-shot RE models — **yes, as a baseline and possibly a teacher**

These take the relation label as *text*, not as a softmax index, so a new entity pair
costs a prompt, not a retrain:

- **GLiREL** (NAACL 2025, arXiv 2501.03172) — sentence-level, one forward pass for all
  pairs; SOTA on FewRel / WikiZSL.
- **GLiDRE** (arXiv 2508.00757) — document-level variant, which is the scope we need.
- **NLI / label verbalization** (Sainz et al., EMNLP 2021) — turns each label into a
  hypothesis string, uses an off-the-shelf entailment model. Roughly an hour of work
  to implement, four templates.
- **LLM few-shot with a constrained output schema.**

Caveat that must be stated up front: GLiREL and GLiDRE were pretrained on FineWeb web
text and benchmarked on Wikipedia-derived data. Recon3D subsystem names are
effectively absent from that pretraining. Their zero-shot transfer to PubMed abstracts
is unmeasured, and there is no published biomedical evaluation of GLiREL that I could
find. Treat their reported numbers as irrelevant to us and measure locally.

For the LLM route, the numbers we do have are directly informative.
**Few-Shot Biomedical RE with LLMs** (arXiv 2606.15412, BioREDirect):

| Setting | micro-F1 | macro-F1 |
|---|---|---|
| Best prompt-based (few-shot LLM) | 0.44 | **0.45** |
| Prior few-shot SOTA | 0.34 | — |
| Supervised baseline | **0.56** | 0.38 |

Two readings matter here:

1. Few-shot LLM still trails supervised on micro-F1 by ~12 points. Prompting is not a
   substitute for training data.
2. Few-shot LLM **beats** supervised on macro-F1, i.e. on the rare relation types.
   This argument weakens under the three-label schema — there is no long tail of rare
   classes left, only a `downregulation` class that will be perhaps 2–3× rarer than
   `upregulation`. Keep it as a reason to check macro-F1 alongside precision, not as a
   reason to keep an LLM permanently in the loop.

The same paper also reports the pairwise-vs-joint trade-off: pairwise classification
(one call per entity pair) gets higher recall; joint generation (extract all relations
in one call) is more precise and much cheaper. Given §0, **joint generation is the
right default for a precision-first database**, with pairwise reserved for a recall
sweep on high-value pairs.

### 1c. Reuse the *gene layer* that already exists at scale — **underrated, and my main addition**

Pathways are gene sets. PubTator 3.0 already ships gene–disease relations over ~36M
abstracts, refreshed weekly, entity-linked, free. Recon3D/KEGG/Reactome already map
pathways to genes. Compose them and you get a pathway–disease signal with no model
at all:

    pathway --(membership, from Recon3D/KEGG)--> genes --(relation, from PubTator3)--> disease

The 2026-08-11 survey listed this as "Option A" and dismissed it in favour of
distillation. I think that dismissal was correct *as a replacement* and wrong *as a
component*. Gene-mediated inference cannot be the product — it produces
`pathway X is implicated in disease Y` with no sentence to quote, no sign, and
severe false positives from promiscuous genes (TP53 is in everything). But it is
excellent as three other things:

1. **A candidate ranker.** Which pathway–disease pairs are worth reading at all.
   Cuts the candidate space before any expensive model runs.
2. **A distant-supervision channel.** ChemDisGene (arXiv 2204.06584) and the
   DisGeNET-derived GDA corpus are the precedents: label abstracts by KB membership,
   accept the noise, use the volume. Cheap silver at a scale annotation can't reach.
3. **A disagreement detector.** Where the gene-mediated prior says "strong link" and
   the text model says `no_relation`, one of them is wrong. That set is the highest
   value-per-hour annotation queue we will ever have — far better than random
   sampling for finding model failure modes.

Concretely available and worth wiring up early: KEGG DISEASE (disease→gene/pathway),
DisGeNET (gene–disease, curated + literature-derived, with scores), Reactome and
WikiPathways (pathway→gene), CTD/ChemDisGene (distant-supervision precedent),
PubTator 3.0 API (gene and disease spans with MeSH/NCBI IDs, plus relations).

---

## 2. How to fine-tune our own model (Q2)

### The formulation, stated concretely

Input: abstract with the two target spans marked. Standard entity-marker approach:

    ... upregulation of [P] glycolysis [/P] was observed in [D] breast cancer [/D] tissue ...

Encode, take the two marker-start hidden states, concatenate, classify. This is the
strongest cheap baseline for document-level RE and it is the same encoder family
already tuned in this repo for NER, so the training harness, split contract, and
`test_results.json` conventions carry over. That is a real cost saving and an argument
for it over anything exotic.

### 2.0 The schema, as revised

One field, three mutually exclusive values:

| Label | Meaning |
|---|---|
| `upregulation` | the abstract asserts the pathway's activity/expression is **increased** in the disease context |
| `downregulation` | the abstract asserts it is **decreased** |
| `no_relation` | the abstract asserts neither — co-mention only, or a claim with no sign |

Removed: `association` (the unsigned relation class) and `direction`
(`pathway_to_disease` / `disease_to_pathway` / `undirected`).

**This is a smaller schema, but it is not merely the old one with fields deleted — it
changes what the label means, and mostly for the better.**

Under the four-label schema, `positive_regulation` was a *causal* claim and
`direction` carried the subject–object asymmetry. That is what made `direction` the
IAA-killing field, and it is why observational phrasing ("glycolysis is elevated in
tumor tissue") had to be routed to `association` + `undirected` — a 50–70% majority
of instances landing in the least informative cell of the schema.

With direction gone, the natural reading of `upregulation` shifts from *"the pathway
causes the disease by being up"* to **"the pathway is up in this disease"** — a state
claim, not a causal one. Observational phrasing, which is the dominant phrasing in
abstracts, is now the *central* case of the schema rather than an awkward exception.
The annotator question becomes "does this abstract say the pathway goes up or down in
this disease?", which is a far more answerable question than "which entity is the
subject of the regulatory verb?".

Predicted consequences, which the pilot must check rather than assume:

- **IAA should go up, materially.** The two hardest decisions (assign a direction;
  distinguish `association` from a weak `positive_regulation`) are both gone.
- **The `no_relation` class grows.** Everything that used to be `association` —
  co-mention, unsigned mechanistic discussion, "X plays a role in Y" — now falls to
  `no_relation` unless a sign is stated. Expect `no_relation` to be the majority
  class, plausibly 60–75% of candidate pairs.
- **Some real information is discarded.** "PI3K/AKT signaling plays a central role in
  breast cancer" becomes `no_relation`, which is a claim the literature clearly makes
  and the database will no longer carry. That is the accepted cost of the revision.
  If it later matters, `association` can be **added back as a fourth class without
  re-annotating** the existing gold — the up/down instances keep their labels, and only
  the `no_relation` pool needs a second pass. Removing `direction`, by contrast, is not
  reversible in that way; re-adding it means re-reading every positive instance.
- **Direction is recoverable in aggregate, not per-instance.** For a downstream
  Biolink-style mapping, a pathway consistently `upregulation` across many abstracts
  for one disease supports a directed edge better than any single sentence did.

### Heads: one, not three

`label` as a single 3-way softmax over one encoder. The earlier three-head design
(and the argument against the 24-class cross-product) is obsolete — there is no
cross-product left to avoid.

Two direct benefits beyond simplicity: the class-imbalance problem shrinks to one
axis instead of three, and every architecture in §1b expresses this schema natively.
An NLI baseline needs exactly two hypothesis templates ("pathway X is increased in
disease Y" / "pathway X is decreased in disease Y") with `no_relation` as the
below-threshold fallback — that is now roughly a 30-minute baseline, not an hour.

One addition retained: **store a `confidence` and allow an `abstain` outcome at
inference**, per §0. Not an annotation-schema change — an inference-time threshold
calibrated on dev. With three classes and a precision-first target, the natural
policy is: emit a row only when the argmax is `upregulation` or `downregulation`
*and* its probability clears the calibrated threshold; everything else is silence.

### The one field the revision leaves undecided: `negated`

The instruction cut `association` and `direction` and did not mention `negated`.
Proceeding on this assumption, which should be confirmed:

**`negated` is dropped as a prediction target for v1.** An explicit absence claim
("inhibition of glycolysis did **not** affect tumor growth") is annotated
`no_relation`, with a free-text annotator note recording that it was an explicit
negation rather than silence.

Reasoning: `negated: true` was already the rarest class — perhaps 8 instances in a
120-instance test set, too few to measure. Keeping it as a second head would
reintroduce the multi-head complexity the revision just removed, in service of a
target we cannot evaluate. Keeping the annotator note costs nothing and means the
instances can be recovered later if the class ever becomes worth training on.

The cost is honest: `no_relation` now conflates "the abstract is silent" with "the
abstract says it does not happen". Those are different evidence and a mature database
would distinguish them. For v1, with no way to measure the rare class, they are
merged.

### The trap this repo has already fallen into once, in a new form

CLAUDE.md documents the 2026-07-31 `biomedbert-base` non-reproduction: 0.8199 recorded,
0.7662 / 0.7736 on replicate. RE runs will be *noisier* than NER runs, because the
label distribution is skewed and the eval set will be small (a 500-abstract gold set
gives maybe 120 test instances, of which — with `no_relation` at 60–75% —
`downregulation` might be 10–15). A 3-point F1 difference on that test set is noise,
full stop. The revision reduces the number of things being measured but does **not**
fix this: the binding constraint is test-set size, and `downregulation` remains the
class that will drive the variance.

Therefore, before any RE sweep starts:
- **report bootstrap confidence intervals on every RE metric**, not point estimates;
- **run ≥3 seeds per configuration** and report the spread — a single-seed RE number
  on 120 instances is not evidence;
- keep the pipeline-clean-tree rule; RE adds `train_re.py` and the candidate generator
  to the set of files that must be committed before a recorded run.

Also: `runs/summary.jsonl` will collide between NER and RE branches. Use a separate
`runs/summary_re.jsonl`. This was open decision #5 in the previous survey; there is no
reason to leave it open, the append-only merge conflict is certain.

---

## 3. Can we build the dataset with LLMs? (Q3)

Split this into three sub-questions that get different answers.

### 3a. LLM-*generated* (synthetic) abstracts — **no**

Do not have an LLM write abstract-like text to train on. The failure mode is
documented and specific: synthetic data inherits the teacher's free-form generation
bias, and for schema-constrained relation extraction the performance curve
**rises with volume and then falls** — past a threshold, low-quality synthetic
examples actively hurt. Our text distribution (real PubMed abstracts, hedged
observational phrasing, Recon3D subsystem names) is exactly what an LLM will fail to
imitate, and imitating it badly means the student learns a phrasing distribution that
does not exist in deployment.

### 3b. LLM-*labelled* real abstracts (silver) — **yes, this is the core of the plan**

Take real abstracts, real NER spans, and have an LLM assign the 3-way `label`. This
is annotation, not generation, and it is the well-supported route. The three-label
schema helps here concretely: a shorter label inventory with sharper boundaries is
exactly the condition under which LLM-vs-expert agreement is reported highest, and
the 2606.15412 authors close by underscoring "the importance of well-defined relation
schemas" for precisely this reason.
Reference points for what agreement to expect: LLM-vs-expert Cohen's κ in biomedical
RE benchmarks sits around 0.59 for the best single models, and LLM-judge-vs-expert
concordance across healthcare studies runs 0.66–0.96 (median 0.83). So a single LLM
pass is roughly at the level of a mediocre human annotator — usable as silver,
never as gold.

Two techniques that materially improve it and are cheap:

- **Majority voting over 2–3 different LLMs.** There is direct evidence that
  classifiers trained on multi-LLM majority-vote labels **surpass each individual LLM
  teacher**. This is the single highest-leverage trick available here, and it is also
  a free confidence signal: unanimous = high-confidence silver, split = route to human.
- **Two-stage / scenario-based prompting** for document-level biomedical RE — the
  published zero-shot document-level approach (LLMRE, arXiv 2505.01077 /
  S1476927126001039) separates candidate identification from relation typing rather
  than asking for everything in one shot.

The disagreement set from voting is also the annotation queue from §1c. Same
mechanism, two sources of signal.

### 3c. Where the real (human) labels come from

There is no way around a human gold set, and I want to be blunt about *why*, because
"the LLM can label it" makes it tempting to skip: the gold set's job is
**measurement**, not training. Without it we cannot report precision, cannot set the
abstain threshold, cannot detect that the silver labels are systematically wrong in
one direction. Every route in this document — zero-shot, few-shot, distilled,
supervised — needs the same gold set. It is not a cost of the supervised option, it is
a cost of the project.

Sizing: ~500 abstracts double-annotated is the plan already specced, and it is a
reasonable number (published biomedical gold sets in this space run 400–600 expert
items). But sample it for *measurement power*, not for naturalness:

- stratify so `downregulation` is over-sampled relative to its natural rate, and
  reweight at evaluation time; with only three classes this is a single stratification
  axis and is much easier to execute than the previous three-field version;
- **do not draw the gold set only from the existing 450-record corpus.** Those pairs
  were retrieved with `"{pathway}"[ab] AND "{disease}"[ab]` against Recon3D subsystem
  names, so the pathway is always mentioned in canonical form. That is precisely the
  slice where NER is easy and grounding is already solved. A gold set drawn from there
  measures RE on a distribution the deployed pipeline will never see. Draw the gold
  set from **NER output over the 10k corpus**, which is what deployment feeds the model.
  This was open decision #1 in the previous survey; the answer is not ambiguous.

---

## 4. Distillation (Q4)

**Yes — and it is the right backbone, for reasons that are operational rather than
accuracy-driven.**

The precedent is direct: *Distilling LLMs for Biomedical Knowledge Extraction*
(arXiv 2307.06439) on adverse drug events, and UniversalNER's targeted-distillation
recipe. The pattern: LLM teacher labels a large unlabelled corpus, a small encoder
student trains on the silver, the student runs at a fraction of the cost and
frequently matches or beats the teacher on the narrow task.

Why it fits *this* project specifically:

1. **Cost at corpus scale.** 10k abstracts is affordable to run through an LLM once.
   The eventual target — a literature-scale database, refreshed as PubMed grows — is
   not. A distilled encoder is the only thing that can be re-run over millions of
   abstracts on the hardware this project has.
2. **Determinism and reproducibility.** An encoder with a fixed checkpoint and a
   `git_sha` satisfies the traceability rule in CLAUDE.md. A hosted LLM API does not —
   the model behind the endpoint changes without notice, and a database row extracted
   in March is not reproducible in September.
3. **Calibration.** An encoder gives a probability we can threshold and calibrate for
   the abstain policy of §0. LLM verbalised confidence does not calibrate reliably.

Design notes that matter for it working:

- **Teacher = ensemble, not the single strongest model.** Per §3b, majority vote over
  several LLMs beats each of them; and there is 2026 work showing the strongest teacher
  is not always the best teacher for a given student. Ensemble, and keep the vote
  margin as a per-example weight.
- **Train on soft/weighted targets.** Feed the vote distribution, not the argmax; and
  down-weight examples where the teachers disagreed. This is the cheap version of what
  graded distillation does and it directly mitigates the label-noise ceiling.
- **The bias inheritance risk is the one to watch.** If the teacher runs only over the
  canonical-form 450-record corpus, the student inherits that bias *permanently* and no
  amount of student training fixes it. Run the teacher over NER output on the full 10k.
- **Measure the student against the gold set, and against the teacher separately.**
  Student-vs-gold is the product number. Student-vs-teacher agreement tells us whether
  the distillation worked or whether we are just measuring the teacher's errors.

---

## 5. Recommended sequence

Ordered so that each step produces a number that can kill or redirect the next one.
Nothing here requires committing to an architecture before it has been measured.

**Step 1 — 100-pair measurement probe (days, not weeks).**
Before anything is trained: take 100 candidate pairs from real NER output, label them
by hand once (single annotator, no IAA yet), and run four things over them —
an NLI/verbalization baseline, GLiDRE zero-shot, an LLM few-shot prompt, and the
surrogate-`@GENE$` BioREx run of §1a-bis (plus, if cheap, its gene-expansion variant).
Cost is roughly a day. Output: four precision numbers on the same 100 items. That tells us
whether zero-shot is at 0.2 or 0.7, which changes everything downstream, and it costs
1/5 of what the full gold set costs. **Do this before the gold-set build, not after.**

**Step 2 — gene-mediated prior (§1c).**
Wire Recon3D/KEGG pathway→gene and PubTator3 gene–disease into a candidate ranker.
No model training. Produces the candidate ordering and the distant-supervision
channel, and immediately shows how much of the 10k corpus is even in scope.

**Step 3 — gold set, ~500 abstracts, double-annotated, drawn from NER output.**
Per the existing spec, with the sampling corrections in §3c. Pilot gate on 50 items:
a single κ on the 3-way `label`. Set the bar **higher than the old 0.6**, because the
two hardest decisions were removed — κ ≥ 0.75 is the right gate now, and failing it
means the up/down boundary itself is underspecified (most likely on hedged or
mixed-evidence abstracts), not that a field needs deleting. Report bootstrap CIs.

**Step 4 — silver at scale.** Ensemble LLM teacher (2–3 models, majority vote,
two-stage prompting) over the full 10k via NER spans. Keep vote margins.

**Step 5 — distil.** Entity-marker encoder, one 3-way head, soft targets, ≥3 seeds,
bootstrap CIs, separate `runs/summary_re.jsonl`. Calibrate the abstain threshold on
dev for a target precision, e.g. P ≥ 0.90.

**Step 6 — pair-level aggregation and the database.** Aggregate instances into pairs
with evidence counts and sign agreement. Report **pair-level precision at coverage**,
sampled and hand-checked. That is the number the project should be judged on.

---

## 6. Where this review disagrees with the 2026-08-11 survey

| Topic | Previous survey | This review |
|---|---|---|
| Headline metric | micro/macro-F1 | precision at coverage, with abstain; pair-level, not instance-level |
| Gene-mediated inference (Option A) | rejected in favour of distillation | rejected *as the product*, adopted as candidate ranker + distant supervision + disagreement queue |
| Teacher | LLM teacher | *ensemble* teacher with vote margin as example weight — measurably better, and free confidence |
| Ordering | gold set, then measure | 100-pair probe **first**; it is 1/5 the cost and redirects the plan |
| Surrogate-entity reuse of BioREx | not considered | mechanically possible (input is already entity-masked); demoted to a one-hour fourth probe baseline rather than dismissed on schema grounds alone (§1a-bis) |
| Gold-set source (open decision #1) | left open | settled: NER output over the 10k corpus, not the 450-record canonical corpus |
| `summary.jsonl` collision (open decision #5) | left open | settled: separate `runs/summary_re.jsonl` |
| Eval rigor | not addressed | ≥3 seeds and bootstrap CIs mandatory; the 2026-07-31 non-reproduction will be worse at RE scale |
| Direction field | contain with rules | **removed** by the 2026-08-20 revision; direction is recoverable in aggregate, not per instance (§2.0) |
| Label set | 4 labels + direction + negated | 3 labels (`upregulation`/`downregulation`/`no_relation`), one head; `association` folded into `no_relation`, re-addable later without re-annotation |
| `negated` | separate binary head | dropped as a target for v1, retained as an annotator note (§2.0) — assumption, needs confirming |
| Pilot IAA gate | κ ≥ 0.6 on `direction` | κ ≥ 0.75 on the single 3-way label |

Agreements: no off-the-shelf model exists; distillation is the right backbone; the
canonical-form retrieval bias in the 450-record corpus is real and dangerous.

**Downstream documents that the schema revision invalidates** and must be re-frozen
before annotation starts: `doccano/RELATION_SCHEMA.md` (frozen at commit `6944b98`
with four labels, direction and negation) and
`docs/superpowers/specs/2026-08-16-relation-extraction-gold-corpus-design.md`
(§7.2 relation fields, §9.1 pilot gate, §15 downstream contract). Annotating against
the old guide and the new one would split the gold set across two schemas — exactly
the failure mode CLAUDE.md's clean-tree rule exists to prevent, one level up.

---

## Sources

- [Few-Shot Biomedical Relation Extraction with LLMs: A Viable Alternative to Supervised Learning?](https://arxiv.org/abs/2606.15412)
- [Zero-shot document-level biomedical RE via scenario-based prompt design in two-stage with LLM](https://www.sciencedirect.com/science/article/pii/S1476927126001039) — [code](https://github.com/tyrone1979/LLMRE), [preprint](https://arxiv.org/pdf/2505.01077)
- [A Benchmark for End-to-End Zero-Shot Biomedical Relation Extraction with LLMs](https://arxiv.org/abs/2504.04083)
- [Applicability Condition Extraction for Therapeutic Drug-Disease Relations (Drug-ACE)](https://arxiv.org/abs/2606.14031)
- [BioREx: Improving biomedical relation extraction by leveraging heterogeneous datasets](https://www.sciencedirect.com/science/article/pii/S1532046423002083) · [PMC version](https://pmc.ncbi.nlm.nih.gov/articles/PMC10370213/)
- [BioRED: A Rich Biomedical Relation Extraction Dataset](https://academic.oup.com/bib/article/23/5/bbac282/6645993)
- [EMBRE: entity-aware masking for biomedical relation extraction](https://arxiv.org/pdf/2401.07877)
- [Enhancing biomedical relation extraction with directionality (PMC12261447)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12261447/)
- [PubTator 3.0: an AI-powered Literature Resource](https://arxiv.org/pdf/2401.11048)
- [GLiREL — Generalist Model for Zero-Shot Relation Extraction (NAACL 2025)](https://aclanthology.org/2025.naacl-long.418.pdf)
- [GLiDRE: Generalist Lightweight model for Document-level Relation Extraction](https://arxiv.org/pdf/2508.00757)
- [Distilling Large Language Models for Biomedical Knowledge Extraction (adverse drug events)](https://arxiv.org/pdf/2307.06439)
- [The Strongest Teacher Is Not Always the Best Teacher: Student-Centric Answer Selection](https://arxiv.org/pdf/2605.26872)
- [A Distant Supervision Corpus for Biomedical Relationships Between Chemicals, Diseases and Genes (ChemDisGene)](https://arxiv.org/pdf/2204.06584)
- [Distant Supervision for Large-Scale Extraction of Gene–Disease Associations (DeepDive)](https://link.springer.com/chapter/10.1007/978-981-13-2354-6_39)
- [High-throughput biomedical relation extraction empowered by LLMs (expert benchmark, κ figures)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12482089/)
- [LLM-as-a-Judge in Healthcare: applications, methods, and human alignment](https://arxiv.org/pdf/2605.25273)
- [BIOME-Bench: Biomolecular Interaction Inference and Multi-Omics Pathway Mechanism Elucidation](https://arxiv.org/pdf/2512.24733)
- [Exploring transformer models: fine-tuning vs inference on biomedical RE](https://pmc.ncbi.nlm.nih.gov/articles/PMC12796933/)
- [KEGG DISEASE](https://www.genome.jp/kegg/disease/) · [DisGeNET–Reactome overlay](https://reactome.org/overlays/disgenet)
