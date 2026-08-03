#!/usr/bin/env python3
"""
run_matrix.py — sweep model x learning rate x training-set fraction x seed

Runs `train.py` over the cartesian product and collects one line per run into
`runs/summary.jsonl`, which `scripts/aggregate_runs.py` reads.

Why a sweep and not single runs
-------------------------------
Measured on the frozen split, the seed band at lr 5e-5 is **±0.0175** — the same
recipe gave 0.7947 / 0.8199 / 0.8282 across three seeds. Published evidence puts
an encoder swap at +0.005 to +0.02, i.e. inside that band. A single-seed
comparison here is not weak evidence, it is no evidence.

Why fractions
-------------
Ranking encoders on 860 documents is close to unanswerable, and answering it
would not generalise anyway. The measurement that survives is the *slope*: run
the same grid at 25 / 50 / 75 / 100% of the training set and watch whether the
models spread apart. Subsets are nested and identical across models, so
successive points add documents rather than resampling them.

Runs are sequential — a 4060 fits one job — and resumable: a cell whose
`test_results.json` already exists is skipped, so an interrupted sweep continues
where it stopped, and a grid can be widened later without recomputing it.

Examples:
    # what would run, without running it
    venv310/bin/python3 scripts/run_matrix.py --models biomedbert-base --dry-run

    # domain axis: does biomedical pretraining matter, and how does that change
    # with supervision?
    venv310/bin/python3 scripts/run_matrix.py \\
        --models bert-base scibert biomedbert-base bio-clinicalbert \\
        --lrs 5e-5 --train-fractions 0.25 0.5 1.0 --seeds 42 1 7

    # objective axis at fixed size, corpus and vocabulary
    venv310/bin/python3 scripts/run_matrix.py \\
        --models biomedbert-base bioelectra-base biolinkbert-base \\
        --lrs 5e-5 --seeds 42 1 7 13 21
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from encoders import resolve  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# The interpreter each cell runs under. `venv310` is this machine's; on a cluster
# the environment lives in a container and the path comes from the job script, so
# it is overridable rather than assumed.
PYTHON = os.environ.get("NER_PYTHON", str(ROOT / "venv310" / "bin" / "python3"))

# The gold-004+ recipe. Changing these changes what the sweep measures, so they
# are explicit rather than inherited from train.py's defaults.
RECIPE = ["--class-weights", "0.5", "1.5", "1.0",
          "--epochs", "40", "--patience", "8", "--frozen-layers", "0"]


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True,
                    help="Registry keys (see `python3 encoders.py`)")
    ap.add_argument("--lrs", nargs="+", type=float, default=None,
                    help="Learning rates (default: each model's registry lr_grid)")
    ap.add_argument("--seeds", nargs="+", type=int, default=[42, 1, 7, 13, 21])
    ap.add_argument("--train-fractions", nargs="+", type=float, default=[1.0],
                    help="Fractions of the training set to sweep, e.g. 0.25 0.5 "
                         "0.75 1.0 for a learning curve. Subsets are nested and "
                         "identical across models")
    ap.add_argument("--dataset", default="gold",
                    help="Corpus root under data/processed. `gold` is the 860-doc "
                         "Phase 4b set; `gold-wave4` is the 2664-doc expansion "
                         "sharing its validation and test PMIDs. Each model reads "
                         "<dataset>-<slug>/ and every model in one sweep reads the "
                         "same split file")
    ap.add_argument("--runs-dir", default="runs")
    ap.add_argument("--summary", default=None,
                    help="Default: <runs-dir>/summary.jsonl")
    ap.add_argument("--keep-checkpoints", action="store_true",
                    help="Keep fine-tuned weights (~0.5-1.6 GB per run)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    runs_dir = Path(args.runs_dir)
    summary_path = Path(args.summary) if args.summary else runs_dir / "summary.jsonl"
    sha = git_sha()

    cells = []
    for model in args.models:
        spec = resolve(model)
        for lr in (args.lrs if args.lrs is not None else spec.lr_grid):
            for fraction in args.train_fractions:
                for seed in args.seeds:
                    cells.append((model, spec, lr, seed, fraction))

    print(f"{len(cells)} cells: {len(args.models)} models x lrs x "
          f"{len(args.train_fractions)} fractions x {len(args.seeds)} seeds")

    done = failed = skipped = 0
    for i, (model, spec, lr, seed, fraction) in enumerate(cells, 1):
        # Full-data runs keep the original path so earlier sweeps stay resumable.
        frac_dir = "" if fraction >= 1.0 else f"frac{fraction:g}/"
        # `gold` keeps the original layout for the same reason; a corpus change is
        # not comparable with what sits next to it, so it gets its own subtree
        # rather than overwriting a cell that answers a different question.
        data_dir_prefix = "" if args.dataset == "gold" else f"{args.dataset}/"
        out = runs_dir / f"{data_dir_prefix}{model}" / f"lr{lr:g}" / f"{frac_dir}seed{seed}"
        results_path = out / "test_results.json"

        data_dir = Path("data/processed") / f"{args.dataset}-{spec.data_slug}"
        splits = Path("data/processed") / args.dataset / "splits.json"

        cmd = [PYTHON, "train.py", "--model", model, "--output-dir", str(out),
               "--data-dir", str(data_dir), "--splits", str(splits),
               "--lr", f"{lr:g}", "--seed", str(seed), *RECIPE]
        if fraction < 1.0:
            cmd += ["--train-fraction", f"{fraction:g}"]
        if not args.keep_checkpoints:
            cmd.append("--no-save-model")

        if args.dry_run:
            print(f"[{i}/{len(cells)}] {' '.join(cmd)}")
            continue

        if results_path.exists():
            print(f"[{i}/{len(cells)}] skip (already done) {out}")
            skipped += 1
            continue

        label = f"{model} lr={lr:g} seed={seed}" + (f" frac={fraction:g}" if fraction < 1.0 else "")
        print(f"[{i}/{len(cells)}] {label} …", flush=True)
        out.mkdir(parents=True, exist_ok=True)

        # An interrupted cell leaves the epoch checkpoints `load_best_model_at_end`
        # needs — 1.3 GB each, two of them, and worthless because this cell is
        # about to restart from scratch. train.py clears them on a clean finish;
        # this clears them after a kill.
        for stale in out.glob("checkpoint-*"):
            shutil.rmtree(stale, ignore_errors=True)
        started = time.time()
        with (out / "train.log").open("w", encoding="utf-8") as logfile:
            proc = subprocess.run(cmd, cwd=ROOT, stdout=logfile,
                                  stderr=subprocess.STDOUT)

        if proc.returncode != 0 or not results_path.exists():
            print(f"    FAILED (exit {proc.returncode}) — see {out}/train.log")
            failed += 1
            continue

        results = json.loads(results_path.read_text(encoding="utf-8"))
        results["git_sha"] = sha
        results["wall_s"] = round(time.time() - started, 1)
        results["run_dir"] = str(out)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(results) + "\n")
        print(f"    F1 {results.get('test_f1', 0):.4f}  "
              f"P {results.get('test_precision', 0):.4f}  "
              f"R {results.get('test_recall', 0):.4f}  "
              f"({results['wall_s']:.0f}s)")
        done += 1

    if not args.dry_run:
        print(f"\ndone {done}   skipped {skipped}   failed {failed}")
        print(f"summary: {summary_path}")
        if failed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
