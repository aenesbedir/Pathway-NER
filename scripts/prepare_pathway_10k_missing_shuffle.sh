#!/bin/bash
# Build the 10k + missing corpus extended with the sentence-shuffle copies, its
# split, and the tokenizer-specific datasets. The copies come from
# preprocessing/shuffle_sentence/shuffle_sentence.py; validation and test are
# those of pathway-10k-missing (scripts/build_shuffle_splits.py).

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

PYTHON=${NER_PYTHON:-/home/enes/NER-pipeline/venv310/bin/python3}
BASE_SOURCE=data/doccano/pathway_10k_plus_missing.jsonl
SHUFFLE=${SHUFFLE:-data/processed/10k-missing-shuffle/k2_n2_seed42/sentence_shuffle.jsonl}
CORPUS=data/processed/pathway-10k-missing-shuffle
MODELS=(
    biomedbert-base
)

"$PYTHON" preprocessing/gold_to_matches.py \
    --sources "$BASE_SOURCE" "$SHUFFLE" \
    --label PATHWAY \
    --outdir "$CORPUS"

"$PYTHON" scripts/build_shuffle_splits.py --shuffle "$SHUFFLE" --out "$CORPUS/splits.json"

for model in "${MODELS[@]}"; do
    data_dir="$CORPUS-$model"

    "$PYTHON" preprocessing/tag_bio.py \
        --matches "$CORPUS/matches.jsonl" \
        --articles "$CORPUS/articles.jsonl" \
        --output "$data_dir/bio_tags.jsonl" \
        --db "" \
        --model "$model" \
        --include-span-free

    "$PYTHON" preprocessing/build_dataset.py \
        --input "$data_dir/bio_tags.jsonl" \
        --outdir "$data_dir" \
        --splits "$CORPUS/splits.json" \
        --keep-span-free

    "$PYTHON" preprocessing/check_alignment.py \
        --data-dir "$data_dir" \
        --matches "$CORPUS/matches.jsonl" \
        --articles "$CORPUS/articles.jsonl" \
        --splits "$CORPUS/splits.json" \
        --model "$model" \
        --report "analysis/alignment_pathway-10k-missing-shuffle-$model.json"
done
