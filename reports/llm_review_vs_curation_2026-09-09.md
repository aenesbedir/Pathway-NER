# LLM audit of the missing-pathway corpus vs human curation

Date: 2026-09-09

Source of every number below:

- `doccano/golden_dataset/gt_125/review_vs_curation.json`
  (`scripts/compare_review_vs_curation.py`) — the production audit against the
  curator, span by span.
- `doccano/golden_dataset/gt_125/review_prompt_trials.json`
  (`scripts/review_prompt_trials.py --model opus`) — five alternative prompts
  on the same 25 abstracts.

The audit under test is `scripts/review_missing_dataset.py` with its
gt_100-grounded prompt, run over the 831 missing-pathway abstracts with
`claude-opus-5[1m]` (recorded per record in `llm_review.jsonl`). The reference
is the 25 abstracts of the missing corpus's test split that were curated by
hand for gt_125: 69 gold spans against 53 pipeline spans.

## What the curator did

The curator removed nothing. Of the 53 pipeline spans, 49 were kept as they
were and 4 were widened (`formation of steroid` → `formation of steroid
hormones`, `cholesterol synthesis` → `de novo cholesterol synthesis`,
`glutamine metabolism` → `glucose and glutamine metabolism`, `P450-dependent
catabolism` → `catabolism of retinoic acid (RA).`). Then 16 new spans were
added that no pipeline stage had produced. So precision of the pipeline was
never the problem on these abstracts; recall was (49/69 = 0.71).

## What the audit got right

Verdicts on the 53 pipeline spans, against what the curator did with them:

| audit said | curator kept | curator widened |
|---|---|---|
| correct (46) | 45 | 1 |
| boundary (7) | 4 | 3 |
| wrong (0) | — | — |

The `correct` label was reliable (45/46). The `boundary` label caught 3 of the
4 real boundary errors, at the cost of 4 false alarms. No span was called
`wrong`, and the curator deleted none — the audit and the curator agree that
the pipeline's spans are clean.

## What the audit missed, and why

The curator added 20 spans. The audit's "missed" list contained 21 proposals;
7 of them matched a curator addition. The 13 additions the audit did not
produce split by cause:

| cause | spans | example |
|---|---|---|
| abstract never reviewed | 3 | `polyphosphoinositide hydrolysis`, `calcium homeostasis` |
| boundary correction of an existing span, not a discovery | 4 | `de novo cholesterol synthesis` |
| reviewed, no overlap, not proposed | 7 | `glucose uptake`, `protein lipoylation`, `lysosomal pathways` |

Three causes, in order of how much they cost:

**1. The audit only ran where the pipeline had already found something.**
`review_missing_dataset.py` skips span-free abstracts (`recs = [r for r in recs
if r["spans"] ...]`). PMID 1317042 had no pipeline span and three curator
spans; it was never sent to the judge. Any abstract where the pipeline has zero
recall is exactly where a discovery pass is worth most, and it is exactly where
none was made. Cost here: 3 of 20.

**2. Boundary verdicts carried no correction.** The prompt asked for a verdict
(`correct` / `boundary` / `wrong`) and a 15-word reason, not the corrected
text. Three of the four real boundary errors were flagged, and none could be
applied, because there was nothing to apply. `apply_llm_review.py` therefore
touched only `wrong` spans. Cost: 4 of 20 (one of the four the audit did in
fact propose in its missed list, `de novo cholesterol synthesis`, but as a new
span, not as a widening of the existing one).

**3. The definition excluded categories the curator includes.** The prompt
was derived from gt_100, and gt_100 is close to empty on transport, uptake,
absorption, homeostasis and enzymatic modification (1, 0 and 2 gold spans
respectively over 100 abstracts, although the words occur 8, 11 and 13 times
in its text). It also lists `signal transduction` as excluded. The curator
marked `glucose uptake`, `cholesterol absorption and synthesis`, `protein
lipoylation`, `androgen signaling/metabolism` and `lysosomal pathways`. The
judge followed the prompt; the prompt followed gt_100; gt_100 is silent. This
is an annotation-policy gap, not a reasoning failure. Cost: 7 of 20, of which
`glycolytic parameters` is arguably the curator's error rather than the
audit's.

A fourth, smaller problem: 4 of the 21 proposals were not verbatim substrings
of the abstract (`Glycolysis` for a text that says `glycolytic parameters`,
`mevalonate pathway` for a text that says `mevalonate`, `Estrogen synthesis`
where the text has no such phrase). The prompt asked for exact substrings and
the judge paraphrased anyway. Such proposals cannot be turned into offsets.

## Prompt trials

