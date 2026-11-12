#!/bin/bash
# Kev-4B fine-tune on the silver_2k_10kplusmissing relation pairs on UHEM Altay
# (one A100 80GB of a100q), then score the dev slice and the gt_100 test set.
#
# One job is one (EPOCHS, SEED) cell. The epoch comparison runs as separate jobs
# because Kev saves no LoRA checkpoint between epochs and its OneCycleLR schedule
# spans the whole run, so epoch 1 of a 3-epoch run is not a 1-epoch model. Choose
# the epoch count on the dev mean over seeds; gt_100 is the reported number.
#
# Training data is built inside the job from the tracked silver labels and
# split_pmids.json (pmid split of pathway-re-synth, seed 13, plus the 18 abstracts
# that only the new pathway spans gave pairs, in train). silver_test stays closed.
# Both input files print their sha256 into the log.
#
# Before the first job, on the Altay login node (it has network; see
# relation_extraction/decision_models/train_kev.sh for what Kev needs):
#   - this repository cloned at the commit to run, with a clean tree,
#   - $KEV_WORK/kev/$KEV_COMMIT: a Kev clone with `uv sync --frozen --extra serve`,
#   - $KEV_WORK/hf: Hugging Face cache holding BASE@BASE_REVISION and INIT.
# Jobs run with HF_HUB_OFFLINE=1 and SKIP_SYNC=1 so every cell uses that same
# prepared environment.
#
# UHEM rejects jobs without -n. h200q nodes are exclusive and billed at 2x their
# 192 cores, so a100q is the default; gpu2dq shares the a100q nodes with a 2-day
# limit. The time limit fits 3 epochs at the V100 speed (1.7 h per epoch);
# lower it once the smoke test has measured the A100 speed.
#
#   cd <repo> && export KEV_WORK=<work dir on Altay>
#   sbatch --time=00:30:00 --export=ALL,EPOCHS=1,SEED=0,MAX_STEPS=2 slurm/kev_altay.slurm   # smoke test
#   for s in 0 1 2; do for e in 1 3; do
#       sbatch --export=ALL,EPOCHS=$e,SEED=$s slurm/kev_altay.slurm
#   done; done

#SBATCH --account=mvmatk
#SBATCH --partition=a100q
#SBATCH --job-name=kev-4b-10kpm
#SBATCH --output=logs/kev-altay-%j.out
#SBATCH --error=logs/kev-altay-%j.err
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --gres=gpu:1
#SBATCH --time=08:00:00

set -euo pipefail

: "${KEV_WORK:?export KEV_WORK, the Altay directory holding kev/, hf/ and runs/}"
: "${EPOCHS:?set EPOCHS}"
: "${SEED:?set SEED}"
MAX_STEPS=${MAX_STEPS:-0}

REPO=${SLURM_SUBMIT_DIR:-$PWD}
KEV_COMMIT=2074cc44256200bb37540103fa4572901faa10f3
SILVER=data/processed/relation/silver_2k_10kplusmissing

cd "$REPO"
mkdir -p logs

if [ -n "$(git status --porcelain relation_extraction slurm "$SILVER" data/processed/gt_100)" ]; then
    echo "FATAL: experiment files are dirty — commit before recording runs" >&2
    exit 1
fi

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
export OUT=$KEV_WORK/runs/kev-4b_10kpm_e${EPOCHS}_s${SEED}${SUFFIX}_${SLURM_JOB_ID}

git rev-parse HEAD
nvidia-smi
echo "EPOCHS=$EPOCHS SEED=$SEED MAX_STEPS=$MAX_STEPS OUT=$OUT"

# The system python3 of RHEL 8 can be 3.6; the builder needs 3.7+, so Kev's venv runs it.
PY=$KEV_DIR/.venv/bin/python
sha256sum "$SILVER/relations_llm_opus48_same_sentence.jsonl" "$SILVER/split_pmids.json"
"$PY" relation_extraction/decision_models/build_kev_data.py --silver "$SILVER" --outdir "$DATA"
"$PY" relation_extraction/decision_models/build_kev_data.py --gt100 --outdir "$DATA"
sha256sum "$DATA/gt_100.jsonl"

relation_extraction/decision_models/train_kev.sh

cd "$KEV_DIR"
"$PY" "$REPO/relation_extraction/decision_models/eval_kev.py" \
    --run "$OUT" --data "$DATA/gt_100.jsonl" --out "$OUT/gt_100_predictions.json" --dtype "$EVAL_DTYPE"
