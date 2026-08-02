# Gold wave-4 dataset

Versioned expansion of the historical Phase 4b gold dataset. The old
`data/processed/gold/` snapshot and every `data/processed/gold-<tokenizer>/`
dataset remain unchanged.

## Sources

The four sources have no PMID overlap:

| source | documents | positive documents | spans | review status |
|---|---:|---:|---:|---|
| pilot batch 05 | 200 | 182 | 483 | mixed human/assistant |
| wave-2 | 1000 | 901 | 2334 | assistant-reviewed |
| wave-3 | 1000 | 901 | 2339 | human-reviewed |
| wave-4 | 1000 | 903 | 2306 | human-reviewed |
| **total** | **3200** | **2887** | **7462** | — |

`articles.jsonl` contains all 3200 documents. `matches.jsonl` contains the 2887
documents with at least one span; the current NER pipeline does not train on the
313 span-free documents.

## Frozen split

`splits.json` extends `data/processed/gold/splits.json` instead of re-deriving a
split:

| split | assigned PMIDs | policy |
|---|---:|---|
| train | 2664 | historical 860 plus 1804 new positive wave-3/4 PMIDs |
| validation | 107 | byte-order identical to Phase 4b |
| test | 109 | byte-order identical to Phase 4b |
| excluded | 7 | preserved historical truncation exclusions |

Keeping validation and test fixed isolates the supervision change. The seven
historical exclusions remain outside every split so long-context models do not
silently evaluate on a different corpus.

## Tokenizer-specific datasets

Tokenization can remove a document when every positive span lies beyond the
context limit. These are the effective files generated from the frozen assignment:

| model | context | train kept | validation kept | test kept | unassigned kept |
|---|---:|---:|---:|---:|---:|
| `biomedbert-base` | 512 | 2659 | 107 | 109 | 0 |
| `bert-base` | 512 | 2637 | 107 | 109 | 0 |
| `bio-clinicalbert` | 512 | 2611 | 106 | 108 | 0 |
| `bioelectra-base` | 512 | 2659 | 107 | 109 | 0 |
| `bio-modernbert-base` | 8192 | 2664 | 107 | 109 | 7 |

For every model, validation and test JSONL files are byte-identical to that
model's Phase 4b files. The historical train JSONL is also an unchanged prefix of
the expanded train file. Alignment validation accounts for all 7462 spans under
all five tokenizers with zero unexplained losses.

## Regenerate

Run from the repository root. The final wave-3/4 gold files are tracked canonical
inputs; the model-independent JSONLs and per-tokenizer datasets are ignored.
The historical wave-2 and pilot gold intermediates must already exist; see
`../gold/README.md` if they need to be regenerated from their tracked sources.

```bash
venv310/bin/python3 preprocessing/gold_to_matches.py \
    --sources doccano/wave2_1k_gold.jsonl \
              doccano/pilot_1k_batch05_gold.jsonl \
              doccano/wave3_1k_gold.jsonl \
              doccano/wave4_1k_gold.jsonl \
    --outdir data/processed/gold-wave4

venv310/bin/python3 preprocessing/make_splits.py \
    --base-splits data/processed/gold/splits.json \
    --matches data/processed/gold-wave4/matches.jsonl \
    --output data/processed/gold-wave4/splits.json
```

For each registry key in `biomedbert-base`, `bert-base`,
`bio-clinicalbert`, `bioelectra-base`, and `bio-modernbert-base`:

```bash
MODEL=biomedbert-base
DIR=data/processed/gold-wave4-$MODEL

HF_HUB_OFFLINE=1 venv310/bin/python3 preprocessing/tag_bio.py \
    --matches data/processed/gold-wave4/matches.jsonl \
    --articles data/processed/gold-wave4/articles.jsonl \
    --output $DIR/bio_tags.jsonl --db "" --model $MODEL

venv310/bin/python3 preprocessing/build_dataset.py \
    --input $DIR/bio_tags.jsonl --outdir $DIR \
    --splits data/processed/gold-wave4/splits.json

HF_HUB_OFFLINE=1 venv310/bin/python3 preprocessing/check_alignment.py \
    --data-dir $DIR \
    --matches data/processed/gold-wave4/matches.jsonl \
    --articles data/processed/gold-wave4/articles.jsonl \
    --splits data/processed/gold-wave4/splits.json \
    --model $MODEL --report analysis/alignment_gold-wave4-$MODEL.json
```
