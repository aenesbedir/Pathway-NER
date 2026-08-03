#!/bin/bash
# Prove the HuggingFace cache is complete before a job waits in the queue for it.
#
# Loads each model the way a compute node will: from inside the container, with
# HF_HUB_OFFLINE=1 so the hub is unreachable by construction. A model that only
# appears to be cached — config present, weights missing, or a revision the
# offline resolver cannot match — fails here in seconds instead of after hours of
# queue time.
#
#     cd /arf/scratch/$USER/NER-pipeline
#     bash slurm/verify_cache.sh biomedbert-base bioelectra-base biolinkbert-base
#
# No GPU and no allocation needed: this is a disk read, not training.

set -euo pipefail

REPO=/arf/scratch/$USER/NER-pipeline
SIF=/arf/home/$USER/container-user/nerenv.sif

export HF_HOME=/arf/scratch/$USER/hf
export HF_HUB_OFFLINE=1

cd "$REPO"

apptainer exec --bind /arf/scratch/$USER:/arf/scratch/$USER "$SIF" \
    python3 - "$@" <<'EOF'
import sys

sys.path.insert(0, ".")
from transformers import AutoModelForTokenClassification

from encoders import resolve

failed = []
for key in sys.argv[1:]:
    spec = resolve(key)
    try:
        spec.load_tokenizer()
        AutoModelForTokenClassification.from_pretrained(spec.hf_id, num_labels=3)
        print(f"OK      {key}  ({spec.hf_id})")
    except Exception as exc:
        failed.append(key)
        print(f"MISSING {key}  ({spec.hf_id})\n        {type(exc).__name__}: {exc}")

if failed:
    print("\nrun slurm/prefetch_models.sh for:", " ".join(failed))
    sys.exit(1)
print("\nall models load offline")
EOF
