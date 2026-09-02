#!/bin/bash
# Build the tokenizer-specific datasets for the merged 10k + missing-pathway
# corpus. The corpus itself (articles.jsonl, matches.jsonl) comes from
# scripts/build_merged_pathway_dataset.py + preprocessing/gold_to_matches.py,
# and splits.json from scripts/build_merged_splits.py; this script only does the
# per-tokenizer part.

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

PYTHON=${NER_PYTHON:-/home/enes/NER-pipeline/venv310/bin/python3}
CORPUS=data/processed/pathway-10k-missing
MODELS=(
    biom-electra-large
    bioelectra-base
    biomedbert-base
)

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
        --report "analysis/alignment_pathway-10k-missing-$model.json"
done
