# High-impact modelling directions and their adaptation cost (August 2026)

Third instalment in the base-model line of work, after
`reports/base_model_survey_2026-07.md` (five candidates, no measurement) and
`reports/base_model_expansion_analysis_2026-07.md` (full candidate landscape,
Tier 0–3 plan). Those two argued a case from the literature. Phase 4b then
*measured* it, and the measurement changed the question.

This report is about the directions that can still plausibly move the number,
what each costs to adapt into this pipeline, and which ones the 2026 literature
has quietly demoted since July.

**Status:** research only. No code changed, no model swapped.

## 1. What the completed grid already settled

Phase 4b ran 30 clean cells — 5 encoders × 2 learning rates × 3 seeds — on the
frozen 860/107/109 split at commit `5e7e3f1` (`runs/summary.jsonl`):

| model | lr | mean test F1 | sd |
|---|---:|---:|---:|
| bioelectra-base | 3e-05 | 0.8156 | 0.0175 |
| biomedbert-base | 3e-05 | 0.8033 | 0.0179 |
| bio-clinicalbert | 5e-05 | 0.8032 | 0.0064 |
| bio-modernbert-base | 8e-05 | 0.8031 | 0.0226 |
| biomedbert-base | 5e-05 | 0.7999 | 0.0275 |
| bert-base | 3e-05 | 0.7982 | 0.0201 |
| bio-modernbert-base | 5e-05 | 0.7893 | 0.0068 |
| bioelectra-base | 5e-05 | 0.7931 | 0.0021 |

The decisive row is the paired contrast. `bert-base` — general-domain BERT, no
biomedical pretraining at all — against `biomedbert-base`: delta **−0.0051**,
95% CI **[−0.0354, +0.0275]**, `P(delta > 0) = 0.382`. **Indistinguishable.**

That is the strongest possible statement about the encoder axis on this dataset,
because it is the largest contrast in the grid. If 50B tokens of PubMed
pretraining cannot be resolved against no domain pretraining at all, then
BiomedBERT-base against BiomedBERT-large (BLURB NER 86.13 vs 86.28) cannot be
resolved either. Not "probably won't win" — *cannot be measured* at this sample
size.

Two consequences that frame everything below:

1. **Tier 2 (the large encoders) is not a high-impact direction.** The July
   report already priced it at +0.005…+0.02 F1 against a seed band of ±0.017.
   The grid confirmed the axis carries no resolvable signal. Five large-model
   registry entries exist and are essentially free to run — but they are a
   *completeness* exercise, not a lever. Section 5 keeps them for that reason.
2. **A direction only qualifies as high-impact if it changes the learning
   problem, not the parameter count.** Four do.

## 2. What changed since July

| finding | source | effect on the plan |
|---|---|---|
| Decoder-only LLMs fine-tuned with **full attention + LoRA** beat 300M encoder baselines by **2–8 F1** on biomedical NER; gains largest on multi-token entities | Obeidat et al., arXiv 2504.00664 (IEEE ICHI); Yano & Takamura, BioNLP 2026 | promotes the paradigm the July report rejected in one line |
| Adaptive pretraining effects are **small** — 9 LMs × 9 datasets, clinical/scientific/social | Lynam & Henry, BioNLP 2026 | demotes TAPT/DAPT from "the lever that beats the encoder swap" to a coin flip |
| GLiNER **bi-encoder v2** on Ettin backbones: 530M/194M/108M/60M, 130× throughput at 1024 labels, +3.3 avg zero-shot F1 over uni-encoder large | arXiv 2602.18487 | a better, smaller entry point than `gliner-biomed-bi-large` |
| Ettin: paired encoder/decoder suite at 17M–1B on identical 2T-token data; **beats ModernBERT as an encoder**, and a 400M encoder beats a 1B decoder on classification | arXiv 2507.11412 | gives a clean encoder-scale probe up to 1B, and evidence that "encoder vs decoder" is not settled by size alone |
| Intermediate-task transfer from large biomedical NER corpora reaches equal F1 with **3–8× less labelled data** | Fries et al., PLOS ONE (pretrain+self-train) | promotes intermediate fine-tuning to a first-class candidate |

