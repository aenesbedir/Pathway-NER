#!/bin/bash
# Score a Kev checkpoint on the gt_100 relation test set (180 pairs). The input is
# built from the tracked gt_100 files on first use; its sha256 is printed.
#
# Needs KEV_DIR prepared on the login node and the Hugging Face cache filled, as
# for kev_4b_silver.slurm. RUN is the checkpoint directory to score.
#
#   sbatch --export=ALL,RUN=/arf/scratch/$USER/kev-runs/kev-4b_silver_6893708 slurm/kev_eval.slurm

#SBATCH --partition=akya-cuda
#SBATCH --account=abedir
#SBATCH --job-name=kev-eval
#SBATCH --output=logs/kev-eval-%j.out
#SBATCH --error=logs/kev-eval-%j.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=10
#SBATCH --gres=gpu:1
#SBATCH --time=00:30:00

set -euo pipefail

SCR=/arf/scratch/$USER
REPO=$SCR/NER-pipeline-kev
KEV_COMMIT=2074cc44256200bb37540103fa4572901faa10f3
KEV_DIR=$SCR/kev/$KEV_COMMIT
DATA=$SCR/kev-data/gt_100
: "${RUN:?set RUN to the checkpoint directory}"
EVAL_DTYPE=${EVAL_DTYPE:-bf16}
OUT=${OUT:-$RUN/gt_100_predictions.json}

cd "$REPO"
mkdir -p logs

if [ -n "$(git status --porcelain relation_extraction slurm data/processed/gt_100)" ]; then
    echo "FATAL: experiment files are dirty — commit before recording runs" >&2
    exit 1
fi

export HF_HOME=$SCR/hf
export HF_HUB_OFFLINE=1
export TMPDIR=/tmp/$SLURM_JOB_ID
mkdir -p "$TMPDIR"

git rev-parse HEAD
nvidia-smi

if [ ! -s "$DATA/gt_100.jsonl" ]; then
    python3 relation_extraction/decision_models/build_kev_data.py --gt100 --outdir "$DATA"
fi
sha256sum "$DATA/gt_100.jsonl"

if [ "$(git -C "$KEV_DIR" rev-parse HEAD)" != "$KEV_COMMIT" ] || [ -n "$(git -C "$KEV_DIR" status --porcelain)" ]; then
    echo "FATAL: $KEV_DIR is not a clean checkout of $KEV_COMMIT" >&2
    exit 1
fi
cd "$KEV_DIR"
.venv/bin/python "$REPO/relation_extraction/decision_models/eval_kev.py" \
    --run "$RUN" --data "$DATA/gt_100.jsonl" --out "$OUT" --dtype "$EVAL_DTYPE"
