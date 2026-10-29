#!/bin/bash
# Retrain the single best (lr, seed) cell for each large model with weights
# kept, for the same reason as sweep_10k_checkpoints_base.slurm: the original
# sweep_10k_large.slurm ran every cell with --no-save-model, so no large-model
# weights survived it.
#
# "Best" here means the lr group with the highest mean best_val_f1 among seeds
# completed so far in runs-truba-10k, and within that group the seed with the
# highest individual best_val_f1:
#   biolinkbert-large   lr=3e-5 seed=1  (val_f1 0.8914 — this lr's only
#                                        completed seed; the other two seeds in
#                                        this group are in runs-truba-timeouts)
#   biom-electra-large  lr=3e-5 seed=7  (val_f1 0.8931, mean 0.8902 over 2 seeds)
#
# Same 12h wall limit as sweep_10k_timeouts.slurm / sweep_10k_large_5e-5.slurm:
# completed large cells cost 879-940s/epoch regardless of lr, so a full
# un-early-stopped 40-epoch run is bounded at ~10.4h.
#
# Submit only from a clean checkout of experiment/ner-10k-sweep:
#   sbatch slurm/sweep_10k_checkpoints_large.slurm

#SBATCH --partition=akya-cuda
#SBATCH --account=abedir
#SBATCH --job-name=ner-10k-ckpt-large
#SBATCH --output=logs/ner-10k-ckpt-large-%A_%a.out
#SBATCH --error=logs/ner-10k-ckpt-large-%A_%a.err
#SBATCH --array=0-1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=10
#SBATCH --gres=gpu:1
#SBATCH --time=12:00:00

set -euo pipefail

REPO=/arf/scratch/$USER/NER-pipeline
SIF=/arf/home/$USER/container-user/nerenv.sif
RUNS_DIR=runs-truba-checkpoints
DATASET=pathway-10k

# task:    0                    1
MODELS=(biolinkbert-large   biom-electra-large)
LRS=(   3e-5                 3e-5)
SEEDS=( 1                    7)

MODEL=${MODELS[$SLURM_ARRAY_TASK_ID]}
LR=${LRS[$SLURM_ARRAY_TASK_ID]}
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
        --summary "$RUNS_DIR/summary-ckpt-large-${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}.jsonl" \
        --dataset "$DATASET" \
        --models "$MODEL" \
        --lrs "$LR" \
        --seeds "$SEED" \
        --keep-checkpoints
