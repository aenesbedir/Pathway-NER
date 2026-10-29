# Gold dataset with the fully reviewed pilot

This is the canonical model-independent corpus after applying the completed
review of all 1,000 pilot documents. Raw silver inputs remain unchanged.

## Sources

The four sources have no PMID overlap:

| source | documents | positive documents | spans | review status |
|---|---:|---:|---:|---|
| full pilot | 1000 | 914 | 2504 | batches 01-03 assistant-reviewed; batches 04-05 previously reviewed |
| wave-2 | 1000 | 901 | 2334 | assistant-reviewed |
| wave-3 | 1000 | 901 | 2339 | human-reviewed |
| wave-4 | 1000 | 903 | 2306 | human-reviewed |
| **total** | **4000** | **3619** | **9483** | — |

`articles.jsonl` contains every document. `matches.jsonl` contains only positive
documents because the current BIO conversion pipeline skips span-free records.

## Frozen split

`splits.json` extends `data/processed/gold-wave4/splits.json`. It keeps the
existing 107-document validation set and 109-document test set unchanged, then
adds the 732 newly available positive pilot PMIDs to training.

| split | assigned PMIDs |
|---|---:|
| train | 3396 |
| validation | 107 |
| test | 109 |
| excluded | 7 |

The seven historical long-document exclusions are preserved so results remain
comparable with the earlier gold and gold-wave4 experiments.

## BiomedBERT dataset

The local `gold-pilot1k-biomedbert-base` dataset is ready for training:

| split | assigned | kept after 512-token filtering | positive BIO labels |
|---|---:|---:|---:|
| train | 3396 | 3389 | 22605 |
| validation | 107 | 107 | 673 |
| test | 109 | 109 | 709 |

Alignment validation accounts for all 9,483 gold spans with zero unexplained
losses. The tokenizer-specific directory and alignment report are regenerable.

## Regenerate

Run from the repository root:

```bash
venv310/bin/python3 doccano/build_gold_from_review.py

venv310/bin/python3 preprocessing/gold_to_matches.py \
    --sources doccano/wave2_1k_gold.jsonl \
              doccano/pilot_1k_gold.jsonl \
              doccano/wave3_1k_gold.jsonl \
              doccano/wave4_1k_gold.jsonl \
    --outdir data/processed/gold-pilot1k

venv310/bin/python3 preprocessing/make_splits.py \
    --base-splits data/processed/gold-wave4/splits.json \
    --matches data/processed/gold-pilot1k/matches.jsonl \
    --output data/processed/gold-pilot1k/splits.json
```

Tokenizer-specific BIO and train/validation/test files should use a distinct
directory such as `data/processed/gold-pilot1k-biomedbert-base/`.
