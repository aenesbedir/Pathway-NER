#!/bin/bash
# Keep weights for the three best configurations of the merged 10k +
# missing-pathway sweep, so later experiments (latency, representation analysis,
# further fine-tuning) have something to load. The sweep itself ran with
# --no-save-model, which is why these have to be retrained.
#
# The seed is fixed at 42 across all three rather than taking each
# configuration's best seed: the seed spread on gt_100 is 0.033, wider than the
# differences being compared, so picking the best seed per configuration would
# select on the evaluation set and make the checkpoint's gt_100 score an
# optimistic estimate rather than an honest one.
#
#   sbatch slurm/checkpoints_10k_missing.slurm

#SBATCH --partition=akya-cuda
#SBATCH --account=abedir
#SBATCH --job-name=ner-10k-missing-ckpt
#SBATCH --output=logs/ner-10k-missing-ckpt-%A_%a.out
#SBATCH --error=logs/ner-10k-missing-ckpt-%A_%a.err
#SBATCH --array=0-2
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=10
#SBATCH --gres=gpu:1
#SBATCH --time=08:00:00

set -euo pipefail

REPO=/arf/scratch/$USER/NER-pipeline
SIF=/arf/home/$USER/container-user/nerenv.sif
RUNS_DIR=runs-truba-10k-missing-checkpoints
DATASET=pathway-10k-missing

# gt_100 exact-F1 mean over three seeds picked these three cells
MODELS=(biom-electra-large biom-electra-large bioelectra-base)
LRS=(2e-5 3e-5 3e-5)
SEED=42

MODEL=${MODELS[$SLURM_ARRAY_TASK_ID]}
LR=${LRS[$SLURM_ARRAY_TASK_ID]}

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
        --seeds "$SEED" \
        --keep-checkpoints
