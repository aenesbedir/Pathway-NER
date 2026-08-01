# Base-encoder expansion — full candidate analysis (July 2026)

Follow-up to `reports/base_model_survey_2026-07.md`. That note listed five
candidates and stopped at a recommendation. This one widens the search to every
encoder family that is plausibly usable for this task, pulls the numbers the
papers actually report, and specifies what has to change in the pipeline before
any cross-model number is trustworthy.

**Status:** research only. No code changed, no model swapped.

## 0. Scope

"Base model" here means the **encoder that `train.py` fine-tunes**
(currently `microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext`), not
the annotator LLM (`llm/models.py`, currently `qwen2.5:14b`). Those are two
independent axes:

| Axis | Component | Registry | What swapping it changes |
|---|---|---|---|
| **A — encoder** (this document) | `train.py`, `preprocessing/tag_bio.py` | none yet | how well the student fits the existing gold labels |
| B — annotator LLM | `llm/run_silver.py` | `llm/models.py` | the gold labels themselves |

"Deriving a new dataset per base model" on axis A means exactly one thing:
**re-tokenizing the same gold spans with that model's tokenizer**. Gold spans are
stored as character offsets in `data/processed/gold/matches.jsonl`, which is
tokenizer-independent; only `bio_tags.jsonl` and `{train,val,test}.jsonl` carry
`input_ids` and are therefore model-specific. Nothing is re-annotated.

## 1. Baseline to beat

| Quantity | Value | Source |
|---|---|---|
| Best model | gold-008 (lr 5e-5, all layers trainable) | `knowledge_base/model_experiments.md` |
| Test F1 / P / R | **0.8197** / 0.7826 / 0.8606 | same |
| Seed noise band (3 seeds) | **± 0.007 F1**, ± 0.019 P | gold-004/005/006 |
| Teacher qwen2.5:14b | F1 0.864 | golden-set eval |
| Train / val / test | 860 / 107 / 109 documents | `data/processed/gold/README.md` |
| Positive tokens (train) | 5,943 | same |

Two facts dominate everything below: the training set is **860 abstracts**, and
the test set is **109 abstracts**. At that size the 95% bootstrap interval on
test F1 is roughly ±0.04 — wider than any encoder-swap effect reported in the
literature.

## 2. Candidate landscape

### 2.1 Classic BERT-family biomedical encoders (512 ctx, WordPiece)

