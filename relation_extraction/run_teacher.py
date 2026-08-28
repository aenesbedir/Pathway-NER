#!/usr/bin/env python3
"""
run_teacher.py

Run an LLM teacher over candidate pairs and write grounded relation records.

One request per abstract, carrying every candidate pair for that abstract. This
is both cheaper and more accurate than one request per pair: the model reads the
abstract once, and pairs that compete for the same evidence sentence are decided
together.

Grounding
---------
Nothing the model returns is trusted. Each row must satisfy:

- the index refers to a pair that was actually asked about;
- the label is one of the five schema values;
- the evidence is a verbatim substring of the abstract;
- a non-`none` label carries evidence, and `none` carries none.

Rows failing any check are dropped and counted by reason in the run summary. A
model that returns fewer rows than pairs leaves those pairs unlabelled rather
than defaulting them to `none`, because a silent default would manufacture
training examples for the majority class out of a parsing failure.

Caching
-------
One JSON file per (model, pmid) under `--cache-dir`, valid only while the pair
list, the annotation guide and the invocation are unchanged. The cache stores the raw
response text, so re-parsing after a grounding fix costs nothing while a model
change is a cache miss. An error response is never cached as a success, which is
the failure mode that silently froze bad answers in the NER silver run
(`project_tracking.md`, "Silent LLM failures could be cached forever").
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import prompts
from schema import (
    Candidate,
    Mention,
    Relation,
    SCHEMA_TAG,
    CONFIDENCE,
    LABELS,
    RecordError,
    read_jsonl,
    write_jsonl,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_INDIR = REPO / "data/processed/relation/silver_2k"
DEFAULT_CACHE = REPO / "data/raw/relation_teacher_cache"


def slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


#: Flags that strip the Claude Code agent scaffolding from a headless call.
#:
#: `claude -p` is not a raw API call. By default it sends its own agent system
#: prompt, every built-in tool definition, the discovered CLAUDE.md and machine
#: context - measured at ~28,000 input tokens for a five-word prompt, and 1,745
#: tokens more when run from a directory carrying a CLAUDE.md. The annotation
#: task then depends on the working directory and on the Claude Code version,
#: neither of which belongs in an annotation protocol.
#:
#: With these flags the same probe costs ~285 tokens. What remains, and cannot be
#: removed from the CLI, is one identity line plus a system-reminder carrying the
#: user's email address and the current date. `--bare` would go further but
#: requires ANTHROPIC_API_KEY; `--setting-sources ""` does not affect this block.
#: `--exclude-dynamic-system-prompt-sections` is deliberately absent: its help
#: text states it is ignored whenever `--system-prompt` is given.
#:
#: `--system-prompt ""` empties the default prompt; `--append-system-prompt` then
#: adds ours to it. The pair is verified to deliver our text.
RAW_FLAGS = [
    "--safe-mode",
    "--system-prompt",
    "",
    "--strict-mcp-config",
    "--mcp-config",
    '{"mcpServers":{}}',
    "--tools",
    "",
    "--no-session-persistence",
]

#: The current date reaches the model through that system-reminder, so two runs
#: on different days are not byte-identical requests. Recorded, not hidden.
RESIDUAL_CONTEXT = "claude-agent-sdk identity line + system-reminder (userEmail, currentDate)"

#: Digest of everything that decides what the model is asked, other than the
#: abstract and its pairs: the guide, our system prompt, and the invocation.
#:
#: The guide belongs here for the obvious reason - a revised guide is a different
#: question. The invocation belongs here for a less obvious one: the same guide
#: sent with the default Claude Code scaffolding and sent with RAW_FLAGS are two
#: different requests, and the first run of this pipeline used the former. Keying
#: only on the guide would let those answers pass as valid under the new
#: configuration.
PROMPT_FINGERPRINT = hashlib.sha1(
    "\x1f".join((prompts.SYSTEM, prompts.GUIDE, *RAW_FLAGS)).encode("utf-8")
).hexdigest()[:12]


class ClaudeCLI:
    """Teacher backed by the local `claude` CLI, stripped to a near-raw call."""

    def __init__(self, model: str, timeout: int = 300):
        self.model = model
        self.timeout = timeout
        self.name = f"llm:{model}"

    def __call__(self, user_prompt: str) -> str:
        cmd = [
            "claude",
            "-p",
            user_prompt,
            "--model",
            self.model,
            *RAW_FLAGS,
            "--append-system-prompt",
            prompts.SYSTEM,
            "--output-format",
            "text",
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=self.timeout
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"claude exited {proc.returncode}: {proc.stderr.strip()[:300]}"
            )
        out = proc.stdout.strip()
        if not out:
            raise RuntimeError("claude returned an empty response")
        return out


class OllamaHTTP:
    """Teacher backed by a local Ollama model, for a cost-free comparison run."""

    def __init__(self, model: str, timeout: int = 600):
        self.model = model
        self.timeout = timeout
        self.name = f"ollama:{model}"

    def __call__(self, user_prompt: str) -> str:
        import urllib.request

        body = json.dumps(
            {
                "model": self.model,
                "prompt": prompts.SYSTEM + "\n\n" + user_prompt,
                "stream": False,
                "think": False,
                "options": {"temperature": 0, "seed": 42, "num_ctx": 8192},
            }
        ).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read())["response"].strip()


def parse_array(text: str) -> list[dict]:
    """Pull the JSON array out of a model response, tolerating fences and prose."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE)
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
        if not match:
            raise
        obj = json.loads(match.group(0))
    if isinstance(obj, dict):
        for key in ("pairs", "relations", "results"):
            if isinstance(obj.get(key), list):
                return obj[key]
        raise ValueError("response object has no array field")
    if not isinstance(obj, list):
        raise ValueError(f"response is {type(obj).__name__}, expected list")
    return obj


