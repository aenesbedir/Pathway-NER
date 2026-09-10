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
import random
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import prompts
from schema import (
    CONFIDENCE,
    Candidate,
    LABELS,
    MAX_EVIDENCE_QUOTES,
    Mention,
    RecordError,
    Relation,
    SCHEMA_TAG,
    as_quotes,
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

def prompt_fingerprint(mode: str) -> str:
    """Digest of what decides the question, bar the abstract: guide, system
    prompt, invocation.

    The invocation belongs here for a non-obvious reason: the same guide sent with
    the default Claude Code scaffolding and sent with RAW_FLAGS are two different
    requests, and the first runs of this pipeline used the former.

    The mode is not hashed in by name. Each mode carries its own guide and the
    guide is already in the digest, so naming the mode as well would have changed
    the batch fingerprint the moment a second mode was added, invalidating answers
    produced by an identical request.
    """
    guide = {
        "batch": prompts.GUIDE,
        "single": prompts.GUIDE_SINGLE,
        "grouped": prompts.GUIDE_GROUPED,
    }[mode]
    return hashlib.sha1(
        "\x1f".join((prompts.SYSTEM, guide, *RAW_FLAGS)).encode("utf-8")
    ).hexdigest()[:12]


class SafeguardRefusal(RuntimeError):
    """The provider's safety filter refused this prompt. Not retryable."""


class ClaudeCLI:
    """Teacher backed by the local `claude` CLI, stripped to a near-raw call."""

    def __init__(self, model: str, timeout: int = 300, retries: int = 5):
        self.model = model
        self.timeout = timeout
        self.retries = retries
        self.name = f"llm:{model}"

    def __call__(self, user_prompt: str) -> str:
        """One call, retried on transient failure.

        Under concurrency the CLI returns exit 1 with an empty stderr often
        enough to ruin a sweep: three runs over this corpus lost between a fifth
        and three quarters of their requests that way, while the same prompt
        sent alone succeeded immediately. The failure carries no message to
        distinguish it from a real one, so every non-zero exit is retried with
        an exponential, jittered backoff, and only the last one is raised.

        Retrying here rather than in the caching layer keeps an error out of the
        cache: `_fetch` still never writes a failure, it just sees fewer.
        """
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
        last = ""
        for attempt in range(self.retries):
            if attempt:
                time.sleep(min(60, 2 ** attempt) * (0.5 + random.random()))
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=self.timeout
                )
            except subprocess.TimeoutExpired:
                last = f"timed out after {self.timeout}s"
                continue
            if proc.returncode != 0:
                # A safeguard refusal is deterministic: the same abstract is
                # refused every time, and the CLI reports it on stdout with an
                # empty stderr and exit 1 - indistinguishable from a transient
                # failure unless the text is read. Retrying one wastes five
                # calls, and this corpus is biomedical enough that Opus refused
                # roughly three quarters of it.
                blob = (proc.stdout or "") + (proc.stderr or "")
                if "safeguards flagged" in blob:
                    raise SafeguardRefusal(blob.strip()[:200])
                last = f"claude exited {proc.returncode}: {proc.stderr.strip()[:300]}"
                continue
            out = proc.stdout.strip()
            if not out:
                last = "claude returned an empty response"
                continue
            return out
        raise RuntimeError(f"{last} (after {self.retries} attempts)")


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


