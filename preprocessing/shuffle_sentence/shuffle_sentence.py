#!/usr/bin/env python3
"""
shuffle_sentence.py

Synthetic PATHWAY NER data by moving pathway-bearing sentences between abstracts.

Idea
----
A pathway name is recognised from its own words and from the sentence around it.
Moving that sentence into a different abstract keeps the local evidence and
changes everything else, so the encoder sees the same naming pattern against
contexts it was never paired with. Each synthetic document is a recipient
abstract with some of its sentences replaced by sentences of a donor abstract.

Rules
-----
For each recipient and each copy:

1. A donor is drawn at random from the other training documents that carry at
   least one PATHWAY span.
2. The donor gives its top-k sentences by number of PATHWAY spans (ties go to
   the earlier sentence). Only sentences with at least one span count, so a donor
   with a single pathway sentence gives one.
3. Each donor sentence replaces the recipient sentence at the same position:
   the donor's 2nd sentence lands in the recipient's 2nd slot. A donor whose
   sentences sit beyond the recipient's last sentence is not compatible and
   another is drawn.
4. Recipient spans inside a replaced sentence are dropped with it; every other
   recipient span is kept and shifted. Donor spans are re-based onto the new
   offsets.

The rule is the same whether or not the recipient carries pathway spans of its
own; a recipient without any receives the donor's names and nothing else.

Only the train split takes part, as donor or recipient, so no sentence of a
validation or test document - gt_125 lives in the test split - can reach a
training copy.

Documents with a PATHWAY span that crosses a sentence boundary are excluded from
both roles: such a span belongs to neither sentence and cannot be moved or kept
whole. Their count is in the manifest.

Outputs
-------
    data/processed/10k-missing-shuffle/k<K>_n<N>_seed<S>/
        sentence_shuffle.jsonl          doccano format: text, label, meta
        sentence_shuffle.manifest.json  inputs with sha256, parameters, counts

Each record's `meta.pmid` is `<recipient pmid>-shuf<copy>` so it never collides
with a real PMID, and `meta.augmentation` names the method, recipient, donor,
the donor sentence indices that moved and the recipient spans that were dropped.

Run from the repository root:

    venv310/bin/python3 preprocessing/shuffle_sentence/shuffle_sentence.py --k 2 --n-copies 2 --seed 42
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
from collections import Counter
from pathlib import Path

import spacy

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = REPO / "data/doccano/pathway_10k_plus_missing.jsonl"
DEFAULT_SPLITS = REPO / "data/processed/pathway-10k-missing/splits.json"
OUT_ROOT = REPO / "data/processed/10k-missing-shuffle"

METHOD = "sentence_shuffle"
LABEL = "PATHWAY"
MAX_DRAWS = 50


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_state() -> tuple[str, bool]:
    def run(*args):
        return subprocess.run(["git", "-C", str(REPO), *args],
                              capture_output=True, text=True).stdout.strip()
    return run("rev-parse", "HEAD"), bool(run("status", "--porcelain", str(Path(__file__))))


class Doc:
    """One training abstract split into sentences, its spans assigned to them."""

    def __init__(self, pmid: str, text: str, spans: list[tuple[int, int]], nlp):
        self.pmid = pmid
        self.text = text
        self.sents = [(s.start_char, s.end_char) for s in nlp(text).sents]
        self.by_sent: list[list[tuple[int, int]]] = [[] for _ in self.sents]
        self.crossing = False
        for start, end in sorted(spans):
            idx = next((i for i, (s, e) in enumerate(self.sents) if s <= start < e), None)
            if idx is None or end > self.sents[idx][1]:
                self.crossing = True
                continue
            self.by_sent[idx].append((start, end))

    def top_sentences(self, k: int) -> list[int]:
        """Indices of the k sentences with most spans, in document order."""
        ranked = sorted(
            (i for i, spans in enumerate(self.by_sent) if spans),
            key=lambda i: (-len(self.by_sent[i]), i),
        )
        return sorted(ranked[:k])


def compose(recipient: Doc, donor: Doc, moved: list[int]) -> tuple[str, list, int]:
    """Recipient text with its sentences at `moved` replaced by the donor's."""
    replace = set(moved)
    parts, labels, dropped = [], [], 0
    cursor = 0  # position in the recipient text
    out_len = 0
    for i, (s, e) in enumerate(recipient.sents):
        gap = recipient.text[cursor:s]
        parts.append(gap)
        out_len += len(gap)
        if i in replace:
            ds, de = donor.sents[i]
            parts.append(donor.text[ds:de])
            labels += [[out_len + a - ds, out_len + b - ds, LABEL] for a, b in donor.by_sent[i]]
            out_len += de - ds
            dropped += len(recipient.by_sent[i])
        else:
            parts.append(recipient.text[s:e])
            labels += [[out_len + a - s, out_len + b - s, LABEL] for a, b in recipient.by_sent[i]]
            out_len += e - s
        cursor = e
    parts.append(recipient.text[cursor:])
    return "".join(parts), labels, dropped


