# Progress Report: Pathway NER Dataset Construction and Model Development

**Reporting period:** 9 June–16 August 2026

**Project:** Metabolic pathway and disease named-entity recognition from biomedical abstracts

## 1. Executive summary

This project has progressed from small, automatically labelled pathway datasets to a
10,125-document disease–pathway corpus with reviewed and curated annotations. The
current canonical dataset contains 96,629 `DISEASE` spans and 24,636 `PATHWAY` spans.
The pathway NER experiments use only the
`PATHWAY` labels; the disease annotations are retained for the later joint
disease–pathway pipeline.

The corpus originated from 9,604 PubMed searches formed by crossing **98 Recon3D**
**pathway terms** with **98 selected MeSH diseases**. The searches returned 1,959 **non-empty**
**pathway–disease pairs** and **10,329 unique PMIDs**. The pathway annotations were produced
with a guided **Qwen2.5:14B** extraction pipeline, deterministic recall and
canonicalisation steps, and successive review or curation stages. Disease spans were
produced with the BENT PubMedBERT disease model.

**Pathway NER is formulated as BIO token classification and trained by full**
**fine-tuning of pretrained biomedical encoders.** Earlier reviewed-gold experiments
established the training recipe and showed that full fine-tuning was substantially
better than freezing lower layers. A five-encoder comparison on the original frozen
gold test set did not separate the encoders reliably. The current TRUBA experiment
therefore evaluates three base and two large biomedical encoders on the common
10,125-document corpus. As of 16 August, all nine base-model runs and 12 of 18
large-model runs had completed. The best complete base result was **BioLinkBERT-base** at
**0.8772 ± 0.0095 test F1**. The highest available mean was **BioM-ELECTRA-large** at
3e-5, **0.8820 ± 0.0054**, but that value covered only two of three seeds. The missing
large-model cells, an additional 5e-5 large-model sweep, and checkpoint-retaining
retrains had been submitted as follow-up TRUBA jobs.

## 2. Project objective and scope

The immediate objective is to detect spans in biomedical abstracts that name
metabolic pathways or metabolic processes. **The current pathway model does not**
**predict a canonical Recon3D identifier; it predicts the character extent of a**
**pathway mention.** Canonicalisation was used in the silver-annotation pipeline to
support review and provenance, while fine-tuning uses the three BIO labels `O`,
`B-Pathway`, and `I-Pathway`.

The combined dataset also contains disease mentions. These annotations are not used
as labels in the current pathway-only fine-tuning experiments. They are preserved so
that a later stage can detect pathway–disease co-occurrence or relations without
reconstructing the disease side of the corpus.

## 3. Construction of the 10,125-document corpus

### 3.1 Disease and pathway vocabularies

**The disease vocabulary** was derived from three MeSH tree branches:

| MeSH tree | Scope | Descriptors retrieved |
|---|---|---:|
| C04 | Neoplasms | 455 |
| C10.574 | Neurodegenerative diseases | 77 |
| C18 | Metabolic and nutritional diseases | 334 |
| **Unique total** | — | **834** |

From these descriptors, 98 target diseases were selected: **37 cancer, 28**
**neurodegenerative, and 33 metabolic diseases.**

**The pathway vocabulary** was derived from 98 unique Recon3D pathway names.

The complete pathway and disease query vocabularies, including hit/no-hit status and retrieved PMID counts, are provided in **Appendices A and B**.

### 3.2 PubMed query and retrieval

Each pathway was paired with each disease, producing 98 × 98 = 9,604 PubMed
ESearch queries. The query template implemented in
[`pubmed_api/fetch_pathway_disease_pairs.py`](../pubmed_api/fetch_pathway_disease_pairs.py)
was:

```text
("<pathway>"[Title/Abstract]) AND ("<disease>"[Title/Abstract])
```

Each pair returned at most 20 PMIDs. Results were cached per pair so that an
interrupted run could resume without repeating completed API requests. The final
retrieval statistics were:

| Retrieval measure | Result |
|---|---:|
| Pathway–disease pairs queried | 9,604 |
| Pairs returning at least one PMID | 1,959 |
| Pairs returning zero PMIDs | 7,645 |
| Pairs reaching the 20-PMID cap | 314 |
| Unique PMIDs | 10,329 |
| Pathways with at least one non-empty pair | 75/98 |
| Diseases with at least one non-empty pair | 88/98 |

**For complete term-level hit/no-hit coverage and retrieved PMID counts, see**
**Appendices A and B.**

The pair-level output, including all PMIDs returned for non-empty queries, is tracked
in [`data/raw/pathway_disease_pairs.json`](../data/raw/pathway_disease_pairs.json).

For every unique PMID, the article pipeline requested PubMed metadata and abstract
text and, where available, mapped the PMID to a PMCID and fetched PMC full text. The
later LLM annotation pipeline operated on abstracts longer than 100 characters and
excluded the ten PMIDs reserved for the independent golden set. This yielded 10,125
eligible documents. Four non-overlapping 1,000-document review waves covered 4,000
documents; the remaining 6,125 formed the final curation batch.

### 3.3 Pathway annotation

Exact string matching was initially useful for high-precision matches but did not
capture the surface variation found in biomedical writing. The scalable annotation
pipeline therefore used `qwen2.5:14b` as a local annotator. For each complete
abstract, the model received the query pathway names as hints and returned surface
strings under a structured JSON schema. Its output was then processed as follows:

1. Every returned surface was grounded verbatim to character offsets; ungrounded
   generations were discarded.