Five prompts on the same 25 abstracts, judge pinned to `claude-opus-5`
(116 calls). Discovery is scored on the 20 curator additions; boundary on the
4 real errors and the 49 correct spans that must survive.

| prompt | recall | precision | fixed / 4 | broken / 49 |
|---|---|---|---|---|
| A — the production prompt's "missed" instruction alone | 12/20 = 0.60 | 0.46 | | |
| B — recall-first: positive definition, short exclusion list | 16/20 = 0.80 | 0.23 | | |
| C — B, then a second call that filters by form | 14/20 = 0.70 | 0.48 | | |
| D — boundary channel, no constraint on what may be added | | | 3 | 9 |
| E — D plus a list of what must not be added | | | 2 | 2 |

Three things this shows:

- The 4 spans B does not find are all boundary corrections of existing
  spans, which B was told not to repeat. On the 16 genuinely new spans its
  recall is 16/16. Discovery and boundary are different jobs and need
  different calls.
- Recall is bought by removing the exclusion list, and precision is bought
  back by a separate filter that judges *form* (a noun phrase with a process
  head and a named compound) rather than *topic*. Asking one call to do both
  makes it self-censor: A vs B is 0.60 vs 0.80 on the same model.
- An unconstrained boundary channel is net harmful: 3 fixes against 9 broken
  spans, every one of them by pulling in a location (`within the central
  nucleus of the amygdala`), a coordinated non-process (`and secretion`) or a
  shifted head (`androgen synthesis inhibitors`). Naming those three patterns
  as forbidden brings the damage to 2, and both of those are defensible
  widenings (`metabolism of inositol` → `metabolism of inositol
  phospholipids`).

The trials ran twice: once unpinned, which after the session model changed
mid-run mixed `claude-fable-5-1` (89 calls) and `claude-opus-5` (25), and once
pinned to Opus. Only the pinned run is kept. The two runs differed by up to
0.10 in recall on identical prompts, which is the same run-to-run spread seen
when the full 795-abstract audit was repeated with an unchanged prompt (`wrong`
29 → 57, `boundary` 240 → 183). Twenty-five abstracts is enough to rank the
prompts, not to put a second decimal on them.

## What I would change in the prompt

In order of expected gain.

1. **Send every abstract, including span-free ones.** One line in
   `review_missing_dataset.py`. Abstracts where the pipeline found nothing
   are where the judge's recall pass has the most to add.

2. **Split the single call into three: audit, discovery, boundary.** They
   pull in opposite directions. The audit's long exclusion list suppressed
   discovery; the discovery instruction, tacked on at the end, got 21
   proposals out of 23 abstracts.

3. **Discovery: positive definition, short exclusion, verbatim quoting,
   then a filter call.** Prompt B followed by the filter is the best
   discovery configuration tested (0.70 / 0.48). The filter should state a
   *form* test — noun phrase, process head noun, a compound or class named —
   and reject clauses, release/secretion/entry events, and agent-headed
   phrases (`genes`, `enzymes`, `machinery`). Reject any proposal that is not
   a verbatim substring before it reaches the filter.

4. **Boundary: return the corrected text, and say what may not be added.**
   Prompt E. Without the "never extend to" list the channel breaks more than
   it fixes. Keep "most phrases are correct; repeat them unchanged".

5. **Do not delete on a single verdict.** The repeated full audit moved a
   third of its `wrong`/`boundary` calls between runs. Either require
   agreement across two runs before `apply_llm_review.py` drops a span, or
   have it flag rather than drop and leave deletion to a person. On these 25
   abstracts the curator deleted nothing, so the cost of never deleting is
   low.

6. **Settle the policy before tuning the prompt further.** Whether `glucose
   uptake`, `cholesterol absorption`, `calcium homeostasis`, `protein
   lipoylation` and `androgen signaling/metabolism` are PATHWAY is not
   something a prompt can decide. gt_100 has no examples either way; the
   curator says yes. One sentence per category in `doccano/ANNOTATION_GUIDE.md`
   settles it for the judge, the curators and the model alike. Until then
   every measurement of "recall" on these categories is measuring a
   disagreement, not an error.

## Caveats

- 25 abstracts, 69 spans, 20 additions. Enough for the ranking and the
  causes; not for the decimals.
- The curated reference has its own noise: `catabolism of retinoic acid
  (RA).` keeps a trailing full stop, and `glycolytic parameters` is a
  measurement by the prompt's own rule.
- The curator saw the pipeline's spans pre-filled and accepted 49 of 53 as
  they were. A curator annotating from a blank page might have drawn some
  boundaries differently; this comparison measures agreement with a
  curator who started from the pipeline's output.
