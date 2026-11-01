#!/bin/bash
# 10k + missing corpus with the sentence-shuffle copies added to train:
# biomedbert-base at 3e-5 across the three seeds of the pathway-10k-missing
# sweep. Validation and test are that sweep's sets, unchanged, so the training
# data is the only changed variable against its biomedbert-base 3e-5 cells.
#
# The train set is about three times the size of pathway-10k-missing, and that
# corpus's biomedbert-base cells took about 3.2 h of the 40 epochs on a V100, so
# the limit is raised from 8 h to 16 h rather than cutting epochs.
#
#   sbatch slurm/sweep_10k_missing_shuffle.slurm

#SBATCH --partition=akya-cuda
#SBATCH --account=abedir
#SBATCH --job-name=ner-10k-shuffle
#SBATCH --output=logs/ner-10k-shuffle-%A_%a.out
#SBATCH --error=logs/ner-10k-shuffle-%A_%a.err
#SBATCH --array=0-2
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=10
#SBATCH --gres=gpu:1
#SBATCH --time=16:00:00

set -euo pipefail

REPO=/arf/scratch/$USER/NER-pipeline
SIF=/arf/home/$USER/container-user/nerenv.sif
RUNS_DIR=runs-truba-10k-missing-shuffle
DATASET=pathway-10k-missing-shuffle

MODEL=biomedbert-base
LR=3e-5
SEEDS=(42 1 7)
SEED=${SEEDS[$SLURM_ARRAY_TASK_ID]}

cd "$REPO"
mkdir -p logs

if [ -n "$(git status --porcelain train.py encoders.py preprocessing scripts slurm)" ]; then
    echo "FATAL: experiment files are dirty — commit before recording runs" >&2
    exit 1
fi

for required in \
    "data/processed/$DATASET/splits.json" \
    "data/processed/$DATASET-$MODEL/meta.json" \
    "data/processed/$DATASET-$MODEL/train.jsonl" \
    "data/processed/$DATASET-$MODEL/val.jsonl" \
    "data/processed/$DATASET-$MODEL/test.jsonl"; do
    if [ ! -s "$required" ]; then
        echo "FATAL: required dataset file missing or empty: $required" >&2
        exit 1
    fi
done

export HF_HOME=/arf/scratch/$USER/hf
export HF_HUB_OFFLINE=1
export TMPDIR=/tmp/$SLURM_JOB_ID
export NER_PYTHON=python3
mkdir -p "$TMPDIR"

echo "task $SLURM_ARRAY_TASK_ID -> $MODEL lr=$LR seed=$SEED on $(hostname)"
nvidia-smi

apptainer exec --nv \
    --bind /arf/scratch/$USER:/arf/scratch/$USER \
    "$SIF" \
    python3 scripts/run_matrix.py \
        --runs-dir "$RUNS_DIR" \
        --summary "$RUNS_DIR/summary-${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}.jsonl" \
        --dataset "$DATASET" \
        --models "$MODEL" \
        --lrs "$LR" \
        --seeds "$SEED"
