#!/usr/bin/env python3
"""
synth_generate.py

Generate KG-seeded synthetic abstracts for the synthetic-data probe.

THROWAWAY PROBE. See `synth_kg_seed.py` for the framing.

Each seed pair from SMPDB is written about once per requested relation class. The
knowledge graph decides which pair is discussed; the requested class decides what
is claimed; neither becomes the label. The output is a `candidates.jsonl` in
exactly the shape `run_teacher.py` consumes, so the filter step is the existing
teacher run over new text rather than new judging code.

Grounding, on the way in as much as on the way out
--------------------------------------------------
A generated paragraph is kept only if the entity surfaces it was told to use
appear in it verbatim, the offsets resolve, and the returned evidence sentence is
a verbatim substring. This is the same discipline `run_teacher.py` applies to
annotations, for the same reason: a surface that does not resolve to an offset
cannot be a training instance, however good the prose reads.

Caching mirrors `run_teacher.py`: one file per (seed, class), keyed on a
fingerprint of the prompt text and the CLI invocation, and an error is never
cached as a success.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import synth_prompts
from run_teacher import RAW_FLAGS, parse_object, slug
from schema import Candidate, Mention, RecordError, candidate_id, write_jsonl

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SEEDS = REPO / "data/processed/relation/synth_probe/kg_seeds.jsonl"
DEFAULT_OUT = REPO / "data/processed/relation/synth_probe/kg_seeded"
DEFAULT_CACHE = REPO / "data/raw/relation_synth_cache"

CLASSES = ("upregulation", "downregulation", "association", "no_association_stated", "none")


class ClaudeCLI:
    """Generator backed by the local `claude` CLI, stripped the same way the
    teacher is. Separate from `run_teacher.ClaudeCLI` only in its system prompt."""

    def __init__(self, model: str, timeout: int = 300):
        self.model = model
        self.timeout = timeout
        self.name = f"llm:{model}"

    def __call__(self, user_prompt: str) -> str:
        cmd = [
            "claude", "-p", user_prompt, "--model", self.model, *RAW_FLAGS,
            "--append-system-prompt", synth_prompts.SYSTEM,
            "--output-format", "text",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr.strip()[:300]}")
        out = proc.stdout.strip()
        if not out:
            raise RuntimeError("claude returned an empty response")
        return out


def prompt_fingerprint() -> str:
    parts = [synth_prompts.SYSTEM, synth_prompts.GUIDE, *synth_prompts.TARGETS.values(), *RAW_FLAGS]
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:12]


def surfaces(disease: str, pathway: str) -> tuple[str, str]:
    """The exact strings the paragraph must contain.

    The disease name is used as SMPDB writes it, minus a parenthesised
    abbreviation, which the generator would otherwise be forced to reproduce
    including the brackets. The pathway is the Recon name, which is lowercase;
    that is the surface the pathway NER model tags, so it is the surface the
    student has to learn to read.
    """
    d = re.sub(r"\s*\([^)]*\)\s*$", "", disease).strip()
    return d, pathway.strip()


def build(seed: dict, label: str, obj: dict, model: str, rejected: collections.Counter):
    """Turn one generated object into a Candidate, or reject it with a reason."""
    abstract = str(obj.get("abstract") or "").strip()
    if len(abstract) < 200:
        rejected["abstract_too_short"] += 1
        return None
    d_surface, p_surface = surfaces(seed["disease"], seed["recon_pathway"])

    d_at = abstract.find(d_surface)
    if d_at < 0:
        rejected["disease_surface_absent"] += 1
        return None
    p_at = abstract.find(p_surface)
    if p_at < 0:
        rejected["pathway_surface_absent"] += 1
        return None

    evidence = str(obj.get("evidence") or "").strip()
    if label == "none":
        evidence = ""
    elif not evidence:
        rejected["missing_evidence"] += 1
        return None
    elif evidence not in abstract:
        rejected["evidence_not_verbatim"] += 1
        return None

    identity = "\x1f".join((seed["disease"], seed["recon_pathway"], label))
    pmid = "KG" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
    cand = Candidate(
        candidate_id=candidate_id(pmid, p_surface.lower(), d_surface.lower()),
        pmid=pmid,
        abstract=abstract,
        pathway_key=p_surface.lower(),
        disease_key=d_surface.lower(),
        pathway_mentions=[Mention(p_surface, p_at, p_at + len(p_surface), "PATHWAY")],
        disease_mentions=[Mention(d_surface, d_at, d_at + len(d_surface), "DISEASE")],
        shared_sentences=[],
        stratum="doc_level",
    )
    try:
        cand.check()
    except RecordError as exc:
        rejected[f"schema_invalid:{exc}"[:60]] += 1
        return None
    return cand, {
        "candidate_id": cand.candidate_id,
        "pmid": cand.pmid,
        "expected_label": label,
        "disease": seed["disease"],
        "recon_pathway": seed["recon_pathway"],
        "smpdb_pathway": seed["smpdb_pathway"],
        "metabolite_jaccard": seed["metabolite_jaccard"],
        "generator": model,
        "evidence_requested": evidence,
        "method": "kg_seeded",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=Path, default=DEFAULT_SEEDS)
    ap.add_argument("--outdir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--model", default="opus")
    ap.add_argument("--classes", nargs="+", default=list(CLASSES), choices=CLASSES)
    ap.add_argument("--n-seeds", type=int, default=20, help="seeds to write about")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    seeds = [json.loads(l) for l in args.seeds.read_text().splitlines() if l.strip()]
    # One seed per disease, best-scoring first: writing about the same disease
    # twice under two Recon names would duplicate the text, not diversify it.
    picked, seen_disease = [], set()
    for s in seeds:
        if s["disease"] in seen_disease:
            continue
        seen_disease.add(s["disease"])
        picked.append(s)
        if len(picked) >= args.n_seeds:
            break

    gen = ClaudeCLI(args.model)
    fp = prompt_fingerprint()
    cache_dir = args.cache_dir / f"{slug(gen.name)}__{fp}"
    cache_dir.mkdir(parents=True, exist_ok=True)

    jobs = [(s, c) for s in picked for c in args.classes]
    print(
        f"{len(picked)} seeds x {len(args.classes)} classes = {len(jobs)} requests, "
        f"model={gen.name}, cache={cache_dir}",
        file=sys.stderr,
    )

    rejected: collections.Counter = collections.Counter()
    statuses: collections.Counter = collections.Counter()
    started = time.time()

    def work(job):
        seed, label = job
        key = hashlib.sha1(
            f"{seed['disease']}\x1f{seed['recon_pathway']}\x1f{label}".encode()
        ).hexdigest()[:16]
        cache_file = cache_dir / f"{key}.json"
        if cache_file.exists():
            return seed, label, json.loads(cache_file.read_text()), "cached"
        d_surface, p_surface = surfaces(seed["disease"], seed["recon_pathway"])
        prompt = synth_prompts.render(
            seed["disease"], seed["recon_pathway"], label, d_surface, p_surface
        )
        try:
            raw = gen(prompt)
        except Exception as exc:  # noqa: BLE001 - reported, never cached
            return seed, label, None, f"error: {exc}"
        payload = {"seed": seed, "label": label, "model": gen.name,
                   "prompt_fingerprint": fp, "raw": raw}
        cache_file.write_text(json.dumps(payload, ensure_ascii=False))
        return seed, label, payload, "fetched"

    out_cands, expected = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for done, (seed, label, payload, status) in enumerate(pool.map(work, jobs), 1):
            statuses[status.split(":")[0]] += 1
            if payload is None:
                print(f"  {seed['disease']} / {label}: {status}", file=sys.stderr)
                rejected["request_failed"] += 1
                continue
            try:
                obj = parse_object(payload["raw"])
            except Exception:  # noqa: BLE001
                rejected["unparsable_response"] += 1
                continue
            made = build(seed, label, obj, payload["model"], rejected)
            if made is None:
                continue
            cand, meta = made
            out_cands.append(cand)
            expected.append(meta)
            if done % 20 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)} requests, {len(out_cands)} kept", file=sys.stderr)

    args.outdir.mkdir(parents=True, exist_ok=True)
    n = write_jsonl(args.outdir / "candidates.jsonl", out_cands)
    write_jsonl(args.outdir / "expected.jsonl", expected)

    summary = {
        "method": "kg_seeded",
        "generator": gen.name,
        "prompt_fingerprint": fp,
        "seeds": str(args.seeds),
        "n_seeds": len(picked),
        "classes": list(args.classes),
        "n_requests": len(jobs),
        "n_generated": n,
        "expected_labels": dict(collections.Counter(e["expected_label"] for e in expected).most_common()),
        "rejected": dict(rejected.most_common()),
        "request_status": dict(statuses.most_common()),
        "wall_s": round(time.time() - started, 1),
        "outdir": str(args.outdir),
    }
    (args.outdir / "generation.summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
