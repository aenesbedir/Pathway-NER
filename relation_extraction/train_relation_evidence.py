#!/usr/bin/env python3
"""
train_relation_evidence.py

Fine-tune one encoder to do two things at once: label a (pathway, disease) pair,
and mark the tokens the label rests on.

FEASIBILITY PROBE, like `train_relation.py`. Nothing here writes to
`runs/summary.jsonl`.

Why a second head
-----------------
`train_relation.py` scores only the label, so a model can be right for the wrong
reason - picking `downregulation` off a polarity word in an unrelated sentence -
and the metric cannot tell. The teacher's evidence quotes are already in the
corpus, so the supervision for "where did you read that" costs nothing extra.

The evidence head predicts `O / B-EV / I-EV` per token. Its output space is token
indices, so a predicted quote is a substring of the abstract by construction; the
verbatim guarantee comes from the architecture rather than from a check applied
afterwards, which is what a generative head would need.

Why token tagging rather than sentence selection
------------------------------------------------
Measured over the 2,620 quotes in the silver corpus: 84.3% are exactly one
sentence, but 15.2% are a clause inside a sentence and 13 span a boundary. A
sentence-selection head cannot represent the 15%; token tagging can. 7.9% of
evidence-bearing rows carry more than one quote, and 21% of rows (`none`) carry
none at all - both are natural for per-token tagging and awkward for a softmax
over sentences.

Two alignment hazards, both handled here
----------------------------------------
1. Markers shift offsets. The pair's mentions are wrapped in `[[PATHWAY]]` /
   `[[DISEASE]]` before tokenization, and a marker can land *inside* an evidence
   quote - so the raw quote string is not always a substring of the marked text.
   Quote spans are therefore located in the raw abstract and mapped through the
   insertion offsets, never searched for in the marked text.
2. Cropping can cut the evidence away. `train_relation.py` crops a long abstract
   to a window around the entity mentions; if the evidence falls outside that
   window the target becomes silently empty and the model learns "no evidence
   here". The window here must cover the evidence extent too, and a row whose
   evidence cannot fit is dropped and counted rather than emitted with an empty
   target.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset
from transformers import AutoConfig, AutoModel, EarlyStoppingCallback, Trainer, TrainingArguments

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import encoders  # noqa: E402

from schema import LABELS, MAX_EVIDENCE_QUOTES, as_quotes, read_jsonl  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SILVER = REPO / "data/processed/relation/silver_2k_full"
DEFAULT_TRAIN = SILVER / "relations_llm_opus48_same_sentence.jsonl"
DEFAULT_TRAIN_CANDS = SILVER / "candidates_same_sentence.jsonl"
DEFAULT_TEST = REPO / (
    "data/processed/gt_100/"
    "gt_100_disease_pathway_bent-pubmedbert-ner-disease_relation_fable_v4d_single.jsonl"
)
DEFAULT_TEST_CANDS = REPO / "data/processed/gt_100/candidates_v4.jsonl"
DEFAULT_OUT = REPO / "models_re/relation_ft_evidence"

LABEL2ID = {l: i for i, l in enumerate(LABELS)}

#: Evidence tagging is binary, not BIO. `B` occurs once per span and `I` fills
#: the rest, so inverse-frequency weighting handed B a weight of 184 against
#: O's 0.38 and the head answered "evidence" almost everywhere. Spans are
#: recovered from contiguous runs either way, since quotes are whole sentences
#: or clauses separated by tokens that fall outside them.
EV_O, EV_POS = 0, 1

MARK = {"PATHWAY": ("[[PATHWAY]]", "[[/PATHWAY]]"), "DISEASE": ("[[DISEASE]]", "[[/DISEASE]]")}
#: Added to the tokenizer so each marker costs one token. Unadded, BiomedBERT
#: splits "[[PATHWAY]]" into five pieces whose text ("pathway", "disease") also
#: collides with the abstract's own vocabulary; a pair with twenty mentions then
#: spends 200 of its 512 tokens on punctuation.
MARK_TOKENS = [t for pair in MARK.values() for t in pair]


def mark_with_map(abstract: str, pathway_spans, disease_spans):
    """Insert markers and return the text plus a raw->marked offset map.

    The map is what makes evidence alignment safe: a quote is found in the raw
    abstract, then each of its endpoints is translated, so a marker sitting
    inside the quote cannot break the lookup.
    """
    spans = sorted(
        [(s, e, "PATHWAY") for s, e in pathway_spans] + [(s, e, "DISEASE") for s, e in disease_spans]
    )
    out, cur, shift = [], 0, 0
    # shift_at[i] is the number of characters inserted before raw offset i.
    shift_at = [0] * (len(abstract) + 1)
    kept: dict[str, list[tuple[int, int]]] = {"PATHWAY": [], "DISEASE": []}
    for s, e, kind in spans:
        if s < cur:
            continue
        open_t, close_t = MARK[kind]
        out.append(abstract[cur:s])
        for i in range(cur, s + 1):
            shift_at[i] = shift
        shift += len(open_t)
        out.append(open_t + abstract[s:e] + close_t)
        for i in range(s, e + 1):
            shift_at[i] = shift
        shift += len(close_t)
        cur = e
        kept[kind].append((s, e))
    out.append(abstract[cur:])
    for i in range(cur, len(abstract) + 1):
        shift_at[i] = shift
    return "".join(out), shift_at, kept


def evidence_spans(abstract: str, quotes) -> list[tuple[int, int]]:
    """Char spans of each quote in the raw abstract. Unlocatable quotes are dropped."""
    out = []
    for q in quotes[:MAX_EVIDENCE_QUOTES]:
        at = abstract.find(q)
        if at >= 0:
            out.append((at, at + len(q)))
    return out


def build(relations: Path, candidates: Path, tokenizer, max_len: int):
    cands = {c["candidate_id"]: c for c in read_jsonl(candidates)}
    rows: list[dict] = []
    stats: Counter = Counter()
    budget = max_len * 5  # characters; the tokenizer truncates whatever survives

    for r in read_jsonl(relations):
        c = cands.get(r["candidate_id"])
        if c is None:
            stats["candidate_not_found"] += 1
            continue
        abstract = c["abstract"]
        quotes = list(as_quotes(r.get("evidence")))
        ev_raw = evidence_spans(abstract, quotes)
        if len(ev_raw) < len(quotes):
            stats["quote_not_located"] += len(quotes) - len(ev_raw)

        text, shift_at, kept = mark_with_map(
            abstract,
            [(m["start"], m["end"]) for m in c["pathway_mentions"]],
            [(m["start"], m["end"]) for m in c["disease_mentions"]],
        )
        ev_marked = [(s + shift_at[s], e + shift_at[e]) for s, e in ev_raw]

        # The window has to show the evidence and at least one marked mention of
        # each entity. Requiring the *full* mention extent instead threw away 108
        # rows, because an entity named twenty times can span the whole abstract
        # while the claim sits in one sentence.
        #
        # A kind can be missing from `kept`: `mark_with_map` skips a mention that
        # overlaps an already-marked one, which happens when a pathway name sits
        # inside a disease name. The centre then falls back to whatever is there.
        marked = [
            (s0 + shift_at[s0], e0 + shift_at[e0])
            for kind in ("PATHWAY", "DISEASE")
            for s0, e0 in kept[kind]
        ]
        if ev_marked:
            centre = (min(s0 for s0, _ in ev_marked) + max(e0 for _, e0 in ev_marked)) // 2
        elif marked:
            centre = marked[0][0]
        else:
            centre = 0
        near = []
        for kind in ("PATHWAY", "DISEASE"):
            if not kept[kind]:
                continue
            s0, e0 = min(kept[kind], key=lambda t: abs((t[0] + shift_at[t[0]]) - centre))
            near.append((s0 + shift_at[s0], e0 + shift_at[e0]))
        anchors = ev_marked + near
        lo = min(s0 for s0, _ in anchors) if anchors else 0
        hi = max(e0 for _, e0 in anchors) if anchors else min(len(text), budget)
        if len(text) > budget:
            if hi - lo > budget:
                stats["dropped_window_too_small"] += 1
                continue
            slack = (budget - (hi - lo)) // 2
            start = max(0, lo - slack)
            text = text[start : start + budget]
            ev_marked = [(s - start, e - start) for s, e in ev_marked]
            stats["cropped"] += 1

        rows.append(
            {
                "text": text,
                "label": LABEL2ID[r["label"]],
                "evidence": ev_marked,
                "pmid": str(c["pmid"]),
                "candidate_id": c["candidate_id"],
            }
        )
    return rows, dict(stats)


class PairDataset(Dataset):
    """Tokenizes once and turns evidence char spans into per-token tags.

    Every non-special token carries a tag, including subword continuations -
    unlike `preprocessing/tag_bio.py`, which masks continuations because its
    task is word-level. Here the decoded output is a character span, so a masked
    continuation would leave a hole in the middle of a predicted quote.

    Marker tokens are masked out instead. A quote usually contains one of the
    pair's mentions, so the markers sit inside the evidence span through no
    decision of the model's; tagging them would teach it that "[[PATHWAY]]" is
    evidence, and decoding would splice the marker text into the quote.
    """

    def __init__(self, rows, tokenizer, max_len):
        self.enc = tokenizer(
            [r["text"] for r in rows],
            truncation=True,
            max_length=max_len,
            padding=False,
            return_offsets_mapping=True,
        )
        marker_ids = {
            i for i in tokenizer.convert_tokens_to_ids(MARK_TOKENS) if i is not None
        }
        self.labels = [r["label"] for r in rows]
        self.ev: list[list[int]] = []
        self.counts = Counter()
        for i, row in enumerate(rows):
            tags = []
            for tid, (a, b) in zip(self.enc["input_ids"][i], self.enc["offset_mapping"][i]):
                if a == b or tid in marker_ids:
                    tags.append(-100)
                    continue
                hit = any(a < e and s < b for s, e in row["evidence"])
                tags.append(EV_POS if hit else EV_O)
            self.ev.append(tags)
            self.counts.update(t for t in tags if t != -100)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, i):
        return {
            "input_ids": self.enc["input_ids"][i],
            "attention_mask": self.enc["attention_mask"][i],
            "labels": self.labels[i],
            "evidence_labels": self.ev[i],
        }


def collate(batch, pad_id: int):
    width = max(len(b["input_ids"]) for b in batch)
    def pad(seq, value):
        return seq + [value] * (width - len(seq))
    return {
        "input_ids": torch.tensor([pad(b["input_ids"], pad_id) for b in batch]),
        "attention_mask": torch.tensor([pad(b["attention_mask"], 0) for b in batch]),
        "labels": torch.tensor([b["labels"] for b in batch]),
        "evidence_labels": torch.tensor([pad(b["evidence_labels"], -100) for b in batch]),
    }


class TwoHeadModel(nn.Module):
    """Shared encoder, one head on [CLS] for the label, one per token for evidence."""

    def __init__(self, hf_id: str, n_labels: int, ev_weights, lam: float,
                 vocab_size: int | None = None, dropout: float = 0.1):
        super().__init__()
        self.config = AutoConfig.from_pretrained(hf_id)
        self.encoder = AutoModel.from_pretrained(hf_id)
        if vocab_size is not None and vocab_size != self.config.vocab_size:
            # The marker tokens were added to the tokenizer; their embeddings
            # start random and are learned like any other parameter.
            self.encoder.resize_token_embeddings(vocab_size)
        hidden = self.config.hidden_size
        self.dropout = nn.Dropout(dropout)
        self.label_head = nn.Linear(hidden, n_labels)
        self.evidence_head = nn.Linear(hidden, 2)
        self.lam = lam
        self.register_buffer("ev_weights", torch.tensor(ev_weights, dtype=torch.float))

    def state_dict(self, *args, **kwargs):
        """Contiguous copies, because the checkpoint writer refuses views.

        This is a plain `nn.Module`, so `Trainer` saves it through safetensors,
        which rejects a tensor sharing storage with another - which several of
        the encoder's attention weights do. Only the saved copy is packed; the
        live parameters are untouched.
        """
        sd = super().state_dict(*args, **kwargs)
        return {k: (v.contiguous() if hasattr(v, "contiguous") else v) for k, v in sd.items()}

    def forward(self, input_ids=None, attention_mask=None, labels=None, evidence_labels=None):
        h = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        h = self.dropout(h)
        label_logits = self.label_head(h[:, 0, :])
        ev_logits = self.evidence_head(h)

        loss = None
        if labels is not None:
            loss = nn.functional.cross_entropy(label_logits, labels)
            if evidence_labels is not None:
                # Evidence tokens are a small minority of an abstract, and 21% of
                # rows carry none at all; unweighted, the head learns to answer O
                # everywhere and the loss barely moves.
                ev_loss = nn.functional.cross_entropy(
                    ev_logits.reshape(-1, 2),
                    evidence_labels.reshape(-1),
                    weight=self.ev_weights,
                    ignore_index=-100,
                )
                loss = loss + self.lam * ev_loss
        return {"loss": loss, "logits": label_logits, "evidence_logits": ev_logits}


def compute_metrics(eval_pred):
    preds, gold = eval_pred
    label_logits, ev_logits = preds
    label_gold, ev_gold = gold

    pred = np.asarray(label_logits).argmax(-1)
    labels = np.asarray(label_gold)
    out = {"accuracy": float((pred == labels).mean())}
    f1s = []
    for i, name in enumerate(LABELS):
        tp = int(((pred == i) & (labels == i)).sum())
        fp = int(((pred == i) & (labels != i)).sum())
        fn = int(((pred != i) & (labels == i)).sum())
        f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
        out[f"f1_{name}"] = round(f1, 4)
        if (labels == i).sum():
            f1s.append(f1)
    out["macro_f1"] = round(float(np.mean(f1s)), 4) if f1s else 0.0

    ev_pred = np.asarray(ev_logits).argmax(-1)
    ev_gold = np.asarray(ev_gold)
    keep = ev_gold != -100
    p, g = ev_pred[keep], ev_gold[keep]
    pos_p, pos_g = p == EV_POS, g == EV_POS
    tp = int((pos_p & pos_g).sum())
    fp = int((pos_p & ~pos_g).sum())
    fn = int((~pos_p & pos_g).sum())
    out["evidence_token_f1"] = round(2 * tp / (2 * tp + fp + fn), 4) if (2 * tp + fp + fn) else 0.0
    out["evidence_token_precision"] = round(tp / (tp + fp), 4) if (tp + fp) else 0.0
    out["evidence_token_recall"] = round(tp / (tp + fn), 4) if (tp + fn) else 0.0

    # Row-level: did the prediction touch the gold evidence at all, and did it
    # get the label too. The joint number is the one the second head exists for.
    row_overlap, row_joint, n_rows = 0, 0, len(labels)
    for r in range(n_rows):
        k = ev_gold[r] != -100
        gp, pp = ev_gold[r][k] == EV_POS, ev_pred[r][k] == EV_POS
        if not gp.any():
            touched = not pp.any()          # `none`: correct iff it marks nothing
        else:
            touched = bool((gp & pp).any())
        row_overlap += touched
        row_joint += touched and (pred[r] == labels[r])
    out["evidence_row_overlap"] = round(row_overlap / n_rows, 4)
    out["joint_tp"] = round(row_joint / n_rows, 4)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="biomedbert-base")
    ap.add_argument("--train", type=Path, default=DEFAULT_TRAIN)
    ap.add_argument("--train-candidates", type=Path, default=DEFAULT_TRAIN_CANDS)
    ap.add_argument("--test", type=Path, default=DEFAULT_TEST)
    ap.add_argument("--test-candidates", type=Path, default=DEFAULT_TEST_CANDS)
    ap.add_argument("--outdir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--run-name", default=None)
    ap.add_argument("--max-len", type=int, default=512)
    ap.add_argument("--batch-size", type=int, default=None)
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--patience", type=int, default=3)
    ap.add_argument("--lam", type=float, default=1.0, help="weight of the evidence loss")
    ap.add_argument("--select-metric", default="joint_tp",
                    help="metric the best epoch is chosen by. Use macro_f1 to compare "
                         "the label head against the single-head baseline on equal terms")
    ap.add_argument("--ev-weights", nargs=2, type=float, default=None,
                    help="class weights for O / evidence (default: inverse frequency)")
    ap.add_argument("--val-fraction", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--save-model", action=argparse.BooleanOptionalAction, default=False)
    args = ap.parse_args()

    spec = encoders.resolve(args.model)
    tokenizer = spec.load_tokenizer()
    n_added = tokenizer.add_tokens(MARK_TOKENS)
    batch_size = args.batch_size or spec.batch_size

    train_rows, train_stats = build(args.train, args.train_candidates, tokenizer, args.max_len)
    test_rows, test_stats = build(args.test, args.test_candidates, tokenizer, args.max_len)

    pmids = sorted({r["pmid"] for r in train_rows})
    random.Random(args.seed).shuffle(pmids)
    val_pmids = set(pmids[: max(1, int(len(pmids) * args.val_fraction))])
    val_rows = [r for r in train_rows if r["pmid"] in val_pmids]
    fit_rows = [r for r in train_rows if r["pmid"] not in val_pmids]
    if args.limit:
        fit_rows = fit_rows[: args.limit]

    fit_ds = PairDataset(fit_rows, tokenizer, args.max_len)
    val_ds = PairDataset(val_rows, tokenizer, args.max_len)
    test_ds = PairDataset(test_rows, tokenizer, args.max_len)

    if args.ev_weights:
        ev_weights = list(args.ev_weights)
    else:
        counts = fit_ds.counts
        total = sum(counts.values())
        ev_weights = [round(total / (2 * max(counts.get(i, 1), 1)), 3) for i in (EV_O, EV_POS)]

    torch.manual_seed(args.seed)
    model = TwoHeadModel(spec.hf_id, len(LABELS), ev_weights, args.lam, vocab_size=len(tokenizer))

    run = args.run_name or f"{args.model}_ev_lam{args.lam:g}_lr{args.lr:g}"
    out = args.outdir / run
    out.mkdir(parents=True, exist_ok=True)

    targs = TrainingArguments(
        output_dir=str(out / "checkpoints"),
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=args.lr,
        num_train_epochs=args.epochs,
        warmup_ratio=0.1,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model=args.select_metric,
        greater_is_better=True,
        save_total_limit=1,
        logging_steps=50,
        seed=args.seed,
        bf16=torch.cuda.is_available(),
        report_to=[],
        label_names=["labels", "evidence_labels"],
        remove_unused_columns=False,
    )
    trainer = Trainer(
        model=model,
        args=targs,
        train_dataset=fit_ds,
        eval_dataset=val_ds,
        data_collator=lambda b: collate(b, tokenizer.pad_token_id),
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=args.patience)],
    )
    trainer.train()

    val_metrics = trainer.evaluate()
    test_metrics = trainer.evaluate(test_ds, metric_key_prefix="test")

    result = {
        "run": run,
        "model_key": args.model,
        "hf_id": spec.hf_id,
        "lr": args.lr,
        "epochs": args.epochs,
        "lam": args.lam,
        "select_metric": args.select_metric,
        "ev_weights": ev_weights,
        "batch_size": batch_size,
        "max_len": args.max_len,
        "seed": args.seed,
        "n_fit": len(fit_rows),
        "n_val": len(val_rows),
        "n_test": len(test_rows),
        "marker_tokens_added": n_added,
        "evidence_token_counts_fit": {"O": fit_ds.counts[EV_O], "EV": fit_ds.counts[EV_POS]},
        "build_stats": {"train": train_stats, "test": test_stats},
        "val": {k: v for k, v in val_metrics.items() if k.startswith("eval_")},
        "test": {k: v for k, v in test_metrics.items() if k.startswith("test_")},
    }
    (out / "metrics.json").write_text(json.dumps(result, indent=2) + "\n")
    if args.save_model:
        torch.save(model.state_dict(), out / "model.pt")
        tokenizer.save_pretrained(str(out / "model"))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