2. A deterministic booster detected word-order and process-word variations that the
   LLM could miss.
3. Overlapping outputs were merged.
4. A deterministic canonicaliser mapped resolvable surfaces to Recon3D pathway
   names while allowing uncertain cases to remain unmapped.
5. The resulting silver spans were converted to Doccano sequence-labelling imports.

Qwen2.5:14B was selected over Qwen2.5:7B because it produced cleaner and more stable
annotations. On the later 200-document annotator comparison, Qwen2.5:14B also
outperformed Qwen3.5:9B: exact F1 was 0.783 versus 0.715, and lenient overlap F1 was
0.831 versus 0.814. The relevant pipeline and evaluation code is tracked under
[`llm/`](../llm), [`doccano/`](../doccano), and
[`analysis/score_against_review.py`](../analysis/score_against_review.py).

### 3.4 Review and curation of the 10,125-document Pathway corpus

The first 10,125 documents were prepared totally. Annotators(humans and Frontier AI Models) accepted correct spans, removed false positives, corrected boundaries, and added missed mentions under the common annotation guide. 

| Source layer     |  Documents | Pathway-positive documents | Final pathway spans | Review provenance                          |
| ---------------- | ---------: | -------------------------: | ------------------: | ------------------------------------------ |
| Full pilot       |      1,000 |                        914 |               2,504 | human +  Frontier AI Models                |
| Wave 2           |      1,000 |                        901 |               2,334 | Frontier AI Models                         |
| Wave 3           |      1,000 |                        901 |               2,339 | Frontier AI Models                         |
| Wave 4           |      1,000 |                        903 |               2,306 | Frontier AI Models                         |
| Remaining corpus |      6,125 |                      5,549 |              15,153 | Frontier AI Models + models trained so far |
| **Total**        | **10,125** |                  **9,168** |          **24,636** | —                                          |


### 3.5 Disease annotation method

Disease spans were generated with
`pruas/BENT-PubMedBERT-NER-Disease` at model revision
`e70d6a5b1bd797b38092b0f2e4707ec36db9de59`. Long abstracts were processed in
overlapping token windows. Probabilities for duplicate tokens were averaged before
global BIO decoding, preventing duplicate entities at window boundaries.

BENT-style postprocessing merged adjacent WordPiece fragments and removed remaining
one-character entities. On a manually annotated 50-article sample containing 509
disease mentions, the raw output and postprocessed output scored as follows:

| Disease representation | Predictions | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| Raw BENT spans | 698 | 0.5516 | 0.7564 | 0.6379 |
| BENT-postprocessed spans | 530 | **0.8849** | **0.9214** | **0.9028** |

The extraction and postprocessing implementation is tracked in
[`scripts/extract_disease_spans.py`](../scripts/extract_disease_spans.py). PubTator
retrieval for the independent disease comparison is implemented in
[`scripts/fetch_pubtator_disease.py`](../scripts/fetch_pubtator_disease.py).

### 3.6 Final merge and model-ready pathway dataset

The reviewed 4,000-document layer and curated 6,125-document layer were merged into
the final 10,125-document Doccano corpus. Its composition is:

| Component | Documents | Pathway spans | Disease spans |
|---|---:|---:|---:|
| Reviewed 4k layer | 4,000 | 9,483 | 38,099 |
| Curated remaining layer | 6,125 | 15,153 | 58,530 |
| **Combined corpus** | **10,125** | **24,636** | **96,629** |

The pathway fine-tuning preparation entry point is
[`scripts/prepare_pathway_10k.sh`](../scripts/prepare_pathway_10k.sh). It retains
only `PATHWAY` labels, converts Doccano spans to model-independent article and match
records, creates a frozen split, and builds a BIO dataset for each tokenizer.

| Split | Documents | Documents without a pathway span |
|---|---:|---:|
| Train | 8,100 | 765 |
| Validation | 1,012 | 96 |
| Test | 1,013 | 96 |
| **Total** | **10,125** | **957** |

The split uses seed 42, is stratified by pathway-span-count band, and groups exact
duplicate abstracts so they cannot cross partitions. The tracked
[`data/processed/pathway-10k/splits.json`](../data/processed/pathway-10k/splits.json)
also records the source hashes. Each tokenizer-specific dataset is validated by
decoding BIO labels back to character spans; all five 10k datasets completed with
zero unexplained alignment losses.

## 4. Pathway NER development

### 4.1 Fine-tuning method

The pathway NER model is an encoder with a token-classification head. Abstracts are
tokenised with the tokenizer belonging to the selected base encoder, and character
spans are converted to BIO labels. Training uses weighted cross-entropy to address
the dominance of non-entity tokens. The established recipe fine-tunes all encoder
layers, uses early stopping on entity-level validation F1, reloads the best
validation checkpoint, and evaluates precision, recall, and F1 on the frozen test
set.

The current common recipe is:

| Setting | Value |
|---|---|
| Labels | `O`, `B-Pathway`, `I-Pathway` |
| Class weights, O/B/I | 0.5 / 1.5 / 1.0 |
| Maximum epochs | 40 |
| Early-stopping patience | 8 epochs |
| Frozen encoder layers | 0 |
| Effective batch size | 16 |
| Model selection | Highest validation F1 |
| Reported test metrics | Entity-level precision, recall, and F1 |

[`encoders.py`](../encoders.py) centralises the Hugging Face model ID, tokenizer,
context length, precision mode, batch size, gradient accumulation, and learning-rate
grid for each encoder. Tokenizer fingerprints stored with the processed data prevent
a model from silently training on token IDs produced by a different vocabulary.

