#!/usr/bin/env python3
"""
select_diseases.py

Curates a list of ~100 diseases from fetched MeSH data covering:
  - Cancer / Neoplasms          (~40)
  - Neurodegenerative diseases  (~30)
  - Metabolic diseases          (~30)

Reads MeSH JSON files produced by fetch_mesh_diseases.py and looks up
each target disease name. Falls back to partial match if exact not found.

Input:  data/raw/mesh_*.json
Output: data/raw/selected_diseases.json
  [{mesh_id, name, synonyms, tree_numbers, category}]

Run:
  cd /home/enes/NER-pipeline
  python3 pubmed_api/select_diseases.py
"""

import json
import logging
import os
import time
from pathlib import Path

import requests

FALLBACK_API_KEY = "d4e795e70597e6edfa4d1282886100ecee08"
API_KEY = os.environ.get("NCBI_API_KEY", FALLBACK_API_KEY)
BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CACHE_DIR = Path("data/raw/mesh_cache")
SLEEP = 0.34

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

OUTPUT = Path("data/raw/selected_diseases.json")

# ─── Target disease list ─────────────────────────────────────────────────────
# Each entry: (canonical MeSH name, category)
# Names must match what NCBI MeSH returns (case-insensitive, partial ok)

TARGETS = [
    # Cancer
    ("Breast Neoplasms", "cancer"),
    ("Lung Neoplasms", "cancer"),
    ("Colorectal Neoplasms", "cancer"),
    ("Liver Neoplasms", "cancer"),
    ("Carcinoma, Hepatocellular", "cancer"),
    ("Pancreatic Neoplasms", "cancer"),
    ("Prostatic Neoplasms", "cancer"),
    ("Stomach Neoplasms", "cancer"),
    ("Ovarian Neoplasms", "cancer"),
    ("Brain Neoplasms", "cancer"),
    ("Glioblastoma", "cancer"),
    ("Glioma", "cancer"),
    ("Leukemia", "cancer"),
    ("Leukemia, Myeloid, Acute", "cancer"),
    ("Leukemia, Lymphocytic, Chronic, B-Cell", "cancer"),
    ("Lymphoma", "cancer"),
    ("Lymphoma, Non-Hodgkin", "cancer"),
    ("Hodgkin Disease", "cancer"),
    ("Multiple Myeloma", "cancer"),
    ("Melanoma", "cancer"),
    ("Thyroid Neoplasms", "cancer"),
    ("Carcinoma, Thyroid", "cancer"),
    ("Kidney Neoplasms", "cancer"),
    ("Carcinoma, Renal Cell", "cancer"),
    ("Urinary Bladder Neoplasms", "cancer"),
    ("Esophageal Neoplasms", "cancer"),
    ("Uterine Cervical Neoplasms", "cancer"),
    ("Endometrial Neoplasms", "cancer"),
    ("Head and Neck Neoplasms", "cancer"),
    ("Mesothelioma", "cancer"),
    ("Neuroblastoma", "cancer"),
    ("Cholangiocarcinoma", "cancer"),
    ("Carcinoma, Non-Small-Cell Lung", "cancer"),
    ("Sarcoma", "cancer"),
    ("Neoplasms, Hormone-Dependent", "cancer"),
    ("Adenocarcinoma", "cancer"),
    ("Carcinoma, Squamous Cell", "cancer"),
    ("Carcinoma, Pancreatic Ductal", "cancer"),

    # Neurodegenerative
    ("Alzheimer Disease", "neurodegenerative"),
    ("Parkinson Disease", "neurodegenerative"),
    ("Amyotrophic Lateral Sclerosis", "neurodegenerative"),
    ("Huntington Disease", "neurodegenerative"),
    ("Multiple Sclerosis", "neurodegenerative"),
    ("Frontotemporal Dementia", "neurodegenerative"),
    ("Lewy Body Disease", "neurodegenerative"),
    ("Dementia, Vascular", "neurodegenerative"),
    ("Prion Diseases", "neurodegenerative"),
    ("Spinocerebellar Ataxias", "neurodegenerative"),
    ("Friedreich Ataxia", "neurodegenerative"),
    ("Progressive Supranuclear Palsy", "neurodegenerative"),
    ("Multiple System Atrophy", "neurodegenerative"),
    ("Muscular Dystrophies", "neurodegenerative"),
    ("Muscular Dystrophy, Duchenne", "neurodegenerative"),
    ("Spinal Muscular Atrophies of Childhood", "neurodegenerative"),
    ("Charcot-Marie-Tooth Disease", "neurodegenerative"),
    ("Hereditary Spastic Paraplegia", "neurodegenerative"),
    ("Epilepsy", "neurodegenerative"),
    ("Dementia", "neurodegenerative"),
    ("Schizophrenia", "neurodegenerative"),
    ("Bipolar Disorder", "neurodegenerative"),
    ("Depressive Disorder, Major", "neurodegenerative"),
    ("Autism Spectrum Disorder", "neurodegenerative"),
    ("Attention Deficit Disorder with Hyperactivity", "neurodegenerative"),
    ("Brain Ischemia", "neurodegenerative"),
    ("Stroke", "neurodegenerative"),
    ("Encephalopathies", "neurodegenerative"),
    ("Neurodegenerative Diseases", "neurodegenerative"),

    # Metabolic
    ("Diabetes Mellitus, Type 2", "metabolic"),
    ("Diabetes Mellitus, Type 1", "metabolic"),
    ("Obesity", "metabolic"),
    ("Metabolic Syndrome", "metabolic"),
    ("Non-alcoholic Fatty Liver Disease", "metabolic"),
    ("Hyperlipidemias", "metabolic"),
    ("Hypercholesterolemia", "metabolic"),
    ("Hypertriglyceridemia", "metabolic"),
    ("Gout", "metabolic"),
    ("Phenylketonurias", "metabolic"),
    ("Insulin Resistance", "metabolic"),
    ("Hyperuricemia", "metabolic"),
    ("Fatty Liver", "metabolic"),
    ("Liver Cirrhosis", "metabolic"),
    ("Atherosclerosis", "metabolic"),
    ("Coronary Artery Disease", "metabolic"),
    ("Hypertension", "metabolic"),
    ("Anemia", "metabolic"),
    ("Anemia, Sickle Cell", "metabolic"),
    ("Porphyrias", "metabolic"),
    ("Galactosemias", "metabolic"),
    ("Glycogen Storage Disease", "metabolic"),
    ("Mucopolysaccharidoses", "metabolic"),
    ("Gaucher Disease", "metabolic"),
    ("Niemann-Pick Diseases", "metabolic"),
    ("Fabry Disease", "metabolic"),
    ("Maple Syrup Urine Disease", "metabolic"),
    ("Homocystinuria", "metabolic"),
    ("Cystic Fibrosis", "metabolic"),
    ("Wilson Disease", "metabolic"),
    ("Hemochromatosis", "metabolic"),
    ("Vitamin D Deficiency", "metabolic"),
    ("Scurvy", "metabolic"),
]


