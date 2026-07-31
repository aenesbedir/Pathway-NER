#!/usr/bin/env python3
"""
aggregate_runs.py — turn a sweep into results a paper can use

Reads `runs/summary.jsonl` and prints, in order: mean ± std per (model, lr); the
learning curve across training-set fractions; the same runs regrouped by
ablation axis; and optionally a paired bootstrap between two configurations.

Why mean ± std
--------------
Measured on the frozen split, the seed band at lr 5e-5 is **±0.0175** — three
seeds of the same recipe gave 0.7947 / 0.8199 / 0.8282. (The ±0.007 quoted in
older notes was measured at lr 3e-5.) Two 5-seed configurations therefore
separate only at ≈0.022 F1; resolving 0.015 needs 11 seeds. Nothing here ever
reports a single run.

Why the learning curve is the headline, not the ranking
-------------------------------------------------------
At 860 training documents the biomedical encoder families are expected to sit
inside each other's noise, and the published evidence agrees: the whole BLURB NER
column spans 0.76 points. Ranking them at this size answers almost nothing. What
does carry information is the *shape* — whether the gaps widen as supervision
grows. That is what predicts the value of wave-3, and it is measurable now, by
running the same grid at 25 / 50 / 75 / 100% of the training set.

Why paired, for the comparisons that are made
---------------------------------------------
The test split is 109 documents, so an unpaired comparison of two confidence
intervals is ~±0.04 wide — useless at this effect size. A paired bootstrap
resamples *documents* and scores both models on the same resample, cancelling the
document-difficulty variance that dominates the unpaired interval.

Examples:
    venv310/bin/python3 scripts/aggregate_runs.py
    venv310/bin/python3 scripts/aggregate_runs.py --by domain objective arch
    venv310/bin/python3 scripts/aggregate_runs.py \\
        --compare biomedbert-base bio-modernbert-base
"""

import argparse
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

DECISION_MARGIN = 0.015


# ---------------------------------------------------------------------------
# Entity-level scoring, from BIO tag sequences
# ---------------------------------------------------------------------------

def entities(tags: list[str]) -> set[tuple[int, int]]:
    """(start, end) token spans. `I` without a preceding `B` opens a span — the
    same lenient decode `playground/golden_set/eval_bert_model.py` uses."""
    spans, start = set(), None
    for i, tag in enumerate(tags):
        if tag == "B-Pathway":
            if start is not None:
                spans.add((start, i))
            start = i
        elif tag == "I-Pathway":
            if start is None:
                start = i
        else:
            if start is not None:
                spans.add((start, i))
            start = None
    if start is not None:
        spans.add((start, len(tags)))
    return spans


def doc_counts(record: dict) -> tuple[int, int, int]:
    """(tp, fp, fn) for one document."""
    gold, pred = entities(record["true"]), entities(record["pred"])
    tp = len(gold & pred)
    return tp, len(pred) - tp, len(gold) - tp


def micro_f1(counts: list[tuple[int, int, int]]) -> float:
    tp = sum(c[0] for c in counts)
    fp = sum(c[1] for c in counts)
    fn = sum(c[2] for c in counts)
    if tp == 0:
        return 0.0
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    return 2 * precision * recall / (precision + recall)


# ---------------------------------------------------------------------------

def load_runs(summary: Path) -> list[dict]:
    if not summary.exists():
        raise SystemExit(f"{summary} not found — run scripts/run_matrix.py first")
    runs = [json.loads(l) for l in summary.open(encoding="utf-8")]
    # A re-run of the same cell appends a second line; the last one wins.
    latest: dict[tuple, dict] = {}
    for r in runs:
        latest[(r["model_key"], r["lr"], r["seed"], r.get("train_fraction", 1.0))] = r
    return list(latest.values())


