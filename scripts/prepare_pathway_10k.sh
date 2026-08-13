#!/bin/bash
# Build the pathway-only 10,125-document corpus and every tokenizer-specific
# dataset used by the TRUBA sweep. Generated JSONL files remain local and are
# transferred separately from the git branch.

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

PYTHON=${NER_PYTHON:-venv310/bin/python3}
SOURCE=${PATHWAY_10K_SOURCE:-data/doccano/disease_pathway_10125_doccano_combined_v1.jsonl}
CORPUS=data/processed/pathway-10k
MODELS=(
    biomedbert-base
    biolinkbert-base
    bioelectra-base
    biolinkbert-large
    biom-electra-large
)

"$PYTHON" preprocessing/gold_to_matches.py \
    --sources "$SOURCE" \
    --label PATHWAY \
    --outdir "$CORPUS"

"$PYTHON" preprocessing/make_random_splits.py \
    --articles "$CORPUS/articles.jsonl" \
    --matches "$CORPUS/matches.jsonl" \
    --output "$CORPUS/splits.json" \
    --seed 42 \
    --train-ratio 0.8 \
    --val-ratio 0.1

for model in "${MODELS[@]}"; do
    data_dir="data/processed/pathway-10k-$model"

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
        --report "analysis/alignment_pathway-10k-$model.json"
done