def load_all_mesh(data_dir: Path) -> list[dict]:
    """Load all mesh_*.json files from data/raw."""
    all_diseases = []
    seen_ids: set[str] = set()
    for f in sorted(data_dir.glob("mesh_*.json")):
        diseases = json.loads(f.read_text(encoding="utf-8"))
        log.info("Loaded %d entries from %s", len(diseases), f.name)
        for d in diseases:
            if d["mesh_id"] not in seen_ids:
                seen_ids.add(d["mesh_id"])
                all_diseases.append(d)
    log.info("Total unique MeSH entries: %d", len(all_diseases))
    return all_diseases


def find_disease(name: str, all_diseases: list[dict]) -> dict | None:
    """Find a MeSH disease by exact name match, then partial match."""
    name_lower = name.lower()
    for d in all_diseases:
        if d["name"].lower() == name_lower:
            return d
    for d in all_diseases:
        if name_lower in d["name"].lower() or d["name"].lower() in name_lower:
            return d
    return None


def _parse_mesh_text(text: str, ncbi_ids: list[str]) -> list[dict]:
    """Minimal inline copy of fetch_mesh_diseases.parse_mesh_text."""
    import re
    boundaries = [(m.start(), m.group()) for m in re.compile(r"^\d+: .+", re.MULTILINE).finditer(text)]
    records = []
    for i, (start, header) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        block = text[start:end]
        lines = block.splitlines()
        name_match = re.match(r"^\d+: (.+)", lines[0])
        if not name_match:
            continue
        name = name_match.group(1).strip()
        tree_numbers = []
        synonyms = []
        in_entry = False
        for line in lines:
            if line.startswith("Tree Number(s):"):
                tree_numbers = [t.strip() for t in line[len("Tree Number(s):"):].strip().split(",") if t.strip()]
            if line.strip() == "Entry Terms:":
                in_entry = True
                continue
            if in_entry:
                if line.startswith("    ") or line.startswith("\t"):
                    t = line.strip()
                    if t and t.lower() != name.lower():
                        synonyms.append(t)
                elif line.strip():
                    in_entry = False
        records.append({
            "mesh_id": ncbi_ids[i] if i < len(ncbi_ids) else "",
            "name": name,
            "synonyms": list(dict.fromkeys(synonyms)),
            "tree_numbers": tree_numbers,
        })
    return records