The July report's headline evidence for TAPT was OpenMed NER (arXiv 2508.01630):
DAPT on 350k passages + LoRA, <12 GPU-hours, SOTA on 10/12 datasets, +2.7 to
+9.7 pp. That result stands, but it **bundles** DAPT with LoRA fine-tuning, a
tuned recipe and stronger backbones (BiomedELECTRA-large). BioNLP 2026's
controlled study isolates the adaptive-pretraining term and finds it small. The
honest reading: OpenMed's gain is mostly *recipe and backbone*, not *DAPT*.
Which is good news — the recipe is far cheaper to borrow than the pretraining.

## 3. The four candidates that can exceed the noise band

### A. Decoder-only LLM as a token classifier (LoRA + full attention)

**Mechanism.** Take a 1.7B–8B causal LLM, replace causal masking with full
bidirectional attention, attach a token-classification head, train with LoRA.
The token representations then carry right-side context, which is the one thing
that made encoders structurally correct for NER. Reported +2–8 F1 over
BiomedBERT/DeBERTa-v3 baselines, with the gain concentrated on entities of 3+
tokens.

**Why it fits this task specifically.** Our entity type is multi-token by
nature — `tetrahydrobiopterin metabolism`, `mitochondrial iron-sulfur cluster
biogenesis`, `phosphatidylinositol signaling system`. The error profile in
`analysis/error_analysis.json` is dominated by exactly the failure mode this
approach improves: boundary errors, mid-word starts, umbrella-vs-specific
confusion. This is the only candidate whose reported strength lines up with our
measured weakness.

**Adaptation cost — small, which is the surprise.**

| item | cost |
|---|---|
| `train.py` | already `AutoModelForTokenClassification` (`train.py:309`). Qwen3/Llama/Gemma all ship a `*ForTokenClassification` class |
| attention patch | one-line config (`is_causal=False` / `attn_implementation` + a bidirectional mask), applied in the registry's model-loading path |
| LoRA | new dependency `peft`; ~15 lines to wrap the model, plus rank/alpha/target-modules in `EncoderSpec` |
| tokenization | no new machinery — `tag_bio.py` + `data_slug` already give every tokenizer its own dataset directory. A 150k BPE vocabulary is just another entry |
| class weights | must be re-checked; `check_alignment.py` already prints the per-tokenizer B:I:O statistics |
| eval | unchanged — same BIO tags, same `compute_metrics` |

Realistically **half a day of code**, most of it in `encoders.py`.

**Hardware — this is where it costs.** 8B + LoRA + bf16 at 512 tokens needs
~24 GB at small batch, ~40 GB comfortably. That rules out the 8 GB 4060 entirely
and **rules out `akya-cuda` (V100 has no bf16)** — the partition the current
TRUBA sweep targets. It belongs on `palamut-cuda` (A100-40GB) or `kolyoz-cuda`
(H100/H200), which have longer queues. A 1.7B or 4B backbone fits a V100 in
fp16 and is the sensible first probe.

Estimated ~2664 training documents × 20 epochs at batch 8: **≈1 GPU-hour per
run on an A100**, so a 2-lr × 5-seed grid is ~10 A100-hours. Not a capacity
problem.

**The strategic objection, stated plainly.** This project exists to distil a
14B teacher into a cheap student. An 8B student is not cheap, and re-introduces
at inference the cost the distillation was meant to remove. Three answers:

1. The distillation target was *deployment cost*, and a 1.7B–4B LoRA student is
   still 20–100× cheaper than the teacher at inference, while plausibly beating
   the teacher's 0.864.
2. Even as a non-deployable model, it establishes the **ceiling** — how much
   signal the 2664 documents actually contain. Right now we do not know whether
   0.82 is a data limit or a model limit, and every "the encoder axis is flat"
   conclusion is ambiguous between the two. That is worth one experiment on its
   own.
3. If it wins big, it becomes the new *teacher*, and the encoder student is
   re-distilled from it.

**Expected Δ F1: +0.02 … +0.06.** The only candidate whose central estimate is
outside the noise band.

### B. GLiNER — span-level NER with an LLM-distilled prior

**Mechanism.** Not a base encoder with a linear head. GLiNER scores
(span × label-embedding) pairs, so it has no BIO-consistency failure mode at
all, and it arrives already trained on the *task* of entity extraction over
hundreds of thousands of types. GLiNER-biomed was built by distilling LLM
annotation ability into a small model — structurally identical to what this
project does with `qwen2.5:14b`, at a scale we cannot reach.

