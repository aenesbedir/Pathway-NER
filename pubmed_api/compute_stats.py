#!/usr/bin/env python3
"""
compute_stats.py

Reads all pipeline output files and rewrites the statistics sections
in STATS.md. Run after any pipeline step to keep the doc current.

Run:
  cd /home/enes/NER-pipeline
  python3 pubmed_api/compute_stats.py
"""

import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

STATS_FILE = Path("pubmed_api/STATS.md")

# ─── Helpers ─────────────────────────────────────────────────────────────────

def load_json(path):
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.open(encoding="utf-8") if line.strip()]


def na(val, fmt=None):
    if val is None:
        return "—"
    if fmt:
        return fmt.format(val)
    return str(val)


def pct(num, den):
    if not den:
        return "—"
    return f"{100 * num / den:.1f}%"


# ─── Collectors ──────────────────────────────────────────────────────────────

def disease_stats():
    rows = []
    total_unique = 0
    seen = set()
    for tree, label in [("C18", "Metabolic / Nutritional"), ("C04", "Neoplasms (Cancer)"), ("C10_574", "Neurodegenerative")]:
        # Handle both lowercase (legacy c18) and uppercase filenames
        path = f"data/raw/mesh_{tree}_diseases.json"
        if not Path(path).exists():
            path = f"data/raw/mesh_{tree.lower()}_diseases.json"
        data = load_json(path)
        count = len(data) if data else "—"
        if data:
            for d in data:
                if d["mesh_id"] not in seen:
                    seen.add(d["mesh_id"])
                    total_unique += 1
        rows.append(f"| {label} | {tree.replace('_', '.')} | {count} |")
    rows.append(f"| **Total unique (combined)** | — | **{total_unique or '—'}** |")
    return rows


def selected_stats():
    data = load_json("data/raw/selected_diseases.json")
    if not data:
        return {}, []
    by_cat = Counter(d.get("category", "unknown") for d in data)
    total = len(data)
    rows = []
    for cat, cnt in sorted(by_cat.items()):
        rows.append(f"| {cat.capitalize()} | {cnt} |")
    rows.append(f"| **Total** | **{total}** |")
    names_by_cat = defaultdict(list)
    for d in data:
        names_by_cat[d.get("category", "unknown")].append(d["name"])
    return names_by_cat, rows


def pathway_stats():
    data = load_json("unique_pathways_from_recon.json")
    return len(data) if data else None


def pair_stats():
    data = load_json("data/raw/pathway_disease_pairs.json")
    if not data:
        return None
    total_pairs = None  # we don't store total searched, only hits
    hit_pairs = len(data)
    all_pmids = {pmid for pair in data for pmid in pair["pmids"]}
    pmids_per_cat = defaultdict(set)
    for pair in data:
        cat = pair.get("disease_category", "unknown")
        for pmid in pair["pmids"]:
            pmids_per_cat[cat].add(pmid)
    return {
        "hit_pairs": hit_pairs,
        "unique_pmids": len(all_pmids),
        "pmids_per_cat": {k: len(v) for k, v in pmids_per_cat.items()},
        "pairs_by_cat": Counter(p.get("disease_category", "unknown") for p in data),
    }


def article_stats():
    articles = load_json("data/raw/articles.json")
    if not articles:
        return None
    total = len(articles)
    has_full = sum(1 for a in articles if a.get("has_full_text"))
    has_abstract = sum(1 for a in articles if a.get("abstract"))
    has_mesh = sum(1 for a in articles if a.get("mesh_headings"))
    has_doi = sum(1 for a in articles if a.get("doi"))
    pub_type_counts = Counter(pt for a in articles for pt in a.get("pub_types", []))
    return {
        "total": total,
        "has_full_text": has_full,
        "abstract_only": total - has_full,
        "has_abstract": has_abstract,
        "has_mesh": has_mesh,
        "has_doi": has_doi,
        "full_text_rate": pct(has_full, total),
        "top_pub_types": pub_type_counts.most_common(5),
    }


# ─── Markdown builder ────────────────────────────────────────────────────────

