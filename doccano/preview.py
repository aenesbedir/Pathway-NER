#!/usr/bin/env python3
"""
preview.py

Renders the doccano import file as a static HTML page so the spans can be eyeballed
before the data goes to annotators — no doccano instance required.

It reads the **same file doccano will read** and highlights exactly the offsets in
its `label` array, so what you see here is what doccano will show. Span colour marks
provenance (LLM vs booster), and hovering a span shows its canonical/match_type.

Output: doccano/preview.html  (open in a browser)

Run from repo root:
    venv310/bin/python3 doccano/preview.py            # first 40 documents
    venv310/bin/python3 doccano/preview.py --limit 100
"""

import argparse
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPORT_FILE = ROOT / "doccano/pilot_1k_doccano.jsonl"
OUT = ROOT / "doccano/preview.html"

CSS = """
:root { --bg:#fff; --fg:#1a1a1a; --muted:#666; --line:#e3e3e3;
        --llm:#cfe8ff; --llm-b:#3b82f6; --boost:#ffe4b3; --boost-b:#f59e0b;
        --warn:#ffd0d0; --warn-b:#ef4444; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#16181d; --fg:#e8e8e8; --muted:#9aa0a6; --line:#2c2f36;
          --llm:#1e3a5f; --llm-b:#60a5fa; --boost:#4a3410; --boost-b:#fbbf24;
          --warn:#4a1c1c; --warn-b:#f87171; }
}
* { box-sizing:border-box; }
body { margin:0; padding:2rem 1rem; background:var(--bg); color:var(--fg);
       font:15px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
.wrap { max-width:900px; margin:0 auto; }
h1 { font-size:1.4rem; margin:0 0 .3rem; }
.sub { color:var(--muted); margin:0 0 1.5rem; font-size:.9rem; }
.legend { display:flex; gap:1rem; flex-wrap:wrap; padding:.8rem 1rem; border:1px solid var(--line);
          border-radius:8px; margin-bottom:1.5rem; font-size:.85rem; }
.doc { border:1px solid var(--line); border-radius:8px; padding:1rem 1.2rem; margin-bottom:1rem; }
.doc h2 { font-size:.8rem; color:var(--muted); margin:0 0 .6rem; font-weight:600;
          letter-spacing:.04em; text-transform:uppercase; }
.txt { white-space:pre-wrap; word-wrap:break-word; }
mark { padding:.1em .15em; border-radius:3px; border-bottom:2px solid; cursor:help; }
mark.llm   { background:var(--llm);   border-color:var(--llm-b); }
mark.boost { background:var(--boost); border-color:var(--boost-b); }
.chip { display:inline-block; padding:.1em .45em; border-radius:4px; border:1px solid var(--line);
        font-size:.75rem; color:var(--muted); margin-left:.4rem; }
.none { color:var(--muted); font-style:italic; }
"""


def render_doc(rec: dict) -> str:
    text = rec["text"]
    info = {s["text"]: s for s in rec.get("meta", {}).get("spans", [])}
    spans = sorted(rec["label"], key=lambda x: x[0])

    out, cur = [], 0
    for start, end, _label in spans:
        out.append(html.escape(text[cur:start]))
        surface = text[start:end]
        meta = info.get(surface, {})
        cls = "boost" if meta.get("source") == "booster" else "llm"
        canon = meta.get("canonical")
        title = (f"{meta.get('match_type', '?')}"
                 + (f" → {canon}" if canon else "")
                 + f" · {meta.get('source', '?')}"
)
        out.append(f'<mark class="{cls}" title="{html.escape(title)}">'
                   f'{html.escape(surface)}</mark>')
        cur = end
    out.append(html.escape(text[cur:]))

    body = "".join(out) if spans else f'<span class="none">{html.escape(text)}</span>'
    n = len(spans)
    return (f'<div class="doc"><h2>PMID {rec["meta"]["pmid"]}'
            f'<span class="chip">{n} span</span></h2>'
            f'<div class="txt">{body}</div></div>')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(IMPORT_FILE))
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--output", default=str(OUT))
    args = ap.parse_args()

    recs = [json.loads(l) for l in Path(args.input).read_text(encoding="utf-8").splitlines() if l.strip()]
    total = len(recs)
    shown = recs[:args.limit]

    docs = "\n".join(render_doc(r) for r in shown)
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>doccano import preview</title><style>{CSS}</style></head><body><div class="wrap">
<h1>doccano import preview</h1>
<p class="sub">Rendered straight from <code>{html.escape(Path(args.input).name)}</code> —
the same offsets doccano will import. Showing {len(shown)} of {total} documents.
Hover a span for its canonical / match_type / source.</p>
<div class="legend">
  <span><mark class="llm">LLM span</mark></span>
  <span><mark class="boost">booster span</mark></span>
</div>
{docs}
</div></body></html>"""

    Path(args.output).write_text(page, encoding="utf-8")
    print(f"Written: {args.output}  ({len(shown)} of {total} documents)")


if __name__ == "__main__":
    main()
