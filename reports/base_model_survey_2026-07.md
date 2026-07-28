# Base-model survey — larger encoders for pathway NER (July 2026)

Investigation into replacing the current base encoder
(`microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext`, 110M) with a
larger one, after hyperparameter tuning plateaued at **gold-008** (test F1 0.820,
see `knowledge_base/model_experiments.md`).

**Status:** research only — no model swap implemented.

## Candidates

| Model | HF id | Params | Ctx | BLURB / NER | Notes |
|---|---|---|---|---|---|
| **Current** BiomedBERT-base | `microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext` | 110M | 512 | ~82.9 | in use |
| **BioLinkBERT-large** | `michiyasunaga/BioLinkBERT-large` | 340M | 512 | **84.30 / 86.89** | BLURB **#1** |
| BioM-ELECTRA-large | `sultan/BioM-ELECTRA-Large-Discriminator` | 335M | 512 | 83.81 / 86.88 | NER ≈ tied with #1 |
| BiomedBERT-large | `microsoft/BiomedNLP-BiomedBERT-large-uncased-abstract` | 340M | 512 | — | same family → least code churn; abstract-only pretraining |
| BioClinical-ModernBERT-large | `thomas-sounack/BioClinical-ModernBERT-large` | 396M | **8192** | SOTA on 4/5 tasks | 2025-26 arch (RoPE, FlashAttn); **clinical-heavy** (MIMIC-IV, DEID) |
| Bio-ModernBERT-large | `thomas-sounack/Bio-ModernBERT-large` | ~396M | 8192 | — | biomedical-only variant of the above — closer to our domain |

BLURB leaderboard reference: BioLinkBERT-Large 84.30 (NER 86.89) > BioM-ALBERT-xxlarge
84.10 > BioM-ELECTRA-Large 83.81 > BioLinkBERT-Base 83.39 (NER 86.39). PubMedBERT /
BiomedBERT base sits at ~82.91.

## Expected gain — reality check

Base → large on BLURB NER is worth roughly **+0.5 points** (BioLinkBERT base 86.39 →
large 86.89). Our measured **seed noise band is ±0.007 F1** (3 seeds, gold-004/005/006).

So:
- realistic gain ≈ **+0.01 – 0.03 F1**
- gap to teacher qwen2.5:14b ≈ **0.044**
- any single-seed comparison below ~0.015 F1 is **indistinguishable from noise** →
  every candidate needs ≥3 seeds

Additional risk: only **860 training documents**. Large encoders are unstable on
small data and typically need a lower LR and longer warmup. The gain is not
guaranteed and can go negative without care.

## Code impact — larger than it looks

`MODEL` is hardcoded in **two** places and `bio_tags.jsonl` stores
tokenizer-specific `input_ids`:

- `preprocessing/tag_bio.py:39`
- `train.py:46`

Swapping the base model therefore requires:

1. a `--model` flag in **both** scripts;
2. **re-tokenizing** — re-run `tag_bio.py` + `build_dataset.py` into a
   per-tokenizer data dir (`data/processed/gold-<model>/`);
3. for any ModernBERT variant, switching `BertForTokenClassification` →
   `AutoModelForTokenClassification`.

A ModernBERT model's 8192 context would also recover the ~7 documents currently
lost to 512-token truncation (minor).

## Hardware

| Where | GPU | Verdict for a 340–396M full fine-tune |
|---|---|---|
| Local | RTX 4060 Laptop, **8 GB** | batch 16 needs ~10 GB → **does not fit**. Workable at batch 4 + grad-accum 4, or gradient checkpointing; slow. |
| TÜBİTAK TRUBA | `palamut-cuda` 8×A100-40GB; `kolyoz-cuda` 4×H100/H200; `akya-cuda` 4×V100 | batch 16 fits comfortably — the right place for large-model runs. |

## Recommendation

Ranked by value/cost:

1. **BioLinkBERT-large** — BLURB #1, 512 ctx so the existing pipeline shape holds.
2. **Bio-ModernBERT-large** — newest architecture, 8192 ctx, but needs the
   `AutoModel` refactor.
3. **BiomedBERT-large** — lowest risk and least code, probably the smallest gain.

**Caveat:** this path is worth perhaps +0.02 F1, whereas **more reviewed data
(wave-3, 860 → 2000+ docs)** remains the dominant lever. Treat a larger base model
as a complement to more data, not a substitute.

## Sources

- [BLURB Leaderboard](https://microsoft.github.io/BLURB/leaderboard.html)
- [BioClinical ModernBERT (arXiv 2506.10896)](https://huggingface.co/papers/2506.10896)
- [BioLinkBERT-large](https://huggingface.co/michiyasunaga/BioLinkBERT-large)
- [TRUBA GPU documentation](https://docs.truba.gov.tr/2-temel_bilgiler/gpu.html)
- [GLiNER-BioMed (Bioinformatics)](https://academic.oup.com/bioinformatics/article/42/6/btag322/8690923)
