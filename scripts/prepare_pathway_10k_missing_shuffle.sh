#!/bin/bash
# Build the 10k + missing corpus extended with the sentence-shuffle copies, its
# split, and the tokenizer-specific datasets. The copies come from
# preprocessing/shuffle_sentence/shuffle_sentence.py; validation and test are
# those of pathway-10k-missing (scripts/build_shuffle_splits.py).
#
# The corpus is named after the shuffle version it holds: SHUFFLE under
# data/processed/10k-missing-shuffle/v<N>/ builds pathway-10k-missing-shuffle-v<N>,
# so the version reaches every dataset and run directory built on it. The legacy
# k2_n2_seed42/ output is version 1 and keeps the unversioned name. Nothing is
# overwritten: an existing corpus must match SHUFFLE through its manifest.json
# (scripts/shuffle_corpus_manifest.py) and is then reused, and an existing
# tokenizer-specific dataset is left alone.
#
#   SHUFFLE=data/processed/10k-missing-shuffle/v2/sentence_shuffle.jsonl \
#       scripts/prepare_pathway_10k_missing_shuffle.sh

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

PYTHON=${NER_PYTHON:-/home/enes/NER-pipeline/venv310/bin/python3}
BASE_SOURCE=data/doccano/pathway_10k_plus_missing.jsonl
SHUFFLE=${SHUFFLE:-data/processed/10k-missing-shuffle/k2_n2_seed42/sentence_shuffle.jsonl}
version_dir=$(basename "$(dirname "$SHUFFLE")")
case "$version_dir" in
    k2_n2_seed42) CORPUS=data/processed/pathway-10k-missing-shuffle ;;
    v[0-9]*) CORPUS=data/processed/pathway-10k-missing-shuffle-$version_dir ;;
    *) echo "FATAL: $SHUFFLE is not in a shuffle version directory (v<N>)" >&2; exit 1 ;;
esac
MODELS=(
    biomedbert-base
)

if [ -d "$CORPUS" ]; then
    "$PYTHON" scripts/shuffle_corpus_manifest.py check --corpus "$CORPUS" --shuffle "$SHUFFLE"
    echo "$CORPUS already holds $SHUFFLE; reusing it"
else
    "$PYTHON" preprocessing/gold_to_matches.py \
        --sources "$BASE_SOURCE" "$SHUFFLE" \
        --label PATHWAY \
        --outdir "$CORPUS"

    "$PYTHON" scripts/build_shuffle_splits.py --shuffle "$SHUFFLE" --out "$CORPUS/splits.json"

    "$PYTHON" scripts/shuffle_corpus_manifest.py write \
        --corpus "$CORPUS" --shuffle "$SHUFFLE" --base-source "$BASE_SOURCE"
fi

for model in "${MODELS[@]}"; do
    data_dir="$CORPUS-$model"
    if [ -d "$data_dir" ]; then
        echo "$data_dir exists; not rebuilding it"
        continue
    fi

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
        --report "analysis/alignment_$(basename "$CORPUS")-$model.json"
done
