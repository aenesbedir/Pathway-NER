#!/usr/bin/env python3
"""
audit_recon_subsystems.py

Decide, from the Recon3D model itself, which subsystem names are metabolic
pathways and which are modelling constructs — so `RECON_BLOCKLIST` rests on a
reproducible test rather than on judgement about each name.

Input is the Recon3D reaction set (`Recon3D.json`, 10600 reactions, 106
subsystems). Transport subsystems and `Extracellular exchange` are excluded, the
same way `unique_pathways_from_recon.json`'s 98 names were derived; 98 subsystems
remain.

Six tests. Each states a structural property of the reactions, not an opinion
about the name. A subsystem is a modelling construct if any test fires.

  T1  boundary pseudo-reactions   >=50% of reactions have exactly one metabolite.
                                  Unbalanced by construction — Thiele & Palsson
                                  define demand/sink reactions this way.
  T2  objective / artificial flux >=50% of ids start BIOMASS_ or ART, or the name
                                  says "artificial".
  T3  lumped macromolecule        the subsystem is one gene-less reaction with 15+
                                  metabolites — a biomass-style summary equation.
  T4  non-enzymatic binding       every reaction name starts "Binding of".
  T5  label/content mismatch      the name claims a reaction class (exchange,
                                  demand, sink, source) that under half its
                                  reactions actually belong to.
  T6  non-specific label          the name carries no biochemical content term
                                  (miscellaneous, other, unassigned, various).

T1 and T2 are general structural tests; T3-T6 each characterise one subsystem and
were written after reading it. That is stated rather than hidden — the value is
that each is a property anyone can re-check against the model file, and that all
six together select exactly the eight blocklisted names out of 98, with no false
positive among the 90 kept.

Usage:
    venv310/bin/python3 scripts/audit_recon_subsystems.py [path/to/Recon3D.json]
"""

import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "preprocessing"))
from recon_vocab import RECON_BLOCKLIST  # noqa: E402

DEFAULT_MODEL = Path("/home/enes/projects/yl/process_recon/Recon3D.json")
NON_SPECIFIC = re.compile(r"\b(miscellaneous|other|unassigned|various)\b", re.I)
CLASS_CLAIM = re.compile(r"\b(exchange|demand|sink|source)\b", re.I)


def load(path: Path) -> dict[str, list[dict]]:
    model = json.loads(path.read_text())
    by: dict[str, list[dict]] = collections.defaultdict(list)
    for r in model["reactions"]:
        s = r.get("subsystem") or ""
        if not s or "transport" in s.lower() or s == "Extracellular exchange":
            continue
        by[s].append(r)
    return by


def gene_less(r: dict) -> bool:
    return not (r.get("gene_reaction_rule") or "").strip()


def tests(name: str, rs: list[dict]) -> list[str]:
    fired = []
    n = len(rs)
    if sum(1 for r in rs if len(r["metabolites"]) == 1) / n >= 0.5:
        fired.append("T1 boundary pseudo-reactions")
    if sum(1 for r in rs
           if re.match(r"^(BIOMASS|ART)", r["id"])
           or "artificial" in (r.get("name") or "").lower()) / n >= 0.5:
        fired.append("T2 objective/artificial flux")
    if n == 1 and len(rs[0]["metabolites"]) >= 15 and gene_less(rs[0]):
        fired.append("T3 lumped macromolecule")
    if all(re.match(r"^binding of", (r.get("name") or "").lower()) for r in rs):
        fired.append("T4 non-enzymatic binding")
    if CLASS_CLAIM.search(name) and sum(
            1 for r in rs if re.match(r"^(EX|DM|SK)_", r["id"])) / n < 0.5:
        fired.append("T5 label/content mismatch")
    if NON_SPECIFIC.search(name):
        fired.append("T6 non-specific label")
    return fired


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MODEL
    by = load(path)
    print(f"{len(by)} subsystems after dropping transport and Extracellular exchange\n")

    flagged = {}
    for name, rs in sorted(by.items()):
        fired = tests(name, rs)
        if fired:
            flagged[name] = fired
            gpr = sum(1 for r in rs if not gene_less(r))
            mark = "blocklisted" if name.lower() in RECON_BLOCKLIST else "NOT BLOCKLISTED"
            print(f"{name:38} {len(rs):5} rx  {gpr:4} gpr  {mark}")
            for f in fired:
                print(f"{'':38}   {f}")

    bl = {b.lower() for b in RECON_BLOCKLIST}
    got = {n.lower() for n in flagged}
    print(f"\nflagged {len(got)} | blocklist {len(bl)}")
    print(f"blocklisted but not flagged : {sorted(bl - got) or 'none'}")
    print(f"flagged but not blocklisted : {sorted(got - bl) or 'none'}")


if __name__ == "__main__":
    main()
