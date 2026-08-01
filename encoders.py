#!/usr/bin/env python3
"""
encoders.py

One place to declare a base encoder and everything the pipeline needs to use it
correctly. Adding a model should be a dict entry here, never an edit to
`preprocessing/tag_bio.py` or `train.py`.

Why this exists
---------------
This is the encoder-side twin of `llm/models.py`, and it exists for the same
reason: the settings that differ per model family are all silent failures when
wrong.

1. **Tokenizer / data coupling.** `bio_tags.jsonl` stores `input_ids`, which are
   meaningless outside the tokenizer that produced them. Vocabularies overlap in
   range (28895 / 30522 / 50368), so feeding one model's ids to another raises
   nothing — it just trains a worse model, and the bad F1 reads as a verdict on
   the encoder. `data_slug` gives every model its own dataset directory, and
   `tag_bio.py` writes a `meta.json` that `train.py` refuses to disagree with.

   Measured: BioLinkBERT (base and large), BiomedBERT-large-abstract and
   BioELECTRA all ship **byte-identical** 28895-token PubMedBERT vocabularies
   (`vocab.txt` md5 `1f30c96333`), so those four produce identical datasets.
   BiomedBERT-**base**-abstract-fulltext does not — its own 30522-token
   vocabulary is a different vocabulary of a similar size, which is exactly the
   pairing that would fail silently. The guard therefore compares `tokenizer_id`,
   not `hf_id`.
2. **Context length.** 512 for the BERT/ELECTRA families, 8192 for ModernBERT.
   Hardcoding 512 silently truncates; hardcoding 8192 breaks position embeddings.
3. **Precision.** ModernBERT was pretrained in bf16 and fp16 fine-tuning is a
   known NaN source. `auto` picks bf16 wherever the GPU supports it (Ada, A100,
   H100/H200) and falls back to fp16 on older cards (V100 has no bf16).
4. **Learning rate.** The usable range differs by roughly 3x between families:
   BERT-large wants 1e-5…3e-5 while ModernBERT papers fine-tune at 5e-5…2e-4.
   Carrying one hardcoded value across a model sweep measures the learning rate,
   not the encoder.
4b. **Batch size.** A 512-token model pads batches to at most 512; an 8192-token
   one pads to the longest document in the batch, which for our abstracts is
   ~2750 tokens for the longest. Measured on the 8 GB 4060: Bio-ModernBERT-base
   peaks at 7.2 GB at batch 4 and fits at batch 2 (4.5 GB), despite being only
   150M. `batch_size` × `grad_accum` keeps the effective batch
   at 16 everywhere, so the optimizer trajectory is comparable across models even
   when the memory footprint is not.
5. **Layer naming.** `--frozen-layers` matches parameter names, and those differ:
   `encoder.layer.{i}.` for BERT/ELECTRA, `layers.{i}.` for ModernBERT. A wrong
   pattern does not raise — it just freezes nothing.

BLURB NER scores in the notes are from the leaderboard
(https://microsoft.github.io/BLURB/leaderboard.html) and are the six-corpus
average, not a prediction for this task.

Usage:
    from encoders import resolve
    spec = resolve("biolinkbert-large")     # registry key or raw HF id
    spec.hf_id, spec.data_dir(), spec.max_tokens
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Class weights for CrossEntropy over O / B-Pathway / I-Pathway. Tuned on the
# BiomedBERT WordPiece tokenization (gold-003 onward). Tokenizers disagree on how
# much of a word survives as one token, which moves the B:I:O ratio: measured on
# the gold set, Bio-ModernBERT's 50k BPE masks 14.8% of positions as continuation
# subwords against BiomedBERT's 7.4% — the general-domain vocabulary fragments
# biomedical terms *more*, not less. `check_alignment.py` prints the per-tokenizer
# counts; treat these weights as a default, not as a constant.
DEFAULT_CLASS_WEIGHTS = (0.5, 1.5, 1.0)

# Fallback for an unregistered tag: BERT-style naming and a conservative context.
DEFAULT_FROZEN_PATTERN = "encoder.layer.{i}."


def _slug(hf_id: str) -> str:
    """HF id -> filesystem-safe directory name."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", hf_id.split("/")[-1]).lower()


