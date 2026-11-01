#!/bin/bash
# Kev-4B fine-tune on the silver relation pairs, scored on the dev slice, with the
# untuned checkpoint scored first. The backbone runs in bf16: in fp32 it is about
# 18.6 GB and does not fit the V100's 16 GB.
#
# Needs KEV_DIR prepared on the login node, the Hugging Face cache filled and
# train.jsonl and dev.jsonl in DATA.
#
#   sbatch slurm/kev_4b_silver.slurm
#   sbatch --time=01:00:00 --export=ALL,MAX_STEPS=2 slurm/kev_4b_silver.slurm

#SBATCH --partition=akya-cuda
#SBATCH --account=abedir
#SBATCH --job-name=kev-4b-silver
#SBATCH --output=logs/kev-4b-silver-%j.out
#SBATCH --error=logs/kev-4b-silver-%j.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=10
#SBATCH --gres=gpu:1
#SBATCH --time=08:00:00

set -euo pipefail

SCR=/arf/scratch/$USER
REPO=$SCR/NER-pipeline-kev
KEV_COMMIT=2074cc44256200bb37540103fa4572901faa10f3

cd "$REPO"
mkdir -p logs

if [ -n "$(git status --porcelain relation_extraction slurm)" ]; then
    echo "FATAL: experiment files are dirty — commit before recording runs" >&2
    exit 1
fi

export HF_HOME=$SCR/hf
export HF_HUB_OFFLINE=1
export TMPDIR=/tmp/$SLURM_JOB_ID
mkdir -p "$TMPDIR"

export KEV_DIR=$SCR/kev/$KEV_COMMIT
export DATA=$SCR/kev-data/silver
export OUT=$SCR/kev-runs/kev-4b_silver_${SLURM_JOB_ID}
export BASE=Qwen/Qwen3.5-4B-Base
export BASE_REVISION=1001bb4d826a52d1f399e183466143f4da7b741b
export INIT=jaredpalmer/kev-4b@6cfce5c2fa4b4bd64026336ab649c5ca78857d52
export WEIGHTS_DTYPE=bf16
export EVAL_DTYPE=bf16
export BASELINE=1
export SKIP_SYNC=1

git rev-parse HEAD
nvidia-smi
relation_extraction/decision_models/train_kev.sh
