#!/bin/bash
# 10k + missing corpus with the sentence-shuffle copies added to train:
# biomedbert-base at 3e-5, seed 42, with the full 40-epoch recipe of the
# pathway-10k-missing baseline, split into two jobs because one 40-epoch job did
# not get scheduled.
#
# PART=1 trains epochs 1-20 and stops after saving the epoch-20 checkpoint
# (run_matrix.py --stop-after-epoch 20). PART=2 resumes from it (--resume) with
# the optimizer, learning-rate schedule, RNG and early-stopping state, so the
# two parts are one 40-epoch run, not two 20-epoch runs. Both parts must run on
# the same commit; run_matrix.py refuses a resume otherwise, so do not pull
# between them. The final model is kept (--keep-checkpoints).
#
# A V100 epoch on this train set took about 15 minutes in the 20-epoch runs
# (job 6901057: about 5.0 h for 20 epochs).
#
# Submit both parts at once; the second starts only if the first succeeds:
#
#   j1=$(sbatch --parsable --export=ALL,PART=1 slurm/sweep_10k_missing_shuffle_e40_parts.slurm)
#   sbatch --dependency=afterok:$j1 --export=ALL,PART=2 slurm/sweep_10k_missing_shuffle_e40_parts.slurm

#SBATCH --partition=akya-cuda
#SBATCH --account=abedir
#SBATCH --job-name=ner-10k-shuf-e40
#SBATCH --output=logs/ner-10k-shuf-e40-%j.out
#SBATCH --error=logs/ner-10k-shuf-e40-%j.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=10
#SBATCH --gres=gpu:1
#SBATCH --time=06:30:00

set -euo pipefail

REPO=/arf/scratch/$USER/NER-pipeline
SIF=/arf/home/$USER/container-user/nerenv.sif
DATASET=${DATASET:-pathway-10k-missing-shuffle}
RUNS_DIR=runs-truba-${DATASET#pathway-}-e40

MODEL=biomedbert-base
LR=3e-5
EPOCHS=40
STOP_AFTER=20
SEED=42
: "${PART:?set PART=1 or PART=2}"

case "$PART" in
    1) PART_ARGS=(--stop-after-epoch "$STOP_AFTER") ;;
    2) PART_ARGS=(--resume) ;;
    *) echo "FATAL: PART must be 1 or 2, not $PART" >&2; exit 1 ;;
esac

cd "$REPO"
mkdir -p logs

if [ -n "$(git status --porcelain train.py encoders.py preprocessing scripts slurm)" ]; then
    echo "FATAL: experiment files are dirty — commit before recording runs" >&2
    exit 1
fi

for required in \
    "data/processed/$DATASET/splits.json" \
    "data/processed/$DATASET/manifest.json" \
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

echo "part $PART -> $MODEL lr=$LR seed=$SEED epochs=$EPOCHS on $(hostname), commit $(git rev-parse --short HEAD)"
nvidia-smi

apptainer exec --nv \
    --bind /arf/scratch/$USER:/arf/scratch/$USER \
    "$SIF" \
    python3 scripts/run_matrix.py \
        --runs-dir "$RUNS_DIR" \
        --summary "$RUNS_DIR/summary.jsonl" \
        --dataset "$DATASET" \
        --models "$MODEL" \
        --lrs "$LR" \
        --seeds "$SEED" \
        --epochs "$EPOCHS" \
        --keep-checkpoints \
        "${PART_ARGS[@]}"