def build_stats_md(names_by_cat, selected_rows, disease_rows, n_pathways, pairs, articles):
    today = date.today().isoformat()

    # Disease details blocks
    detail_blocks = ""
    for cat in ("cancer", "neurodegenerative", "metabolic"):
        names = sorted(names_by_cat.get(cat, []))
        cnt = len(names)
        joined = ", ".join(names)
        detail_blocks += f"""
<details>
<summary>{cat.capitalize()} ({cnt})</summary>

{joined}

</details>
"""

    # Pair stats block
    if pairs:
        pair_rows = "\n".join([
            f"| Total pair hits (≥1 PMID) | {pairs['hit_pairs']} |",
            f"| Unique PMIDs collected | {pairs['unique_pmids']} |",
            f"| Max PMIDs per pair (cap) | 20 |",
        ])
        pair_by_cat = "\n".join(
            f"| {cat.capitalize()} | {pairs['pairs_by_cat'].get(cat, 0)} pairs | {pairs['pmids_per_cat'].get(cat, 0)} PMIDs |"
            for cat in ("cancer", "neurodegenerative", "metabolic")
        )
        pair_section = f"""
| Metric | Value |
|---|---|
{pair_rows}

### Hits by disease category

| Category | Pair hits | Unique PMIDs |
|---|---|---|
{pair_by_cat}
"""
    else:
        pair_section = "\n*Not yet run. Update after running Step 2.*\n\n| Metric | Value |\n|---|---|\n| Total pair hits | — |\n| Unique PMIDs | — |\n"

    # Article stats block
    if articles:
        pub_type_rows = "\n".join(
            f"| {pt} | {cnt} |" for pt, cnt in articles.get("top_pub_types", [])
        )
        art_section = f"""
| Metric | Value |
|---|---|
| Total articles fetched | {articles['total']} |
| Has full text (PMC) | {articles['has_full_text']} |
| Abstract only | {articles['abstract_only']} |
| Has abstract | {articles['has_abstract']} |
| Has MeSH headings | {articles['has_mesh']} |
| Has DOI | {articles['has_doi']} |
| Full text rate | {articles['full_text_rate']} |

### Top publication types

| Type | Count |
|---|---|
{pub_type_rows}
"""
    else:
        art_section = "\n*Not yet run. Update after running Step 3.*\n\n| Metric | Value |\n|---|---|\n| Total articles fetched | — |\n| Has full text (PMC) | — |\n| Abstract only | — |\n| Full text rate | — |\n"

    selected_table = "\n".join(selected_rows)
    disease_table = "\n".join(disease_rows)
    n_path = na(n_pathways)

    return f"""# Pipeline Statistics

Auto-updated by `compute_stats.py` after each run. Edit header sections manually if needed.

---

## Disease Corpus

| Source | Tree | Descriptors |
|---|---|---|
{disease_table}

### Selected diseases (`selected_diseases.json`)

| Category | Count |
|---|---|
{selected_table}
{detail_blocks}

---

## Pathways

| Source | Count |
|---|---|
| Recon3D unique pathways | {n_path} |

---

## Pair Search (`fetch_pathway_disease_pairs.py`)
{pair_section}

---

## Article Fetch (`fetch_articles.py`)
{art_section}

---

## Last updated

<!-- updated by compute_stats.py -->
{today}
"""


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    disease_rows = disease_stats()
    names_by_cat, selected_rows = selected_stats()
    n_pathways = pathway_stats()
    pairs = pair_stats()
    articles = article_stats()

    md = build_stats_md(names_by_cat, selected_rows, disease_rows, n_pathways, pairs, articles)
    STATS_FILE.write_text(md, encoding="utf-8")
    print(f"Updated {STATS_FILE}")

    # Quick summary to stdout
    print(f"  Diseases selected : {sum(len(v) for v in names_by_cat.values())}")
    print(f"  Pathways          : {n_pathways}")
    if pairs:
        print(f"  Pair hits         : {pairs['hit_pairs']}  ({pairs['unique_pmids']} unique PMIDs)")
    if articles:
        print(f"  Articles fetched  : {articles['total']}  ({articles['has_full_text']} full text, {articles['full_text_rate']})")


if __name__ == "__main__":
    main()
