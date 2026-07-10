# Challenges & Lessons Learned

---

## Data Leakage via Article-Level Split Mismatch

**When:** Phase 2 training (Run 005, first attempt)

**Symptom:**
Validation F1 reached **0.980** at epoch 13 — unrealistically high compared to Phase 1's best of ~0.49 on a similar task.

**Root Cause:**
`build_dataset.py` split the dataset by `pathway_id` (the first pathway assigned to each record). However, a single article (PMID) generates multiple records:
- 1 abstract record
- N full-text window records (±500 char context windows around each annotated span)

Because splitting was pathway-based, records from the **same PMID** could end up in different splits. The model would train on one full-text window of an article and then be evaluated on another window from that same article — text that is nearly identical in structure and vocabulary.

```
PMID 12345, pathway "Glycolysis" → abstract record   → train
PMID 12345, pathway "Glycolysis" → ft window 1       → train
PMID 12345, pathway "Glycolysis" → ft window 2       → val   ← same article!
```

**Fix:**
Changed the grouping key in `build_dataset.py` from `pathway_ids[0]` to `pmid`. All records originating from the same article are now guaranteed to land in the same split.

```python
# Before (leaky)
primary = r["pathway_ids"][0]

# After (fixed)
primary = r["pmid"]
```

Split sizes after fix (Phase 2):

| Split | PMIDs | Records |
|-------|-------|---------|
| train | 7,085 | 33,328  |
| val   | 885   | 3,970   |
| test  | 887   | 4,403   |

Previously, val had only 1,311 records (suspiciously small) — a sign that the split was imbalanced at the article level even though it looked balanced at the pathway level.

**Takeaway:**
Whenever a single source document produces multiple training records (sliding windows, multi-span abstracts, augmented views), the split boundary must be drawn at the **document level**, not at the label/entity level. Splitting at a finer granularity almost always causes leakage.
