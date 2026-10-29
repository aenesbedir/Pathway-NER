#!/usr/bin/env python3
"""
ground_surface_forms.py

Check every surface form in preprocessing/pathway_surface_forms.py against
external vocabularies, so the dictionary rests on citable sources rather than on
hand-written domain knowledge.

Sources, in the order a verdict is taken from them:

  MeSH descriptors
         data/raw/mesh_metabolic_pathways.json (pubmed_api/fetch_mesh_pathways.py)
         Descriptor names and NLM entry terms for the G03 / G02.111 trees. An
         entry term is NLM's own statement that two strings name one concept.
  MeSH substances
         data/raw/mesh_substances.json (pubmed_api/fetch_mesh_substances.py)
         MeSH has no descriptor for "tryptophan metabolism": it holds the
         substance and expresses the process as the /metabolism qualifier. Since
         Recon canonicals are written "<substance> <process>" throughout, most
         forms can only be compared by resolving their substance halves and
         asking whether they land on the same descriptor.
  KEGG / Reactome
         data/raw/{kegg,reactome}_pathways.jsonl — canonical_name and synonyms.
  gt_100 doccano/golden_dataset/gt_100.jsonl — human-reviewed PATHWAY spans.
  corpus data/doccano/disease_pathway_10125_doccano_combined_v1.jsonl — how often
         the form actually occurs, which decides whether a form matters at all.

Matching is token-set based after normalization (lowercase, punctuation to
spaces, trailing "s" removed per token, tokens sorted). MeSH stores inverted
forms — "Cycle, Krebs" beside "Krebs Cycle" — and token-set equality makes both
match without a special case. The same convention is already used in
scripts/compare_query_string_vs_predicted.py.

Verdicts, per surface form:

  mesh_confirmed  the form and its Recon canonical resolve to the SAME MeSH
                  descriptor. NLM says they name one concept.
  mesh_conflict   both resolve, but to DIFFERENT descriptors. The form denotes
                  something MeSH keeps separate from the canonical — e.g.
                  "respiratory chain" is an entry term of Electron Transport,
                  not of Oxidative Phosphorylation.
  mesh_form_only  the form resolves, the canonical does not. No contradiction,
                  but no confirmation either: MeSH has no descriptor to compare.
  mesh_none       the form is not in MeSH as a descriptor. Falls back to the
                  substance verdicts below and to KEGG/Reactome, gt_100 and
                  corpus evidence, all reported alongside.

Substance verdicts, for the "<substance> <process>" forms MeSH cannot name
directly (both the form and its canonical must have that shape):

  substance_confirmed  both substances resolve to the SAME MeSH descriptor and
                       the process words agree in direction. "retinol metabolism"
                       and "vitamin a metabolism" both reduce to Vitamin A. A
                       multi-substance canonical is split first, so "proline
                       metabolism" is confirmed against "arginine and proline
                       metabolism" through its second component.
  substance_direction  same descriptor, opposing process direction — anabolic
                       against catabolic ("purine synthesis" vs the canonical
                       "purine catabolism").
  substance_narrower   both resolve; the form's substance is a DESCENDANT of the
                       canonical's in the MeSH tree. "ceramide metabolism" under
                       "sphingolipid metabolism" is a real subset, not an error.
  substance_broader    the reverse: the form's substance is an ancestor, so the
                       form is wider than the canonical ("sterol metabolism" for
                       "cholesterol metabolism") and will over-match.
  substance_conflict   both resolve to DIFFERENT descriptors with no ancestry
                       between them. The form names another substance than the
                       canonical does.
  substance_unresolved at least one substance has no MeSH descriptor. Every
                       abbreviation lands here ("trp", "gsh", "bcaa"), which is
                       the honest outcome: MeSH cannot speak to them.
  ungrounded           neither route applies.

A verdict is evidence, not a decision: MeSH models concepts, Recon models
metabolic subsystems, and the two do not partition the space the same way. The
output is meant to be read before editing the dictionary, not applied to it
automatically.

Outputs:
  analysis/pathway_surface_forms_grounding.json   per-form record
  stdout                                           summary + the conflict list

Run from the repository root:
    venv310/bin/python3 scripts/ground_surface_forms.py
    venv310/bin/python3 scripts/ground_surface_forms.py --verdict mesh_conflict
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "preprocessing"))

sys.path.insert(0, str(REPO_ROOT / "llm"))
sys.path.insert(0, str(REPO_ROOT / "pubmed_api"))

from booster import process_class  # noqa: E402
from fetch_mesh_substances import components_of, substance_of  # noqa: E402
from pathway_surface_forms import PROCESS_WORDS, build_surface_forms  # noqa: E402

MESH_FILE = REPO_ROOT / "data/raw/mesh_metabolic_pathways.json"
MESH_SUBSTANCE_FILE = REPO_ROOT / "data/raw/mesh_substances.json"
KEGG_FILE = REPO_ROOT / "data/raw/kegg_pathways.jsonl"
REACTOME_FILE = REPO_ROOT / "data/raw/reactome_pathways.jsonl"
GOLD_FILE = REPO_ROOT / "doccano/golden_dataset/gt_100.jsonl"
CORPUS_FILE = REPO_ROOT / "data/doccano/disease_pathway_10125_doccano_combined_v1.jsonl"
SOURCE_FILE = REPO_ROOT / "preprocessing/pathway_surface_forms.py"
OUTPUT_FILE = REPO_ROOT / "analysis/pathway_surface_forms_grounding.json"


def token_key(s: str) -> str:
    """Order-insensitive, plural-insensitive key: 'Cycle, Krebs' == 'Krebs cycle'."""
    words = re.sub(r"[^a-z0-9+]+", " ", s.lower()).split()
    return " ".join(sorted(re.sub(r"s$", "", w) if len(w) > 3 else w for w in words))


_PROCESS_RE = "|".join(re.escape(p) for p in PROCESS_WORDS)


def split_process(text: str) -> tuple[str, str] | None:
    """('retinol', 'metabolism') for '<substance> <process>', else None.

    The substance side peels every trailing process word (see
    fetch_mesh_substances.substance_of); the process returned is the last one,
    which is what carries the anabolic/catabolic direction.
    """
    sub = substance_of(text)
    if not sub:
        return None
    m = re.search(rf"({_PROCESS_RE})\s*$", text.lower().strip())
    return (sub, m.group(1)) if m else None


def substance_verdict(form: str, canonical: str, subs: dict) -> tuple[str, dict]:
    """Compare the substance halves of a form and its canonical via MeSH."""
    f_parts, c_parts = split_process(form), split_process(canonical)
    detail: dict = {}
    if not f_parts or not c_parts:
        return "ungrounded", detail

    f_sub, f_proc = f_parts
    c_sub, c_proc = c_parts
    f_desc = subs.get(f_sub)

    # A multi-substance canonical ("arginine and proline") has no descriptor of
    # its own; each component is resolved and the closest one is used, so a
    # split form is compared against the component it actually names.
    c_components = components_of(c_sub)
    c_resolved = [(comp, subs.get(comp)) for comp in c_components]
    c_sub, c_desc = next(
        ((comp, d) for comp, d in c_resolved if d and f_desc and d["mesh_id"] == f_desc["mesh_id"]),
        next(((comp, d) for comp, d in c_resolved if d), (c_components[0], None)),
    )

    detail = {
        "form_substance": f_sub, "form_descriptor": f_desc,
        "canonical_substance": c_sub, "canonical_descriptor": c_desc,
        "canonical_components": c_components if len(c_components) > 1 else None,
    }
    if not f_desc or not c_desc:
        return "substance_unresolved", detail
    if f_desc["mesh_id"] != c_desc["mesh_id"]:
        f_trees = f_desc.get("tree_numbers") or []
        c_trees = c_desc.get("tree_numbers") or []
        if any(f.startswith(c + ".") for f in f_trees for c in c_trees):
            return "substance_narrower", detail
        if any(c.startswith(f + ".") for f in f_trees for c in c_trees):
            return "substance_broader", detail
        return "substance_conflict", detail

    a, b = process_class(f_proc), process_class(c_proc)
    if a != "neutral" and b != "neutral" and a != b:
        return "substance_direction", detail
    return "substance_confirmed", detail


def load_mesh() -> dict[str, list[dict]]:
    """token_key -> [{mesh_id, name, matched_term}]; names and entry terms alike."""
    index: dict[str, list[dict]] = collections.defaultdict(list)
    for rec in json.loads(MESH_FILE.read_text(encoding="utf-8")):
        for term in [rec["name"], *rec["entry_terms"]]:
            index[token_key(term)].append(
                {"mesh_id": rec["mesh_id"], "name": rec["name"], "matched_term": term}
            )
    return index


def load_db() -> dict[str, list[str]]:
    """token_key -> ['kegg:hsa00020', ...] over canonical names and synonyms."""
    index: dict[str, list[str]] = collections.defaultdict(list)
    for path, tag in ((KEGG_FILE, "kegg"), (REACTOME_FILE, "reactome")):
        for line in path.open(encoding="utf-8"):
            p = json.loads(line)
            for name in [p["canonical_name"], *p.get("synonyms", [])]:
                index[token_key(name)].append(f"{tag}:{p['pathway_id']}")
    return index


def load_gold() -> collections.Counter:
    counts: collections.Counter = collections.Counter()
    for line in GOLD_FILE.open(encoding="utf-8"):
        d = json.loads(line)
        for e in d["entities"]:
            if e["label"] == "PATHWAY":
                counts[token_key(d["text"][e["start_offset"]:e["end_offset"]])] += 1
    return counts


def load_corpus_text() -> tuple[str, str]:
    texts = [json.loads(l)["text"] for l in CORPUS_FILE.open(encoding="utf-8")]
    blob = "\n".join(texts)
    return blob, blob.lower()


def parse_scores() -> dict[str, int]:
    """The '# <score>' comments in pathway_surface_forms.py, keyed by form text.

    Only literal table lines carry a score; generated forms (split, prefix,
    canonical) have none.
    """
    scores: dict[str, int] = {}
    item = re.compile(r'^\s+"((?:[^"\\]|\\.)*)",\s+#\s+(\d+)')
    for line in SOURCE_FILE.read_text(encoding="utf-8").split("\n"):
        m = item.match(line)
        if m:
            scores[m.group(1)] = int(m.group(2))
    return scores


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--output", type=Path, default=OUTPUT_FILE)
    ap.add_argument("--verdict", help="print only forms with this verdict")
    args = ap.parse_args()

    mesh = load_mesh()
    substances = json.loads(MESH_SUBSTANCE_FILE.read_text(encoding="utf-8"))
    db = load_db()
    gold = load_gold()
    blob_cs, blob_ci = load_corpus_text()
    scores = parse_scores()
    forms = build_surface_forms()

    records = []
    for canonical, items in forms.items():
        canon_mesh = mesh.get(token_key(canonical), [])
        canon_ids = {m["mesh_id"] for m in canon_mesh}
        for f in items:
            key = token_key(f.text)
            form_mesh = mesh.get(key, [])
            form_ids = {m["mesh_id"] for m in form_mesh}

            substance_detail: dict = {}
            if not form_mesh:
                verdict, substance_detail = substance_verdict(f.text, canonical, substances)
            elif not canon_mesh:
                verdict = "mesh_form_only"
            elif form_ids & canon_ids:
                verdict = "mesh_confirmed"
            else:
                verdict = "mesh_conflict"

            hay = blob_cs if f.case_sensitive else blob_ci
            needle = f.text if f.case_sensitive else f.text.lower()
            occurrences = len(re.findall(rf"(?<![\w-]){re.escape(needle)}(?![\w-])", hay))

            records.append({
                "canonical": canonical,
                "form": f.text,
                "origin": f.origin,
                "case_sensitive": f.case_sensitive,
                "score_comment": scores.get(f.text),
                "verdict": verdict,
                "mesh_form": [
                    {"mesh_id": m["mesh_id"], "name": m["name"], "via": m["matched_term"]}
                    for m in form_mesh
                ],
                "mesh_canonical": [
                    {"mesh_id": m["mesh_id"], "name": m["name"]} for m in canon_mesh
                ],
                "substance": substance_detail,
                "db_ids": db.get(key, []),
                "gold_count": gold.get(key, 0),
                "corpus_occurrences": occurrences,
            })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.verdict:
        for r in records:
            if r["verdict"] != args.verdict:
                continue
            print(f"{r['corpus_occurrences']:5d}  {r['form']:40s} -> {r['canonical']}")
            if r["mesh_form"]:
                names = ", ".join(m["name"] for m in r["mesh_form"])
                print(f"       MeSH descriptor: {names}   (via {r['mesh_form'][0]['via']})")
            sd = r.get("substance") or {}
            if sd:
                fd = (sd.get("form_descriptor") or {}).get("name", "-")
                cd = (sd.get("canonical_descriptor") or {}).get("name", "-")
                print(f"       substance: {sd['form_substance']!r} -> {fd}   |   "
                      f"canonical {sd['canonical_substance']!r} -> {cd}")
        return 0

    by_verdict = collections.Counter(r["verdict"] for r in records)
    by_origin = collections.Counter((r["origin"], r["verdict"]) for r in records)
    print(f"{len(records)} surface forms")
    for v, n in by_verdict.most_common():
        firing = sum(1 for r in records if r["verdict"] == v and r["corpus_occurrences"])
        print(f"  {v:16s} {n:4d}   ({firing} of them occur in the corpus)")
    print("\nby origin:")
    origins = sorted({o for o, _ in by_origin})
    verdicts = ["mesh_confirmed", "mesh_conflict", "mesh_form_only",
                "substance_confirmed", "substance_narrower", "substance_broader",
                "substance_conflict", "substance_direction",
                "substance_unresolved", "ungrounded"]
    verdicts = [v for v in verdicts if any(by_origin[(o, v)] for o in {o for o, _ in by_origin})]
    short = {v: (v.split("_", 1)[1] if "_" in v else v)[:9] for v in verdicts}
    print(f"  {'origin':16s} " + "  ".join(f"{short[v]:>10s}" for v in verdicts))
    for o in origins:
        cells = "  ".join(f"{by_origin[(o, v)]:>10d}" for v in verdicts)
        print(f"  {o:16s} {cells}")
    print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