def ground(
    rows: list[dict],
    cands: list[Candidate],
    abstract: str,
    source: str,
    rejected: Counter,
) -> list[Relation]:
    """Validate model rows against the pairs actually asked about."""
    out: list[Relation] = []
    seen: set[int] = set()
    for row in rows:
        try:
            idx = int(row["i"])
        except (KeyError, TypeError, ValueError):
            rejected["missing_index"] += 1
            continue
        if not 1 <= idx <= len(cands):
            rejected["index_out_of_range"] += 1
            continue
        if idx in seen:
            rejected["duplicate_index"] += 1
            continue
        seen.add(idx)

        cand = cands[idx - 1]
        label = str(row.get("label", "")).strip()
        if label not in LABELS:
            rejected["unknown_label"] += 1
            continue
        confidence = str(row.get("confidence", "medium")).strip()
        if confidence not in CONFIDENCE:
            confidence = "medium"

        evidence = str(row.get("evidence") or "").strip()
        if label == "none":
            evidence = ""
        elif not evidence:
            rejected["missing_evidence"] += 1
            continue
        elif evidence not in abstract:
            rejected["evidence_not_verbatim"] += 1
            continue

        rel = Relation(
            pmid=cand.pmid,
            disease=cand.disease_mentions[0],
            pathway=cand.pathway_mentions[0],
            label=label,
            confidence=confidence,
            evidence=evidence,
            relation_source=source,
            candidate_id=cand.candidate_id,
            stratum=cand.stratum,
            schema=SCHEMA_TAG,
        )
        try:
            rel.check(abstract)
        except RecordError:
            rejected["schema_invalid"] += 1
            continue
        out.append(rel)

    rejected["unanswered_pair"] += len(cands) - len(seen)
    return out


