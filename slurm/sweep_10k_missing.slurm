#!/bin/bash
# Merged 10k + missing-pathway sweep: three models x two learning rates x three
# seeds, one independent array task per cell. Each model keeps the best cell of
# the pathway-10k sweep plus one neighbouring learning rate, so the corpus is the
# only changed variable against the earlier results. The rates differ per model
# because 5e-5 is outside biom-electra-large's documented lr_grid in encoders.py
# and would not be a comparable cell.
#
#   sbatch slurm/sweep_10k_missing.slurm

#SBATCH --partition=akya-cuda
#SBATCH --account=abedir
#SBATCH --job-name=ner-10k-missing
#SBATCH --output=logs/ner-10k-missing-%A_%a.out
#SBATCH --error=logs/ner-10k-missing-%A_%a.err
#SBATCH --array=0-17
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=10
#SBATCH --gres=gpu:1
#SBATCH --time=08:00:00

set -euo pipefail

REPO=/arf/scratch/$USER/NER-pipeline
SIF=/arf/home/$USER/container-user/nerenv.sif
RUNS_DIR=runs-truba-10k-missing
DATASET=pathway-10k-missing

MODELS=(biom-electra-large bioelectra-base biomedbert-base)
# best pathway-10k lr first, neighbour second
LRS_biom_electra_large="2e-5 3e-5"
LRS_bioelectra_base="3e-5 5e-5"
LRS_biomedbert_base="3e-5 5e-5"
SEEDS=(42 1 7)

N_LRS=2
CELLS_PER_MODEL=$((N_LRS * ${#SEEDS[@]}))
MODEL_INDEX=$((SLURM_ARRAY_TASK_ID / CELLS_PER_MODEL))
WITHIN_MODEL=$((SLURM_ARRAY_TASK_ID % CELLS_PER_MODEL))
LR_INDEX=$((WITHIN_MODEL / ${#SEEDS[@]}))
SEED_INDEX=$((WITHIN_MODEL % ${#SEEDS[@]}))
MODEL=${MODELS[$MODEL_INDEX]}
LRS_VAR="LRS_${MODEL//-/_}"
read -r -a LRS <<< "${!LRS_VAR}"
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
        --summary "$RUNS_DIR/summary-${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}.jsonl" \
        --dataset "$DATASET" \
        --models "$MODEL" \
        --lrs "$LR" \
        --seeds "$SEED"
