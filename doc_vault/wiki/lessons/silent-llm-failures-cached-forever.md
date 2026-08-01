---
type: concept
title: Silent LLM failures could be cached forever
status: evergreen
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - lesson
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
source_paths:
  - project_tracking.md
last_reviewed: 2026-08-01
---

# Silent LLM failures could be cached forever

**The defect.** `call_llm` swallowed every exception into `return []`. A timeout,
a dropped connection and a non-JSON reply were therefore indistinguishable from
"the model found no pathway in this abstract". `run_silver.py` then wrote that
empty result to the per-PMID cache — and since the cache file *is* the resume
key, the abstract was lost permanently: no later run would ever retry it.

**Fix.** `call_llm` raises `LLMCallError` on transport failure, HTTP error,
missing or malformed JSON, or a non-list `mentions`. An empty list now means one
thing only. `process_one()` returns `None` on that error: **no cache write**, the
PMID is dropped from the output, a warning is logged, and the run summary gains
an `LLM FAILURES / OUTPUT IS INCOMPLETE` line. A re-run retries exactly those
PMIDs.

**Audit.** All 91 zero-span records in the existing pilot were re-queried:
**0 call errors**, 87/91 identical, 4 differing from ordinary run-to-run
nondeterminism. Of the 8 spans the re-query produced, 6 were bare
metabolites/proteins/enzymes the lenient rule explicitly forbids, so the refill
was reverted and `pilot_1k.jsonl` left byte-identical.

**Conclusion recorded honestly:** no silent loss ever occurred. The fix is
insurance for slower models, where the 120 s timeout margin — currently
1.9–2.4 s per abstract — closes.

## What generalises

A cache keyed on "we have an answer" must never be written by a code path that
cannot distinguish an answer from a failure. And an empty result is a value with
meaning; it deserves the same scrutiny as a wrong one.

Related: [[cache-keys-must-cover-the-request|cache keys must cover the request]],
[[freeze-silver-samples-by-pmid-file|frozen silver samples]].
