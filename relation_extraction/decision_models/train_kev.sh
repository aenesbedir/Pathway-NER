#!/bin/bash
# Fine-tune Kev on the silver relation pairs and score the dev slice. Defaults are
# the 2026-11-01 Kev-0.8B pilot.
#
# Kev is not vendored. It is cloned at KEV_COMMIT into KEV_DIR and installed from
# its own uv.lock; it needs Python 3.12-3.13, so it cannot share venv310. PyPI's
# `kev` is an unrelated package. Compute nodes without network need KEV_DIR, its
# environment and the Hugging Face cache prepared beforehand.
#
#   relation_extraction/decision_models/train_kev.sh
#
# Set MAX_STEPS to stop early, for a smoke test. Set BASELINE=1 to score INIT
# before training. An existing $DATA/train.jsonl is used as it is, and SKIP_SYNC=1
# trusts the prepared environment; both are for compute nodes without network.

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
KEV_COMMIT=2074cc44256200bb37540103fa4572901faa10f3
KEV_DIR=${KEV_DIR:-$HOME/.cache/kev/$KEV_COMMIT}
DATA=${DATA:-$ROOT/data/processed/relation/kev_silver}
OUT=${OUT:-$ROOT/models_re/kev-0.8b_silver}
BASE=${BASE:-Qwen/Qwen3.5-0.8B-Base}
BASE_REVISION=${BASE_REVISION:-dc7cdfe2ee4154fa7e30f5b51ca41bfa40174e68}
INIT=${INIT:-jaredpalmer/kev-0.8b@bf75a6a8848ea6960ff2ed108d9ed44c2941174f}
EPOCHS=${EPOCHS:-2}
LR=${LR:-2e-5}
MAX_STATE=${MAX_STATE:-2200}
MAX_STEPS=${MAX_STEPS:-0}
WEIGHTS_DTYPE=${WEIGHTS_DTYPE:-fp32}
EVAL_DTYPE=${EVAL_DTYPE:-}
BASELINE=${BASELINE:-0}
SKIP_SYNC=${SKIP_SYNC:-0}
EVAL=(.venv/bin/python "$ROOT/relation_extraction/decision_models/eval_kev.py")

if [ ! -d "$KEV_DIR/.git" ]; then
    git clone https://github.com/jaredpalmer/kev.git "$KEV_DIR"
    git -C "$KEV_DIR" checkout -q "$KEV_COMMIT"
fi
if [ "$(git -C "$KEV_DIR" rev-parse HEAD)" != "$KEV_COMMIT" ] || [ -n "$(git -C "$KEV_DIR" status --porcelain)" ]; then
    echo "FATAL: $KEV_DIR is not a clean checkout of $KEV_COMMIT" >&2
    exit 1
fi

if [ ! -s "$DATA/train.jsonl" ]; then
    python3 "$ROOT/relation_extraction/decision_models/build_kev_data.py" --outdir "$DATA"
fi
sha256sum "$DATA/train.jsonl" "$DATA/dev.jsonl"

cd "$KEV_DIR"
if [ "$SKIP_SYNC" != 1 ]; then
    uv sync -q --frozen --extra serve
fi
mkdir -p "$(dirname "$OUT")"
if [ -n "$EVAL_DTYPE" ]; then
    EVAL+=(--dtype "$EVAL_DTYPE")
fi

if [ "$BASELINE" = 1 ]; then
    "${EVAL[@]}" --run "$INIT" --data "$DATA/dev.jsonl" --out "${OUT}_baseline_dev_predictions.json"
fi

.venv/bin/python -m kev.train \
    --data "$DATA/train.jsonl" \
    --base "$BASE" \
    --base_revision "$BASE_REVISION" \
    --init_from "$INIT" \
    --epochs "$EPOCHS" --lr "$LR" --batch 1 --accum 8 \
    --dtype bf16 --weights_dtype "$WEIGHTS_DTYPE" --checkpointing 1 --device cuda \
    --max_state "$MAX_STATE" \
    --max_steps "$MAX_STEPS" \
    --out "$OUT"

"${EVAL[@]}" --run "$OUT" --data "$DATA/dev.jsonl" --out "$OUT/dev_predictions.json"
