#!/bin/bash
# Retrain the single best (lr, seed) cell for each base model with weights kept,
# so the deployable checkpoints exist on disk to rsync back — the original
# sweep_10k_base.slurm ran every cell with run_matrix.py's default
# --no-save-model (a checkpoint is 0.5-1.6 GB; the full model x lr x seed matrix
# would not fit), so no base-model weights survived that sweep.
#
# "Best" here means: this model's only swept lr (base models were not lr-swept
# beyond their registry default), and within that lr the seed with the highest
# best_val_f1 from the original completed runs in runs-truba-10k:
#   biomedbert-base   lr=5e-5 seed=1  (val_f1 0.8909)
#   biolinkbert-base  lr=5e-5 seed=7  (val_f1 0.8875)
#   bioelectra-base   lr=3e-5 seed=7  (val_f1 0.8906)
#
# Uses a separate --runs-dir so run_matrix.py's test_results.json-exists skip
# doesn't short-circuit a cell that already "completed" in runs-truba-10k —
# what's missing here is the weights, not the metrics.
#
# Submit only from a clean checkout of experiment/ner-10k-sweep:
#   sbatch slurm/sweep_10k_checkpoints_base.slurm

#SBATCH --partition=akya-cuda
#SBATCH --account=abedir
#SBATCH --job-name=ner-10k-ckpt-base
#SBATCH --output=logs/ner-10k-ckpt-base-%A_%a.out
#SBATCH --error=logs/ner-10k-ckpt-base-%A_%a.err
#SBATCH --array=0-2
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=10
#SBATCH --gres=gpu:1
#SBATCH --time=04:00:00

set -euo pipefail

REPO=/arf/scratch/$USER/NER-pipeline
SIF=/arf/home/$USER/container-user/nerenv.sif
RUNS_DIR=runs-truba-checkpoints
DATASET=pathway-10k

# task:    0                  1                   2
MODELS=(biomedbert-base   biolinkbert-base    bioelectra-base)
LRS=(   5e-5               5e-5                3e-5)
SEEDS=( 1                  7                   7)

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
        --summary "$RUNS_DIR/summary-ckpt-base-${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}.jsonl" \
        --dataset "$DATASET" \
        --models "$MODEL" \
        --lrs "$LR" \
        --seeds "$SEED" \
        --keep-checkpoints