def label_document(teacher, cache_dir: Path, pmid: str, cands: list[Candidate]):
    """Return (relations, rejected_counter, status) for one abstract."""
    abstract = cands[0].abstract
    cache_file = cache_dir / f"{pmid}.json"
    status = "cached"
    want_ids = [c.candidate_id for c in cands]

    payload = None
    if cache_file.exists():
        cached = json.loads(cache_file.read_text())
        # The response answers one specific list of pairs, but the cache is keyed
        # on the PMID alone. Two candidate files can cover the same abstract with
        # different pairs - a different stratum sample, a reviewed pathway layer -
        # and replaying the old answer would silently label the new pairs with the
        # old ones' indices. `llm/models.py` records the same failure for the NER
        # silver cache, where swapping the model replayed the previous model's
        # answers. Treat a changed pair list as a miss.
        if (
            cached.get("candidate_ids") == want_ids
            and cached.get("prompt_fingerprint") == PROMPT_FINGERPRINT
        ):
            payload = cached
        else:
            status = "stale_cache"

    if payload is None:
        pairs = [
            (c.pathway_mentions[0].text, c.disease_mentions[0].text) for c in cands
        ]
        prompt = prompts.render(abstract, pairs)
        started = time.time()
        try:
            raw = teacher(prompt)
        except Exception as exc:  # noqa: BLE001 - reported, never cached
            return [], Counter({"request_failed": len(cands)}), f"error: {exc}"
        payload = {
            "pmid": pmid,
            "model": teacher.name,
            "n_pairs": len(cands),
            "candidate_ids": want_ids,
            "prompt_fingerprint": PROMPT_FINGERPRINT,
            "raw": raw,
            "wall_s": round(time.time() - started, 2),
        }
        cache_file.write_text(json.dumps(payload, ensure_ascii=False))
        status = "refetched" if status == "stale_cache" else "fetched"

    rejected: Counter = Counter()
    try:
        rows = parse_array(payload["raw"])
    except Exception:  # noqa: BLE001 - a bad response is data, not a crash
        return [], Counter({"unparsable_response": len(cands)}), "unparsable"

    rels = ground(rows, cands, abstract, payload["model"], rejected)
    return rels, rejected, status


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--indir", type=Path, default=DEFAULT_INDIR)
    ap.add_argument("--candidates", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--backend", choices=("claude", "ollama"), default="claude")
    ap.add_argument("--model", default="opus")
    ap.add_argument("--limit", type=int, default=0, help="stop after N abstracts")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    cand_path = args.candidates or (args.indir / "candidates.jsonl")
    cands = [Candidate.from_json(d) for d in read_jsonl(cand_path)]
    by_pmid: dict[str, list[Candidate]] = defaultdict(list)
    for c in cands:
        by_pmid[c.pmid].append(c)
    for pmid in by_pmid:
        by_pmid[pmid].sort(key=lambda c: c.candidate_id)

    teacher = (
        ClaudeCLI(args.model) if args.backend == "claude" else OllamaHTTP(args.model)
    )
    cache_dir = args.cache_dir / slug(teacher.name)
    cache_dir.mkdir(parents=True, exist_ok=True)

    pmids = sorted(by_pmid)
    if args.limit:
        pmids = pmids[: args.limit]

    out_path = args.out or (args.indir / f"relations_{slug(teacher.name)}.jsonl")
    print(
        f"{len(pmids)} abstracts, {sum(len(by_pmid[p]) for p in pmids)} pairs, "
        f"teacher={teacher.name}, cache={cache_dir}",
        file=sys.stderr,
    )

    all_rels: list[Relation] = []
    rejected: Counter = Counter()
    statuses: Counter = Counter()
    started = time.time()

    def work(pmid: str):
        return pmid, label_document(teacher, cache_dir, pmid, by_pmid[pmid])

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for done, (pmid, (rels, rej, status)) in enumerate(
            pool.map(work, pmids), 1
        ):
            all_rels.extend(rels)
            rejected.update(rej)
            statuses[status.split(":")[0]] += 1
            if status.startswith("error"):
                print(f"  {pmid}: {status}", file=sys.stderr)
            if done % 25 == 0 or done == len(pmids):
                rate = done / max(time.time() - started, 1e-9)
                print(
                    f"  {done}/{len(pmids)} abstracts, {len(all_rels)} rows, "
                    f"{rate*60:.1f}/min",
                    file=sys.stderr,
                )

    all_rels.sort(key=lambda r: (r.pmid, r.candidate_id))
    n = write_jsonl(out_path, all_rels)

    summary = {
        "teacher": teacher.name,
        "prompt_fingerprint": PROMPT_FINGERPRINT,
        "raw_flags": RAW_FLAGS,
        "residual_context": RESIDUAL_CONTEXT,
        "schema": SCHEMA_TAG,
        "backend": args.backend,
        "candidates": str(cand_path),
        "n_abstracts": len(pmids),
        "n_pairs_asked": sum(len(by_pmid[p]) for p in pmids),
        "n_rows_kept": n,
        "labels": dict(Counter(r.label for r in all_rels).most_common()),
        "confidence": dict(Counter(r.confidence for r in all_rels).most_common()),
        "by_stratum": dict(Counter(r.stratum for r in all_rels).most_common()),
        "rejected": dict(rejected.most_common()),
        "request_status": dict(statuses.most_common()),
        "wall_s": round(time.time() - started, 1),
        "output": str(out_path),
    }
    summary_path = out_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
