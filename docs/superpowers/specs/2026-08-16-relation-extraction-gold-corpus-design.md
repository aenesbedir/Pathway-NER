# Relation Extraction Program and Gold Corpus Design

Date: 2026-08-16  
Status: Approved design; implementation not started

## 1. Purpose

Build the first reliable dataset boundary for Option C: an LLM teacher produces
silver pathway–disease relation labels, and a biomedical encoder student learns
from them. This specification defines the program-level boundaries and fully
defines the first subproject: candidate generation, human annotation,
inter-annotator agreement, adjudication, and an immutable gold corpus.

The relation model is relation classification, not joint entity and relation
extraction. Pathway spans come from the existing pathway NER model. Disease spans
and MeSH identifiers come from PubTator3. One training or evaluation instance is
one normalized pathway–disease pair in one PubMed abstract.

## 2. Scope

### 2.1 Program decomposition

Option C is split into four independent subprojects connected by versioned JSONL
contracts:

1. **Candidate and gold corpus** — pathway NER and PubTator3 produce normalized
   candidate pairs; Label Studio supports independent double annotation and
   adjudication; the output is a locked gold corpus. This specification covers
   this subproject.
2. **Teacher and silver corpus** — local and cloud LLM teachers are compared on
   the gold development set; the selected frozen teacher configuration labels
   10,000–50,000 non-gold candidates.
3. **Student training** — a biomedical encoder with separate relation,
   direction, negation, and evidence heads trains on silver data and is evaluated
   on the locked gold panels.
4. **Production reading and evidence database** — upstream NER models, the
   student, and evidence aggregation process new PubMed abstracts. Training is
   outside this subsystem.

Each subproject owns one responsibility. Candidate generation does not call an
LLM teacher. Teacher inference does not train the student. Student training does
not depend on Label Studio or teacher response formats. Production inference does
not train any model.

### 2.2 Included in this specification

- Disease-only PubMed retrieval for a deployment-like source population.
- A limited legacy canonical-query stratum.
- Pathway NER inference and deterministic metabolic pathway grounding.
- PubTator3 disease spans and MeSH normalization.
- Document-level candidate pair construction.
- A 500-task, two-panel, source- and disease-stratified gold sample.
- Label Studio import and export adapters.
- Independent annotation by two annotators and third-party adjudication.
- Evidence-sentence annotation.
- IAA, validation, manifests, provenance, and gold/silver leakage protection.

### 2.3 Non-goals

- Signalling pathways. Version 1 covers metabolic pathways only.
- Training or selecting the LLM teacher.
- Student architecture, loss weights, optimization, or model selection.
- Production database tables, belief aggregation, or scanning all PubMed.
- Full-text relation extraction. Version 1 uses abstracts.
- Changing the existing NER training pipeline, `train.py`, or NER run summaries.
- Running any command on TRUBA/ARF.

## 3. Program invariants

- The pathway ontology is the frozen 98-name metabolic vocabulary derived from
  Recon3D, with KEGG/Reactome mappings where available.
- Disease concepts use PubTator3-provided MeSH identifiers.
- The annotation unit is one normalized `(pathway_id, disease_id)` pair in one
  abstract, not one mention pair.
- All mentions of each target concept in the abstract are retained in that pair's
  record.
- `label`, `direction`, and `negated` are independent fields. They are never
  converted into one cross-product training class.
- One or more sentence-aligned evidence offsets are mandatory for a positive
  relation and forbidden for `no_relation`.
- Entity validity is separate from relation absence. A false entity span is not a
  `no_relation` example.
- Every persisted dataset has a schema version, manifest, source fingerprints,
  and content checksums.
- Gold and silver PMIDs never overlap.
- Prevalence and challenge panels are reported separately; they do not produce a
  combined overall F1.
- Text is never silently truncated. Any context-limit exclusion must be explicit
  in a later tokenized dataset manifest.

## 4. Candidate source population

### 4.1 Deployment-like source

The current `data/raw/articles.jsonl` is not deployment-like for this purpose. It
was collected through canonical pathway × disease PubMed queries. Running NER on
that corpus would preserve the canonical-name selection bias.