| Model | HF id | Params | Vocab / case | Pretraining corpus | Objective | BLURB NER |
|---|---|---|---|---|---|---|
| **Current** BiomedBERT-base | `microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext` | 110M | 30522 / uncased | PubMed abstracts + PMC full text | MLM | 86.13 |
| BiomedBERT-base (abstracts) | `microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract` | 110M | 28895 / uncased | PubMed abstracts | MLM | 86.08 (86.17 w/ stabilization) |
| **BioLinkBERT-large** | `michiyasunaga/BioLinkBERT-large` | 340M | 28895 / uncased | PubMed + **citation graph** | MLM + document-relation prediction | **86.89** (BLURB #1) |
| BioLinkBERT-base | `michiyasunaga/BioLinkBERT-base` | 110M | 28895 / uncased | same | same | 86.39 |
| **BioM-ELECTRA-large** | `sultan/BioM-ELECTRA-Large-Discriminator` | 335M | 28895 / uncased | PubMed abstracts | ELECTRA RTD | **86.88** |
| BioM-ALBERT-xxlarge-PMC | `sultan/BioM-ALBERT-xxlarge-PMC` | 235M (shared) | 28895 | PubMed + PMC | MLM | 85.30 |
| BiomedBERT-large | `microsoft/BiomedNLP-BiomedBERT-large-uncased-abstract` | 340M | 30522 / uncased | PubMed abstracts only | MLM | 86.28 |
| **BioELECTRA-base** | `kamalkraj/bioelectra-base-discriminator-pubmed-pmc` | 110M | 30522 | PubMed + PMC | ELECTRA RTD | **86.67** |
| BioBERT-large | `dmis-lab/biobert-large-cased-v1.1` | 340M | 30522 / **cased** | PubMed, from general BERT | MLM | 85.81 (base) |
| BioMed-RoBERTa | `allenai/biomed_roberta_base` | 125M | 50265 / cased | 2.68M PMC papers (DAPT) | MLM | — |
| SciBERT | `allenai/scibert_scivocab_uncased` | 110M | 31090 | Semantic Scholar (18% bio) | MLM | 85.43 |
| Bio_ClinicalBERT | `emilyalsentzer/Bio_ClinicalBERT` | 110M | 28996 / cased | MIMIC-III notes | MLM | 83.99 |

**Read of the BLURB NER column:** the entire span from our current base (86.13)
to the leaderboard's best (86.89) is **0.76 points**, and that is averaged over
six large NER corpora with thousands of training documents each. Model size
buys +0.1 to +0.5; the pretraining *objective* and *corpus* buy more than the
parameter count (BioELECTRA-**base** at 86.67 beats BiomedBERT-**large** at 86.28).

### 2.2 ModernBERT generation (8192 ctx, BPE, RoPE + FlashAttention)

| Model | HF id | Params | Ctx | Corpus | Note |
|---|---|---|---|---|---|
| ModernBERT-large | `answerdotai/ModernBERT-large` | 396M | 8192 | 2T general tokens | general domain; the base all bio variants continue from |
| BioClinical-ModernBERT-large | `thomas-sounack/BioClinical-ModernBERT-large` | 396M | 8192 | 50.7B bio + **2.8B clinical** (20 sources) | SOTA on clinical tasks |
| BioClinical-ModernBERT-base | `thomas-sounack/BioClinical-ModernBERT-base` | 150M | 8192 | same | |
| **Bio-ModernBERT-large** | `thomas-sounack/Bio-ModernBERT-large` | 396M | 8192 | biomedical only (no clinical) | ablation sibling; closest to our domain |
| Bio-ModernBERT-base | `thomas-sounack/Bio-ModernBERT-base` | 150M | 8192 | same | |
| **ModernBERT-bio-large** | `almanach/ModernBERT-bio-large` | 396M | 8192 | 50B: PubMed 60% / Med-Inst 20% / MIMIC 20% | **CLM-detour** pretraining (arXiv 2605.12438, 2026) |
| ModernBERT-bio-base | `almanach/ModernBERT-bio-base` | 150M | 8192 | same | |
| Clinical ModernBERT | `Simonlee711/Clinical_ModernBERT` | 137M | 8192 | PubMed + MIMIC-IV + medical ontologies | clinical skew |

The decisive evidence is Table 2 of the almanach paper (5 seeds, 42–50), because
it is the only place where a ModernBERT-class bio encoder is put head to head
with PubMedBERT on **literature** NER:

| Model | Ctx | BC5CDR | JNLPBA | NCBI | AnatEM |
|---|---|---|---|---|---|
| PubMedBERT (110M) | 512 | 89.7 | 74.9 | **82.1** | **83.3** |
| BioClinical-ModernBERT | 8192 | 88.7 | 74.8 | 78.7 | 79.2 |
| ModernBERT-bio base (150M) | 8192 | 89.1 | 74.2 | 80.4 | 79.9 |
| ModernBERT-bio large (396M) | 8192 | **89.8** | **75.3** | 81.7 | 83.2 |

Two conclusions, both uncomfortable for the "bigger encoder" thesis:

1. A 396M 8192-context 2026 encoder is **within noise of 110M PubmedBERT** on
   biomedical-literature NER (+0.1 BC5CDR, +0.4 JNLPBA, −0.4 NCBI, −0.1 AnatEM).
2. **Clinical-heavy pretraining actively hurts literature NER** (BioClinical-
   ModernBERT is 1.0–4.1 points below PubMedBERT on all four). This rules
   `BioClinical-ModernBERT-*` out for us despite its "SOTA" headline — its SOTA
   is on DEID / Social History / COS, i.e. clinical notes. Our corpus is PubMed
   abstracts.

So within the ModernBERT family the right picks are `Bio-ModernBERT-large`
(bio-only) and `almanach/ModernBERT-bio-large` (best measured average), not the
BioClinical one the earlier survey ranked second.

### 2.3 NER-specialised models — a different paradigm

These are not "base encoders" you attach a linear head to; they are already
trained on the NER *task* over hundreds of thousands of entity types. That is
precisely the kind of prior 860 documents cannot buy.

| Model | HF id | Backbone | Paradigm |
|---|---|---|---|
| GLiNER-biomed-large (uni) | `Ihor/gliner-biomed-large-v1.0` | DeBERTa-v3-large | span × label-embedding scoring |
| GLiNER-biomed-bi-large | `Ihor/gliner-biomed-bi-large-v1.0` | DeBERTa-v3-large + bge-base | bi-encoder, cheap with many labels |
| GLiNER-biomed-base / small | `Ihor/gliner-biomed-*-v1.0` | DeBERTa-v3-base/small | same |
| NuNER v2 | `numind/NuNER-v2.0` | RoBERTa-base | encoder pretrained on 4.38M GPT-3.5 annotations, 200k concepts |

GLiNER-biomed (Bioinformatics 2026, arXiv 2504.00676) was built by **distilling
LLM annotation ability into a small model** — structurally the same idea as this
project's `qwen2.5:14b → BiomedBERT` distillation, but done at a scale we cannot
reach. Reported numbers:

| Regime | GLiNER-biomed-bi | Best baseline |
|---|---|---|
| zero-shot (8 corpora, micro-F1) | 59.77 | 53.81 (GLiNER-v2.5-large) |
| 10-shot | 70.39 | 65.93 |
| 20-shot | 73.07 | — |
| 50-shot | 76.02 | — |
| full supervision | ~84.9 | converges with baselines |

The last row is the honest caveat: **with enough labelled data the advantage
disappears**. Our 860 documents sit between "50-shot" and "full", so GLiNER-biomed
is a genuine candidate rather than a certainty — but it is the only candidate
whose expected gain is plausibly larger than the ±0.007 noise band.

### 2.4 Domain/task-adaptive pretraining instead of a bigger model

`OpenMed NER` (arXiv 2508.01630) reaches SOTA on **10 of 12** biomedical NER
benchmarks using ordinary backbones (DeBERTa-v3, PubMedBERT, BioELECTRA) by
combining domain-adaptive pretraining on a 350k-passage biomedical corpus with
LoRA (<1.5% of parameters updated), under 12 GPU-hours per model. Improvements
of +2.7 (BC5CDR-Disease) to +9.7 points come from *adaptation*, not from size.

We already hold a large unlabelled, on-topic corpus (`data/raw/` — PubMed
abstracts fetched by pathway×disease co-occurrence). Continued MLM on that corpus
before fine-tuning (TAPT) is a lever the earlier survey never considered, and on
paper it beats the encoder swap.

### 2.5 Rejected without experiment

| Model | Why not |
|---|---|
| BioClinical-ModernBERT (any size) | measurably worse than a 110M model on literature NER (§2.2) |
| Bio_ClinicalBERT, Clinical ModernBERT | clinical-note domain; BLURB NER 83.99 |
| DeBERTa-v3-large (general) | out-of-domain vocabulary; only useful as a control, and it is already the GLiNER-biomed backbone |
| BioM-ALBERT-xxlarge | parameter sharing makes it slow to fine-tune; NER 85.30, below cheaper options |
| BioBERT, SciBERT, BlueBERT | strictly dominated on BLURB NER by BiomedBERT/BioLinkBERT at equal size |
| Decoder LLMs with a token-classification head (Qwen/Llama + LoRA) | the teacher is already an LLM at F1 0.864; a distilled student exists to be cheap. Re-introducing a 7B+ model at inference defeats the purpose |

## 3. What each candidate would actually fix — mapped to our error profile

Current failure modes (from `analysis/error_analysis.json` and the gold-run notes):
over-tagging of umbrella terms (`lipid metabolism`), coordination boundaries,
subword fragmentation (`dermatan` → `dermat` + `##an` produced 10 FNs),
7 documents lost to 512-token truncation, precision 0.78 vs recall 0.86.

| Candidate | Mechanism | Which failure it plausibly touches | Expected Δ F1 |
|---|---|---|---|
| BioLinkBERT-large | citation-linked pretraining gives cross-document term knowledge; best BLURB NER | rare pathway names, umbrella/specific distinction | +0.005 … +0.02 |
| BioM-ELECTRA-large | RTD objective trains **every token** as a discriminative decision — architecturally the closest pretraining task to token classification | boundary decisions, precision | +0.005 … +0.02 |
| BiomedBERT-large | pure size ablation, same family, same tokenizer family | nothing specific | +0.00 … +0.01 |
| BioELECTRA-base | RTD at base size, fits the 8 GB card | same as BioM-ELECTRA, at zero infra cost | +0.00 … +0.015 |
| Bio-ModernBERT-large / ModernBERT-bio-large | 8192 ctx; modern architecture (~~50k BPE vocab → fewer subword splits~~ — see correction below) | the 7 truncated docs; future full-text windows | −0.01 … +0.02 |
| GLiNER-biomed-bi-large | already NER-pretrained on LLM-distilled biomedical spans; span-level scoring instead of BIO | low-data regime as a whole; boundary errors (span scoring has no BIO inconsistency failure mode) | −0.02 … +0.05 |
| TAPT/DAPT on our own PubMed corpus + any backbone | adapts the representation to *pathway* language specifically | recall on unseen pathway names | +0.01 … +0.03 |

The honest summary: **five of seven rows are inside or barely outside the ±0.007
seed band.** Only the last two have an expected value that justifies the
engineering, and only the last one is compatible with keeping the current
inference stack.

### Correction — measured while building the Tier 0 harness

Two claims above were assumptions, and both turned out to be wrong when the
tokenizers were actually run over the gold set
(`analysis/alignment_*.json`, produced by `preprocessing/check_alignment.py`):

| claim | measured |
|---|---|
| "50k BPE vocab → fewer subword splits on chemistry terms" | **The opposite.** Bio-ModernBERT masks **14.8%** of positions as continuation subwords against BiomedBERT's **7.4%**. ModernBERT inherits a general-domain vocabulary; BiomedBERT's 30k WordPiece was built on PubMed and fragments biomedical terms *less*. Any ModernBERT gain will not come from tokenization. |
| ModernBERT's `trim_offsets: true` means offsets exclude the leading space | **False.** `Ġfatty` reports offsets covering `' fatty'`. The flag governs the post-processor, not the ByteLevel pre-tokenizer. A per-character label lookup at `offset_mapping[i][0]` would have silently dropped spans; `tag_bio.py` now tests the token's whole range. |

The long-context claim did hold: at 8192 tokens ModernBERT truncates **0** of 2817
gold spans against BiomedBERT's 29.

A third fact emerged that changes the hardware plan: Bio-ModernBERT-**base**
(150M) OOMs at batch 16 on the 8 GB card and needs batch 2 with gradient
accumulation. A 512-token model pads batches to at most 512; an 8192-token one
pads to the longest document in the batch, ~2750 tokens here. Long context is not
free even when the parameter count is small.

## 4. Blockers that must be fixed *before* any comparison is meaningful

### 4.1 The split is not tokenizer-invariant — this is the critical one

`preprocessing/build_dataset.py:68` drops records with no positive labels *after*
tokenization, then shuffles the surviving PMID list (`:77-87`) with `seed=42`.
With the current tokenizer, 1083 documents → **1076** survive (7 lost to 512-token
truncation).

A different tokenizer loses a different number of documents. A ModernBERT
tokenizer at 8192 context loses **zero**. `random.shuffle` over a list of 1076
elements and over a list of 1083 elements produces **completely different splits**
— not a slightly different one. Every model would be scored on a different test
set, and the comparison would be meaningless in a way that is invisible in the
logs.

Fix: freeze the split once as a PMID→split mapping file (e.g.
`data/processed/gold/splits.json`), derive it from `matches.jsonl` (tokenizer-
independent), and have `build_dataset.py` read it instead of re-shuffling.
Do this before generating any per-model dataset.

### 4.2 Statistical power

- **Measured after this report was first written: the seed band at lr 5e-5 is
  ±0.0175, not ±0.007.** The ±0.007 figure came from gold-004/005/006 at lr 3e-5;
  three seeds of the gold-008 recipe (5e-5) on the frozen split give
  0.7947 / 0.8199 / 0.8282 → **0.8143 ± 0.0175**. Every "inside the noise band"
  judgement below is therefore *more* forgiving than stated, and gold-008's 0.8197
  was a lucky seed rather than a real improvement over gold-004's 0.8154.
- Seeds needed, from the measured σ:

  | seeds / config | SEM | smallest detectable difference |
  |---|---|---|
  | 5 | 0.0078 | 0.022 |
  | 8 | 0.0062 | 0.018 |
  | **11** | 0.0053 | **0.015** |

  **5 seeds is not enough** — it resolves 0.022 F1, the very top of the range an
  encoder swap is predicted to deliver. Use **11**; at ~8 min/run that is ~7.3
  GPU-hours for five configurations, an overnight job on the 4060.
- Report mean ± std, never a single seed.
- Adopt an explicit acceptance rule: a candidate replaces gold-008 only if its
  11-seed mean exceeds the baseline's 11-seed mean by **> 0.015 F1** — which is
  what 11 seeds can actually resolve at the measured σ of 0.0175.
- With 109 test documents, also report a paired bootstrap over documents on the
  same frozen split — a paired test is far more sensitive than comparing two
  independent confidence intervals.
- Consider promoting the golden set (`reports/golden_set_gold-008_results.md`) to
  a second, fixed evaluation set so a candidate must win on both.

### 4.3 Code changes implied

| Change | File | Why |
|---|---|---|
| `--model` flag | `preprocessing/tag_bio.py:39`, `train.py:46` | currently hardcoded in two places |
| per-model data dir | driver script | `data/processed/gold-<slug>/` holds only `input_ids` |
| `BertForTokenClassification` → `AutoModelForTokenClassification` | `train.py:176` | ELECTRA, ModernBERT, DeBERTa are not `BertModel` |
| freeze split | `build_dataset.py` | §4.1 |
| `--frozen-layers` layer-name matching | `train.py:188` | matches `encoder.layer.{i}.`; ModernBERT uses `layers.{i}.`, ELECTRA uses `encoder.layer.{i}.`. With `--frozen-layers 0` (the current best recipe) this silently does nothing, which is fine — but it must not be re-enabled blindly |
| bf16 instead of fp16 | `train.py:214` | ModernBERT was trained in bf16; fp16 fine-tuning is a known NaN source. The RTX 4060 (Ada) and A100/H100 all support bf16 |
| per-model lr | CLI already exists | see §5.2 |
| class weights are tokenizer-dependent | `train.py:53` | `0.5/1.5/1.0` was tuned against WordPiece token statistics. A 50k BPE vocab changes the B:I:O token ratio; the weights need at least a sanity re-check per tokenizer family |

An encoder registry mirroring `llm/models.py` (tag, HF id, model class, recommended
lr, precision, cache slug) is the natural shape — it is the same problem the
annotator registry already solved.

### 4.4 Environment

`venv310` → `.venv` is currently a bare Python 3.12 venv containing only
`huggingface_hub`; **`torch` is not installed anywhere on this machine**. Any run,
local or remote, needs the environment rebuilt first. `transformers ≥ 4.48` is
required for `ModernBertForTokenClassification`.

## 5. Hardware plan

### 5.1 Local — RTX 4060 Laptop, 8 GB

Full fine-tuning memory with AdamW ≈ 18 bytes/parameter (fp32 weights + grads +
two optimizer moments + a half-precision copy), plus activations:

| Size | Optimizer state | Verdict at batch 16 × 512 |
|---|---|---|
| 110M (base) | ~2.0 GB | fits comfortably — current runs use ~4 GB |
| 150M (ModernBERT base) | ~2.7 GB | fits |
| 340–396M (large) | ~6.5–7.1 GB | **does not fit** with activations; needs batch 4 + grad-accum 4, or gradient checkpointing, or 8-bit Adam |

So: **all base-sized candidates are testable locally**; every large candidate
belongs on TRUBA.

### 5.2 TRUBA

`palamut-cuda` (8×A100-40GB), `kolyoz-cuda` (4×H100/H200), `akya-cuda` (4×V100).
A 340–396M full fine-tune at batch 16 fits a single A100 with room to spare.

Scale reference: gold-004 (110M, all layers, ~31 epochs) took **452 s** on the
4060. A 396M model is ~3.5× the compute per step, but an A100 is ~4–6× the 4060,
so **expect 5–15 minutes per run**. The entire experiment matrix below is a
handful of GPU-hours — this is a job-array problem, not a capacity problem.

Practical TRUBA notes:
- compute nodes are typically without outbound internet — pre-download every
  checkpoint into `$HOME/.cache/huggingface` from the login node and run with
  `HF_HUB_OFFLINE=1` (the repo already uses this pattern in the gold README);
- ~1.6 GB per large checkpoint, ~7 candidates → budget ~12 GB of quota;
- local free disk is 28 GB, adequate for the base-size tier;
- one SLURM array over `(model × lr × seed)` writing `test_results.json` per run,
  then a single aggregation script, is the whole harness.

## 6. Proposed experiment matrix

**Tier 0 — infrastructure (no science, but nothing is valid without it)**
Freeze the split; add `--model`; switch to `AutoModelForTokenClassification`;
bf16; encoder registry; multi-seed runner + aggregation.

**Tier 1 — local, base-size, cheap (≈ 4 GPU-hours on the 4060)**

| Model | Why in the tier | lr grid |
|---|---|---|
| BiomedBERT-base (control, re-run on the frozen split) | re-establishes the baseline on the new split | 5e-5 |
| BioELECTRA-base | best BLURB NER per parameter (86.67) | 3e-5, 5e-5 |
| BioLinkBERT-base | isolates the LinkBERT objective from model size | 3e-5, 5e-5 |
| Bio-ModernBERT-base | isolates the ModernBERT tokenizer/arch from size | 5e-5, 8e-5 |
| ModernBERT-bio-base | best-measured bio ModernBERT | 5e-5, 8e-5 |

11 seeds each (~7.3 GPU-hours). Tier 1 answers the real question — *does the
encoder family matter at all on this dataset?* — for a fraction of the cost of
the large tier. If no base-size candidate moves more than 0.015, the large tier
is very unlikely to.

Worth one cheap experiment first: the lr 3e-5 band measured ±0.007 against
5e-5's ±0.0175. If that holds on the frozen split, running the sweep at 3e-5
buys a factor of ~6 in seeds-for-the-same-power, for free.

**Tier 2 — TRUBA, large (only if Tier 1 shows separation, or as a one-shot check)**

| Model | lr grid (large models want lower lr) |
|---|---|
| BioLinkBERT-large | 1e-5, 2e-5, 3e-5 |
| BioM-ELECTRA-large | 1e-5, 2e-5, 3e-5 |
| BiomedBERT-large | 2e-5, 3e-5 |
| Bio-ModernBERT-large | 2e-5, 5e-5 |
| ModernBERT-bio-large | 2e-5, 5e-5 |

3 seeds for the lr search, then 11 for the winner. Add the Tinn et al.
stabilization recipe for the 340M BERT/ELECTRA models — **layerwise learning-rate
decay** was found to be the effective technique for BERT-LARGE/ELECTRA in
low-resource biomedical fine-tuning, while plain layer freezing (which we already
measured as harmful, gold-003 → gold-004) is the wrong tool. Longer warmup than
the current fixed 50 steps (use a 10% warmup ratio) belongs here too.

**Tier 3 — paradigm changes (highest expected value, most engineering)**

1. Fine-tune `Ihor/gliner-biomed-bi-large-v1.0` on the same 860 documents with a
   single entity type `pathway`. Needs a span-format converter from
   `matches.jsonl` (character offsets — already the right shape) and a separate
   inference path. Also gives a free zero-shot baseline before any training.
2. TAPT: continued MLM on the unlabelled pathway corpus in `data/raw/`, then the
   standard fine-tune. Applicable to whichever backbone wins Tier 1.

## 7. Recommendation

1. **Do Tier 0 first.** The frozen-split issue (§4.1) is not optional; without it
   every number produced by this whole effort is uninterpretable.
2. **Run Tier 1 locally.** It is cheap, it needs no TRUBA account, and it
   measures the thing that actually decides whether Tier 2 is worth booking.
3. **Treat Tier 2 as a confirmation run, not the plan.** The published evidence
   (§2.1, §2.2) says base → large on biomedical-literature NER is worth +0.1 to
   +0.5 BLURB points, i.e. ≈ +0.005–0.02 F1 for us — one to three times our noise
   band, on a 109-document test set. It is a *possible* win, not an expected one.
4. **Put the real effort into Tier 3 and into data.** GLiNER-biomed's few-shot
   curve and OpenMed NER's adaptation results both point at the same conclusion
   the earlier survey reached from a different direction: at 860 training
   documents, the binding constraint is the amount and adaptation of supervision,
   not the parameter count of the encoder. Wave-3 review (860 → 2000+ documents)
   remains the single highest-value action available.

Expected outcome if all tiers run: F1 0.820 → **0.83–0.86**, with most of the
gain coming from Tier 3 rather than from any encoder swap. Reaching or passing
the teacher's 0.864 on encoder choice alone is not a realistic target.

## 8. Sources

- [BLURB Leaderboard](https://microsoft.github.io/BLURB/leaderboard.html)
- Gu et al., *Domain-Specific Language Model Pretraining for Biomedical NLP* — [arXiv 2007.15779](https://arxiv.org/pdf/2007.15779)
- Tinn et al., *Fine-Tuning Large Neural Language Models for Biomedical NLP* — [Patterns 2023](https://www.cell.com/patterns/fulltext/S2666-3899(23)00069-7)
- Yasunaga et al., *LinkBERT: Pretraining Language Models with Document Links* — [arXiv 2203.15827](https://arxiv.org/abs/2203.15827)
- Alrowili & Shanker, *BioM-Transformers* — [ACL BioNLP 2021](https://aclanthology.org/2021.bionlp-1.24/)
- Warner et al., *ModernBERT* — [arXiv 2412.13663](https://arxiv.org/abs/2412.13663)
- Sounack et al., *BioClinical ModernBERT* — [arXiv 2506.10896](https://arxiv.org/html/2506.10896v1)
- Touchent & de la Clergerie, *A Causal Language Modeling Detour Improves Encoder Continued Pretraining* — [arXiv 2605.12438](https://arxiv.org/pdf/2605.12438) / [`almanach/ModernBERT-bio-large`](https://huggingface.co/almanach/ModernBERT-bio-large)
- Lee et al., *Clinical ModernBERT* — [arXiv 2504.03964](https://arxiv.org/html/2504.03964v1)
- Yazdani et al., *GLiNER-biomed* — [arXiv 2504.00676](https://arxiv.org/html/2504.00676v1) / [Bioinformatics](https://academic.oup.com/bioinformatics/article/42/6/btag322/8690923)
- Bogdanov et al., *NuNER: Entity Recognition Encoder Pre-training via LLM-Annotated Data* — [arXiv 2402.15343](https://arxiv.org/abs/2402.15343)
- *OpenMed NER* — [arXiv 2508.01630](https://arxiv.org/pdf/2508.01630)
- *What Do Biomedical NER and Entity Linking Benchmarks Measure?* — [arXiv 2605.20537](https://arxiv.org/abs/2605.20537)
- [TRUBA GPU documentation](https://docs.truba.gov.tr/2-temel_bilgiler/gpu.html)
