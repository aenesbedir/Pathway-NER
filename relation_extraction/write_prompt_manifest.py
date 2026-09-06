#!/usr/bin/env python3
"""
write_prompt_manifest.py

Record, next to a teacher output, the exact question that produced it.

`run_teacher.py` already writes a run summary carrying `prompt_fingerprint`,
`raw_flags` and `residual_context`. A fingerprint identifies a prompt only to
someone holding the code that generated it, and `prompts.py` changes between
runs. This manifest stores the prompt *text* - system prompt and mode guide,
verbatim - so a labelled file can be read years later without checking out the
commit that made it.

The manifest is written from the same modules `run_teacher.py` imports, so a
mismatch between the recorded text and the run is possible if the file is
generated after `prompts.py` changes. Guarding against that is the point of also
recording the fingerprint and the git sha: if the fingerprint here differs from
the one in the run summary, the manifest was written against different code and
should not be trusted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import prompts
from run_teacher import RAW_FLAGS, RESIDUAL_CONTEXT, prompt_fingerprint

GUIDES = {
    "batch": "GUIDE",
    "single": "GUIDE_SINGLE",
    "grouped": "GUIDE_GROUPED",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_sha() -> str:
    """HEAD, marked `+dirty` when the labelling code is not committed.

    Both commands run from the repository root: `git status --porcelain <path>`
    resolves its pathspec against the working directory, so running it from
    inside `relation_extraction/` matches nothing and reports a clean tree for a
    directory full of uncommitted work.
    """
    root = Path(__file__).resolve().parents[1]
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "relation_extraction"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return head + ("+dirty" if dirty else "")
    except Exception:  # noqa: BLE001 - provenance is best-effort, never fatal
        return "unknown"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", type=Path, required=True, help="teacher output being described")
    ap.add_argument("--candidates", type=Path, required=True)
    ap.add_argument("--mode", choices=tuple(GUIDES), required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--source", type=Path, default=None,
                    help="file the candidates were derived from, if any")
    ap.add_argument("--note", default="")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    guide_name = GUIDES[args.mode]
    guide_text = getattr(prompts, guide_name)

    manifest = {
        "labels": str(args.labels),
        "labels_sha256": sha256(args.labels),
        "candidates": str(args.candidates),
        "candidates_sha256": sha256(args.candidates),
        "source": str(args.source) if args.source else None,
        "source_sha256": sha256(args.source) if args.source else None,
        "schema_version": prompts.__dict__.get("SCHEMA_TAG", "see schema.py"),
        "model": args.model,
        "mode": args.mode,
        "prompt_fingerprint": prompt_fingerprint(args.mode),
        "guide_name": guide_name,
        "system_prompt": prompts.SYSTEM,
        "guide_text": guide_text,
        "raw_flags": RAW_FLAGS,
        "residual_context": RESIDUAL_CONTEXT,
        "git_sha": git_sha(),
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": args.note,
    }

    out = args.out or args.labels.with_suffix(".manifest.json")
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out}")
    print(f"  fingerprint {manifest['prompt_fingerprint']}  guide {guide_name} "
          f"({len(guide_text)} chars)  git {manifest['git_sha']}")


if __name__ == "__main__":
    main()