### 4.2 Reviewed-gold recipe development

The first relevant model series was derived from 1,200 reviewed documents. Of these,
1,083 contained at least one pathway span, and 1,076 remained effective under
BiomedBERT tokenisation after seven documents lost all positive labels beyond the
512-token context limit. All runs used the same 860/107/109 split. Balanced class
weights and longer training improved the initial model, while unfreezing all encoder
layers produced the largest gain.

**1,200 reviewed documents → 1,083 pathway-positive documents → 860/107/109**
**effective train/validation/test examples**

All runs used `microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext`,
effective batch size 16, and the same split.

| Run | O/B/I weights | Frozen layers | LR | Seed | Max epochs / patience | Best epoch | Test P | Test R | Test F1 |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|
| gold-001 | 0.1/5.0/3.0 | 9 | 3e-5 | 42 | 20 / 5 | 8 | 0.5809 | 0.8008 | 0.6734 |
| gold-002 | 0.3/2.0/1.5 | 9 | 3e-5 | 42 | 20 / 5 | 18 | 0.6558 | 0.8048 | 0.7227 |
| gold-003 | 0.5/1.5/1.0 | 9 | 3e-5 | 42 | 40 / 8 | 17 | 0.6799 | 0.8207 | 0.7437 |
| gold-004 | 0.5/1.5/1.0 | 0 | 3e-5 | 42 | 40 / 8 | 23 | 0.7881 | 0.8446 | 0.8154 |
| gold-005 | 0.5/1.5/1.0 | 0 | 3e-5 | 1 | 40 / 8 | 30 | 0.7645 | 0.8406 | 0.8008 |
| gold-006 | 0.5/1.5/1.0 | 0 | 3e-5 | 7 | 40 / 8 | 21 | 0.8103 | 0.8167 | 0.8135 |
| gold-007 | 0.5/1.5/1.0 | 0 | 2e-5 | 42 | 40 / 8 | 15 | 0.7420 | 0.8367 | 0.7865 |
| gold-008 | 0.5/1.5/1.0 | 0 | 5e-5 | 42 | 40 / 8 | 21 | 0.7826 | 0.8606 | 0.8197 |

The detailed experiment record is tracked in
[`knowledge_base/model_experiments.md`](../knowledge_base/model_experiments.md).

### 4.3 Five-encoder comparison on the frozen reviewed-gold test set

The next experiment fixed the PMID assignment and compared **five encoders at two
learning rates and three seeds, for 30 completed cells**. Learning rates below are
selected by mean validation F1. Tokenizer-specific truncation caused small
differences in the effective datasets, which are shown explicitly below.

**1,200 reviewed documents → 1,083 pathway-positive documents; effective splits**
**vary by tokenizer**

| Encoder | Selected LR | Seeds | Test F1 | Precision | Recall | Effective train/validation/test |
|---|---:|---:|---:|---:|---:|---:|
| BiomedBERT-base | 3e-5 | 3 | 0.8033 ± 0.0179 | 0.7737 ± 0.0155 | 0.8353 ± 0.0219 | 860/107/109 |
| BERT-base | 3e-5 | 3 | 0.7982 ± 0.0201 | 0.7614 ± 0.0200 | 0.8388 ± 0.0209 | 851/107/109 |
| BioClinicalBERT | 5e-5 | 3 | 0.8032 ± 0.0064 | 0.7564 ± 0.0128 | 0.8563 ± 0.0105 | 847/106/108 |
| BioELECTRA-base | 3e-5 | 3 | **0.8156 ± 0.0175** | 0.7752 ± 0.0192 | 0.8606 ± 0.0174 | 860/107/109 |
| Bio-ModernBERT-base | 8e-5 | 3 | 0.8031 ± 0.0226 | 0.7660 ± 0.0304 | 0.8446 ± 0.0242 | 860/107/109 |

**Detailed results and configurations: Appendix C.1.**

BioELECTRA had the highest descriptive mean, but the differences were smaller than
the observed run variation. In the paired comparison between BERT-base and
BiomedBERT-base, the estimated F1 difference was -0.0051 with a 95% interval of
[-0.0354, +0.0275], so the experiment did not establish an encoder advantage. The
30-cell result record is tracked in [`runs/summary.jsonl`](../runs/summary.jsonl).

### 4.4 Full-corpus pathway reviewer

A separate BiomedBERT-base model was trained on a random split containing all 3,200
documents in the then-current reviewed `gold-wave4` corpus, including documents with
no pathway span.

**3,200 reviewed documents → 2,560/320/320 train/validation/test documents,**
**including span-free documents**

With learning rate 3e-5 and seed 42, the model reached validation F1 0.8583 and test
precision 0.8126, recall 0.8694, and F1 0.8400. This checkpoint was subsequently
used as the independent pathway source in the disagreement analysis for the
remaining 6,125 documents. Its role was annotation curation rather than comparison
with the frozen-test-set models.

**Complete training configuration: Appendix C.2.**

### 4.5 Expanded reviewed training corpus

The next TRUBA run increased the reviewed training supervision while preserving the
same 107-document validation and 109-document test sets. The source corpus contained
3,200 reviewed documents, of which 2,887 had at least one pathway span. The frozen
assignment contained 2,664/107/109 documents plus seven historical exclusions. Under
the 512-token processing used by these three encoders, five assigned training
documents lost all positive labels, producing the effective split below.

