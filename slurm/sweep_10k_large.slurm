#!/bin/bash
# Pathway-only 10k sweep: one independent array task per large model, learning
# rate, and seed. Both selected models use fp16 and fit the akya V100 comparison;
# the 8h wall limit leaves room for the first unmeasured 340M runs.
#
# Submit only after the base array's dataset/cache checks succeed:
#   sbatch slurm/sweep_10k_large.slurm

#SBATCH --partition=akya-cuda
#SBATCH --account=abedir
#SBATCH --job-name=ner-10k-large
#SBATCH --output=logs/ner-10k-large-%A_%a.out
#SBATCH --error=logs/ner-10k-large-%A_%a.err
#SBATCH --array=0-17
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=10
#SBATCH --gres=gpu:1
#SBATCH --time=08:00:00

set -euo pipefail

REPO=/arf/scratch/$USER/NER-pipeline
SIF=/arf/home/$USER/container-user/nerenv.sif
RUNS_DIR=runs-truba-10k
DATASET=pathway-10k

MODELS=(biolinkbert-large biom-electra-large)
LRS=(1e-5 2e-5 3e-5)
SEEDS=(42 1 7)
CELLS_PER_MODEL=$((${#LRS[@]} * ${#SEEDS[@]}))
MODEL_INDEX=$((SLURM_ARRAY_TASK_ID / CELLS_PER_MODEL))
WITHIN_MODEL=$((SLURM_ARRAY_TASK_ID % CELLS_PER_MODEL))
LR_INDEX=$((WITHIN_MODEL / ${#SEEDS[@]}))
SEED_INDEX=$((WITHIN_MODEL % ${#SEEDS[@]}))
MODEL=${MODELS[$MODEL_INDEX]}
LR=${LRS[$LR_INDEX]}
SEED=${SEEDS[$SEED_INDEX]}

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
        --summary "$RUNS_DIR/summary-large-${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}.jsonl" \
        --dataset "$DATASET" \
        --models "$MODEL" \
        --lrs "$LR" \
        --seeds "$SEED"
