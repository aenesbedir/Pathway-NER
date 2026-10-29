#!/usr/bin/env python3
"""
schema.py

Canonical record definitions for pathway-disease relation extraction, v4.

Why v4 exists
-------------
`doccano/RELATION_SCHEMA.md` froze a four-label schema with separate `direction`
and `negated` fields. `reports/relation_extraction_independent_review_2026-08-19.md`
then cut it to three labels (upregulation / downregulation / no_relation),
removing `association` and `direction`, and folding explicit absence claims into
`no_relation`. The Opus teacher output in
`data/processed/gt_100/gt_100_disease_pathway_bent-pubmedbert-ner-disease_relation.jsonl`
was produced under that two-signed-class reading.

A manual pass over all 100 gt_100 abstracts measured what the cut costs. Of the
90 abstracts carrying both entity types, 27 state a signed direction, 34 state an
unsigned change ("enriched in", "perturbations in", "dysregulated in"), 14 state
only that intervening on the pathway treats the disease, and 6 state an explicit
absence. Under the three-label schema the last three groups collapse into
`no_relation`, and the Opus run shows the failure mode this produces: 12 of its 64
pairs are unsigned or interventional claims forced into a signed class, all at
`confidence: medium`, including one abstract whose sentence explicitly denies the
association.

The 2026-08-19 review anticipated this exact repair: "`association` can be added
back as a fourth class without re-annotating the existing gold". v4 does that.

v3 additionally carried a `therapeutic_target` label and a `certainty` field.
Both are removed here. They were the two parts of the schema with no counterpart
in `doccano/RELATION_SCHEMA.md` or the 2026-08-19 review - they were introduced
from the gt_100 reading alone - and every label in a thesis-facing schema should
trace to an established annotation scheme. An intervention claim now falls to
`association` when the abstract connects the pathway to the disease at all, and
to `none` when it does not; hedging is not recorded.

The cost is measured, not assumed: in the v3 silver corpus `therapeutic_target`
was 429 of 4,982 pairs (8.6%), and hedged claims were 34% of those and 21% of
`association`. Losing the interventional distinction means the database cannot
separate "this pathway is disturbed in this disease" from "targeting this pathway
treats this disease" without re-reading the evidence sentence.

Labels
------
`upregulation`          the pathway's activity/expression is increased in the disease
`downregulation`        it is decreased
`association`           a change or involvement is claimed with no sign
`no_association_stated` the abstract makes an explicit claim that the relation is
                        absent (measured and not found), which is evidence, not silence
`none`                  the abstract makes no claim connecting the two entities

`direction` is not annotated. The 2026-08-19 review's argument stands: it was the
IAA-killing field, observational phrasing dominates, and aggregate direction is
recoverable across abstracts. `upregulation` is a state claim, not a causal one.

`negated` is not a separate field either. Its only frequent realisation, the
explicit absence claim, is `no_association_stated`; keeping a boolean head for a
class this rare was rejected for the reasons the review gives.

Hedging is not annotated. `doccano/RELATION_SCHEMA.md` made the same call and
gave the reason: a hedged claim keeps its label, and separating the two is a
second annotation axis this version does not carry.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Iterable, Sequence

SCHEMA_VERSION = "pathway_disease_v4"
SCHEMA_TAG = (
    "pathway_disease_v4:"
    "upregulation|downregulation|association|no_association_stated|none"
)

#: Namespace for `candidate_id`, frozen at the value in use when the first
#: candidate files were built. A candidate's identity is (pmid, pathway, disease);
#: it does not change when the *label* set is revised. Deriving the digest from
#: SCHEMA_VERSION instead would rewrite every id on a label change, invalidating
#: the candidate files, their manifests and the teacher cache for no reason.
CANDIDATE_NAMESPACE = "pathway_disease_v3"

LABELS = (
    "upregulation",
    "downregulation",
    "association",
    "no_association_stated",
    "none",
)

#: Labels that require at least one verbatim evidence quote. `none` forbids any.
EVIDENCE_REQUIRED = tuple(l for l in LABELS if l != "none")

#: Upper bound on evidence quotes per relation.
#:
#: Evidence was one sentence until 2026-09-07. The limit was raised because a
#: claim is often split across an abstract: a `doc_level` pair - 155 of the 175
#: rows in the gt_100 panel - can never have both entities in one sentence, so a
#: single-sentence quote could not show that the claim connects them at all.
#:
#: A cap is still needed. Without one a model that cannot decide quotes half the
#: abstract, and an evidence field that holds everything identifies nothing.
MAX_EVIDENCE_QUOTES = 3

CONFIDENCE = ("high", "medium", "low")


def as_quotes(evidence) -> tuple[str, ...]:
    """Normalize an evidence field to a tuple of non-empty quotes.

    Accepts the pre-2026-09-07 single string, the list written since, and None.
    Records produced under the old rule stay readable without a migration.
    """
    if evidence is None:
        return ()
    if isinstance(evidence, str):
        evidence = [evidence]
    return tuple(q for q in (str(e).strip() for e in evidence) if q)


class RecordError(ValueError):
    """A record violates the schema. The message names the field and the reason."""


@dataclass(frozen=True)
class Mention:
    text: str
    start: int
    end: int
    label: str

    def check(self, abstract: str) -> None:
        if not 0 <= self.start < self.end <= len(abstract):
            raise RecordError(f"mention offsets out of range: {self.start}-{self.end}")
        if abstract[self.start : self.end] != self.text:
            raise RecordError(
                f"mention text does not match abstract at {self.start}-{self.end}: "
                f"{self.text!r} != {abstract[self.start:self.end]!r}"
            )


def normalize_surface(text: str) -> str:
    """Fold a mention surface to the key that groups mentions of one entity.

    Case and whitespace only. No stemming, no synonym expansion: a normalizer that
    guesses here would silently merge two different pathways into one candidate.
    """
    return re.sub(r"\s+", " ", text).strip().lower()


def candidate_id(pmid: str, pathway_key: str, disease_key: str) -> str:
    """Deterministic digest of the pair identity. Same inputs, same id, always."""
    raw = "\x1f".join((CANDIDATE_NAMESPACE, str(pmid), pathway_key, disease_key))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class Candidate:
    """One normalized (pathway, disease) pair in one abstract, before labelling."""

    candidate_id: str
    pmid: str
    abstract: str
    pathway_key: str
    disease_key: str
    pathway_mentions: list[Mention]
    disease_mentions: list[Mention]
    #: Sentence spans where both entities appear. Empty for a doc-level candidate.
    shared_sentences: list[tuple[int, int]]
    stratum: str  # "same_sentence" | "doc_level"
    #: Other surfaces folded into this entity, when the candidate builder merged
    #: an abbreviation with the form that defines it. Empty when no merge applied.
    #: Kept so a prompt can disclose the variants and a reviewer can see what was
    #: merged without re-running the detector.
    pathway_variants: list[str] = field(default_factory=list)
    disease_variants: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def check(self) -> None:
        if self.stratum not in ("same_sentence", "doc_level"):
            raise RecordError(f"unknown stratum: {self.stratum}")
        if not self.pathway_mentions or not self.disease_mentions:
            raise RecordError("a candidate needs at least one mention on each side")
        for m in (*self.pathway_mentions, *self.disease_mentions):
            m.check(self.abstract)
        if self.stratum == "same_sentence" and not self.shared_sentences:
            raise RecordError("same_sentence stratum with no shared sentence")
        if self.stratum == "doc_level" and self.shared_sentences:
            raise RecordError("doc_level stratum with a shared sentence")
        want = candidate_id(self.pmid, self.pathway_key, self.disease_key)
        if self.candidate_id != want:
            raise RecordError(f"candidate_id does not match its identity: {want}")

    def to_json(self) -> dict:
        d = asdict(self)
        d["shared_sentences"] = [list(s) for s in self.shared_sentences]
        # Omit the variant lists when nothing was merged, so a candidate file
        # built without --merge-abbreviations stays byte-identical to the ones
        # built before the option existed. Their manifests record a sha256, and a
        # field appearing out of nowhere would break every one of them for a
        # change that carries no information.
        for key in ("pathway_variants", "disease_variants"):
            if not d[key]:
                del d[key]
        return d

    @staticmethod
    def from_json(d: dict) -> "Candidate":
        return Candidate(
            candidate_id=d["candidate_id"],
            pmid=str(d["pmid"]),
            abstract=d["abstract"],
            pathway_key=d["pathway_key"],
            disease_key=d["disease_key"],
            pathway_mentions=[Mention(**m) for m in d["pathway_mentions"]],
            disease_mentions=[Mention(**m) for m in d["disease_mentions"]],
            shared_sentences=[tuple(s) for s in d["shared_sentences"]],
            stratum=d["stratum"],
            pathway_variants=list(d.get("pathway_variants", [])),
            disease_variants=list(d.get("disease_variants", [])),
            schema_version=d.get("schema_version", SCHEMA_VERSION),
        )


@dataclass
class Relation:
    """One labelled pair. The on-disk shape of a teacher or human annotation.

    Field names match
    `data/processed/gt_100/gt_100_disease_pathway_*_relation.jsonl` so that the
    gt_100 files, the teacher output and any human annotation stay one format.
    """

    pmid: str
    disease: Mention
    pathway: Mention
    label: str
    #: Verbatim quotes carrying the claim. Normalized to a tuple by
    #: `__post_init__`; a single string is accepted for records written before
    #: multi-quote evidence was allowed.
    evidence: "str | Sequence[str]"
    relation_source: str
    confidence: str = "medium"
    candidate_id: str = ""
    stratum: str = ""
    schema: str = SCHEMA_TAG

    def __post_init__(self) -> None:
        # A caller may pass one string or several; the record keeps a tuple so
        # every consumer sees one shape.
        self.evidence = as_quotes(self.evidence)

    def check(self, abstract: str | None = None) -> None:
        if self.label not in LABELS:
            raise RecordError(f"unknown label: {self.label!r}")
        if self.confidence not in CONFIDENCE:
            raise RecordError(f"unknown confidence: {self.confidence!r}")
        if self.label in EVIDENCE_REQUIRED and not self.evidence:
            raise RecordError(f"label {self.label} requires at least one evidence quote")
        if self.label == "none" and self.evidence:
            raise RecordError("label none must not carry evidence")
        if len(self.evidence) > MAX_EVIDENCE_QUOTES:
            raise RecordError(
                f"{len(self.evidence)} evidence quotes, at most {MAX_EVIDENCE_QUOTES}"
            )
        if abstract is None:
            return
        self.disease.check(abstract)
        self.pathway.check(abstract)
        for quote in self.evidence:
            if quote not in abstract:
                raise RecordError("evidence is not a verbatim substring of the abstract")

    def to_json(self) -> dict:
        return {
            "pmid": self.pmid,
            "disease": asdict(self.disease),
            "pathway": asdict(self.pathway),
            "label": self.label,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "relation_source": self.relation_source,
            "candidate_id": self.candidate_id,
            "stratum": self.stratum,
            "schema": self.schema,
        }

    @staticmethod
    def from_json(d: dict) -> "Relation":
        return Relation(
            pmid=str(d["pmid"]),
            disease=Mention(**d["disease"]),
            pathway=Mention(**d["pathway"]),
            label=d["label"],
            evidence=d.get("evidence", ""),
            relation_source=d.get("relation_source", ""),
            confidence=d.get("confidence", "medium"),
            candidate_id=d.get("candidate_id", ""),
            stratum=d.get("stratum", ""),
            schema=d.get("schema", SCHEMA_TAG),
        )


def write_jsonl(path, rows: Iterable) -> int:
    """Write records to `path`, one JSON object per line. Returns the row count."""
    n = 0
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            obj = r.to_json() if hasattr(r, "to_json") else r
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
