#!/bin/bash
# Rerun the 6 large-model cells lost to the 8h wall limit in sweep_10k_large.slurm
# (job 6240152, tasks 2, 4, 6, 8, 12, 15). Each of these hit exactly 8:00:0x and
# was TIMEOUT-killed before test_results.json was written — no summary line, no
# partial credit, just a dead run.
#
# Why 12h and not a bigger bump: run_matrix.py's RECIPE fixes --epochs 40
# --patience 8. Every one of the 12 large cells that *did* finish in the original
# sweep took 879-940s per epoch regardless of model or lr, and none needed more
# than 31 epochs to trigger patience. A full un-early-stopped 40-epoch run is
# therefore bounded above by 40 * 940s = 10.4h; +25min of container/model/dataset
# load and final test-set eval leaves ~11h. 12h covers the worst case with margin
# and stays inside akya-cuda's 3-day MaxTime without asking for it.
#
# These 6 cells are not a cartesian product (different model/lr/seed per
# timed-out task), so they're listed explicitly by index rather than computed
# from nested loop counters.
#
# Submit only from a clean checkout of experiment/ner-10k-sweep:
#   sbatch slurm/sweep_10k_timeouts.slurm

#SBATCH --partition=akya-cuda
#SBATCH --account=abedir
#SBATCH --job-name=ner-10k-timeouts
#SBATCH --output=logs/ner-10k-timeouts-%A_%a.out
#SBATCH --error=logs/ner-10k-timeouts-%A_%a.err
#SBATCH --array=0-5
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=10
#SBATCH --gres=gpu:1
#SBATCH --time=12:00:00

set -euo pipefail

REPO=/arf/scratch/$USER/NER-pipeline
SIF=/arf/home/$USER/container-user/nerenv.sif
RUNS_DIR=runs-truba-timeouts
DATASET=pathway-10k

# task:      0                   1                   2                   3                   4                    5
MODELS=(biolinkbert-large  biolinkbert-large   biolinkbert-large   biolinkbert-large   biom-electra-large   biom-electra-large)
LRS=(   1e-5               2e-5                3e-5                3e-5                2e-5                 3e-5)
SEEDS=( 7                  1                   42                  7                   42                   7)

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
        --summary "$RUNS_DIR/summary-timeouts-${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}.jsonl" \
        --dataset "$DATASET" \
        --models "$MODEL" \
        --lrs "$LR" \
        --seeds "$SEED"
