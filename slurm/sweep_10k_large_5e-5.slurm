#!/bin/bash
# Pathway-only 10k sweep: add lr=5e-5 for both large candidates. The original
# sweep_10k_large.slurm only tried 1e-5/2e-5/3e-5 (the registry's large-model lr
# grid); this fills in the base-tier lr (5e-5, what all three base models used)
# so the size comparison isn't confounded by an lr grid the large models never
# got to compete at.
#
# Same 12h wall limit as sweep_10k_timeouts.slurm and for the same reason: every
# completed large cell in the original sweep took 879-940s/epoch regardless of
# lr, so a full 40-epoch run is bounded at ~10.4h; 12h leaves margin without
# asking akya-cuda for more than the earlier sweep already showed was needed.
#
# Submit only from a clean checkout of experiment/ner-10k-sweep:
#   sbatch slurm/sweep_10k_large_5e-5.slurm

#SBATCH --partition=akya-cuda
#SBATCH --account=abedir
#SBATCH --job-name=ner-10k-large-5e-5
#SBATCH --output=logs/ner-10k-large-5e-5-%A_%a.out
#SBATCH --error=logs/ner-10k-large-5e-5-%A_%a.err
#SBATCH --array=0-5
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=10
#SBATCH --gres=gpu:1
#SBATCH --time=12:00:00

set -euo pipefail

REPO=/arf/scratch/$USER/NER-pipeline
SIF=/arf/home/$USER/container-user/nerenv.sif
RUNS_DIR=runs-truba-large-5e-5
DATASET=pathway-10k

MODELS=(biolinkbert-large biom-electra-large)
LR=5e-5
SEEDS=(42 1 7)

MODEL_INDEX=$((SLURM_ARRAY_TASK_ID / ${#SEEDS[@]}))
SEED_INDEX=$((SLURM_ARRAY_TASK_ID % ${#SEEDS[@]}))
MODEL=${MODELS[$MODEL_INDEX]}
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
        --summary "$RUNS_DIR/summary-large-5e-5-${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}.jsonl" \
        --dataset "$DATASET" \
        --models "$MODEL" \
        --lrs "$LR" \
        --seeds "$SEED"
