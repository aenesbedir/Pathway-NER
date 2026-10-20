#!/usr/bin/env python3
"""
entity_switch.py

Multiply a labelled relation corpus by switching its entity names.

Every labelled (pathway, disease) pair is copied N times. In each copy every
mention of the pathway is replaced by one other pathway name and every mention
of the disease by one other disease name, drawn from the corpus vocabulary. The
rest of the abstract, the label, the confidence and the evidence sentences are
kept; offsets, the evidence quotes and the shared-sentence spans are recomputed
on the rewritten text.

Why this keeps the label
------------------------
The label is what the abstract CLAIMS about the pair, read from the text, not a
fact about the biology (see `prompts.py`, `# Labels`). "Glycolytic flux was
higher in X than in healthy tissue" states `upregulation` of the marked pathway
in the marked disease whatever the two names are. Switching the names leaves the
claim's wording, comparison and polarity untouched.

The copies are therefore biologically false statements. They are training
material for a classifier that should read the claim rather than memorize which
names tend to go together. They are not facts and must never be used as such;
every record carries an `augmentation` block saying what was switched.

What the switch cannot do
-------------------------
- Words derived from the old entity that are not NER mentions ("glycolytic",
  "Warburg", "lactate", gene symbols) stay in the text. A copy can therefore
  still hint at the original pathway.
- Articles and number agreement are not repaired ("the urea cycle" may become
  "the glycolysis").
- Pairs whose pathway and disease mentions overlap ("urea cycle" inside "urea
  cycle disorders") are skipped: switching one would rewrite part of the other.

Abbreviations
-------------
When the candidate builder merged an abbreviation into its long form, the short
surfaces are listed in `pathway_variants` / `disease_variants`. Those mentions are
replaced by an abbreviation built from the new name's initials, so "inborn
errors of metabolism (IEM) ... IEM" becomes "maple syrup urine disease (MSUD) ...
MSUD" rather than repeating the long name inside its own parenthesis.

Splitting
---------
A copy keeps the PMID of the abstract it was made from. A PMID-level split
therefore keeps every copy on the same side as its source, which is what stops
the copies from leaking a validation abstract into training.
`train_relation_evidence.py --augment` goes further and drops every copy whose
PMID landed in validation, so validation stays real abstracts only.

Outputs
-------
One folder per (source corpus, n_variants, seed), so runs with different
settings never overwrite each other:

    data/processed/relation/entity_switch/<source folder>_n<N>_seed<S>/
        entity_switch_candidates.jsonl   abstracts and mentions after the switch
        entity_switch_relations.jsonl    labels, joined on candidate_id
        entity_switch.manifest.json      script, git sha, command, input and
                                         output sha256s, counts, rejections

The run in use for training (2026-10-21):

    data/processed/relation/entity_switch/silver_2k_full_n5_seed42/

    python3 relation_extraction/entity_switch/entity_switch.py --n-variants 5 --seed 42
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schema import (  # noqa: E402
    Candidate,
    Mention,
    RecordError,
    Relation,
    candidate_id,
    normalize_surface,
    read_jsonl,
)

REPO = Path(__file__).resolve().parents[2]
DEFAULT_RELATIONS = REPO / "data/processed/relation/silver_2k_full/relations_llm_opus48_same_sentence.jsonl"
DEFAULT_CANDIDATES = REPO / "data/processed/relation/silver_2k_full/candidates_same_sentence.jsonl"
OUT_ROOT = REPO / "data/processed/relation/entity_switch"

METHOD = "entity_switch"
PREFIX = "entity_switch"


# --------------------------------------------------------------------------- #
# Vocabulary


def is_short_form(surface: str) -> bool:
    """An abbreviation-like surface: one token, short, carrying a capital."""
    return " " not in surface and len(surface) <= 8 and any(ch.isupper() for ch in surface)


def build_pool(cands: list[dict], side: str) -> dict[str, str]:
    """Map each entity key in the corpus to the surface it is most often written as.

    Short forms are excluded: a name like "AD" cannot stand in for a long form,
    and it would be the long form that the switch writes into the text.
    """
    surfaces: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for c in cands:
        key = c[f"{side}_key"]
        for m in c[f"{side}_mentions"]:
            if normalize_surface(m["text"]) == key:
                surfaces[key][m["text"]] += 1
    pool = {}
    for key, counter in surfaces.items():
        surface = counter.most_common(1)[0][0]
        if not is_short_form(surface):
            pool[key] = surface
    return pool


def initials(name: str) -> str:
    """Abbreviation from the initials of a multi-word name, or "" for one word."""
    words = [w for w in name.replace("-", " ").split() if w[:1].isalnum()]
    if len(words) < 2:
        return ""
    return "".join(w[0] for w in words).upper()


# --------------------------------------------------------------------------- #
# Rewriting


ARTICLE_RE = re.compile(r"(?:^|(?<=[\s(\[]))(an?|An?) $")


def sentence_initial(abstract: str, start: int) -> bool:
    """True if nothing but whitespace or an opening bracket separates `start` from a sentence end."""
    i = start - 1
    while i >= 0 and (abstract[i].isspace() or abstract[i] in "([\"'"):
        i -= 1
    return i < 0 or abstract[i] in ".!?:"


def replacement_for(
    abstract: str, mention: dict, key: str, variants: set[str], new_name: str, new_abbr: str
) -> str:
    """The text a mention becomes. Short forms take the new abbreviation."""
    surface = mention["text"]
    norm = normalize_surface(surface)
    if norm != key and norm in variants and new_abbr:
        # Keep a plural short form plural: "ALLs" -> "MSUDs".
        return new_abbr + ("s" if surface.endswith("s") and not surface.isupper() else "")
    if sentence_initial(abstract, mention["start"]) and not new_name[:1].isupper():
        return new_name[:1].upper() + new_name[1:]
    return new_name


def article_for(old_article: str, word: str) -> str:
    """'a' or 'an' for `word`, in the casing of the article it replaces."""
    an = word[:1].lower() in "aeiou"
    new = "an" if an else "a"
    return new.capitalize() if old_article[:1].isupper() else new


class Edits:
    """Non-overlapping text replacements and the offset map they induce.

    An edit is (start, end, replacement, lead): `lead` characters at the front of
    the replacement are not part of the mention - they are a repaired article
    ("a " -> "an ") that the edit was widened to cover.
    """

    def __init__(self, edits: list[tuple[int, int, str, int]]):
        self.edits = sorted(edits)

    def overlapping(self) -> bool:
        return any(a[1] > b[0] for a, b in zip(self.edits, self.edits[1:]))

    def apply(self, text: str) -> tuple[str, dict[int, tuple[int, int]]]:
        """Rewritten text, and the new (start, end) of the mention behind each edit.

        The second value is keyed by the edit's original end, which is the
        mention's original end whether or not an article was absorbed.
        """
        out, cur, pos, spans = [], 0, 0, {}
        for s, e, new, lead in self.edits:
            chunk = text[cur:s]
            out.append(chunk)
            pos += len(chunk)
            spans[e] = (pos + lead, pos + len(new))
            out.append(new)
            pos += len(new)
            cur = e
        out.append(text[cur:])
        return "".join(out), spans

    def remap(self, pos: int) -> int:
        """New offset of an old position that is not strictly inside an edit."""
        shift = 0
        for s, e, new, _ in self.edits:
            if e <= pos:
                shift += len(new) - (e - s)
        return pos + shift

    def cuts(self, start: int, end: int) -> bool:
        """True if an edit straddles a boundary of [start, end)."""
        return any(s < start < e or s < end < e for s, e, _, _ in self.edits)


def switch_one(cand: dict, rel: dict, new_pw: str, new_ds: str) -> tuple[dict, dict] | str:
    """Build the switched candidate and relation, or return a rejection reason."""
    pw_variants = set(cand.get("pathway_variants", []))
    ds_variants = set(cand.get("disease_variants", []))
    pw_abbr, ds_abbr = initials(new_pw), initials(new_ds)

    abstract = cand["abstract"]
    edits = []
    for side, key, variants, name, abbr in (
        ("pathway", cand["pathway_key"], pw_variants, new_pw, pw_abbr),
        ("disease", cand["disease_key"], ds_variants, new_ds, ds_abbr),
    ):
        for m in cand[f"{side}_mentions"]:
            new = replacement_for(abstract, m, key, variants, name, abbr)
            start, lead = m["start"], 0
            art = ARTICLE_RE.search(abstract[max(0, start - 4) : start])
            if art:
                fixed = article_for(art.group(1), new) + " "
                start -= len(art.group(0))
                new, lead = fixed + new, len(fixed)
            edits.append((start, m["end"], new, lead))
    ed = Edits(edits)
    if ed.overlapping():
        return "overlapping_mentions"

    new_abstract, spans = ed.apply(abstract)

    def moved(m: dict, label: str) -> Mention:
        s, e = spans[m["end"]]
        return Mention(new_abstract[s:e], s, e, label)

    pw_mentions = [moved(m, "PATHWAY") for m in cand["pathway_mentions"]]
    ds_mentions = [moved(m, "DISEASE") for m in cand["disease_mentions"]]

    shared = []
    for s, e in cand["shared_sentences"]:
        if ed.cuts(s, e):
            return "edit_crosses_sentence_boundary"
        shared.append((ed.remap(s), ed.remap(e)))

    evidence = []
    for quote in rel.get("evidence") or []:
        at = abstract.find(quote)
        if at < 0:
            return "evidence_not_in_source_abstract"
        end = at + len(quote)
        if ed.cuts(at, end):
            return "edit_crosses_evidence_boundary"
        evidence.append(new_abstract[ed.remap(at) : ed.remap(end)])

    pw_key, ds_key = normalize_surface(new_pw), normalize_surface(new_ds)
    new_cand = Candidate(
        candidate_id=candidate_id(cand["pmid"], pw_key, ds_key),
        pmid=str(cand["pmid"]),
        abstract=new_abstract,
        pathway_key=pw_key,
        disease_key=ds_key,
        pathway_mentions=pw_mentions,
        disease_mentions=ds_mentions,
        shared_sentences=shared,
        stratum=cand["stratum"],
        pathway_variants=[pw_abbr.lower()] if pw_variants and pw_abbr else [],
        disease_variants=[ds_abbr.lower()] if ds_variants and ds_abbr else [],
    )

    # The relation row points at one mention of each entity; keep pointing at the
    # same one after the rewrite.
    def primary(side: str, mentions: list[Mention]) -> Mention | None:
        src = rel[side]
        for old, new in zip(cand[f"{side}_mentions"], mentions):
            if old["start"] == src["start"] and old["end"] == src["end"]:
                return new
        return None

    pw_primary, ds_primary = primary("pathway", pw_mentions), primary("disease", ds_mentions)
    if pw_primary is None or ds_primary is None:
        return "relation_mention_not_in_candidate"

    new_rel = Relation(
        pmid=str(cand["pmid"]),
        disease=ds_primary,
        pathway=pw_primary,
        label=rel["label"],
        evidence=evidence,
        relation_source=f"{METHOD}:{rel.get('relation_source', '')}",
        confidence=rel.get("confidence", "medium"),
        candidate_id=new_cand.candidate_id,
        stratum=rel.get("stratum", cand["stratum"]),
    )
    try:
        new_cand.check()
        new_rel.check(new_abstract)
    except RecordError as exc:
        return f"schema_invalid: {str(exc)[:50]}"
    return new_cand.to_json(), new_rel.to_json()


# --------------------------------------------------------------------------- #


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_state() -> dict:
    def run(*args):
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()

    return {"git_sha": run("rev-parse", "HEAD"), "git_dirty": bool(run("status", "--porcelain", "--", str(Path(__file__))))}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--relations", type=Path, default=DEFAULT_RELATIONS)
    ap.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    ap.add_argument(
        "--outdir", type=Path, default=None,
        help="default: <OUT_ROOT>/<source folder>_n<N>_seed<S>",
    )
    ap.add_argument("--n-variants", type=int, default=5, help="switched copies per labelled pair")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, default=0, help="only the first N labelled pairs, for a smoke test")
    args = ap.parse_args()
    if args.outdir is None:
        args.outdir = OUT_ROOT / f"{args.relations.parent.name}_n{args.n_variants}_seed{args.seed}"

    cands_list = read_jsonl(args.candidates)
    cands = {c["candidate_id"]: c for c in cands_list}
    rels = read_jsonl(args.relations)
    if args.limit:
        rels = rels[: args.limit]

    pw_pool = build_pool(cands_list, "pathway")
    ds_pool = build_pool(cands_list, "disease")
    pw_keys, ds_keys = sorted(pw_pool), sorted(ds_pool)

    args.outdir.mkdir(parents=True, exist_ok=True)
    out_cands = args.outdir / f"{PREFIX}_candidates.jsonl"
    out_rels = args.outdir / f"{PREFIX}_relations.jsonl"

    rejected: collections.Counter = collections.Counter()
    labels: collections.Counter = collections.Counter()
    seen_ids: set[str] = set()
    n_written, n_sources_used = 0, 0

    with open(out_cands, "w", encoding="utf-8") as fc, open(out_rels, "w", encoding="utf-8") as fr:
        for rel in rels:
            cand = cands.get(rel["candidate_id"])
            if cand is None:
                rejected["candidate_not_found"] += 1
                continue
            # One generator per source pair, so a copy does not change when the
            # file is filtered or reordered.
            rng = random.Random(f"{args.seed}:{rel['candidate_id']}")
            new_pws = rng.sample([k for k in pw_keys if k != cand["pathway_key"]], args.n_variants)
            new_dss = rng.sample([k for k in ds_keys if k != cand["disease_key"]], args.n_variants)

            used = False
            for i, (pk, dk) in enumerate(zip(new_pws, new_dss)):
                result = switch_one(cand, rel, pw_pool[pk], ds_pool[dk])
                if isinstance(result, str):
                    rejected[result] += 1
                    continue
                c_json, r_json = result
                if c_json["candidate_id"] in seen_ids or c_json["candidate_id"] in cands:
                    rejected["duplicate_candidate_id"] += 1
                    continue
                seen_ids.add(c_json["candidate_id"])
                meta = {
                    "method": METHOD,
                    "variant": i,
                    "seed": args.seed,
                    "source_candidate_id": rel["candidate_id"],
                    "source_pathway": cand["pathway_key"],
                    "source_disease": cand["disease_key"],
                    "new_pathway": pk,
                    "new_disease": dk,
                }
                c_json["augmentation"] = meta
                r_json["augmentation"] = meta
                fc.write(json.dumps(c_json, ensure_ascii=False) + "\n")
                fr.write(json.dumps(r_json, ensure_ascii=False) + "\n")
                labels[r_json["label"]] += 1
                n_written += 1
                used = True
            n_sources_used += used

    manifest = {
        "method": METHOD,
        "description": (
            "Every mention of the labelled pathway and disease replaced by another "
            "corpus name; label, confidence and evidence wording kept. Copies are "
            "biologically false statements for classifier training only."
        ),
        "script": str(Path(__file__).relative_to(REPO)),
        **git_state(),
        "command": " ".join(["python3", *sys.argv]),
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": {
            "relations": str(args.relations),
            "relations_sha256": sha256(args.relations),
            "candidates": str(args.candidates),
            "candidates_sha256": sha256(args.candidates),
        },
        "n_variants": args.n_variants,
        "seed": args.seed,
        "limit": args.limit,
        "pool_sizes": {"pathway": len(pw_pool), "disease": len(ds_pool)},
        "n_source_pairs": len(rels),
        "n_source_pairs_used": n_sources_used,
        "n_written": n_written,
        "labels": dict(labels.most_common()),
        "rejected": dict(rejected.most_common()),
        "outputs": {
            "candidates": str(out_cands),
            "candidates_sha256": sha256(out_cands),
            "relations": str(out_rels),
            "relations_sha256": sha256(out_rels),
        },
    }
    (args.outdir / f"{PREFIX}.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: manifest[k] for k in ("pool_sizes", "n_source_pairs", "n_source_pairs_used", "n_written", "labels", "rejected")}, indent=2))


if __name__ == "__main__":
    main()
