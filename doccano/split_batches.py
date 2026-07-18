#!/usr/bin/env python3
"""
split_batches.py

Splits the doccano import file (doccano/pilot_1k_doccano.jsonl) into fixed-size
batches, one file per annotator to import locally. Each batch is a verbatim slice of
the source lines, so every batch is a valid doccano import on its own (self-contained
text + nested meta + PATHWAY spans).

Output naming (so we always know which file was split and which slice this is):
    <source-stem>_batch_<NN>_<TOTAL>.jsonl
e.g. pilot_1k_doccano_batch_01_5.jsonl ... _batch_05_5.jsonl

Run from repo root:
    venv310/bin/python3 doccano/split_batches.py                 # 200 per batch
    venv310/bin/python3 doccano/split_batches.py --size 100
"""

import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPORT_FILE = ROOT / "doccano/pilot_1k_doccano.jsonl"
OUT_DIR = ROOT / "doccano/batches"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(IMPORT_FILE))
    ap.add_argument("--size", type=int, default=200, help="documents per batch")
    ap.add_argument("--outdir", default=str(OUT_DIR))
    args = ap.parse_args()

    src = Path(args.input)
    lines = [l for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    total = math.ceil(len(lines) / args.size)
    stem = src.stem  # pilot_1k_doccano

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"Source: {src.name}  ({len(lines)} documents)")
    print(f"Splitting into {total} batches of up to {args.size}\n")

    for i in range(total):
        chunk = lines[i * args.size:(i + 1) * args.size]
        name = f"{stem}_batch_{i + 1:02d}_{total}.jsonl"
        path = outdir / name
        path.write_text("\n".join(chunk) + "\n", encoding="utf-8")
        n_spans = sum(len(json.loads(l)["label"]) for l in chunk)
        print(f"  {name}  —  {len(chunk)} docs, {n_spans} spans")

    print(f"\nWritten to {outdir}/")


if __name__ == "__main__":
    main()