**3,200 reviewed documents → 2,887 pathway-positive documents → 2,659/107/109**
**effective train/validation/test examples**

| Encoder          | Training documents |   LR | Seeds |             Test F1 |       Precision |          Recall |
| ---------------- | -----------------: | ---: | ----: | ------------------: | --------------: | --------------: |
| BiomedBERT-base  |              2,659 | 5e-5 |     5 | **0.8232 ± 0.0159** | 0.7951 ± 0.0142 | 0.8534 ± 0.0208 |
| BioLinkBERT-base |              2,659 | 5e-5 |     5 |     0.8132 ± 0.0076 | 0.7801 ± 0.0147 | 0.8494 ± 0.0103 |
| BioELECTRA-base  |              2,659 | 5e-5 |     5 |     0.8093 ± 0.0156 | 0.7710 ± 0.0198 | 0.8518 ± 0.0142 |

This experiment belongs to the original frozen reviewed-gold evaluation line. It is
not directly comparable with the later 10k results, which use a new 1,013-document
test set.

**Detailed multi-seed results: Appendix C.3.**

### 4.6 TRUBA sweep on the 10,125-document dataset

The current experiment compares three base encoders and two large encoders on the
same 8,100/1,012/1,013 split. Base-model cells used three seeds. Large models were
scheduled across three learning rates and three seeds; six of the initial cells hit
the eight-hour wall limit and were resubmitted with a 12-hour limit.

**10,125 mixed-curation corpus documents → 8,100/1,012/1,013**
**train/validation/test documents**

| Model | Parameters | Learning rate | Completed seeds | Validation F1 | Test F1 | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| BiomedBERT-base | 110M | 5e-5 | 3/3 | 0.8860 ± 0.0043 | 0.8741 ± 0.0059 | 0.8631 ± 0.0057 | 0.8854 ± 0.0081 |
| BioLinkBERT-base | 110M | 5e-5 | 3/3 | 0.8847 ± 0.0041 | **0.8772 ± 0.0095** | 0.8680 ± 0.0101 | 0.8867 ± 0.0090 |
| BioELECTRA-base | 110M | 3e-5 | 3/3 | 0.8883 ± 0.0024 | 0.8765 ± 0.0050 | 0.8658 ± 0.0068 | 0.8875 ± 0.0033 |
| BioLinkBERT-large | 340M | 1e-5 | 2/3 | 0.8878 ± 0.0031 | 0.8791 ± 0.0019 | 0.8661 ± 0.0113 | 0.8927 ± 0.0081 |
| BioLinkBERT-large | 340M | 2e-5 | 2/3 | 0.8883 ± 0.0083 | 0.8755 ± 0.0005 | 0.8598 ± 0.0058 | 0.8918 ± 0.0052 |
| BioLinkBERT-large | 340M | 3e-5 | 1/3 | 0.8914 | 0.8779 | 0.8616 | 0.8947 |
| BioM-ELECTRA-large | 335M | 1e-5 | 3/3 | 0.8870 ± 0.0009 | 0.8739 ± 0.0007 | 0.8670 ± 0.0041 | 0.8808 ± 0.0033 |
| BioM-ELECTRA-large | 335M | 2e-5 | 2/3 | 0.8842 ± 0.0009 | 0.8723 ± 0.0015 | 0.8632 ± 0.0074 | 0.8816 ± 0.0046 |
| BioM-ELECTRA-large | 335M | 3e-5 | 2/3 | 0.8902 ± 0.0041 | **0.8820 ± 0.0054** | 0.8746 ± 0.0076 | 0.8896 ± 0.0032 |

The best available large-model mean was only 0.0048 F1 above the best complete base
row and was based on two seeds. The completed timeout and 5e-5 sweeps are therefore
needed before choosing a large-model learning rate. The original sweep retained
metrics and predictions but intentionally deleted checkpoints. Separate retrains
were submitted to preserve one validation-selected checkpoint per model.

The TRUBA jobs used the `akya-cuda` partition, one V100 GPU per array task, and an
Apptainer environment with pinned library versions. The tracked job definitions are
under [`slurm/`](../slurm).

**Model IDs, batch and accumulation settings, precision modes, and learning-rate**
**grids: Appendix C.4.**

## 5. Current position

By 16 August, the project had produced a model-ready 10,125-document pathway corpus,
a frozen and leakage-resistant evaluation split, and a common training and
provenance framework for base and large biomedical encoders. The three complete base
models scored within approximately 0.003 F1 of one another. The available large
results were also close to this band, so the final model choice remained contingent
on the submitted timeout, 5e-5, and checkpoint-retaining runs.

The most immediate deliverable after those jobs is a five-model table with complete
three-seed groups and a concrete retained checkpoint for each candidate. Because
every 10k run records dataset, split, tokenizer, software, hardware, and Git
provenance, the final comparison can be tied to the exact corpus and training code
used here.

---

## Appendix A. Pathway query coverage

`Pair queries with hits` is the number of the 98 disease pairings that returned at
least one PMID. `Unique PMIDs` is deduplicated within the pathway term.

