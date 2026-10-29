# Gold dataset (review-corrected)

Training data is built from **reviewed** silver labels, never raw silver. Each span
is the silver output with review corrections applied: false positives dropped,
false negatives added, and true positives kept (gold = `tp + fn` per document).

Four non-overlapping gold sources are now available:

| source | canonical labels | docs | positive docs | spans |
|--------|------------------|-----:|--------------:|------:|
| wave-2 silver (qwen2.5:14b) | `analysis/wave2_batch0[1-5]_review.json` (assistant-reviewed) | 1000 | 901 | 2334 |
| pilot-1k batch 05 | `analysis/batch_05_5_review.json` (docs 1–50 human, 51–200 assistant-reviewed) | 200 | 182 | 483 |
| wave-3 silver (qwen2.5:14b) | `doccano/wave3_1k_gold.jsonl` (human-reviewed) | 1000 | 901 | 2339 |
| wave-4 silver (qwen2.5:14b) | `doccano/wave4_1k_gold.jsonl` (human-reviewed) | 1000 | 903 | 2306 |
| **total** | — | **3200** | **2887** | **7462** |

Wave-3/4 review JSONs remain local audit material and are intentionally not
tracked. Their final gold JSONL files are therefore the tracked canonical records.
The processed `data/processed/gold/` snapshot still represents only wave-2 plus
pilot batch 05; it must remain untouched because its frozen split underlies the
gold-001…008 and Phase 4b results. The expanded corpus is built separately under
`data/processed/gold-wave4/`; see `../gold-wave4/README.md` for its frozen split,
effective per-tokenizer counts and regeneration commands.

The completed 1,000-document pilot review is applied in the newer
`data/processed/gold-pilot1k/` corpus. The historical directories documented
here remain unchanged so published experiment comparisons stay reproducible.

## Provenance chain

```
data/silver/wave2_1k.jsonl                         raw machine output (SILVER)
  └─ doccano/export_doccano.py  → doccano/wave2_1k_doccano.jsonl
       └─ doccano/split_batches.py → doccano/batches/wave2_1k_doccano_batch_NN_5.jsonl
            └─ review (drop FP, add FN) → analysis/wave2_batchNN_review.json
                 └─ doccano/build_gold_from_review.py → doccano/wave2_1k_gold.jsonl   (GOLD = tp+fn)
pilot: analysis/batch_05_5_review.json               → doccano/pilot_1k_batch05_gold.jsonl
                 └─ preprocessing/gold_to_matches.py → matches.jsonl + articles.jsonl   ← canonical, model-free
                      ├─ preprocessing/make_splits.py  → splits.json                    ← frozen contract
                      └─ preprocessing/tag_bio.py --model X → gold-<slug>/bio_tags.jsonl
                           └─ build_dataset.py --splits → gold-<slug>/{train,val,test}.jsonl

data/silver/wave3_1k.jsonl / wave4_1k.jsonl          raw machine output (SILVER)
  └─ local human-review audit JSONs
       └─ doccano/wave3_1k_gold.jsonl / wave4_1k_gold.jsonl   ← tracked canonical gold
```

## Files

This directory is the historical, tokenizer-independent Phase 4b snapshot.
Anything containing `input_ids` lives in a per-model directory,
`data/processed/gold-<slug>/`.

| file | rows | note |
|------|------|------|
| `matches.jsonl` | 1083 | gold spans as character offsets (`source="abstract"`, `pathway_id="gold"`); docs with ≥1 span only |
| `articles.jsonl` | 1200 | pmid → abstract text (all docs, incl. span-free) |
| `splits.json` | 1076 pmids | frozen train/val/test assignment — **tracked in git** |

Per model, e.g. `data/processed/gold-biomedbert-base/`:

| file | rows | note |
|------|------|------|
| `bio_tags.jsonl` | 1083 | BIO-tagged with that model's tokenizer |
| `meta.json` | — | which tokenizer wrote the `input_ids`; `train.py` refuses a mismatch |
| `train.jsonl` | 860 pmids / 5943 pos tokens | |
| `val.jsonl` | 107 pmids / 673 pos tokens | |
| `test.jsonl` | 109 pmids / 709 pos tokens | |

## Why the split is frozen

`build_dataset.py` drops docs with no positive labels *after* tokenization:
1200 → 1083 with spans → 1076 with B/I tokens under BiomedBERT (7 lost to
512-token truncation). It used to shuffle the survivors at `seed=42` — which made
the split depend on the tokenizer, since a ModernBERT at 8192 tokens loses none
of the 7 and would shuffle a 1083-element list into an entirely different
assignment. Every encoder would then be scored on a different test set with
nothing in the logs to show it.

`splits.json` snapshots the assignment gold-001…008 were trained and scored on,
so historical numbers stay comparable. The 7 truncated documents are therefore
excluded for every model, including long-context ones — worth reporting as a
separate measurement rather than worth invalidating eight runs over.

## Regenerate

These commands reproduce the historical wave-2 + pilot snapshot. They deliberately
do not overwrite it with wave-3/4; the expanded corpus has its own output directory
and frozen split under `data/processed/gold-wave4/`.

```bash
# 1. reviews → doccano gold
venv310/bin/python3 doccano/build_gold_from_review.py

# Optional local audit rebuild of the tracked wave-3/4 canonical gold files
venv310/bin/python3 doccano/build_gold_from_review.py --include-local-reviews

# 2. gold → matches + articles (both sources, into data/processed/gold/)
venv310/bin/python3 preprocessing/gold_to_matches.py \
    --sources doccano/wave2_1k_gold.jsonl doccano/pilot_1k_batch05_gold.jsonl \
    --outdir  data/processed/gold

# 3. freeze the split (already done and committed; only re-run if the corpus grows)
venv310/bin/python3 preprocessing/make_splits.py

# 4. matches + articles → BIO tags, per encoder (see `python3 encoders.py`)
MODEL=biomedbert-base
DIR=data/processed/gold-$MODEL
mkdir -p $DIR
venv310/bin/python3 preprocessing/tag_bio.py \
    --matches  data/processed/gold/matches.jsonl \
    --articles data/processed/gold/articles.jsonl \
    --output   $DIR/bio_tags.jsonl \
    --db "" --model $MODEL

# 5. BIO tags → train/val/test, against the frozen split
venv310/bin/python3 preprocessing/build_dataset.py \
    --input  $DIR/bio_tags.jsonl --outdir $DIR \
    --splits data/processed/gold/splits.json

# 6. verify the alignment survived this tokenizer (exit 1 on unexplained loss)
venv310/bin/python3 preprocessing/check_alignment.py \
    --data-dir $DIR --model $MODEL \
    --report analysis/alignment_$MODEL.json
```
