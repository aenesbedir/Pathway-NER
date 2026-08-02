#!/bin/bash
# Populate the HuggingFace cache on TRUBA before any job is submitted.
#
# Run on arf-ui (the login node), which has outbound internet — verified with
# `curl -sI https://huggingface.co` returning HTTP/2 200. Compute nodes do not,
# so a from_pretrained call there can only succeed from this cache. Downloading
# is I/O, not compute, so it does not violate the "no heavy work on arf-ui" rule.
#
#     bash /arf/scratch/$USER/NER-pipeline/slurm/prefetch_models.sh biomedbert-base bioelectra-base
#
# The cache lives on scratch because it is large and regenerable. Scratch is
# wiped after 30 days; re-running this script restores it.

set -euo pipefail

REPO=/arf/scratch/$USER/NER-pipeline
SIF=/arf/home/$USER/container-user/nerenv.sif

export HF_HOME=/arf/scratch/$USER/hf
mkdir -p "$HF_HOME"

cd "$REPO"

apptainer exec --bind /arf/scratch/$USER:/arf/scratch/$USER "$SIF" \
    python3 - "$@" <<'EOF'
import sys
from transformers import AutoModelForTokenClassification

sys.path.insert(0, ".")
from encoders import resolve

for key in sys.argv[1:]:
    spec = resolve(key)
    print(f"--- {key} -> {spec.hf_id}", flush=True)
    # Through spec.tokenizer(), not AutoTokenizer directly: the tokenizer id can
    # differ from the model id and some repos need tokenizer_kwargs, and
    # encoders.py is the one place that knows both.
    spec.tokenizer()
    AutoModelForTokenClassification.from_pretrained(spec.hf_id, num_labels=3)
print("cache ready:", __import__("os").environ["HF_HOME"])
EOF