def check(text: str, labels: list, expected: list[str]) -> None:
    surfaces = [text[a:b] for a, b, _ in labels]
    if surfaces != expected:
        raise AssertionError(f"span surfaces moved: {expected[:3]} != {surfaces[:3]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--splits", type=Path, default=DEFAULT_SPLITS)
    ap.add_argument("--k", type=int, default=2, help="donor sentences moved per copy")
    ap.add_argument("--n-copies", type=int, default=2, help="synthetic copies per recipient")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, default=0, help="recipients to process, for a smoke test")
    ap.add_argument("--outdir", type=Path, default=None)
    args = ap.parse_args()

    outdir = args.outdir or OUT_ROOT / f"k{args.k}_n{args.n_copies}_seed{args.seed}"
    train = set(map(str, json.loads(args.splits.read_text())["train"]))

    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    docs: list[Doc] = []
    with open(args.corpus, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            pmid = str(rec["meta"]["pmid"])
            if pmid not in train:
                continue
            spans = [(a, b) for a, b, lab in rec["label"] if lab == LABEL]
            docs.append(Doc(pmid, rec["text"], spans, nlp))

    usable = [d for d in docs if not d.crossing]
    donors = [d for d in usable if any(d.by_sent)]
    recipients = usable[: args.limit] if args.limit else usable

    counts: Counter = Counter()
    outdir.mkdir(parents=True, exist_ok=True)
    out_path = outdir / "sentence_shuffle.jsonl"
    with open(out_path, "w", encoding="utf-8") as out:
        for rec_doc in recipients:
            rng = random.Random(f"{args.seed}:{rec_doc.pmid}")
            used: set[str] = {rec_doc.pmid}
            for copy in range(1, args.n_copies + 1):
                donor = moved = None
                for _ in range(MAX_DRAWS):
                    cand = rng.choice(donors)
                    if cand.pmid in used:
                        continue
                    idx = cand.top_sentences(args.k)
                    if idx and idx[-1] < len(rec_doc.sents):
                        donor, moved = cand, idx
                        break
                if donor is None:
                    counts["no_compatible_donor"] += 1
                    continue
                used.add(donor.pmid)

                text, labels, dropped = compose(rec_doc, donor, moved)
                expected = []
                for i, spans in enumerate(rec_doc.by_sent):
                    src = donor if i in moved else rec_doc
                    expected += [src.text[a:b] for a, b in src.by_sent[i]]
                check(text, labels, expected)

                counts["written"] += 1
                counts["donor_spans_added"] += sum(len(donor.by_sent[i]) for i in moved)
                counts["recipient_spans_dropped"] += dropped
                counts["recipients_without_pathway"] += not any(rec_doc.by_sent)
                out.write(json.dumps({
                    "text": text,
                    "label": labels,
                    "meta": {
                        "pmid": f"{rec_doc.pmid}-shuf{copy}",
                        "augmentation": {
                            "method": METHOD,
                            "recipient_pmid": rec_doc.pmid,
                            "donor_pmid": donor.pmid,
                            "moved_sentence_indices": moved,
                            "recipient_spans_dropped": dropped,
                            "k": args.k,
                            "copy": copy,
                            "seed": args.seed,
                        },
                    },
                }, ensure_ascii=False) + "\n")

    sha, dirty = git_state()
    manifest = {
        "method": METHOD,
        "script": str(Path(__file__).relative_to(REPO)),
        "git_sha": sha,
        "git_dirty": dirty,
        "corpus": str(args.corpus),
        "corpus_sha256": sha256_file(args.corpus),
        "splits": str(args.splits),
        "splits_sha256": sha256_file(args.splits),
        "split_used": "train",
        "k": args.k,
        "n_copies": args.n_copies,
        "seed": args.seed,
        "limit": args.limit,
        "spacy_version": spacy.__version__,
        "segmentation": "spacy.blank('en') + sentencizer",
        "n_train_docs": len(docs),
        "n_excluded_crossing_span": len(docs) - len(usable),
        "n_donors": len(donors),
        "n_recipients": len(recipients),
        "counts": dict(counts),
        "output": str(out_path),
        "output_sha256": sha256_file(out_path),
    }
    (outdir / "sentence_shuffle.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