The primary source starts with the 98 diseases in
`data/raw/selected_diseases.json`. PubMed retrieval uses disease or MeSH criteria
only; pathway names are absent from the retrieval query. The exact query,
pagination parameters, ordering, retrieval timestamp, and frozen PMID list are
recorded in a manifest. Pathway NER is then responsible for finding metabolic
pathway language, including non-canonical mentions.

The candidate builder performs these operations per abstract:

1. Run the authoritative pathway NER checkpoint.
2. Ground each pathway mention to the frozen metabolic vocabulary.
3. Read PubTator3 disease spans and MeSH identifiers.
4. Group mentions by normalized entity identifier.
5. Form the Cartesian product of normalized pathway and disease entities.
6. Emit one record per normalized pair, merging all mentions of each entity.

### 4.2 Legacy source

The 450 records in
`data/raw/extracted_disease_pathway_db_disease_pathway_just_abstracts.json` form a
limited secondary stratum with
`retrieval_source="legacy_canonical_query"`. They do not enter the prevalence
panel and are never interpreted as a representative deployment sample.

### 4.3 Pathway identifiers

The repository currently has canonical Recon3D subsystem names but no stable
external identifier for every subsystem. Version 1 assigns a versioned internal
identifier:

```text
RECON3D_SUBSYSTEM:<stable-slug>
```

The mapping from identifier to canonical name is immutable within an ontology
version and carries the source vocabulary checksum. Renaming a canonical label
requires a new ontology version or an explicit mapping; it cannot silently change
an existing identifier's meaning.

### 4.4 Candidate identity

`candidate_id` is a deterministic digest of the schema namespace, PMID, pathway
identifier, and disease identifier. A repeated identifier with different content
is a hard error. A normalized pair appears at most once per PMID.

## 5. Candidate record contract

A canonical candidate contains at least:

```json
{
  "schema_version": "re-candidate-v1",
  "candidate_id": "<deterministic digest>",
  "pmid": "12345678",
  "title": "...",
  "abstract": "...",
  "retrieval_source": "disease_only_pubmed",
  "panel": "prevalence",
  "disease_category": "metabolic",
  "pathway": {
    "id": "RECON3D_SUBSYSTEM:glycolysis",
    "canonical_name": "glycolysis",
    "mentions": [
      {"start": 42, "end": 60, "text": "glycolytic pathway"}
    ],
    "ner_checkpoint_sha256": "..."
  },
  "disease": {
    "id": "MESH:D003924",
    "canonical_name": "Diabetes Mellitus, Type 2",
    "mentions": [
      {"start": 101, "end": 116, "text": "type 2 diabetes"}
    ],
    "annotator": "PubTator3",
    "source_version": "..."
  },
  "selection": {
    "seed": 42,
    "reason": "random_prevalence"
  }
}
```

Every mention must satisfy all of these conditions:

- `0 <= start < end <= len(abstract)`.
- `abstract[start:end] == text` exactly.
- All mentions under one entity resolve to the same normalized identifier.
- Mention ordering is deterministic.

Empty abstracts, unresolved identifiers, invalid offsets, content collisions, and
duplicate candidates are rejected with explicit reason codes.

## 6. Gold sampling design

### 6.1 Unit and leakage rule

One annotation task represents one candidate pair from one PMID. Gold sampling
uses unique PMIDs: no PMID appears in two tasks. This prevents document leakage
between development and test panels and bounds annotation cost. It deliberately
does not measure multiple-pair interactions inside one abstract; the relation
classifier processes pairs independently.

### 6.2 Panels

The gold sample contains 500 tasks.

| Panel | Source | Cancer | Neurodegenerative | Metabolic | Total |
|---|---|---:|---:|---:|---:|
| Prevalence | Disease-only deployment source | 100 | 100 | 100 | 300 |
| Challenge | Disease-only, cue-enriched | 50 | 50 | 50 | 150 |
| Challenge | Legacy canonical-query source | 50 | 0 | 0 | 50 |
| **Total** | — | **200** | **150** | **150** | **500** |

The prevalence panel uses deterministic random sampling after candidate
construction and preserves the natural `no_relation` proportion conditional on
candidate generation.