| # | Pathway query term | Pair queries with hits | Unique PMIDs | Status |
|---:|---|---:|---:|---|
| 1 | glycolysis/gluconeogenesis | 38 | 185 | Hit |
| 2 | bile acid synthesis | 41 | 243 | Hit |
| 3 | ubiquinone synthesis | 1 | 4 | Hit |
| 4 | vitamin a metabolism | 25 | 76 | Hit |
| 5 | citric acid cycle | 49 | 232 | Hit |
| 6 | alanine and aspartate metabolism | 0 | 0 | No hit |
| 7 | intracellular demand | 1 | 1 | Hit |
| 8 | vitamin c metabolism | 15 | 31 | Hit |
| 9 | linoleate metabolism | 5 | 4 | Hit |
| 10 | hyaluronan metabolism | 13 | 22 | Hit |
| 11 | d-alanine metabolism | 1 | 1 | Hit |
| 12 | oxidative phosphorylation | 66 | 802 | Hit |
| 13 | r group synthesis | 0 | 0 | No hit |
| 14 | arachidonic acid metabolism | 44 | 367 | Hit |
| 15 | nad metabolism | 38 | 190 | Hit |
| 16 | heme synthesis | 32 | 135 | Hit |
| 17 | chondroitin sulfate degradation | 1 | 1 | Hit |
| 18 | lipoate metabolism | 0 | 0 | No hit |
| 19 | folate metabolism | 44 | 338 | Hit |
| 20 | lysine metabolism | 17 | 45 | Hit |
| 21 | biomass and maintenance functions | 0 | 0 | No hit |
| 22 | nucleotide metabolism | 44 | 308 | Hit |
| 23 | galactose metabolism | 32 | 99 | Hit |
| 24 | nucleotide sugar metabolism | 17 | 41 | Hit |
| 25 | beta-alanine metabolism | 24 | 45 | Hit |
| 26 | fatty acid oxidation | 62 | 588 | Hit |
| 27 | propanoate metabolism | 18 | 39 | Hit |
| 28 | inositol phosphate metabolism | 24 | 57 | Hit |
| 29 | protein formation | 29 | 72 | Hit |
| 30 | starch and sucrose metabolism | 22 | 57 | Hit |
| 31 | vitamin d metabolism | 41 | 256 | Hit |
| 32 | vitamin b6 metabolism | 23 | 68 | Hit |
| 33 | phosphatidylinositol phosphate metabolism | 0 | 0 | No hit |
| 34 | intracellular source/sink | 0 | 0 | No hit |
| 35 | valine, leucine, and isoleucine metabolism | 0 | 0 | No hit |
| 36 | biotin metabolism | 14 | 16 | Hit |
| 37 | thiamine metabolism | 19 | 35 | Hit |
| 38 | urea cycle | 49 | 416 | Hit |
| 39 | miscellaneous | 68 | 556 | Hit |
| 40 | tryptophan metabolism | 47 | 459 | Hit |
| 41 | squalene and cholesterol synthesis | 0 | 0 | No hit |
| 42 | aminosugar metabolism | 0 | 0 | No hit |
| 43 | leukotriene metabolism | 4 | 8 | Hit |
| 44 | androgen and estrogen synthesis and metabolism | 0 | 0 | No hit |
| 45 | coa synthesis | 28 | 57 | Hit |
| 46 | hippurate metabolism | 0 | 0 | No hit |
| 47 | drug metabolism | 56 | 541 | Hit |
| 48 | tetrahydrobiopterin metabolism | 2 | 4 | Hit |
| 49 | vitamin e metabolism | 8 | 10 | Hit |
| 50 | n-glycan synthesis | 4 | 4 | Hit |
| 51 | peptide metabolism | 16 | 34 | Hit |
| 52 | alkaloid synthesis | 0 | 0 | No hit |
| 53 | o-glycan metabolism | 0 | 0 | No hit |
| 54 | fatty acid synthesis | 44 | 364 | Hit |
| 55 | dietary fiber binding | 0 | 0 | No hit |
| 56 | histidine metabolism | 27 | 92 | Hit |
| 57 | pyrimidine catabolism | 6 | 9 | Hit |
| 58 | purine catabolism | 23 | 75 | Hit |
| 59 | nucleotide salvage pathway | 5 | 7 | Hit |
| 60 | pyrimidine synthesis | 24 | 139 | Hit |
| 61 | steroid metabolism | 33 | 176 | Hit |
| 62 | taurine and hypotaurine metabolism | 18 | 56 | Hit |
| 63 | n-glycan metabolism | 0 | 0 | No hit |
| 64 | triacylglycerol synthesis | 17 | 71 | Hit |
| 65 | keratan sulfate synthesis | 0 | 0 | No hit |
| 66 | fructose and mannose metabolism | 13 | 29 | Hit |
| 67 | cholesterol metabolism | 54 | 576 | Hit |
| 68 | heparan sulfate degradation | 12 | 17 | Hit |
| 69 | n-glycan degradation | 3 | 2 | Hit |
| 70 | glutathione metabolism | 50 | 375 | Hit |
| 71 | glutamate metabolism | 44 | 345 | Hit |
| 72 | coa catabolism | 0 | 0 | No hit |
| 73 | glycine, serine, alanine, and threonine metabolism | 0 | 0 | No hit |
| 74 | methionine and cysteine metabolism | 0 | 0 | No hit |
| 75 | heme degradation | 24 | 96 | Hit |
| 76 | vitamin b12 metabolism | 25 | 74 | Hit |
| 77 | pyruvate metabolism | 43 | 193 | Hit |
| 78 | glyoxylate and dicarboxylate metabolism | 22 | 49 | Hit |
| 79 | sphingolipid metabolism | 52 | 475 | Hit |
| 80 | arginine and proline metabolism | 32 | 147 | Hit |
| 81 | limonene and pinene degradation | 0 | 0 | No hit |
| 82 | phenylalanine metabolism | 37 | 144 | Hit |
| 83 | exchange/demand reaction | 0 | 0 | No hit |
| 84 | c5-branched dibasic acid metabolism | 3 | 4 | Hit |
| 85 | tyrosine metabolism | 37 | 192 | Hit |
| 86 | cytochrome metabolism | 7 | 6 | Hit |
| 87 | butanoate metabolism | 22 | 55 | Hit |
| 88 | glycosphingolipid metabolism | 32 | 88 | Hit |
| 89 | pentose phosphate pathway | 47 | 413 | Hit |
| 90 | chondroitin synthesis | 0 | 0 | No hit |
| 91 | purine synthesis | 26 | 168 | Hit |
| 92 | blood group synthesis | 0 | 0 | No hit |
| 93 | eicosanoid metabolism | 25 | 83 | Hit |
| 94 | ros detoxification | 23 | 48 | Hit |
| 95 | nucleotide interconversion | 2 | 2 | Hit |
| 96 | keratan sulfate degradation | 1 | 1 | Hit |
| 97 | glycerophospholipid metabolism | 42 | 294 | Hit |
| 98 | vitamin b2 metabolism | 2 | 2 | Hit |

