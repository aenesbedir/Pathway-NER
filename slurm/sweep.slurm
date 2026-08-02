#!/bin/bash
# Encoder sweep on TRUBA / ARF, one Slurm job running run_matrix.py sequentially.
#
# Why one job and not a job array: a cell takes ~10 minutes, so a 30-cell grid is
# about 5 hours — well inside the 3-day limit. A single job pays the queue wait
# once instead of thirty times, and every cell lands on the same node, which is
# what keeps the table comparable. An array can scatter cells across node types
# and split one table across two GPUs.
#
# --time is deliberately 8h rather than the 3-day maximum. akya-cuda is saturated
# (all 16 nodes allocated, ~128 pending jobs), and the backfill scheduler can only
# slot a job into a gap it fits in. An honest, short limit starts sooner.
#
# Submit from the repo root with a clean working tree. The repo lives on scratch
# because the site's job_submit plugin refuses jobs launched from /arf/home:
#     cd /arf/scratch/$USER/NER-pipeline
#     git status --porcelain          # must print nothing
#     sbatch slurm/sweep.slurm
#
#SBATCH --partition=akya-cuda
#SBATCH --account=abedir
#SBATCH --job-name=ner-sweep
#SBATCH --output=logs/sweep-%j.out
#SBATCH --error=logs/sweep-%j.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=10
#SBATCH --gres=gpu:1
#SBATCH --time=08:00:00

set -euo pipefail

REPO=/arf/scratch/$USER/NER-pipeline
SIF=/arf/home/$USER/container-user/nerenv.sif

cd "$REPO"
mkdir -p logs

# The summary row is only evidence if the tree that produced it is the tree the
# sha names. See CLAUDE.md.
if [ -n "$(git status --porcelain train.py encoders.py preprocessing scripts)" ]; then
    echo "FATAL: pipeline files are dirty — commit before recording runs" >&2
    exit 1
fi

# Model weights are fetched on the login node ahead of time; compute nodes have
# no route to huggingface.co, and without OFFLINE the first from_pretrained call
# hangs until it times out instead of using the cache it already has.
export HF_HOME=/arf/scratch/$USER/hf
export HF_HUB_OFFLINE=1
export TMPDIR=/tmp/$SLURM_JOB_ID
mkdir -p "$TMPDIR"

# Inside the container `python3` is the container's interpreter, not venv310's.
export NER_PYTHON=python3

nvidia-smi

apptainer exec --nv \
    --bind /arf/scratch/$USER:/arf/scratch/$USER \
    "$SIF" \
    python3 scripts/run_matrix.py \
        --runs-dir runs-truba \
        --models biomedbert-base bioelectra-base biolinkbert-base \
        --lrs 5e-5 \
        --seeds 42 1 7 13 21