The challenge panel is enriched with teacher-independent deterministic cues:
same-sentence co-occurrence, association verbs, regulatory verbs, and relation
negation cues. These signals select likely informative examples but never assign
a label. Challenge results cannot estimate deployment prevalence.

### 6.3 Development and locked test

| Split | Prevalence | Challenge | Total |
|---|---:|---:|---:|
| Pilot/development | 30 | 20 | 50 |
| Locked test | 270 | 180 | 450 |
| **Total** | **300** | **200** | **500** |

The first 50 tasks are used to repair the annotation guide, evaluate IAA, calibrate
the deterministic challenge sampler once, and later compare teacher prompts and
models. After the remaining 450 tasks are generated, the sample is locked. Test
labels cannot cause post-hoc additions, removals, or rebalancing.

All 500 PMIDs enter the global silver-exclusion list, including the 50 development
PMIDs.

## 7. Annotation schema

### 7.1 Entity validity

Each annotator records `pathway_valid` and `disease_valid`. If either is false,
relation fields remain empty and the task becomes `invalid_candidate`. Optional
corrected mentions are audit information and never overwrite the original
pipeline input.

Invalid candidates remain in the annotated corpus for upstream error accounting
but are excluded from relation model metrics.

### 7.2 Relation fields

`label` has exactly four values:

- `no_relation`
- `association`
- `positive_regulation`
- `negative_regulation`

`direction`, when a relation exists, has exactly three values:

- `pathway_to_disease`
- `disease_to_pathway`
- `undirected`

`negated` is a boolean when a relation exists.

Conditional invariants:

- `no_relation` requires `direction=null`, `negated=null`, and no evidence.
- A non-null relation requires one direction, one negation value, and at least
  one evidence sentence.
- Negation scopes over the relation itself, not an entity name or subgroup.
- Observational wording remains `undirected`.

### 7.3 Evidence

Evidence is a list of one or more complete supporting sentences:

```json
{
  "evidence_sentences": [
    {"start": 120, "end": 198}
  ]
}
```

Sentence segmentation is deterministic and versioned. An exported evidence span
must match a known sentence boundary. A converter may snap an approximate UI
selection to a boundary only when the operation is deterministic and recorded;
otherwise it rejects the annotation.

If an abstract contains contradictory claims for the same normalized pair that
cannot be represented by the single-label schema, the task receives
`ambiguous_conflict`. It remains in the audit corpus and is excluded from training
and evaluation.

## 8. Label Studio workflow

Label Studio is selected over Doccano parallel relations and a custom annotation
application. It represents pair-level relation fields as independent controls and
evidence as a text span without converting the schema into composite labels.

Each task displays:

- The abstract.
- Highlighted target pathway mentions.
- Highlighted target disease mentions.
- Canonical entity names.
- Entity-validity controls.
- Independent controls for label, direction, and negation.
- An `EVIDENCE` span control.
- An optional annotator note.

The UI hides retrieval source, panel, challenge-selection reason, and all teacher
outputs. It imports no relation prelabel. Only upstream entity highlights are
prefilled.

Two separate Label Studio projects receive identical task IDs and ordering. Each
annotator sees only their project. A third adjudication project contains only
records that need resolution.

Label Studio JSON is a transport format, not the canonical dataset. Import and
export adapters validate and convert it at the boundary.

## 9. Double annotation, IAA, and adjudication

### 9.1 Pilot gate

Both annotators independently complete the first 50 tasks before annotation
continues.

The gate reports:

- Nominal Cohen's kappa for `label`; required `kappa >= 0.70`.
- Nominal Cohen's kappa for `direction`, only where both annotators say a
  relation exists; required `kappa >= 0.60`.
- Raw `negated` disagreement count, with every disagreement reviewed.
- Sentence-level evidence precision, recall, F1, and Jaccard agreement.
- Separate pathway-validity and disease-validity percent agreement.

If either kappa threshold fails or disagreements expose a rule gap, annotation of
the remaining 450 tasks stops. The guide and schema are versioned, and the first
50 tasks are independently re-annotated under the new version. Previous results
remain in the audit trail.

### 9.2 Full corpus

After the pilot gate passes, both annotators independently complete the remaining
450 tasks. IAA is calculated from pre-adjudication outputs, never from adjudicated
labels.