def parse_object(text: str) -> dict:
    """Pull the single JSON object out of a response, tolerating fences and prose."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE)
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        obj = json.loads(match.group(0))
    if isinstance(obj, list):
        if len(obj) != 1:
            raise ValueError(f"expected one object, got a list of {len(obj)}")
        obj = obj[0]
    if not isinstance(obj, dict):
        raise ValueError(f"response is {type(obj).__name__}, expected object")
    return obj


#: Marker tokens `single` and `grouped` insert around the pair being judged.
_MARKER_RE = re.compile(r"\[\[/?(?:PATHWAY|DISEASE)\]\]")


def resolve_quote(quote: str, abstract: str) -> str | None:
    """Return the abstract's own text for `quote`, or None if it is not there.

    A quote is rejected unless it is verbatim, and two harmless mismatches used to
    cause most rejections. The model copies the `[[PATHWAY]]` markers it was shown
    into the quote, and it re-wraps whitespace. Neither changes what was quoted.

    So the match is attempted three ways - exact, marker-stripped, then
    whitespace-normalized - and what gets stored is always the substring taken
    from the abstract, never the model's rendering of it. The record therefore
    still satisfies "evidence is a verbatim substring", which is the property the
    rest of the pipeline relies on.
    """
    quote = quote.strip()
    if not quote:
        return None
    if quote in abstract:
        return quote
    stripped = _MARKER_RE.sub("", quote).strip()
    if stripped and stripped in abstract:
        return stripped
    if not stripped:
        return None

    # Whitespace-insensitive search: walk the abstract keeping a map from each
    # normalized character back to its offset, then slice the original.
    norm_chars: list[str] = []
    offsets: list[int] = []
    prev_space = False
    for i, ch in enumerate(abstract):
        if ch.isspace():
            if prev_space:
                continue
            prev_space = True
            norm_chars.append(" ")
            offsets.append(i)
        else:
            prev_space = False
            norm_chars.append(ch)
            offsets.append(i)
    norm_abstract = "".join(norm_chars)
    norm_quote = re.sub(r"\s+", " ", stripped).strip()
    at = norm_abstract.find(norm_quote)
    if at < 0:
        return None
    start = offsets[at]
    end = offsets[at + len(norm_quote) - 1] + 1
    return abstract[start:end]


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

        # Evidence may arrive as one string or as several quotes; both are
        # normalized to a tuple, and every quote has to be verbatim.
        quotes = as_quotes(row.get("evidence"))
        if label == "none":
            quotes = ()
        elif not quotes:
            rejected["missing_evidence"] += 1
            continue
        elif len(quotes) > MAX_EVIDENCE_QUOTES:
            rejected["too_many_evidence_quotes"] += 1
            continue
        else:
            resolved = tuple(resolve_quote(q, abstract) for q in quotes)
            if any(q is None for q in resolved):
                rejected["evidence_not_verbatim"] += 1
                continue
            quotes = resolved

        rel = Relation(
            pmid=cand.pmid,
            disease=cand.disease_mentions[0],
            pathway=cand.pathway_mentions[0],
            label=label,
            confidence=confidence,
            evidence=quotes,
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


def label_batch(teacher, cache_dir: Path, pmid: str, cands: list[Candidate], fp: str):
    """One request carrying every pair of one abstract."""
    abstract = cands[0].abstract
    want_ids = [c.candidate_id for c in cands]
    cache_file = cache_dir / f"{pmid}.json"
    pairs = [(c.pathway_mentions[0].text, c.disease_mentions[0].text) for c in cands]
    prompt = prompts.render(abstract, pairs)
    payload, status = _read_cache(cache_file, want_ids, fp, prompt_sha(prompt))

    if payload is None:
        payload, status = _fetch(teacher, cache_file, prompt, pmid, want_ids, fp, status)
        if payload is None:
            return [], Counter({"request_failed": len(cands)}), status

    rejected: Counter = Counter()
    try:
        rows = parse_array(payload["raw"])
    except Exception:  # noqa: BLE001 - a bad response is data, not a crash
        return [], Counter({"unparsable_response": len(cands)}), "unparsable"
    return ground(rows, cands, abstract, payload["model"], rejected), rejected, status


def label_grouped(teacher, cache_dir: Path, pmid: str, cands: list[Candidate], fp: str):
    """One request per pair, naming the surfaces folded into each entity.

    Identical to `label_single` except for the prompt: the candidates it reads are
    expected to come from `build_candidates.py --merge-abbreviations`, so a pair
    may carry variant surfaces, and the prompt lists them.
    """
    return label_single(teacher, cache_dir, pmid, cands, fp, grouped=True)


def label_single(
    teacher, cache_dir: Path, pmid: str, cands: list[Candidate], fp: str,
    grouped: bool = False,
):
    """One request per pair, with that pair's mentions marked in the abstract.

    Each request is a separate process and carries no history, so a pair is judged
    without seeing the other pairs of its abstract. That is the point of the mode:
    it removes the cross-pair reasoning that `label_batch` allows and makes the
    label a property of the pair alone.
    """
    abstract = cands[0].abstract
    out: list[Relation] = []
    rejected: Counter = Counter()
    statuses: Counter = Counter()

    for cand in cands:
        want_ids = [cand.candidate_id]
        cache_file = cache_dir / f"{pmid}__{cand.candidate_id}.json"
        if grouped:
            prompt = prompts.render_grouped(
                abstract,
                cand.pathway_mentions,
                cand.disease_mentions,
                cand.pathway_key,
                cand.disease_key,
                cand.pathway_variants,
                cand.disease_variants,
            )
        else:
            prompt = prompts.render_single(
                abstract,
                cand.pathway_mentions,
                cand.disease_mentions,
                cand.pathway_mentions[0].text,
                cand.disease_mentions[0].text,
            )
        payload, status = _read_cache(cache_file, want_ids, fp, prompt_sha(prompt))

        if payload is None:
            payload, status = _fetch(
                teacher, cache_file, prompt, pmid, want_ids, fp, status
            )
            if payload is None:
                rejected["request_failed"] += 1
                statuses[status.split(":")[0]] += 1
                continue

        try:
            obj = parse_object(payload["raw"])
        except Exception:  # noqa: BLE001
            rejected["unparsable_response"] += 1
            statuses["unparsable"] += 1
            continue

        obj["i"] = 1
        out.extend(ground([obj], [cand], abstract, payload["model"], rejected))
        statuses[status.split(":")[0]] += 1

    worst = "error" if statuses["error"] else statuses.most_common(1)[0][0]
    return out, rejected, worst


def prompt_sha(prompt: str) -> str:
    return hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:16]


def _read_cache(cache_file: Path, want_ids: list[str], fp: str, sent: str):
    """Return (payload, status). A payload answering a different question is a miss.

    `sent` is a digest of the exact user message. The pair ids and the guide
    fingerprint do not determine that message on their own: `single` and
    `grouped` mark every mention of the pair inside the abstract, so a candidate
    whose mention list changes produces a different question under an unchanged
    id and an unchanged guide. Keying on the ids alone served a stale answer as a
    fresh one when the gt_100 mention lists were corrected.

    A payload written before this digest existed has no `prompt_sha` and is
    treated as stale, which costs a re-fetch and buys the guarantee that a cached
    answer was produced by the message about to be sent.
    """
    if not cache_file.exists():
        return None, "cached"
    cached = json.loads(cache_file.read_text())
    if (
        cached.get("candidate_ids") == want_ids
        and cached.get("prompt_fingerprint") == fp
        and cached.get("prompt_sha") == sent
    ):
        return cached, "cached"
    return None, "stale_cache"


def _fetch(teacher, cache_file: Path, prompt: str, pmid: str, want_ids, fp, status):
    """Call the teacher and cache the raw answer. An error is never cached."""
    started = time.time()
    try:
        raw = teacher(prompt)
    except SafeguardRefusal as exc:
        # Counted apart from a failed call. A refusal is a property of the
        # abstract and the model, not of the run, and it will not resolve on a
        # re-run; lumping it with transient errors hides a systematic gap in the
        # corpus behind a number that looks like flakiness.
        return None, f"refused: {exc}"
    except Exception as exc:  # noqa: BLE001 - reported, never cached
        return None, f"error: {exc}"
    payload = {
        "pmid": pmid,
        "model": teacher.name,
        "n_pairs": len(want_ids),
        "candidate_ids": want_ids,
        "prompt_fingerprint": fp,
        "prompt_sha": prompt_sha(prompt),
        "raw": raw,
        "wall_s": round(time.time() - started, 2),
    }
    cache_file.write_text(json.dumps(payload, ensure_ascii=False))
    return payload, ("refetched" if status == "stale_cache" else "fetched")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--indir", type=Path, default=DEFAULT_INDIR)
    ap.add_argument("--candidates", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    ap.add_argument(
        "--mode",
        choices=("batch", "single", "grouped"),
        default="batch",
        help=(
            "batch: one request per abstract carrying all its pairs (default). "
            "single: one request per pair, with that pair's mentions marked in "
            "the abstract, so pairs are judged independently of each other. "
            "grouped: as single, but the prompt also names the surfaces folded "
            "into each entity; pair it with candidates built using "
            "--merge-abbreviations."
        ),
    )
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
    fp = prompt_fingerprint(args.mode)
    label = {
        "batch": label_batch,
        "single": label_single,
        "grouped": label_grouped,
    }[args.mode]
    # The two modes ask different questions and cache different units, so they get
    # different directories as well as different fingerprints.
    cache_dir = args.cache_dir / f"{slug(teacher.name)}__{args.mode}"
    cache_dir.mkdir(parents=True, exist_ok=True)

    pmids = sorted(by_pmid)
    if args.limit:
        pmids = pmids[: args.limit]

    out_path = args.out or (
        args.indir / f"relations_{slug(teacher.name)}_{args.mode}.jsonl"
    )
    n_pairs = sum(len(by_pmid[p]) for p in pmids)
    n_requests = len(pmids) if args.mode == "batch" else n_pairs
    print(
        f"{len(pmids)} abstracts, {n_pairs} pairs, {n_requests} requests, "
        f"mode={args.mode}, teacher={teacher.name}, cache={cache_dir}",
        file=sys.stderr,
    )

    all_rels: list[Relation] = []
    rejected: Counter = Counter()
    statuses: Counter = Counter()
    started = time.time()

    def work(pmid: str):
        return pmid, label(teacher, cache_dir, pmid, by_pmid[pmid], fp)

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
        "mode": args.mode,
        "prompt_fingerprint": fp,
        "raw_flags": RAW_FLAGS,
        "residual_context": RESIDUAL_CONTEXT,
        "schema": SCHEMA_TAG,
        "backend": args.backend,
        "candidates": str(cand_path),
        "n_abstracts": len(pmids),
        "n_pairs_asked": n_pairs,
        "n_requests": n_requests,
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