## Appendix B. Disease query coverage

`Pair queries with hits` is the number of the 98 pathway pairings that returned at
least one PMID. `Unique PMIDs` is deduplicated within the disease term.

| # | Category | Disease query term | Pair queries with hits | Unique PMIDs | Status |
|---:|---|---|---:|---:|---|
| 1 | Cancer | Breast Neoplasms | 16 | 30 | Hit |
| 2 | Cancer | Lung Neoplasms | 11 | 14 | Hit |
| 3 | Cancer | Colorectal Neoplasms, Hereditary Nonpolyposis | 0 | 0 | No hit |
| 4 | Cancer | Liver Neoplasms | 11 | 12 | Hit |
| 5 | Cancer | Carcinoma, Hepatocellular | 8 | 6 | Hit |
| 6 | Cancer | Pancreatic Neoplasms | 4 | 7 | Hit |
| 7 | Cancer | Prostatic Neoplasms | 4 | 6 | Hit |
| 8 | Cancer | Stomach Neoplasms | 3 | 4 | Hit |
| 9 | Cancer | Ovarian Neoplasms | 2 | 12 | Hit |
| 10 | Cancer | Brain Neoplasms | 3 | 6 | Hit |
| 11 | Cancer | Glioblastoma | 39 | 334 | Hit |
| 12 | Cancer | Glioma | 41 | 364 | Hit |
| 13 | Cancer | Leukemia | 58 | 474 | Hit |
| 14 | Cancer | Leukemia, Myeloid, Acute | 0 | 0 | No hit |
| 15 | Cancer | Leukemia, Lymphocytic, Chronic, B-Cell | 0 | 0 | No hit |
| 16 | Cancer | Lymphoma | 45 | 315 | Hit |
| 17 | Cancer | Lymphoma, Non-Hodgkin | 0 | 0 | No hit |
| 18 | Cancer | Hodgkin Disease | 3 | 4 | Hit |
| 19 | Cancer | Multiple Myeloma | 35 | 148 | Hit |
| 20 | Cancer | Melanoma | 45 | 334 | Hit |
| 21 | Cancer | Thyroid Neoplasms | 4 | 9 | Hit |
| 22 | Cancer | Carcinoma | 62 | 724 | Hit |
| 23 | Cancer | Kidney Neoplasms | 1 | 1 | Hit |
| 24 | Cancer | Carcinoma, Renal Cell | 1 | 1 | Hit |
| 25 | Cancer | Urinary Bladder Neoplasms | 1 | 1 | Hit |
| 26 | Cancer | Esophageal Neoplasms | 1 | 1 | Hit |
| 27 | Cancer | Uterine Cervical Neoplasms | 1 | 1 | Hit |
| 28 | Cancer | Endometrial Neoplasms | 1 | 2 | Hit |
| 29 | Cancer | Head and Neck Neoplasms | 3 | 4 | Hit |
| 30 | Cancer | Mesothelioma | 27 | 79 | Hit |
| 31 | Cancer | Neuroblastoma | 42 | 244 | Hit |
| 32 | Cancer | Cholangiocarcinoma | 33 | 128 | Hit |
| 33 | Cancer | Sarcoma | 37 | 185 | Hit |
| 34 | Cancer | Neoplasms, Hormone-Dependent | 0 | 0 | No hit |
| 35 | Cancer | Adenocarcinoma | 57 | 424 | Hit |
| 36 | Cancer | Carcinoma, Squamous Cell | 2 | 2 | Hit |
| 37 | Cancer | Carcinoma, Pancreatic Ductal | 0 | 0 | No hit |
| 38 | Neurodegenerative | Alzheimer Disease | 34 | 117 | Hit |
| 39 | Neurodegenerative | Parkinson Disease | 24 | 71 | Hit |
| 40 | Neurodegenerative | Amyotrophic Lateral Sclerosis | 34 | 201 | Hit |
| 41 | Neurodegenerative | Huntington Disease | 16 | 43 | Hit |
| 42 | Neurodegenerative | Multiple Sclerosis | 42 | 304 | Hit |
| 43 | Neurodegenerative | Frontotemporal Dementia | 15 | 55 | Hit |
| 44 | Neurodegenerative | Lewy Body Disease | 7 | 11 | Hit |
| 45 | Neurodegenerative | Dementia, Vascular | 1 | 1 | Hit |
| 46 | Neurodegenerative | Prion Diseases | 14 | 35 | Hit |
| 47 | Neurodegenerative | Spinocerebellar Ataxias | 5 | 5 | Hit |
| 48 | Neurodegenerative | Friedreich Ataxia | 8 | 38 | Hit |
| 49 | Neurodegenerative | Supranuclear Palsy, Progressive | 0 | 0 | No hit |
| 50 | Neurodegenerative | Multiple System Atrophy | 11 | 16 | Hit |
| 51 | Neurodegenerative | Muscular Dystrophies | 6 | 18 | Hit |
| 52 | Neurodegenerative | Muscular Dystrophy, Duchenne | 0 | 0 | No hit |
| 53 | Neurodegenerative | Spinal Muscular Atrophies of Childhood | 0 | 0 | No hit |
| 54 | Neurodegenerative | Charcot-Marie-Tooth Disease | 14 | 25 | Hit |
| 55 | Neurodegenerative | Spastic Paraplegia, Hereditary | 1 | 1 | Hit |
| 56 | Neurodegenerative | Epilepsy | 49 | 368 | Hit |
| 57 | Neurodegenerative | Schizophrenia | 46 | 267 | Hit |
| 58 | Neurodegenerative | Bipolar Disorder | 31 | 136 | Hit |
| 59 | Neurodegenerative | Major Depressive Disorder | 29 | 158 | Hit |
| 60 | Neurodegenerative | Autism Spectrum Disorder | 42 | 187 | Hit |
| 61 | Neurodegenerative | Attention Deficit Disorder with Hyperactivity | 1 | 1 | Hit |
| 62 | Neurodegenerative | Brain Ischemia | 19 | 53 | Hit |
| 63 | Neurodegenerative | Stroke | 55 | 420 | Hit |
| 64 | Neurodegenerative | Brain Diseases | 24 | 55 | Hit |
| 65 | Neurodegenerative | Neurodegenerative Diseases | 45 | 374 | Hit |
| 66 | Metabolic | Diabetes Mellitus, Type 2 | 14 | 28 | Hit |
| 67 | Metabolic | Diabetes Mellitus, Type 1 | 8 | 9 | Hit |
| 68 | Metabolic | Obesity | 62 | 674 | Hit |
| 69 | Metabolic | Metabolic Syndrome | 53 | 422 | Hit |
| 70 | Metabolic | Non-alcoholic Fatty Liver Disease | 48 | 313 | Hit |
| 71 | Metabolic | Hyperlipidemias | 7 | 19 | Hit |
| 72 | Metabolic | Hypercholesterolemia | 28 | 181 | Hit |
| 73 | Metabolic | Hypertriglyceridemia | 27 | 139 | Hit |
| 74 | Metabolic | Gout | 36 | 152 | Hit |
| 75 | Metabolic | Phenylketonurias | 1 | 1 | Hit |
| 76 | Metabolic | Insulin Resistance | 57 | 560 | Hit |
| 77 | Metabolic | Hyperuricemia | 37 | 188 | Hit |
| 78 | Metabolic | Fatty Liver | 51 | 489 | Hit |
| 79 | Metabolic | Liver Cirrhosis | 37 | 204 | Hit |
| 80 | Metabolic | Atherosclerosis | 60 | 482 | Hit |
| 81 | Metabolic | Coronary Artery Disease | 39 | 209 | Hit |
| 82 | Metabolic | Hypertension | 56 | 579 | Hit |
| 83 | Metabolic | Anemia, Iron-Deficiency | 0 | 0 | No hit |
| 84 | Metabolic | Anemia, Sickle Cell | 1 | 1 | Hit |
| 85 | Metabolic | Porphyrias | 12 | 47 | Hit |
| 86 | Metabolic | Galactosemias | 1 | 9 | Hit |
| 87 | Metabolic | Glycogen Storage Disease | 19 | 78 | Hit |
| 88 | Metabolic | Mucopolysaccharidoses | 6 | 17 | Hit |
| 89 | Metabolic | Gaucher Disease | 8 | 57 | Hit |
| 90 | Metabolic | Niemann-Pick Diseases | 1 | 1 | Hit |
| 91 | Metabolic | Fabry Disease | 13 | 52 | Hit |
| 92 | Metabolic | Maple Syrup Urine Disease | 11 | 52 | Hit |
| 93 | Metabolic | Homocystinuria | 13 | 82 | Hit |
| 94 | Metabolic | Cystic Fibrosis | 31 | 187 | Hit |
| 95 | Metabolic | Hepatolenticular Degeneration | 3 | 3 | Hit |
| 96 | Metabolic | Hemochromatosis | 12 | 40 | Hit |
| 97 | Metabolic | Vitamin D Deficiency | 18 | 63 | Hit |
| 98 | Metabolic | Scurvy | 15 | 44 | Hit |

