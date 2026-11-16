#!/bin/bash
# Kev-4B fine-tune on the relation_silver_v1_2026-11-17 snapshot on UHEM Altay
# (one A100 80GB of a100q), then score the dev slice and the gt_100 test set.
#
# One job is one (ARM, EPOCHS, SEED) cell. The grid is
#   arm A, epochs {1, 3, 6} x seeds {0, 1, 2}
#   arm B, epochs {1, 3}    x seeds {0, 1, 2}
# B skips 6 epochs: B has about 3x the pairs of A, so 6 epochs there would be the
# single most expensive cell, and the 2026-11-12 sweep already dropped on gt_100
# after 3 epochs.
#
# Arms (relation_extraction/decision_models/build_kev_data.py, --snapshot):
#   A  silver_2k same_sentence (Opus 4.8) + silver_2k doc_level (Opus 5.5)
#      train 3,677 pairs: 2,225 same_sentence, 1,452 doc_level
#   B  A + silver_4k same_sentence (Opus 5.5 / Sonnet 5.5) + silver_4k doc_level_partial
#      train 10,883 pairs: 8,329 same_sentence, 2,554 doc_level
# Dev is the same file in both arms: 305 same_sentence pairs (the old dev,
# Opus 4.8 labels) + 109 doc_level pairs (Opus 5.5 labels) of the silver_2k dev
# pmids. The silver test pmids stay closed. The split is
# data/processed/relation/kev_silver_v1/split_pmids.json.
#
# Selection rule, fixed before the first job of this grid:
#   1. Only dev is used. gt_100 and the silver test are never used to choose.
#   2. Score of a cell: (accuracy on the 305 same_sentence dev pairs + accuracy on
#      the 109 doc_level dev pairs) / 2, then averaged over seeds 0, 1, 2. The two
#      strata weigh the same although doc_level has fewer pairs, because two
#      thirds of gt_100 is doc_level.
#   3. Within an arm: take the epoch count with the highest score. If a smaller
#      epoch count is within 1.0 point of it, take the smaller one.
#   4. Between arms: B is chosen only if its selected cell beats A's selected
#      cell by at least 1.0 point; otherwise A.
#   5. Reported for every cell, not used for the choice: pooled dev accuracy
#      (414 pairs), dev same_sentence accuracy (comparable to the 2026-11-12
#      sweep), dev doc_level accuracy, gt_100 accuracy on all / doc_level /
#      same_sentence pairs, and macro-F1.
#
# The snapshot is not in git. Copy it unchanged to $KEV_WORK/data-products/ (or set
# SNAPSHOT); the job checks it against its own SHA256SUMS, and the builder checks
# the label and candidate files against the sha256 recorded in split_pmids.json.
#
# Before the first job, on the Altay login node: see slurm/kev_altay.slurm (repo at
# the commit to run with a clean tree, $KEV_WORK/kev/$KEV_COMMIT, $KEV_WORK/hf).
#
# Time: the default 08:00:00 covers A and B at 1 epoch. Pass --time=14:00:00 for
# B at 3 epochs (estimate about 8 h from the 2026-11-12 speed). Measure first with
# a smoke test of each arm.
#
#   cd <repo> && export KEV_WORK=<work dir on Altay>
#   sbatch --time=00:30:00 --export=ALL,ARM=B,EPOCHS=1,SEED=0,MAX_STEPS=20 slurm/kev_altay_silver_v1.slurm   # smoke test
#   for s in 0 1 2; do for e in 1 3 6; do
#       sbatch --export=ALL,ARM=A,EPOCHS=$e,SEED=$s slurm/kev_altay_silver_v1.slurm
#   done; done
#   for s in 0 1 2; do
#       sbatch --export=ALL,ARM=B,EPOCHS=1,SEED=$s slurm/kev_altay_silver_v1.slurm
#       sbatch --time=14:00:00 --export=ALL,ARM=B,EPOCHS=3,SEED=$s slurm/kev_altay_silver_v1.slurm
#   done

#SBATCH --account=mvmatk
#SBATCH --partition=a100q
#SBATCH --job-name=kev-4b-sv1
#SBATCH --output=logs/kev-altay-%j.out
#SBATCH --error=logs/kev-altay-%j.err
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --gres=gpu:1
#SBATCH --time=08:00:00

set -euo pipefail

: "${KEV_WORK:?export KEV_WORK, the Altay directory holding kev/, hf/, data-products/ and runs/}"
: "${ARM:?set ARM to A or B}"
: "${EPOCHS:?set EPOCHS}"
: "${SEED:?set SEED}"
MAX_STEPS=${MAX_STEPS:-0}

REPO=${SLURM_SUBMIT_DIR:-$PWD}
KEV_COMMIT=2074cc44256200bb37540103fa4572901faa10f3
SNAPSHOT=${SNAPSHOT:-$KEV_WORK/data-products/relation_silver_v1_2026-11-17}
SPLIT_DIR=data/processed/relation/kev_silver_v1

cd "$REPO"
mkdir -p logs

if [ -n "$(git status --porcelain relation_extraction slurm "$SPLIT_DIR" data/processed/gt_100)" ]; then
    echo "FATAL: experiment files are dirty — commit before recording runs" >&2
    exit 1
fi

(cd "$SNAPSHOT" && sha256sum -c --quiet SHA256SUMS)
sha256sum "$SNAPSHOT/SHA256SUMS" "$SPLIT_DIR/split_pmids.json"

export HF_HOME=$KEV_WORK/hf
export HF_HUB_OFFLINE=1
export TMPDIR=${TMPDIR:-/tmp}/kev-$SLURM_JOB_ID
mkdir -p "$TMPDIR"

export KEV_DIR=$KEV_WORK/kev/$KEV_COMMIT
export DATA=$TMPDIR/data
export BASE=Qwen/Qwen3.5-4B-Base
export BASE_REVISION=1001bb4d826a52d1f399e183466143f4da7b741b
export INIT=jaredpalmer/kev-4b@6cfce5c2fa4b4bd64026336ab649c5ca78857d52
export WEIGHTS_DTYPE=bf16
export EVAL_DTYPE=bf16
export EPOCHS SEED MAX_STEPS
export BASELINE=${BASELINE:-0}
export SKIP_SYNC=1
SUFFIX=""
if [ "$MAX_STEPS" != 0 ]; then SUFFIX="_smoke"; fi
export OUT=$KEV_WORK/runs/kev-4b_sv1${ARM}_e${EPOCHS}_s${SEED}${SUFFIX}_${SLURM_JOB_ID}

git rev-parse HEAD
nvidia-smi
echo "ARM=$ARM EPOCHS=$EPOCHS SEED=$SEED MAX_STEPS=$MAX_STEPS SNAPSHOT=$SNAPSHOT OUT=$OUT"

# The system python3 of RHEL 8 can be 3.6; the builder needs 3.7+, so Kev's venv runs it.
PY=$KEV_DIR/.venv/bin/python
"$PY" relation_extraction/decision_models/build_kev_data.py --snapshot "$SNAPSHOT" --arm "$ARM" --outdir "$DATA"
"$PY" relation_extraction/decision_models/build_kev_data.py --gt100 --outdir "$DATA"
sha256sum "$DATA/train.jsonl" "$DATA/dev.jsonl" "$DATA/gt_100.jsonl"

relation_extraction/decision_models/train_kev.sh

cd "$KEV_DIR"
"$PY" "$REPO/relation_extraction/decision_models/eval_kev.py" \
    --run "$OUT" --data "$DATA/gt_100.jsonl" --out "$OUT/gt_100_predictions.json" --dtype "$EVAL_DTYPE"