def lookup_mesh_by_name(name: str) -> dict | None:
    """Directly ESearch + EFetch a single MeSH descriptor by name (fallback)."""
    cache_file = CACHE_DIR / f"lookup_{name.lower().replace(' ', '_').replace(',', '')[:80]}.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        return data if data else None

    # ESearch for the exact name
    params = {
        "db": "mesh",
        "term": f'"{name}"[MeSH Terms]',
        "retmax": 5,
        "retmode": "json",
        "api_key": API_KEY,
    }
    try:
        resp = requests.get(f"{BASE_URL}/esearch.fcgi", params=params, timeout=30)
        resp.raise_for_status()
        ids = resp.json()["esearchresult"]["idlist"]
        time.sleep(SLEEP)
        if not ids:
            cache_file.write_text(json.dumps(None))
            return None

        # EFetch the first result
        text_resp = requests.get(
            f"{BASE_URL}/efetch.fcgi",
            params={"db": "mesh", "id": ids[0], "retmode": "text", "api_key": API_KEY},
            timeout=30,
        )
        text_resp.raise_for_status()
        time.sleep(SLEEP)

        records = _parse_mesh_text(text_resp.text, [ids[0]])
        if records:
            result = records[0]
            cache_file.write_text(json.dumps(result, ensure_ascii=False))
            return result
    except Exception as e:
        log.warning("lookup_mesh_by_name failed for '%s': %s", name, e)

    cache_file.write_text(json.dumps(None))
    return None


def main():
    data_dir = Path("data/raw")
    all_diseases = load_all_mesh(data_dir)

    if not all_diseases:
        log.error("No MeSH data found in %s. Run fetch_mesh_diseases.py first.", data_dir)
        return

    selected = []
    not_found = []

    for target_name, category in TARGETS:
        match = find_disease(target_name, all_diseases)
        if match:
            entry = dict(match)
            entry["category"] = category
            entry["query_name"] = target_name
            selected.append(entry)
            log.info("  [%s] %s → %s", category[:4], target_name, match["name"])
        else:
            # Fallback: direct NCBI lookup by name
            match = lookup_mesh_by_name(target_name)
            if match:
                entry = dict(match)
                entry["category"] = category
                entry["query_name"] = target_name
                selected.append(entry)
                log.info("  [%s] %s → %s (via direct lookup)", category[:4], target_name, match["name"])
            else:
                not_found.append(target_name)
                log.warning("  NOT FOUND: %s", target_name)

    # Deduplicate by mesh_id (some targets may resolve to the same descriptor)
    seen: set[str] = set()
    deduped = []
    for d in selected:
        if d["mesh_id"] not in seen:
            seen.add(d["mesh_id"])
            deduped.append(d)

    log.info("\nSelected: %d  |  Not found: %d  |  After dedup: %d", len(selected), len(not_found), len(deduped))

    by_cat = {}
    for d in deduped:
        by_cat.setdefault(d["category"], []).append(d["name"])
    for cat, names in sorted(by_cat.items()):
        log.info("  %s: %d diseases", cat, len(names))

    if not_found:
        log.warning("Diseases not found in MeSH data (may need C04/C10 fetch):")
        for n in not_found:
            log.warning("  - %s", n)

    OUTPUT.write_text(json.dumps(deduped, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Saved %d diseases to %s", len(deduped), OUTPUT)


if __name__ == "__main__":
    main()
