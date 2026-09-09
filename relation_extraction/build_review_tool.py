#!/usr/bin/env python3
"""
build_review_tool.py

Build a self-contained HTML tool for reviewing teacher relation labels by hand.

Why not doccano
---------------
doccano can store relations, but it draws them as arrows between entity
*mentions*. The annotation unit in `schema.py` is a (pathway, disease) pair per
abstract, and an abstract in this panel carries up to six pairs over as many as
twenty mentions of one entity. On screen that becomes a thicket of arrows in
which the pair being judged is not identifiable, which is the one thing the
reviewer has to know.

This tool inverts that: one screen is one pair. The abstract is shown whole with
every mention of that pair highlighted and nothing else marked, so the question
"what does this abstract claim about THESE two" has a visible subject.

Blind by default
----------------
The teacher's label and evidence are hidden until a decision is recorded. An
anchored reviewer agrees with the model more often than an independent one, and
the number this tool exists to produce is teacher accuracy.

Output
------
Progress lives in the browser's localStorage, keyed by candidate_id, so closing
the tab loses nothing. The export button writes a JSONL file with one row per
decision, joinable to the teacher output on candidate_id.

The generated page embeds its data and loads nothing from the network; it opens
from the filesystem.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from schema import Candidate, as_quotes, read_jsonl

REPO = Path(__file__).resolve().parents[1]
DEFAULT_RELATIONS = REPO / (
    "data/processed/gt_100/"
    "gt_100_disease_pathway_bent-pubmedbert-ner-disease_relation_fable_v4d_single.jsonl"
)
DEFAULT_CANDIDATES = REPO / "data/processed/gt_100/candidates_v4.jsonl"
DEFAULT_OUT = REPO / "data/processed/gt_100/review_tool.html"

LABELS = ["upregulation", "downregulation", "association", "no_association_stated", "none"]

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relation review &mdash; gt_100</title>
<style>
  :root {
    --ground: #f7f8f8; --surface: #fff; --ink: #14191b; --soft: #5b6a6e;
    --rule: #dde4e4; --pathway: #0f6e70; --pathway-bg: #d9efee;
    --disease: #9a5a12; --disease-bg: #fbeeda; --accent: #0f6e70;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --ground: #0e1415; --surface: #151d1f; --ink: #e4eaea; --soft: #93a5a8;
      --rule: #263234; --pathway: #6ecfc4; --pathway-bg: #123a38;
      --disease: #e0a869; --disease-bg: #3b2d18; --accent: #6ecfc4;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--ground); color: var(--ink);
    font: 15px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  header {
    position: sticky; top: 0; z-index: 5; background: var(--surface);
    border-bottom: 1px solid var(--rule); padding: .7rem 1.2rem;
    display: flex; gap: 1rem; align-items: center; flex-wrap: wrap;
  }
  header .grow { flex: 1; }
  .pill {
    font: 12px ui-monospace, Menlo, monospace; padding: .15rem .5rem;
    border: 1px solid var(--rule); border-radius: 999px; color: var(--soft);
  }
  main { max-width: 60rem; margin: 0 auto; padding: 1.4rem 1.2rem 6rem; }
  .pair {
    display: flex; gap: 1.5rem; flex-wrap: wrap; margin-bottom: 1rem;
    padding: .9rem 1.1rem; background: var(--surface);
    border: 1px solid var(--rule); border-radius: 4px;
  }
  .pair div { display: flex; flex-direction: column; gap: .15rem; }
  .pair .k {
    font: 11px ui-monospace, monospace; letter-spacing: .09em;
    text-transform: uppercase; color: var(--soft);
  }
  .pair .v { font-size: 1.02rem; font-weight: 600; }
  .v.p { color: var(--pathway); } .v.d { color: var(--disease); }
  article {
    background: var(--surface); border: 1px solid var(--rule); border-radius: 4px;
    padding: 1.2rem 1.4rem; white-space: pre-wrap; line-height: 1.8;
  }
  mark.p { background: var(--pathway-bg); color: var(--pathway); font-weight: 600;
           padding: .05em .15em; border-radius: 2px; }
  mark.d { background: var(--disease-bg); color: var(--disease); font-weight: 600;
           padding: .05em .15em; border-radius: 2px; }
  .choices { display: flex; gap: .5rem; flex-wrap: wrap; margin: 1.2rem 0 .6rem; }
  button {
    font: inherit; padding: .55rem .9rem; border-radius: 4px; cursor: pointer;
    border: 1px solid var(--rule); background: var(--surface); color: var(--ink);
  }
  button:hover { border-color: var(--accent); }
  button.sel { background: var(--accent); border-color: var(--accent); color: var(--ground); }
  button kbd {
    font: 11px ui-monospace, monospace; opacity: .6; margin-right: .4rem;
  }
  .reveal {
    margin-top: 1rem; padding: .9rem 1.1rem; border-left: 3px solid var(--accent);
    background: var(--surface); border-radius: 0 4px 4px 0;
  }
  .reveal h4 { margin: 0 0 .4rem; font-size: .78rem; letter-spacing: .08em;
               text-transform: uppercase; color: var(--soft); font-weight: 600; }
  .reveal blockquote { margin: .4rem 0; padding-left: .8rem;
                       border-left: 2px solid var(--rule); color: var(--soft); }
  .agree { color: var(--pathway); font-weight: 600; }
  .differ { color: var(--disease); font-weight: 600; }
  nav { display: flex; gap: .5rem; align-items: center; margin-top: 1.2rem; }
  .muted { color: var(--soft); font-size: .88rem; }
  progress { width: 10rem; height: .55rem; }
  select { font: inherit; padding: .35rem .5rem; background: var(--surface);
           color: var(--ink); border: 1px solid var(--rule); border-radius: 4px; }
</style>
</head>
<body>
<header>
  <strong>Relation review</strong>
  <span class="pill" id="pos"></span>
  <progress id="prog" max="100" value="0"></progress>
  <span class="muted" id="done"></span>
  <span class="grow"></span>
  <select id="filter">
    <option value="all">all pairs</option>
    <option value="todo">undecided only</option>
    <option value="low">model confidence: low</option>
    <option value="signed">model says up/down</option>
    <option value="differ">disagreements so far</option>
  </select>
  <button id="export">Export JSONL</button>
</header>
<main>
  <div class="pair">
    <div><span class="k">Pathway</span><span class="v p" id="pw"></span></div>
    <div><span class="k">Disease</span><span class="v d" id="ds"></span></div>
    <div><span class="k">PMID</span><span class="v" id="pmid"></span></div>
    <div><span class="k">Stratum</span><span class="v" id="strat"></span></div>
  </div>
  <article id="abs"></article>
  <div class="choices" id="choices"></div>
  <div class="muted">Keys 1&ndash;5 to label, 0 to clear, &larr; &rarr; to move.</div>
  <div id="reveal"></div>
  <nav>
    <button id="prev">&larr; Previous</button>
    <button id="next">Next &rarr;</button>
    <span class="muted" id="cid"></span>
  </nav>
</main>
<script>
const DATA = __DATA__;
const LABELS = __LABELS__;
const KEY = "gt100_relation_review_v1";
let store = {};
try { store = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { store = {}; }
let order = DATA.map((_, i) => i), at = 0;

const save = () => { try { localStorage.setItem(KEY, JSON.stringify(store)); } catch (e) {} };
const esc = s => s.replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

function marked(item) {
  const spans = [...item.pathway.map(m => ({ ...m, c: "p" })),
                 ...item.disease.map(m => ({ ...m, c: "d" }))].sort((a, b) => a.s - b.s);
  let out = "", cur = 0;
  for (const sp of spans) {
    if (sp.s < cur) continue;            // overlapping mention, keep the first
    out += esc(item.text.slice(cur, sp.s));
    out += `<mark class="${sp.c}">${esc(item.text.slice(sp.s, sp.e))}</mark>`;
    cur = sp.e;
  }
  return out + esc(item.text.slice(cur));
}

function applyFilter() {
  const f = document.getElementById("filter").value;
  order = DATA.map((_, i) => i).filter(i => {
    const d = DATA[i], v = store[d.candidate_id];
    if (f === "todo") return !v;
    if (f === "low") return d.model_confidence === "low";
    if (f === "signed") return d.model_label === "upregulation" || d.model_label === "downregulation";
    if (f === "differ") return v && v.label !== d.model_label;
    return true;
  });
  if (!order.length) order = [0];
  at = 0; render();
}

function render() {
  const item = DATA[order[at]];
  document.getElementById("pw").textContent = item.pathway_key;
  document.getElementById("ds").textContent = item.disease_key;
  document.getElementById("pmid").textContent = item.pmid;
  document.getElementById("strat").textContent = item.stratum;
  document.getElementById("abs").innerHTML = marked(item);
  document.getElementById("pos").textContent = `${at + 1} / ${order.length}`;
  document.getElementById("cid").textContent = item.candidate_id;

  const n = Object.keys(store).length;
  document.getElementById("done").textContent = `${n} of ${DATA.length} decided`;
  document.getElementById("prog").value = Math.round(100 * n / DATA.length);

  const chosen = store[item.candidate_id];
  const box = document.getElementById("choices");
  box.innerHTML = "";
  LABELS.forEach((lab, i) => {
    const b = document.createElement("button");
    b.innerHTML = `<kbd>${i + 1}</kbd>${lab}`;
    if (chosen && chosen.label === lab) b.className = "sel";
    b.onclick = () => choose(lab);
    box.appendChild(b);
  });

  const rev = document.getElementById("reveal");
  if (!chosen) { rev.innerHTML = ""; return; }
  const same = chosen.label === item.model_label;
  rev.innerHTML =
    `<div class="reveal"><h4>Teacher's answer &mdash; shown after your decision</h4>` +
    `<div><span class="${same ? "agree" : "differ"}">${item.model_label}</span>` +
    ` <span class="muted">(confidence: ${item.model_confidence})</span>` +
    ` ${same ? "&mdash; agrees with you" : "&mdash; differs from you"}</div>` +
    item.model_evidence.map(q => `<blockquote>${esc(q)}</blockquote>`).join("") +
    `</div>`;
}

function choose(lab) {
  const item = DATA[order[at]];
  store[item.candidate_id] = { label: lab, at: new Date().toISOString() };
  save(); render();
}

function move(d) { at = Math.max(0, Math.min(order.length - 1, at + d)); render(); }

document.getElementById("next").onclick = () => move(1);
document.getElementById("prev").onclick = () => move(-1);
document.getElementById("filter").onchange = applyFilter;
document.addEventListener("keydown", e => {
  if (e.target.tagName === "SELECT") return;
  if (e.key >= "1" && e.key <= String(LABELS.length)) choose(LABELS[+e.key - 1]);
  else if (e.key === "0") { delete store[DATA[order[at]].candidate_id]; save(); render(); }
  else if (e.key === "ArrowRight") move(1);
  else if (e.key === "ArrowLeft") move(-1);
});

document.getElementById("export").onclick = () => {
  const rows = DATA.filter(d => store[d.candidate_id]).map(d => JSON.stringify({
    candidate_id: d.candidate_id, pmid: d.pmid,
    pathway: d.pathway_key, disease: d.disease_key,
    human_label: store[d.candidate_id].label,
    model_label: d.model_label, model_confidence: d.model_confidence,
    agrees: store[d.candidate_id].label === d.model_label,
    decided_at: store[d.candidate_id].at,
  }));
  const blob = new Blob([rows.join("\\n") + "\\n"], { type: "application/x-jsonlines" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "gt100_human_review.jsonl";
  a.click();
};

applyFilter();
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--relations", type=Path, default=DEFAULT_RELATIONS)
    ap.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    cands = {c.candidate_id: c for c in (Candidate.from_json(d) for d in read_jsonl(args.candidates))}
    items = []
    for row in read_jsonl(args.relations):
        cand = cands.get(row["candidate_id"])
        if cand is None:
            continue
        items.append(
            {
                "candidate_id": cand.candidate_id,
                "pmid": cand.pmid,
                "text": cand.abstract,
                "pathway_key": cand.pathway_key,
                "disease_key": cand.disease_key,
                "stratum": cand.stratum,
                "pathway": [{"s": m.start, "e": m.end} for m in cand.pathway_mentions],
                "disease": [{"s": m.start, "e": m.end} for m in cand.disease_mentions],
                "model_label": row["label"],
                "model_confidence": row.get("confidence", ""),
                "model_evidence": list(as_quotes(row.get("evidence"))),
            }
        )
    items.sort(key=lambda d: (d["pmid"], d["pathway_key"], d["disease_key"]))

    page = PAGE.replace("__DATA__", json.dumps(items, ensure_ascii=False))
    page = page.replace("__LABELS__", json.dumps(LABELS))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page, encoding="utf-8")

    print(json.dumps(
        {
            "n_pairs": len(items),
            "n_abstracts": len({i["pmid"] for i in items}),
            "model_labels": dict(collections.Counter(i["model_label"] for i in items).most_common()),
            "size_kb": round(args.out.stat().st_size / 1024),
            "out": str(args.out),
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