**Current best entry points.**

| model | params | note |
|---|---:|---|
| `Ihor/gliner-biomed-bi-large-v1.0` | ~440M | biomedical, bi-encoder, +5.96% F1 over strongest GLiNER baseline |
| `knowledgator/gliner-bi-large-v2.0` | 530M | Ettin-400m + bge-base; newer, general-domain, best zero-shot average (49.7 vs 46.4) |
| `Ihor/gliner-biomed-base-v1.0` | ~200M | small variant ≈ large general-domain GLiNER |

The published few-shot curve is the whole argument: 59.8 zero-shot → 70.4
(10-shot) → 73.1 (20-shot) → 76.0 (50-shot) → ~84.9 at full supervision, *where
the advantage converges with ordinary baselines*. Our 2664 documents sit past
"50-shot" and toward "full", so the prior is worth less than it would have been
at 860. This candidate lost some value when wave-3/4 landed.

**Free first measurement:** run `gliner-biomed-bi-large` **zero-shot** with the
label `pathway` over our 109 test documents. Costs an afternoon, needs no
training, and tells us immediately whether the prior transfers to this entity
type. Do this before writing any training code.

**Adaptation cost — the largest of the four.**

| item | cost |
|---|---|
| data format | span records from `matches.jsonl` (character offsets — already the right shape). ~50 lines |
| training | separate path; the `gliner` library's own trainer, not `train.py` |
| evaluation | `compute_metrics` is seqeval over BIO. Needs a span-level equivalent, and a shared scorer so GLiNER numbers are comparable to encoder numbers |
| inference | separate code path in whatever consumes the model |
| registry | does not fit `EncoderSpec` — needs a second registry or a `paradigm` field |
| dependency | `gliner` package, DeBERTa-v3 / Ettin backbones, sentencepiece |
| hardware | 209M GLiNER fine-tunes in ~30 min on an L4; a 530M bi-encoder fits the V100s and probably the 4060 at small batch |

**≈1.5–2 days of code**, and it permanently forks the pipeline into two training
and evaluation paths. That fork is the real cost, not the GPU time.

**Expected Δ F1: −0.01 … +0.04**, with wide variance — and lower now than the
July estimate, because the corpus grew.

### C. Intermediate-task transfer (the cheapest real lever)

**Mechanism.** Instead of fine-tuning an MLM checkpoint on 2664 pathway
documents, first fine-tune it on a large *biomedical NER* corpus, then on ours.
The model arrives already knowing what a biomedical entity boundary looks like;
only the entity *definition* has to be learned. Reported to reach equal F1 with
3–8× less labelled data.

**Two concrete routes, both nearly free:**

1. **Start from an already-fine-tuned NER checkpoint.** The OpenMed org ships
   Apache-2.0 models like `OpenMed/OpenMed-NER-DiseaseDetect-BioMed-335M`
   (BiomedELECTRA-large backbone, F1 0.90 on its task). Loading one with
   `ignore_mismatched_sizes=True` and a fresh 3-label head is a **one-line
   change** — the registry already handles everything else. Note the family
   match: our descriptive grid leader is `bioelectra-base`, and OpenMed's best
   backbone is BiomedELECTRA-large. That is not a coincidence worth ignoring.
2. **Intermediate-fine-tune on MedMentions ST21pv** — 4,392 PubMed abstracts,
   350k+ mentions, 21 UMLS semantic types **including T038 Biologic Function**,
   which is the closest published semantic type to "pathway". Train on
   MedMentions, then on our gold. Needs a small BIO converter and one extra
   training stage; the pipeline runs unchanged otherwise.

**Adaptation cost.**

| route | code | GPU |
|---|---|---|
| OpenMed checkpoint as init | ~1 line + registry entries | same as any current cell (~23 min on the 4060) |
| MedMentions intermediate stage | ~150 lines (fetch + BIO convert + stage-1 driver) | ~1–2 h per backbone, once; then normal cells |

**Expected Δ F1: +0.01 … +0.04.** The best ratio of expected gain to
engineering hours in this entire report, and the only high-impact candidate that
runs *today* on hardware we already have, in a pipeline we already have.

### D. Data-centric: augmentation and self-training on the silver corpus