Exact agreement is accepted automatically. The adjudicator resolves every task
with any of these conditions:

- Field-level disagreement.
- Different evidence sentence sets.
- Entity-validity disagreement.
- `ambiguous_conflict` from either annotator.
- A validator warning.

Unresolved adjudication is a hard failure for canonical gold generation.

### 9.3 Outputs

The versioned gold dataset contains:

- `annotations/annotator-a.jsonl`
- `annotations/annotator-b.jsonl`
- `annotations/adjudication.jsonl`
- `gold.jsonl`
- `excluded.jsonl`
- `iaa.json`
- `manifest.json`
- `silver_excluded_pmids.txt`

`gold.jsonl` contains only resolved, relation-eligible, schema-valid examples.
`excluded.jsonl` preserves invalid entities, ambiguous conflicts, and technical
exclusions with reason codes. The manifest reports both the 500 annotated tasks
and the smaller number, if any, of valid relation examples.

## 10. Component boundaries

The implementation uses these focused modules:

```text
pubmed_api/
  fetch_disease_abstracts.py

relation_extraction/
  schema.py
  pubtator.py
  pathway_adapter.py
  grounding.py
  build_candidates.py
  sample_gold.py
  label_studio.py
  agreement.py
  adjudication.py
```

Responsibilities:

- `fetch_disease_abstracts.py` owns disease-only PubMed retrieval and its raw
  cache.
- `schema.py` owns canonical record definitions and cross-field validation.
- `pubtator.py` converts PubTator3 responses into disease mentions; it does not
  build pairs.
- `pathway_adapter.py` runs the authoritative NER checkpoint and records its
  fingerprint.
- `grounding.py` maps pathway mentions to the frozen metabolic ontology.
- `build_candidates.py` groups mentions and constructs normalized document-level
  pairs.
- `sample_gold.py` owns deterministic panel, source, category, and split
  selection.
- `label_studio.py` only converts between canonical records and Label Studio
  transport JSON.
- `agreement.py` computes pre-adjudication agreement.
- `adjudication.py` merges exact agreements and adjudicated disagreements into
  canonical gold.

The existing `encoders.py` registry supplies encoder and tokenizer identity. The
existing pathway canonicalization logic may be used behind `grounding.py`; the
relation pipeline does not consume NER silver-record formats directly.

The old relation scripts under `/home/enes/annotations/scripts/` use an obsolete
schema and relation prefill. They are not migrated or treated as canonical inputs.

## 11. Caching and provenance

Caches use keys that invalidate whenever semantics change:

- PubMed: complete query and pagination parameters.
- PubTator3: PMID, endpoint, and source version.
- Pathway NER: PMID, abstract checksum, and checkpoint SHA-256.
- Grounding: mention offsets, ontology checksum, and grounding version.

An external request failure is never cached as an empty successful annotation.
Model names are descriptive metadata; checkpoint checksums are authoritative.

Every generated dataset manifest includes:

- Schema and ontology versions.
- Source file and checkpoint checksums.
- PubMed queries and frozen PMID lists.
- PubTator endpoint/version information.
- Sampling seed and exact quotas.
- Accepted and rejected counts by reason, source, panel, and disease category.
- Content checksums for every final artifact.

## 12. Failure policy

### 12.1 Retryable external failures

Timeouts, HTTP 429/5xx responses, transport errors, and malformed temporary
responses use bounded exponential backoff. Exhausted failures enter an unresolved
failure manifest and are not interpreted as “no entity found.” Failed responses
are not stored in the success cache.

### 12.2 Deterministic invalid records

Empty abstracts, missing normalized identifiers, invalid offsets, unresolved
pathway grounding, candidate identity collisions, and duplicate normalized pairs
are rejected with stable reason codes and are not retried.

### 12.3 Annotation-invalid records

Cross-field schema violations, missing evidence, non-sentence evidence offsets,
mutated target offsets, duplicate single-choice answers, and unresolved
adjudication prevent canonical gold generation. A partial gold file is never
published as successful.

### 12.4 Safe reruns

