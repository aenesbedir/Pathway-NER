#!/bin/bash
# Build the Apptainer image the sweep runs inside, on TRUBA / ARF.
#
# Run this from an interactive debug allocation, never on arf-ui — compiling and
# installing on the login nodes is against the usage policy. A CPU node is enough;
# nothing here needs a GPU.
#
# Submit from a directory under /arf/scratch. The site's job_submit plugin rejects
# anything launched from /arf/home outright:
#     "Lutfen islerinizi /arf/scratch/ dizini altinda calistiriniz!"
#
#     cd /arf/scratch/$USER
#     srun -p debug -C barbun -N 1 -n 1 -c 20 -A $USER -J build \
#          --time=2:00:00 --pty /usr/bin/bash -i
#     bash /arf/scratch/$USER/NER-pipeline/slurm/build_container.sh
#
# The .sif itself stays in /arf/home: scratch is wiped after 30 days and the image
# is one inode, which is exactly what the inode policy asks for. Only the working
# directory has to be on scratch.
#
# Why a container and not a venv: /arf is a Lustre filesystem with a 500K inode
# quota per user, and site policy forbids conda/pip installs on it — a venv is
# ~100K small files that degrade the shared filesystem. A .sif is one file.
#
# Why cu126 and not the newest wheel: akya-cuda is V100 (sm_70) and barbun-cuda is
# P100 (sm_60). Wheels built against CUDA 12.8 and later dropped those
# architectures — the local machine's torch 2.12.0+cu130 compiles only for
# sm_75 and up, so it would fail on every GPU this cluster has.
#
# Consequence, accepted deliberately: this environment is not the local one, so
# TRUBA numbers are not comparable with runs/summary.jsonl. They are kept apart
# (--runs-dir runs-truba) and each row records its own gpu and library versions.

set -euo pipefail

WORK=/arf/home/$USER/container-user
BASE=/arf/sw/containers/miniconda3/miniconda3-container.sif

mkdir -p "$WORK"
cd "$WORK"

cp -n "$BASE" ./miniconda3-container.sif
# --force so a re-run after a failed install starts from the clean base image
# instead of stopping on the sandbox left behind by the previous attempt.
apptainer build --force --sandbox nerenv miniconda3-container.sif

# Piped through stdin with `bash -s`, not written to a file the container reads:
# under --writable --fakeroot apptainer does not bind the host filesystem, so a
# path under /arf/home does not exist inside the sandbox.
apptainer exec --writable --fakeroot nerenv bash -s <<'EOF'
set -euo pipefail
# --extra-index-url is not optional: the pytorch index does not carry torch's own
# dependencies (typing-extensions and friends), so --index-url alone fails to
# resolve them.
python -m pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cu126 \
    --extra-index-url https://pypi.org/simple \
    "torch==2.8.0"
# Pinned, not floating: an unpinned rebuild three months from now resolves to
# different versions and the TRUBA table stops being reproducible against itself.
# These exact versions were resolved against torch 2.8.0+cu126 and import cleanly
# together, Trainer included.
# numpy is held below 2.0 because the spaCy/scispaCy chain breaks on 2.x, which
# keeps one environment valid for the preprocessing side too.
python -m pip install --no-cache-dir \
    "numpy==1.26.4" \
    "transformers==5.14.1" \
    "datasets==5.0.1" \
    "accelerate==1.14.0" \
    "seqeval==1.2.2"
EOF

apptainer build --force nerenv.sif nerenv

# Cheap check that the pieces agree before a GPU node is ever waited for.
apptainer exec nerenv.sif python -c "
import torch, transformers, datasets, seqeval, numpy
print('torch       :', torch.__version__)
print('transformers:', transformers.__version__)
print('datasets    :', datasets.__version__)
print('numpy       :', numpy.__version__)
"

echo
echo "Built $WORK/nerenv.sif"
echo "Remaining check needs a GPU allocation:"
echo "  apptainer exec --nv $WORK/nerenv.sif python -c \\"
echo "    'import torch; print(torch.cuda.get_arch_list(), torch.cuda.get_device_name(0))'"