def table(runs: list[dict]) -> None:
    grouped = defaultdict(list)
    for r in runs:
        if r.get("train_fraction", 1.0) < 1.0:
            continue
        grouped[(r["model_key"], r["lr"])].append(r)

    def stat(values):
        if len(values) == 1:
            return f"{values[0]:.4f}  (1 seed)"
        return f"{statistics.mean(values):.4f} ± {statistics.stdev(values):.4f}"

    print("\n| model | lr | seeds | test F1 | precision | recall | best epoch | n_test |")
    print("|---|---|---|---|---|---|---|---|")
    for (model, lr), group in sorted(grouped.items(),
                                     key=lambda kv: -statistics.mean(
                                         [r["test_f1"] for r in kv[1]])):
        f1s = [r["test_f1"] for r in group]
        ps = [r["test_precision"] for r in group]
        rs = [r["test_recall"] for r in group]
        n_test = sorted({r.get("n_test_effective") for r in group})
        epochs = [r["best_epoch"] for r in group if r.get("best_epoch")]
        print(f"| `{model}` | {lr:g} | {len(group)} | {stat(f1s)} | {stat(ps)} | "
              f"{stat(rs)} | {f'{statistics.mean(epochs):.0f}' if epochs else '-'} | "
              f"{','.join(str(n) for n in n_test)} |")
    print()


def best_of(runs: list[dict], model: str) -> tuple[float, list[dict]]:
    """The (lr, runs) group with the highest mean F1 for one model."""
    grouped = defaultdict(list)
    for r in runs:
        if r["model_key"] == model:
            grouped[r["lr"]].append(r)
    if not grouped:
        raise SystemExit(f"no runs found for model {model!r}")
    lr = max(grouped, key=lambda k: statistics.mean([r["test_f1"] for r in grouped[k]]))
    return lr, grouped[lr]


def paired_bootstrap(runs_a: list[dict], runs_b: list[dict], resamples: int,
                     seed: int = 42) -> None:
    """Bootstrap over documents, scoring both configurations on each resample."""
    def counts_by_pmid(group):
        merged = defaultdict(list)
        for run in group:
            path = Path(run["run_dir"]) / "test_predictions.jsonl"
            if not path.exists():
                raise SystemExit(f"{path} missing — needed for a paired comparison")
            for line in path.open(encoding="utf-8"):
                record = json.loads(line)
                merged[str(record["pmid"])].append(doc_counts(record))
        # Average the per-seed counts so one point per document goes into the
        # bootstrap regardless of how many seeds were run.
        return {pmid: tuple(sum(c[i] for c in cs) / len(cs) for i in range(3))
                for pmid, cs in merged.items()}

    a, b = counts_by_pmid(runs_a), counts_by_pmid(runs_b)
    shared = sorted(set(a) & set(b))
    only_a, only_b = len(set(a) - set(b)), len(set(b) - set(a))
    if not shared:
        raise SystemExit("the two runs share no test documents")

    base_a, base_b = micro_f1([a[p] for p in shared]), micro_f1([b[p] for p in shared])
    rng = random.Random(seed)
    deltas = []
    for _ in range(resamples):
        sample = [shared[rng.randrange(len(shared))] for _ in shared]
        deltas.append(micro_f1([b[p] for p in sample]) - micro_f1([a[p] for p in sample]))
    deltas.sort()

    lo = deltas[int(0.025 * len(deltas))]
    hi = deltas[int(0.975 * len(deltas))]
    above = sum(d > 0 for d in deltas) / len(deltas)
    delta = base_b - base_a

    print(f"  documents scored by both : {len(shared)}"
          f"   (only A: {only_a}, only B: {only_b})")
    print(f"  A micro-F1               : {base_a:.4f}")
    print(f"  B micro-F1               : {base_b:.4f}")
    print(f"  delta (B - A)            : {delta:+.4f}")
    print(f"  95% CI ({resamples} resamples) : [{lo:+.4f}, {hi:+.4f}]")
    print(f"  P(delta > 0)             : {above:.3f}")
    if delta > DECISION_MARGIN and lo > 0:
        print(f"  VERDICT: B wins — beats A by more than {DECISION_MARGIN} "
              f"and the interval excludes zero.")
    elif lo > 0:
        print(f"  VERDICT: B is ahead but by less than the {DECISION_MARGIN} "
              f"decision margin — not worth a swap.")
    else:
        print("  VERDICT: indistinguishable — the interval includes zero.")