- Stable identifiers, ordering, and fixed seeds make sampling deterministic.
- Outputs are completed and validated in temporary locations before atomic
  publication.
- Existing versioned datasets are not overwritten by default.
- Downstream steps verify manifest and content checksums before running.
- Annotator exports and adjudication never mutate original candidates.

## 13. Verification

### 13.1 Behavioral tests

Schema tests cover valid and invalid relation combinations, entity validity,
evidence requirements, offsets, sentence boundaries, and identity collisions.

Candidate-generation tests cover mention grouping, pair Cartesian products,
deduplication, grounding rejection, and the distinction between external failure
and an empty annotation.

Sampling tests require byte-identical ordering for the same inputs and seed, exact
panel/category/source quotas, unique PMIDs, no legacy records in prevalence, and
no development/test overlap.

Label Studio round-trip tests assert that canonical candidate identity, text,
entity offsets, and human selections survive export and import.

Agreement and adjudication tests use fixtures with known kappa and evidence
agreement values. Exact agreements auto-resolve; every disagreement enters the
adjudication queue; unresolved records block gold publication.

### 13.2 Smoke test

A small real pipeline slice contains at least one abstract from each disease
category. It loads the actual pathway NER checkpoint, parses a real recorded
PubTator3 response, builds normalized candidates, imports one task into Label
Studio, exports a completed annotation, and validates the canonical result.

Recorded external responses keep the normal test suite deterministic. A separate
opt-in connectivity smoke check exercises live PubMed and PubTator endpoints.

## 14. Acceptance criteria

The subproject is complete only when:

1. The candidate manifest records all queries, fingerprints, versions, seeds,
   quotas, and checksums.
2. The sample contains 500 unique-PMID tasks with the approved 300/200 panel and
   category/source distribution.
3. The first 50 tasks are independently double annotated.
4. Label kappa is at least 0.70 and direction kappa is at least 0.60.
5. Every negation disagreement is reviewed and evidence agreement is reported.
6. The remaining 450 tasks are independently double annotated.
7. Every disagreement is adjudicated by the third annotator.
8. Canonical gold contains no unresolved or schema-invalid records.
9. Invalid entity and ambiguous records remain in `excluded.jsonl`.
10. The exclusion list contains all 500 gold PMIDs.
11. Prevalence and challenge panels remain separate in all reports.
12. Reproduction from frozen inputs yields identical artifact checksums.

## 15. Downstream contract

Teacher and student subprojects may consume only these semantic fields from the
canonical corpus:

```text
candidate_id
pmid
abstract
pathway.id
pathway.mentions[]
disease.id
disease.mentions[]
gold.label
gold.direction
gold.negated
gold.evidence_sentences[]
panel
disease_category
```

Teacher prompts, generated explanations, API payloads, Label Studio JSON, and UI
metadata cannot become student dataset dependencies.

The teacher subproject will compare one local and one cloud teacher on the
50-task development set. The selected teacher configuration is then frozen before
silver generation. The future student succeeds when it remains within two macro-F1
points of the selected teacher on both locked panels, avoids a material collapse
in any of the three disease categories, and demonstrates measured inference
throughput or cost advantage. No absolute F1 threshold is invented before the
gold distribution is observed.

## 16. Principal risks and decisions

- **Retrieval bias:** solved by disease-only primary retrieval; canonical-query
  records are isolated in the challenge panel.
- **Entity error conflated with relation absence:** solved by explicit entity
  validity fields and exclusion from relation metrics.
- **Annotation anchoring:** no relation label or teacher output is prefilled.
- **Rare signed and negated claims:** measured in a separate cue-enriched challenge
  panel without presenting it as deployment prevalence.
- **Schema cannot express contradictory claims:** such records are retained as
  `ambiguous_conflict` and excluded rather than forced into a wrong class.
- **Missing external Recon3D subsystem IDs:** solved by a versioned internal
  identifier mapping with ontology checksum.
- **Tool mismatch:** Label Studio is selected because independent pair attributes
  and evidence spans fit its configuration; Doccano's one-type relation edge does
  not represent the schema cleanly.
- **Annotation cost:** 500 tasks are independently labeled twice and disagreements
  are adjudicated. The pilot gate prevents scaling an underspecified guide.
