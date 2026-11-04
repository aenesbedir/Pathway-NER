"""Record which sentence-shuffle version a pathway-10k-missing-shuffle corpus holds.

The corpus directory (articles.jsonl, matches.jsonl, splits.json) is built by
scripts/prepare_pathway_10k_missing_shuffle.sh from the base doccano export and
one sentence-shuffle output. This script writes <corpus>/manifest.json linking
the two: the shuffle version, its file and manifest with their sha256, the base
source, and the sha256 of every corpus file. Training runs record the hashes of
matches.jsonl and articles.jsonl (dataset_*_sha256 in test_results.json), so a
run is tied to a shuffle version through this file.

    write   build the manifest for a freshly built corpus
    check   exit non-zero unless <corpus>/manifest.json names this shuffle file

Usage:
    python scripts/shuffle_corpus_manifest.py write \
        --corpus data/processed/pathway-10k-missing-shuffle-v2 \
        --shuffle data/processed/10k-missing-shuffle/v2/sentence_shuffle.jsonl \
        --base-source data/doccano/pathway_10k_plus_missing.jsonl
    python scripts/shuffle_corpus_manifest.py check \
        --corpus data/processed/pathway-10k-missing-shuffle-v2 \
        --shuffle data/processed/10k-missing-shuffle/v2/sentence_shuffle.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
#: k2_n2_seed42/ predates numbered versions; it is version 1.
LEGACY = {"k2_n2_seed42": 1}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path) -> str:
    """Repository-relative when run from a repository root, as the prepare script does."""
    path, cwd = path.absolute(), Path.cwd().absolute()
    return str(path.relative_to(cwd)) if path.is_relative_to(cwd) else str(path)


def version_of(shuffle: Path) -> int:
    name = shuffle.resolve().parent.name
    if name in LEGACY:
        return LEGACY[name]
    if name.startswith("v") and name[1:].isdigit():
        return int(name[1:])
    raise SystemExit(f"{shuffle}: parent directory {name!r} is not a shuffle version (v<N>)")


def write(args) -> None:
    corpus, shuffle = args.corpus, args.shuffle
    shuffle_manifest = shuffle.with_name("sentence_shuffle.manifest.json")
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    manifest = {
        "corpus": rel(corpus),
        "shuffle_version": version_of(shuffle),
        "shuffle": rel(shuffle),
        "shuffle_sha256": sha256(shuffle),
        "shuffle_manifest": rel(shuffle_manifest),
        "shuffle_manifest_sha256": sha256(shuffle_manifest) if shuffle_manifest.exists() else None,
        "base_source": rel(args.base_source),
        "base_source_sha256": sha256(args.base_source),
        "files": {name: sha256(corpus / name) for name in ("articles.jsonl", "matches.jsonl", "splits.json")},
        "git_sha": head,
        "written_on": date.today().isoformat(),
    }
    if args.note:
        manifest["note"] = args.note
    (corpus / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


def check(args) -> None:
    path = args.corpus / "manifest.json"
    if not path.exists():
        sys.exit(f"{path} is missing: cannot tell which shuffle version {args.corpus} holds")
    manifest = json.loads(path.read_text())
    if manifest["shuffle_sha256"] != sha256(args.shuffle):
        sys.exit(f"{args.corpus} holds shuffle {manifest['shuffle']} "
                 f"(v{manifest['shuffle_version']}), not {args.shuffle}")
    for name, digest in manifest["files"].items():
        if sha256(args.corpus / name) != digest:
            sys.exit(f"{args.corpus / name} changed since its manifest was written")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["write", "check"])
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--shuffle", type=Path, required=True)
    ap.add_argument("--base-source", type=Path, default=ROOT / "data/doccano/pathway_10k_plus_missing.jsonl")
    ap.add_argument("--note", default="")
    args = ap.parse_args()
    (write if args.mode == "write" else check)(args)


if __name__ == "__main__":
    main()