def vocab_fingerprint(tokenizer) -> str:
    """Stable hash of a tokenizer's vocabulary.

    This, not the model id, is what a `bio_tags.jsonl` depends on. Four of the
    candidates (BioLinkBERT base/large, BiomedBERT-large-abstract, BioELECTRA)
    ship byte-identical 28895-token PubMedBERT vocabularies and therefore
    produce interchangeable datasets, while BiomedBERT-base-abstract-fulltext's
    own 30522-token vocabulary is a genuinely different one of a similar size —
    the pairing that would otherwise fail silently.
    """
    import hashlib

    vocab = tokenizer.get_vocab()
    payload = "\n".join(f"{token}\t{index}" for token, index in sorted(vocab.items()))
    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class EncoderSpec:
    """How to tokenize for, and fine-tune, one base encoder."""

    hf_id: str                                   # HuggingFace model id
    max_tokens: int = 512                        # tokenizer truncation length
    precision: str = "auto"                      # auto | bf16 | fp16 | fp32
    batch_size: int = 16                         # per-device, sized for the 8 GB 4060
    grad_accum: int = 1                          # keeps the effective batch at 16
    lr_grid: tuple[float, ...] = (3e-5, 5e-5)    # learning rates worth sweeping
    frozen_layer_pattern: str = DEFAULT_FROZEN_PATTERN
    class_weights: tuple[float, float, float] = DEFAULT_CLASS_WEIGHTS
    tokenizer_id: str = ""                       # when it differs from hf_id
    tokenizer_kwargs: dict = field(default_factory=dict)  # overrides for a broken repo config
    note: str = ""
    data_slug: str = ""                          # defaults to a slug of hf_id

    # --- ablation axes -------------------------------------------------------
    # These describe *what varying this entry tests*, so the results table can be
    # grouped by hypothesis rather than by model name. A survey that only reports
    # "model X scored Y" answers nothing about why.
    domain: str = "biomedical"    # general | scientific | biomedical | clinical | bio+clinical
    objective: str = "mlm"        # mlm | rtd | mlm+drp | mlm+clm-detour
    arch: str = "bert"            # bert | electra | modernbert | roberta | deberta
    params_m: int = 110           # parameter count, millions
    role: str = ""                # why this entry is in the grid at all

    def __post_init__(self) -> None:
        if not self.data_slug:
            object.__setattr__(self, "data_slug", _slug(self.hf_id))
        if not self.tokenizer_id:
            object.__setattr__(self, "tokenizer_id", self.hf_id)

    def data_dir(self, root: str | Path = "data/processed") -> Path:
        """Per-tokenizer dataset directory: data/processed/gold-<slug>/."""
        return Path(root) / f"gold-{self.data_slug}"

    def load_tokenizer(self):
        """The one place a tokenizer is constructed, so `tokenizer_kwargs` cannot
        be applied in one script and forgotten in another — which would produce
        two different tokenizations of the same corpus under the same model name."""
        from transformers import AutoTokenizer

        return AutoTokenizer.from_pretrained(self.tokenizer_id, **self.tokenizer_kwargs)

    def torch_dtype_flags(self) -> tuple[bool, bool]:
        """(bf16, fp16) flags for TrainingArguments, resolving `auto`."""
        import torch

        if not torch.cuda.is_available():
            return False, False
        if self.precision == "bf16":
            return True, False
        if self.precision == "fp16":
            return False, True
        if self.precision == "fp32":
            return False, False
        supported = torch.cuda.is_bf16_supported()
        return supported, not supported


