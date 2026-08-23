#!/usr/bin/env python3
"""
agreement.py

Compare two relation files over the pairs they both cover.

Used for three different questions that all reduce to the same computation:

- teacher versus a manual pass, to see whether an LLM can be trusted to label at
  scale (`--a` manual, `--b` teacher);
- teacher versus teacher, to choose between models or prompt versions;
- model predictions versus gold, once a locked gold set exists.

Pairing
-------
Records are matched on `candidate_id` when both files carry one, and otherwise on
`(pmid, pathway span, disease span)`. A looser fallback on `(pmid, pathway span)`
is reported separately, because two annotators frequently pick different disease
mentions of the same disease in one abstract; counting those as non-overlapping
would understate agreement, and silently merging them would overstate it.

Reported numbers
----------------
Raw agreement, Cohen's kappa, the full confusion matrix, and per-label precision
and recall treating file `--a` as the reference. Kappa is reported for the label
field only; with six classes and a few hundred shared pairs the per-class counts
are too small for anything finer, and a single number over an unbalanced set
would hide exactly the classes worth arguing about.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from schema import read_jsonl


def key_strict(r: dict):
    if r.get("candidate_id"):
        return ("cid", r["candidate_id"])
    return (
        "span",
        str(r["pmid"]),
        r["pathway"]["start"],
        r["pathway"]["end"],
        r["disease"]["start"],
        r["disease"]["end"],
    )


def key_loose(r: dict):
    return (str(r["pmid"]), r["pathway"]["start"], r["pathway"]["end"])


def kappa(pairs: list[tuple[str, str]]) -> float:
    if not pairs:
        return float("nan")
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    a_counts = Counter(a for a, _ in pairs)
    b_counts = Counter(b for _, b in pairs)
    expected = sum(
        (a_counts[l] / n) * (b_counts[l] / n) for l in set(a_counts) | set(b_counts)
    )
    if expected >= 1.0:
        return float("nan")
    return (observed - expected) / (1 - expected)


def confusion(pairs, labels):
    m = defaultdict(Counter)
    for a, b in pairs:
        m[a][b] += 1
    lines = ["| a \\ b | " + " | ".join(labels) + " |", "|---" * (len(labels) + 1) + "|"]
    for a in labels:
        lines.append(f"| {a} | " + " | ".join(str(m[a][b]) for b in labels) + " |")
    return "\n".join(lines)


def prf(pairs, label):
    tp = sum(1 for a, b in pairs if a == label and b == label)
    fp = sum(1 for a, b in pairs if a != label and b == label)
    fn = sum(1 for a, b in pairs if a == label and b != label)
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    f = 2 * p * r / (p + r) if p == p and r == r and p + r else float("nan")
    return tp, fp, fn, p, r, f


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a", type=Path, required=True, help="reference file")
    ap.add_argument("--b", type=Path, required=True, help="file under comparison")
    ap.add_argument("--a-name", default="a")
    ap.add_argument("--b-name", default="b")
    ap.add_argument(
        "--map",
        action="append",
        default=[],
        help="rewrite a label before comparing, e.g. --map upregulation=up",
    )
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()

    remap = dict(m.split("=", 1) for m in args.map)

    def load(path):
        rows = read_jsonl(path)
        for r in rows:
            r["label"] = remap.get(r["label"], r["label"])
        return rows

    A, B = load(args.a), load(args.b)
    Bs = {key_strict(r): r for r in B}
    Bl = defaultdict(list)
    for r in B:
        Bl[key_loose(r)].append(r)

    strict, loose_only, missing = [], [], []
    for r in A:
        hit = Bs.get(key_strict(r))
        if hit is not None:
            strict.append((r, hit))
            continue
        cands = Bl.get(key_loose(r))
        if cands:
            loose_only.append((r, cands[0]))
        else:
            missing.append(r)

    print(f"## {args.a_name} vs {args.b_name}\n")
    print(f"- `{args.a_name}` rows: {len(A)}")
    print(f"- `{args.b_name}` rows: {len(B)}")
    print(f"- matched on exact pair: {len(strict)}")
    print(f"- matched on pathway span only: {len(loose_only)}")
    print(f"- in `{args.a_name}` but absent from `{args.b_name}`: {len(missing)}\n")

    report = {
        "a": str(args.a),
        "b": str(args.b),
        "n_a": len(A),
        "n_b": len(B),
        "n_matched_strict": len(strict),
        "n_matched_loose": len(loose_only),
        "n_missing": len(missing),
    }

    for name, matched in (("exact pair", strict), ("exact + pathway-only", strict + loose_only)):
        if not matched:
            continue
        pairs = [(x["label"], y["label"]) for x, y in matched]
        labels = sorted({l for p in pairs for l in p})
        agree = sum(a == b for a, b in pairs) / len(pairs)
        k = kappa(pairs)
        print(f"### Matching on {name} — {len(pairs)} pairs\n")
        print(f"- raw agreement: **{agree:.3f}**")
        print(f"- Cohen's kappa: **{k:.3f}**\n")
        print(confusion(pairs, labels))
        print(f"\n| label | n in {args.a_name} | P | R | F1 |")
        print("|---|---:|---:|---:|---:|")
        for l in labels:
            tp, fp, fn, p, r, f = prf(pairs, l)
            print(f"| {l} | {tp+fn} | {p:.3f} | {r:.3f} | {f:.3f} |")
        print()
        report[name.replace(" ", "_")] = {
            "n": len(pairs),
            "agreement": round(agree, 4),
            "kappa": round(k, 4),
            "confusion": {a: dict(Counter(y for x, y in pairs if x == a)) for a in labels},
        }

    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