## Appendix C. Experiment configurations and complete result groups

**This appendix contains the complete experiment grids and configurations referenced
from Sections 4.3–4.6.**

### C.1 Phase 4b five-encoder grid

Every row contains three seeds. All rows use class weights 0.5/1.5/1.0, 40 maximum
epochs, patience 8, no frozen layers, and effective batch size 16.

| Model | Hugging Face ID | Parameters | Context | LR | Validation F1 | Test P | Test R | Test F1 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| BiomedBERT-base | `microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext` | 110M | 512 | 3e-5 | 0.8296 ± 0.0065 | 0.7737 ± 0.0155 | 0.8353 ± 0.0219 | 0.8033 ± 0.0179 |
| BiomedBERT-base | same | 110M | 512 | 5e-5 | 0.8194 ± 0.0118 | 0.7644 ± 0.0404 | 0.8393 ± 0.0122 | 0.7999 ± 0.0275 |
| BERT-base | `google-bert/bert-base-uncased` | 110M | 512 | 3e-5 | 0.7895 ± 0.0042 | 0.7614 ± 0.0200 | 0.8388 ± 0.0209 | 0.7982 ± 0.0201 |
| BERT-base | same | 110M | 512 | 5e-5 | 0.7889 ± 0.0148 | 0.7597 ± 0.0273 | 0.8374 ± 0.0108 | 0.7966 ± 0.0196 |
| BioClinicalBERT | `emilyalsentzer/Bio_ClinicalBERT` | 110M | 512 | 3e-5 | 0.7867 ± 0.0041 | 0.7356 ± 0.0241 | 0.8703 ± 0.0042 | 0.7971 ± 0.0134 |
| BioClinicalBERT | same | 110M | 512 | 5e-5 | 0.8050 ± 0.0037 | 0.7564 ± 0.0128 | 0.8563 ± 0.0105 | 0.8032 ± 0.0064 |
| BioELECTRA-base | `kamalkraj/bioelectra-base-discriminator-pubmed-pmc` | 110M | 512 | 3e-5 | 0.8205 ± 0.0052 | 0.7752 ± 0.0192 | 0.8606 ± 0.0174 | 0.8156 ± 0.0175 |
| BioELECTRA-base | same | 110M | 512 | 5e-5 | 0.8204 ± 0.0124 | 0.7436 ± 0.0138 | 0.8499 ± 0.0140 | 0.7931 ± 0.0021 |
| Bio-ModernBERT-base | `thomas-sounack/Bio-ModernBERT-base` | 150M | 8192 | 5e-5 | 0.8142 ± 0.0057 | 0.7482 ± 0.0164 | 0.8353 ± 0.0061 | 0.7893 ± 0.0068 |
| Bio-ModernBERT-base | same | 150M | 8192 | 8e-5 | 0.8209 ± 0.0104 | 0.7660 ± 0.0304 | 0.8446 ± 0.0242 | 0.8031 ± 0.0226 |