**Mechanism.** DA-BioNER reports up to +0.08 F1 in extreme few-shot by
LLM-assisted augmentation; BioAug reports +1.5–21.5% in low-resource. The
pre-training/self-training work reaches the 3–8× data-efficiency result partly
through self-training on unlabelled text.

We are unusually well placed for this: `data/silver/` already holds 4,000
LLM-annotated documents (`pilot_1k`, `wave2_1k`, `wave3_1k`, `wave4_1k`), and
2,887 of the 3,200 reviewed documents are positive. Self-training is a matter of
scheduling, not of new annotation: pseudo-label unreviewed PubMed abstracts with
the current student, keep the high-confidence spans, train on gold + pseudo.
`pubmed_api` can fetch far more raw text on demand (10,329 PMIDs already
collected, 10,044 with abstracts; `data/raw/abstracts.jsonl` holds only 1,122).

**Adaptation cost:** no new model, no new dependency, no new evaluation. One
script that mixes weighted gold and silver records into `train.jsonl`, plus a
confidence threshold. **≈1 day.**

**Expected Δ F1: +0.01 … +0.05**, and it compounds with every other candidate
rather than competing with them.

## 4. Cost/benefit, all candidates on one table

| direction | expected Δ F1 | code | GPU cost | hardware needed | forks the pipeline? |
|---|---|---|---|---|---|
| **C. Intermediate transfer (OpenMed init)** | +0.01…+0.04 | ~1 line | ~0.5 h/run | current | no |
| **C′. MedMentions intermediate stage** | +0.01…+0.04 | ~150 lines | +1–2 h once | current | no |
| **D. Self-training on silver** | +0.01…+0.05 | ~1 day | ~0.5 h/run | current | no |
| **A. LLM-as-encoder (1.7B–4B)** | +0.02…+0.06 | ~0.5 day | ~0.5–1 h/run | V100 fp16 / A100 | no (same BIO path) |
| **A′. LLM-as-encoder (8B)** | +0.02…+0.06 | same | ~1 h/run | **A100/H100 only** — not `akya-cuda` | no |
| **B. GLiNER fine-tune** | −0.01…+0.04 | ~1.5–2 days | ~0.5 h/run | current | **yes** |
| E. Large encoders (Tier 2) | −0.005…+0.02 | **0** — registry entries exist | ~1 h/run | TRUBA | no |
| F. TAPT/DAPT on own corpus | −0.01…+0.02 | ~1 day | 8–12 h once | A100 preferred | no |

Note the ordering flip against the July report: **TAPT dropped from first to
last** on the strength of BioNLP 2026's controlled study, and the LLM paradigm
rose from a one-line rejection to the top of the expected-value column.

## 5. What to do with the five large-encoder registry entries

They cost nothing — `biolinkbert-large`, `biom-electra-large`,
`biomedbert-large`, `bio-modernbert-large` and `modernbert-bio-large` are
already written, four of them share the 28895-token vocabulary with datasets we
have already built, and the TRUBA array script runs them unchanged. Run them as
a **completeness tier**, not as a lever, and report them as such: the survey
question "does encoder scale matter on this task?" deserves a measured answer
rather than an inference from BLURB.

Two hard constraints when scheduling them:

- `bio-modernbert-large` and `modernbert-bio-large` require **bf16**. `akya-cuda`
  is V100 — **do not queue them there.** `EncoderSpec.torch_dtype_flags()`
  (`encoders.py`) only consults `torch.cuda.is_bf16_supported()` on the `auto`
  path; a spec pinned to `precision="bf16"` returns `bf16=True` unconditionally.
  On a V100 that is a hard failure at Trainer construction, not a silent
  fallback — which is the correct behaviour, but it means the array task dies
  after queue time rather than before it. The same applies to
  `bio-modernbert-base` and `modernbert-bio-base`, which are already pinned to
  bf16 and were run locally on an Ada card.
- At batch 4 × grad-accum 4 the 340M models should fit a V100-16GB. The 396M
  ModernBERTs at 8192 context are doubtful on 16 GB even at batch 2 — the
  150M version already peaked at 7.2 GB at batch 4 — and would need gradient
  checkpointing. Measure before booking the array.

## 6. Statistical power, restated for the expanded corpus

The wave-4 corpus changes the training set (860 → 2664) but **not the test set**
— still 109 documents, deliberately, so results stay comparable. Every
resolution limit from the July analysis therefore still holds:

- measured σ across seeds: **0.0175**
- 3 seeds resolve ~0.035; 5 seeds ~0.022; 11 seeds ~0.015
- paired document bootstrap on the frozen split, always — it is far more
  sensitive than comparing independent intervals

**A candidate is only interesting if the paired bootstrap's 95% CI excludes
zero.** Under that rule, none of Tier 2 will ever qualify, and only A, C and D
plausibly will. If a direction is expected to deliver +0.02, three seeds cannot
see it — budget seeds accordingly, or expand the test set.

The test set is now the binding constraint on knowledge, not the training set.
2,887 positive reviewed documents exist; 109 of them are the test set. Moving
to a 300–400 document test set would cut the resolution limit by ~40% and cost
nothing but a re-split — at the price of breaking comparability with every
number recorded so far. Worth deciding deliberately, once, rather than drifting.

## 7. Recommended order

1. **GLiNER-biomed zero-shot on the 109 test documents.** No training, one
   afternoon, and it prices candidate B before any of B's cost is paid.
2. **Candidate C, OpenMed-init route.** One line of code, one sweep on existing
   hardware. If intermediate transfer is worth anything here, this finds out for
   the price of a single grid.
3. **Candidate A at 1.7B–4B.** Half a day of code, runs on the V100s in fp16.
   Establishes the ceiling that every "the encoder axis is flat" statement is
   currently missing. Escalate to 8B on `palamut-cuda` only if the small one
   separates.
4. **Candidate D (self-training).** Compounds with whatever wins above.
5. **Tier 2 large encoders**, opportunistically, as array backfill — for the
   record, not for the result.
6. **B (GLiNER training path) and F (TAPT)** only if 1–4 leave the number stuck.

Expected outcome if 1–4 run: **F1 0.82 → 0.85–0.88**, with the teacher's 0.864
no longer the ceiling — candidate A can exceed it, and candidates C and D make
the encoder student a better distillation of it.

## 8. Sources

- Obeidat et al., *Do LLMs Surpass Encoders for Biomedical NER?* — [arXiv 2504.00664](https://arxiv.org/abs/2504.00664)
- Yano & Takamura, *Treating Decoder-Only LLMs as Encoders: A Simple and Effective Fine-tuning Approach for NER* — [BioNLP 2026](https://aclanthology.org/2026.bionlp-1.25/)
- Lynam & Henry, *Effects of Adaptive Pretraining in Specialized Domains for NER* — [BioNLP 2026](https://aclanthology.org/2026.bionlp-1.18/)
- *Tokenization Granularity and Medical Term Representations in Language Models* — [BioNLP 2026](https://aclanthology.org/2026.bionlp-1.45/)
- *Just Pass Twice: Efficient Token Classification with LLMs for Zero-Shot NER* — [arXiv 2604.05158](https://arxiv.org/html/2604.05158v1)
- Yazdani et al., *GLiNER-BioMed* — [arXiv 2504.00676](https://arxiv.org/abs/2504.00676) / [Bioinformatics](https://academic.oup.com/bioinformatics/article/42/6/btag322/8690923)
- *The Million-Label NER: Breaking Scale Barriers with GLiNER bi-encoder* — [arXiv 2602.18487](https://arxiv.org/html/2602.18487v1)
- Weller et al., *Seq vs Seq: An Open Suite of Paired Encoders and Decoders (Ettin)* — [arXiv 2507.11412](https://arxiv.org/abs/2507.11412)
- *OpenMed NER* — [arXiv 2508.01630](https://arxiv.org/abs/2508.01630) / [HF org](https://huggingface.co/OpenMed)
- Mohan & Li, *MedMentions: A Large Biomedical Corpus Annotated with UMLS Concepts* — [arXiv 1902.09476](https://arxiv.org/pdf/1902.09476) / [ST21pv](https://github.com/chanzuckerberg/MedMentions/tree/master/st21pv)
- *A pre-training and self-training approach for biomedical NER* — [PLOS ONE](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0246310)
- *DA-BioNER: data augmentation based on few-shot learning and distant supervision* — [Bioinformatics](https://academic.oup.com/bioinformatics/article/42/6/btag332/8691815)
- [BLURB Leaderboard](https://microsoft.github.io/BLURB/leaderboard.html)
- [TRUBA GPU documentation](https://docs.truba.gov.tr/2-temel_bilgiler/gpu.html)