REGISTRY: dict[str, EncoderSpec] = {
    # --- current production encoder ------------------------------------------
    "biomedbert-base": EncoderSpec(
        domain="biomedical", objective="mlm", arch="bert", params_m=110,
        role="baseline — the production encoder every other row is measured against",
        hf_id="microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext",
        note="Production encoder for gold-001…008 (test F1 0.8197). 110M, "
             "WordPiece 30522 uncased, PubMed abstracts + PMC full text. "
             "BLURB NER 86.13.",
        data_slug="biomedbert-base",
    ),

    # --- base-size candidates (fit the 8 GB card) -----------------------------
    "bioelectra-base": EncoderSpec(
        domain="biomedical", objective="rtd", arch="electra", params_m=110,
        role="objective axis: RTD vs MLM at fixed size, corpus and vocabulary",
        hf_id="kamalkraj/bioelectra-base-discriminator-pubmed-pmc",
        note="ELECTRA replaced-token-detection pretraining makes every token a "
             "discriminative decision — the closest pretraining task to token "
             "classification. BLURB NER 86.67, above BiomedBERT-large's 86.28 at "
             "a third of the size.",
        data_slug="bioelectra-base",
    ),
    "biolinkbert-base": EncoderSpec(
        domain="biomedical", objective="mlm+drp", arch="bert", params_m=110,
        role="objective axis: citation-graph pretraining; base half of the size pair",
        hf_id="michiyasunaga/BioLinkBERT-base",
        note="LinkBERT: MLM + document-relation prediction over the PubMed "
             "citation graph. Vocab 28895 uncased (PubMedBERT abstracts vocab, "
             "not the same as biomedbert-base's 30522). BLURB NER 86.39.",
        data_slug="biolinkbert-base",
    ),
    "bio-modernbert-base": EncoderSpec(
        domain="biomedical", objective="mlm", arch="modernbert", params_m=150,
        role="architecture axis: RoPE/GeGLU/local attention and an 8192 context",
        hf_id="thomas-sounack/Bio-ModernBERT-base",
        max_tokens=8192,
        precision="bf16",
        batch_size=2,
        grad_accum=8,
        lr_grid=(5e-5, 8e-5),
        frozen_layer_pattern="layers.{i}.",
        note="Biomedical-only sibling of BioClinical-ModernBERT (no clinical "
             "corpus) — closer to our domain. 150M, ByteLevel BPE 50368 cased.",
        data_slug="bio-modernbert-base",
    ),
    "modernbert-bio-base": EncoderSpec(
        domain="bio+clinical", objective="mlm+clm-detour", arch="modernbert", params_m=150,
        role="pretraining-recipe axis: CLM detour, 20% MIMIC in the corpus",
        hf_id="almanach/ModernBERT-bio-base",
        max_tokens=8192,
        precision="bf16",
        batch_size=2,
        grad_accum=8,
        lr_grid=(5e-5, 8e-5),
        frozen_layer_pattern="layers.{i}.",
        note="CLM-detour continued pretraining (arXiv 2605.12438, 2026): PubMed "
             "60% / Med-Inst 20% / MIMIC 20%. The large variant is the only "
             "ModernBERT-class encoder measured at parity with PubMedBERT on "
             "literature NER.",
        data_slug="modernbert-bio-base",
    ),

    # --- controls: they are expected to lose, which is what makes them useful --
    # A survey of four biomedical encoders that all score alike proves nothing.
    # These anchor the domain axis, so "domain pretraining is worth N points on
    # this task" becomes a measurement rather than an assumption carried over
    # from BLURB.
    "bert-base": EncoderSpec(
        hf_id="google-bert/bert-base-uncased",
        domain="general", objective="mlm", arch="bert", params_m=110,
        role="domain floor — no scientific or biomedical pretraining at all. "
             "BLURB NER 82.99 against our baseline's 86.13; the gap between this "
             "row and biomedbert-base is the value of domain pretraining, measured "
             "on our data instead of assumed",
        note="General-domain BERT. Not a candidate — a ruler.",
        data_slug="bert-base",
    ),
    "scibert": EncoderSpec(
        hf_id="allenai/scibert_scivocab_uncased",
        domain="scientific", objective="mlm", arch="bert", params_m=110,
        role="domain axis, middle rung: scientific text (Semantic Scholar, ~18% "
             "biomedical) rather than PubMed. Separates 'scientific writing' from "
             "'biomedical specifically'",
        note="BLURB NER 85.43.",
        data_slug="scibert",
    ),
    "biobert": EncoderSpec(
        hf_id="dmis-lab/biobert-base-cased-v1.2",
        domain="biomedical", objective="mlm", arch="bert", params_m=110,
        role="pretraining-strategy axis: continued pretraining from general BERT, "
             "versus BiomedBERT's from-scratch domain pretraining. Same corpus "
             "family, opposite strategy — and the only cased biomedical encoder "
             "in the grid",
        # The repo ships **no tokenizer_config.json**, so AutoTokenizer falls back
        # to do_lower_case=True — wrong for a cased checkpoint whose vocabulary has
        # 8373 capitalised entries out of 28996. Without this override the model
        # never sees any of them ('Alzheimer' -> 'al ##z ##heimer').
        # Nothing raises; the model just underperforms and reads as a weak
        # encoder. Measured, not assumed — see check_alignment.py's cased-vocab
        # warning, which exists because of this entry.
        tokenizer_kwargs={"do_lower_case": False},
        note="BLURB NER 85.81. Cased — and only actually cased with the override "
             "above.",
        data_slug="biobert",
    ),
    "biomed-roberta": EncoderSpec(
        hf_id="allenai/biomed_roberta_base",
        domain="biomedical", objective="mlm", arch="roberta", params_m=125,
        role="architecture axis: RoBERTa recipe and a 50k byte-level vocabulary "
             "on biomedical text — the closest thing to a ModernBERT tokenizer "
             "without the ModernBERT architecture, so it separates the two",
        note="DAPT on 2.68M PMC full-text papers.",
        data_slug="biomed-roberta",
    ),
    "bio-clinicalbert": EncoderSpec(
        hf_id="emilyalsentzer/Bio_ClinicalBERT",
        domain="clinical", objective="mlm", arch="bert", params_m=110,
        role="domain-mismatch control: MIMIC-III clinical notes. Expected to lose "
             "to every literature encoder; confirms on our data the effect the "
             "almanach paper reports for BioClinical-ModernBERT",
        # Same defect as `biobert`, whose vocabulary this shares byte for byte
        # (fingerprint d480c5ef3e08): a cased 28996-entry vocabulary with a
        # tokenizer_config that leaves do_lower_case at its True default. Found by
        # check_alignment.py's cased-vocab check, not by inspection.
        tokenizer_kwargs={"do_lower_case": False},
        note="BLURB NER 83.99.",
        data_slug="bio-clinicalbert",
    ),
    "modernbert-base": EncoderSpec(
        hf_id="answerdotai/ModernBERT-base",
        max_tokens=8192, precision="bf16", batch_size=2, grad_accum=8,
        lr_grid=(5e-5, 8e-5), frozen_layer_pattern="layers.{i}.",
        domain="general", objective="mlm", arch="modernbert", params_m=150,
        role="isolates the ModernBERT *architecture* from its biomedical continued "
             "pretraining: paired with bio-modernbert-base, the difference is "
             "exactly what 50B biomedical tokens bought",
        note="General-domain ModernBERT — the checkpoint every bio variant "
             "continues from.",
        data_slug="modernbert-base",
    ),
    "bioclinical-modernbert-base": EncoderSpec(
        hf_id="thomas-sounack/BioClinical-ModernBERT-base",
        max_tokens=8192, precision="bf16", batch_size=2, grad_accum=8,
        lr_grid=(5e-5, 8e-5), frozen_layer_pattern="layers.{i}.",
        domain="bio+clinical", objective="mlm", arch="modernbert", params_m=150,
        role="corpus-composition axis: identical architecture and biomedical "
             "corpus to bio-modernbert-base, plus 2.8B clinical tokens. The pair "
             "measures what clinical data costs on literature NER — reported as "
             "1.0-4.1 points elsewhere, untested here",
        note="Headline SOTA on clinical tasks; expected to underperform on ours.",
        data_slug="bioclinical-modernbert-base",
    ),

    # --- large candidates (TRUBA; 340-396M does not fit 8 GB at batch 16) -----
    "biolinkbert-large": EncoderSpec(
        domain="biomedical", objective="mlm+drp", arch="bert", params_m=340,
        role="size axis: identical vocabulary to biolinkbert-base, so size is the only variable",
        hf_id="michiyasunaga/BioLinkBERT-large",
        batch_size=4,
        grad_accum=4,
        lr_grid=(1e-5, 2e-5, 3e-5),
        note="BLURB #1 overall (84.30) and #1 NER (86.89). 340M, 512 ctx, "
             "uncased — the least disruptive of the large candidates.",
        data_slug="biolinkbert-large",
    ),
    "biom-electra-large": EncoderSpec(
        domain="biomedical", objective="rtd", arch="electra", params_m=335,
        role="size x objective: the largest RTD encoder on the BLURB board",
        hf_id="sultan/BioM-ELECTRA-Large-Discriminator",
        batch_size=4,
        grad_accum=4,
        lr_grid=(1e-5, 2e-5, 3e-5),
        tokenizer_id="michiyasunaga/BioLinkBERT-large",
        note="BLURB NER 86.88, effectively tied with BioLinkBERT-large. The repo "
             "ships no tokenizer_config.json; it uses the same 28895 uncased "
             "vocabulary, so the tokenizer is borrowed from BioLinkBERT-large — "
             "verify with check_alignment.py before trusting a run.",
        data_slug="biom-electra-large",
    ),
    "biomedbert-large": EncoderSpec(
        domain="biomedical", objective="mlm", arch="bert", params_m=340,
        role="size axis, confounded — its vocabulary is the 28895 one, not biomedbert-base's 30522",
        hf_id="microsoft/BiomedNLP-BiomedBERT-large-uncased-abstract",
        batch_size=4,
        grad_accum=4,
        lr_grid=(2e-5, 3e-5),
        note="Same family as the production encoder, so it isolates model size "
             "from everything else. BLURB NER 86.28 vs the base's 86.13 — the "
             "expected gain is close to nothing, which is the point of running "
             "it as a control.",
        data_slug="biomedbert-large",
    ),
    "bio-modernbert-large": EncoderSpec(
        domain="biomedical", objective="mlm", arch="modernbert", params_m=396,
        role="size axis within the ModernBERT architecture",
        hf_id="thomas-sounack/Bio-ModernBERT-large",
        max_tokens=8192,
        precision="bf16",
        batch_size=2,
        grad_accum=8,
        lr_grid=(2e-5, 5e-5),
        frozen_layer_pattern="layers.{i}.",
        note="396M biomedical-only ModernBERT. bf16 required — do not queue on "
             "TRUBA akya-cuda (V100 has no bf16).",
        data_slug="bio-modernbert-large",
    ),
    "modernbert-bio-large": EncoderSpec(
        domain="bio+clinical", objective="mlm+clm-detour", arch="modernbert", params_m=396,
        role="best measured bio-ModernBERT; parity with 110M PubMedBERT on literature NER",
        hf_id="almanach/ModernBERT-bio-large",
        max_tokens=8192,
        precision="bf16",
        batch_size=2,
        grad_accum=8,
        lr_grid=(2e-5, 5e-5),
        frozen_layer_pattern="layers.{i}.",
        note="396M, best measured average over 11 biomedical benchmarks (78.7 "
             "F1). Reported at parity with 110M PubMedBERT on BC5CDR/NCBI/AnatEM "
             "— the headline evidence that this whole axis is worth ~0.01 F1.",
        data_slug="modernbert-bio-large",
    ),
}

DEFAULT = "biomedbert-base"


def resolve(name: str | None = None) -> EncoderSpec:
    """EncoderSpec for a registry key, or a generic one for an unregistered id.

    An unregistered HF id still runs — it gets 512 tokens, auto precision, BERT
    layer naming and a dataset directory of its own. That keeps one-off
    experiments possible without an edit here, while never letting two tokenizers
    share a dataset directory.
    """
    key = name or DEFAULT
    if key in REGISTRY:
        return REGISTRY[key]
    return EncoderSpec(hf_id=key, note="unregistered — generic 512-token config")


def names() -> list[str]:
    return list(REGISTRY)


if __name__ == "__main__":
    for key, spec in REGISTRY.items():
        mark = "  (default)" if key == DEFAULT else ""
        print(f"{key}{mark}\n  hf_id : {spec.hf_id}\n  data  : {spec.data_dir()}"
              f"\n  ctx   : {spec.max_tokens}   precision: {spec.precision}"
              f"   batch: {spec.batch_size}x{spec.grad_accum}"
              f"   lr: {list(spec.lr_grid)}"
              f"\n  note  : {spec.note}\n")
