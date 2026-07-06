import json
from collections import defaultdict, Counter

PAIRS_FILE = "/home/enes/NER-pipeline/data/raw/pathway_disease_pairs.json"
MATCHES_FILE = "/home/enes/NER-pipeline/data/processed/exact_matches.jsonl"

# 1. Build pmid -> set of expected pathways
expected = defaultdict(set)
with open(PAIRS_FILE) as f:
    pairs = json.load(f)
for entry in pairs:
    pathway = entry["pathway"]
    for pmid in entry["pmids"]:
        expected[pmid].add(pathway)

# 2. Build pmid -> set of found pathways (only non-empty spans)
found = defaultdict(set)
with open(MATCHES_FILE) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec["spans"]:
            found[rec["pmid"]].add(rec["pathway_id"])

# 3. For each pmid in both mappings, classify
all_pmids = set(expected.keys()) & set(found.keys())
# Also consider pmids only in expected (fully missed)
expected_only_pmids = set(expected.keys()) - set(found.keys())

exact_match_pmids = set()
extra_found_pmids = set()
missed_pmids = set()

exact_match_total = 0
extra_found_total = 0
missed_total = 0

missed_counter = Counter()
extra_counter = Counter()

per_pmid = {}

for pmid in set(expected.keys()):
    exp = expected[pmid]
    fnd = found.get(pmid, set())

    exact = exp & fnd
    extra = fnd - exp
    missed = exp - fnd

    per_pmid[pmid] = {"expected": exp, "found": fnd, "exact": exact, "extra": extra, "missed": missed}

    exact_match_total += len(exact)
    extra_found_total += len(extra)
    missed_total += len(missed)

    if exact:
        exact_match_pmids.add(pmid)
    if extra:
        extra_found_pmids.add(pmid)
    if missed:
        missed_pmids.add(pmid)

    for p in missed:
        missed_counter[p] += 1
    for p in extra:
        extra_counter[p] += 1

# 4. Aggregate stats
print("=" * 70)
print("AGGREGATE STATS")
print("=" * 70)
print(f"Total PMIDs with expected pathways: {len(expected)}")
print(f"Total PMIDs with found pathways (non-empty spans): {len(found)}")
print(f"PMIDs in both mappings: {len(all_pmids)}")
print()
print(f"PMIDs with at least one exact_match : {len(exact_match_pmids)}")
print(f"PMIDs with at least one extra_found  : {len(extra_found_pmids)}")
print(f"PMIDs with at least one missed       : {len(missed_pmids)}")
print()
print(f"Total exact_match pathway hits : {exact_match_total}")
print(f"Total extra_found pathway hits : {extra_found_total}")
print(f"Total missed pathway hits      : {missed_total}")

print()
print("Top 10 most commonly MISSED expected pathways:")
for pathway, count in missed_counter.most_common(10):
    print(f"  {count:4d}  {pathway}")

print()
print("Top 10 most commonly EXTRA-FOUND pathways:")
for pathway, count in extra_counter.most_common(10):
    print(f"  {count:4d}  {pathway}")

# 5. Example PMIDs
def print_examples(label, pmid_set, per_pmid, n=10):
    print()
    print("=" * 70)
    print(f"EXAMPLE PMIDs — {label} (up to {n})")
    print("=" * 70)
    for pmid in sorted(pmid_set)[:n]:
        d = per_pmid[pmid]
        print(f"  PMID: {pmid}")
        print(f"    Expected : {sorted(d['expected'])}")
        print(f"    Found    : {sorted(d['found'])}")
        print(f"    Exact    : {sorted(d['exact'])}")
        print(f"    Extra    : {sorted(d['extra'])}")
        print(f"    Missed   : {sorted(d['missed'])}")
        print()

print_examples("exact_match PMIDs", exact_match_pmids, per_pmid)
print_examples("extra_found PMIDs", extra_found_pmids, per_pmid)
print_examples("missed PMIDs", missed_pmids, per_pmid)
