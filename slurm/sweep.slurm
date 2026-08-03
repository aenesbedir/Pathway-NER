#!/bin/bash
# Encoder sweep on TRUBA / ARF as a job array: one array task per model, each
# running run_matrix.py over that model's seeds.
#
# Why an array and not one long job. akya-cuda is saturated — all 16 nodes
# allocated, ~128 pending — so a submitted job waits on priority, not resources.
# Slurm fills the gaps left by large jobs with small ones that fit, and a 4h task
# fits gaps a 12h job never will. Measured: the single 12h job queued at 26 hours.
#
# What makes splitting safe here is that the partition is fixed. Every akya node
# is the same 4x V100, so scattering tasks across nodes does not scatter the table
# across hardware. Splitting across *partitions* would, which is why the sweep
# never spans akya-cuda and barbun-cuda.
#
# Each task writes its own summary file. run_matrix.py appends a line per cell,
# and concurrent appends to one file on Lustre are not guaranteed atomic — an
# interleaved write would leave a corrupt JSON line that stops aggregate_runs.py.
# Merge them once the array finishes:
#
#     cat runs-truba/summary-*.jsonl > runs-truba/summary.jsonl
#     venv310/bin/python3 scripts/aggregate_runs.py --summary runs-truba/summary.jsonl
#
# 4h per task: a gold cell averages 449 s on the 4060 and wave4 trains on 2659
# documents instead of 860, so a cell is ~23 minutes and five seeds ~2 hours. A
# task that hits the wall is resumable — run_matrix.py skips cells whose
# test_results.json exists, so re-submitting continues where it stopped.
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
#SBATCH --output=logs/sweep-%A_%a.out
#SBATCH --error=logs/sweep-%A_%a.err
#SBATCH --array=0-2
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=10
#SBATCH --gres=gpu:1
#SBATCH --time=04:00:00

set -euo pipefail

REPO=/arf/scratch/$USER/NER-pipeline
SIF=/arf/home/$USER/container-user/nerenv.sif

MODELS=(biomedbert-base bioelectra-base biolinkbert-base)
MODEL=${MODELS[$SLURM_ARRAY_TASK_ID]}

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

echo "task $SLURM_ARRAY_TASK_ID -> $MODEL on $(hostname)"
nvidia-smi

apptainer exec --nv \
    --bind /arf/scratch/$USER:/arf/scratch/$USER \
    "$SIF" \
    python3 scripts/run_matrix.py \
        --runs-dir runs-truba \
        --summary "runs-truba/summary-${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}.jsonl" \
        --dataset gold-wave4 \
        --models "$MODEL" \
        --lrs 5e-5 \
        --seeds 42 1 7 13 21