### C.2 Full-corpus pathway reviewer

| Model | Data split | O/B/I weights | Frozen layers | LR | Seed | Max epochs / patience | Best epoch | Validation F1 | Test P | Test R | Test F1 |
|---|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| BiomedBERT-base | `gold-wave4-random-all`, 2560/320/320 | 0.5/1.5/1.0 | 0 | 3e-5 | 42 | 40 / 30 | 38 | 0.8583 | 0.8126 | 0.8694 | 0.8400 |

### C.3 Expanded reviewed-corpus TRUBA grid

All rows used the same frozen 107/109 validation/test sets, 2,659 effective training
documents, class weights 0.5/1.5/1.0, 40 maximum epochs, patience 8, no frozen
layers, and five seeds: 42, 1, 7, 13, and 21.

| Model            |   LR |   Validation F1 |          Test P |          Test R |         Test F1 | Mean best epoch |
| ---------------- | ---: | --------------: | --------------: | --------------: | --------------: | --------------: |
| BiomedBERT-base  | 5e-5 | 0.8427 ± 0.0091 | 0.7951 ± 0.0142 | 0.8534 ± 0.0208 | 0.8232 ± 0.0159 |              11 |
| BioLinkBERT-base | 5e-5 | 0.8447 ± 0.0115 | 0.7801 ± 0.0147 | 0.8494 ± 0.0103 | 0.8132 ± 0.0076 |              13 |
| BioELECTRA-base  | 5e-5 | 0.8420 ± 0.0070 | 0.7710 ± 0.0198 | 0.8518 ± 0.0142 | 0.8093 ± 0.0156 |              15 |

### C.4 Pathway-10k encoder configuration

All 10k runs use class weights 0.5/1.5/1.0, 40 maximum epochs, patience 8, no
frozen layers, and effective batch size 16. The base runs use seeds 42, 1, and 7.
The original large-model grid uses the same seeds at 1e-5, 2e-5, and 3e-5.

| Registry key | Hugging Face ID | Parameters | Batch × accumulation | Precision on V100 | Initial LR grid |
|---|---|---:|---:|---|---|
| `biomedbert-base` | `microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext` | 110M | 16 × 1 | fp16 | 5e-5 |
| `biolinkbert-base` | `michiyasunaga/BioLinkBERT-base` | 110M | 16 × 1 | fp16 | 5e-5 |
| `bioelectra-base` | `kamalkraj/bioelectra-base-discriminator-pubmed-pmc` | 110M | 16 × 1 | fp16 | 3e-5 |
| `biolinkbert-large` | `michiyasunaga/BioLinkBERT-large` | 340M | 4 × 4 | fp16 | 1e-5, 2e-5, 3e-5 |
| `biom-electra-large` | `sultan/BioM-ELECTRA-Large-Discriminator` | 335M | 4 × 4 | fp16 | 1e-5, 2e-5, 3e-5 |

The additional large-model 5e-5 cells and timeout reruns were pending in the latest
status recorded for this report. The checkpoint-retaining jobs selected one seed per
model by validation F1; the large selections remained provisional until the full
learning-rate groups completed.