def axis_table(runs: list[dict], axis: str) -> None:
    """Group results by an ablation axis instead of by model name.

    A survey that reports "model X scored Y" answers nothing about why. Grouping
    by `domain`, `objective`, `arch` or `params_m` turns the same runs into the
    comparisons the design was built to make — and into the rows a paper needs.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from encoders import resolve

    grouped = defaultdict(list)
    for r in runs:
        if r.get("train_fraction", 1.0) < 1.0:
            continue
        grouped[getattr(resolve(r["model_key"]), axis)].append(r["test_f1"])

    print(f"\n### grouped by `{axis}` (full-data runs only)\n")
    print(f"| {axis} | configs | runs | test F1 |")
    print("|---|---|---|---|")
    for value, f1s in sorted(grouped.items(), key=lambda kv: -statistics.mean(kv[1])):
        spread = f" ± {statistics.stdev(f1s):.4f}" if len(f1s) > 1 else ""
        print(f"| {value} | — | {len(f1s)} | {statistics.mean(f1s):.4f}{spread} |")
    print()


def curve_table(runs: list[dict]) -> None:
    """Learning curve: test F1 per model per training-set fraction.

    This is the measurement the whole survey rests on. At 860 documents the
    encoder families are expected to sit inside each other's noise; the question
    that matters is whether the gaps *widen* with supervision, because that is
    what predicts the value of wave-3 and of every encoder decision after it.
    """
    grouped = defaultdict(list)
    fractions = set()
    for r in runs:
        fraction = r.get("train_fraction", 1.0)
        fractions.add(fraction)
        grouped[(r["model_key"], fraction)].append(r["test_f1"])
    if len(fractions) < 2:
        return

    order = sorted(fractions)
    models = sorted({m for m, _ in grouped})
    print("\n### learning curve — test F1 by training-set fraction\n")
    header = " | ".join(f"{f:g} ({round(f * 860)} docs)" for f in order)
    print(f"| model | {header} |")
    print("|---" * (len(order) + 1) + "|")
    for model in models:
        cells = []
        for fraction in order:
            f1s = grouped.get((model, fraction))
            if not f1s:
                cells.append("—")
            elif len(f1s) == 1:
                cells.append(f"{f1s[0]:.4f}")
            else:
                cells.append(f"{statistics.mean(f1s):.4f} ± {statistics.stdev(f1s):.4f}")
        print(f"| `{model}` | {' | '.join(cells)} |")

    # Spread between the best and worst model at each fraction — the number that
    # answers "do they separate as data grows?"
    print("\n| fraction | models | best − worst |")
    print("|---|---|---|")
    for fraction in order:
        means = [statistics.mean(v) for (m, f), v in grouped.items() if f == fraction]
        if len(means) > 1:
            print(f"| {fraction:g} | {len(means)} | {max(means) - min(means):.4f} |")
    print()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", default="runs/summary.jsonl")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"), default=None,
                    help="Two registry keys; each uses its best-mean lr group")
    ap.add_argument("--by", nargs="*", default=["domain", "objective", "arch"],
                    help="Ablation axes to group by (registry fields)")
    ap.add_argument("--resamples", type=int, default=10000)
    args = ap.parse_args()

    runs = load_runs(Path(args.summary))
    print(f"{len(runs)} runs in {args.summary}")
    table(runs)
    curve_table(runs)
    for axis in args.by:
        axis_table(runs, axis)

    if args.compare:
        name_a, name_b = args.compare
        lr_a, group_a = best_of(runs, name_a)
        lr_b, group_b = best_of(runs, name_b)
        print(f"Paired bootstrap over test documents")
        print(f"  A = {name_a} (lr {lr_a:g}, {len(group_a)} seeds)")
        print(f"  B = {name_b} (lr {lr_b:g}, {len(group_b)} seeds)")
        paired_bootstrap(group_a, group_b, args.resamples)


if __name__ == "__main__":
    main()
