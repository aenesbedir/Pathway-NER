"""Trace real tensor shapes of the four relation architectures on one gt_100 pair.

Documentation source for docs/architectures. Paths are hard-coded to the author's machine and
the relation script imports from the sibling pathway-re-synth repository, so each records how the figures'
numbers were produced rather than serving as a reproducible entry point.
"""
import json, sys, torch
sys.path.insert(0, "/home/enes/NER-pipeline")
sys.path.insert(0, "/home/enes/NER-pipeline/relation_extraction")
from transformers import AutoTokenizer, AutoModel
HF = "microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext"
PMID, PW, DS = "32732914", "gtp synthesis", "gbm"
out = {}

# ---- architectures 1 and 2 (NER-pipeline) --------------------------------
import train_relation as tr1, train_relation_evidence as tr2
cands = [json.loads(l) for l in open("/home/enes/NER-pipeline/data/processed/gt_100/candidates_v4.jsonl")]
c = [x for x in cands if str(x["pmid"]) == PMID and x["pathway_mentions"][0]["text"].lower() == "gtp synthesis"
     and x["disease_mentions"][0]["text"].lower() == "gbm"]
print("candidates", len(c), [ (x["candidate_id"], len(x["pathway_mentions"]), len(x["disease_mentions"])) for x in c])
c = c[0]
tok = AutoTokenizer.from_pretrained(HF)
text1, lo, hi = tr1.mark(c["abstract"], [(m["start"], m["end"]) for m in c["pathway_mentions"]],
                         [(m["start"], m["end"]) for m in c["disease_mentions"]])
ids1 = tok(text1, truncation=True, max_length=512)["input_ids"]
tok2 = AutoTokenizer.from_pretrained(HF); n_added = tok2.add_tokens(tr2.MARK_TOKENS)
text2, _, _ = tr2.mark_with_map(c["abstract"], [(m["start"], m["end"]) for m in c["pathway_mentions"]],
                                 [(m["start"], m["end"]) for m in c["disease_mentions"]])
ids2 = tok2(text2, truncation=True, max_length=512)["input_ids"]
enc = AutoModel.from_pretrained(HF).eval()
with torch.no_grad():
    h1 = enc(input_ids=torch.tensor([ids1])).last_hidden_state
out["abstract_chars"] = len(c["abstract"]); out["n_pathway_mentions"] = len(c["pathway_mentions"]); out["n_disease_mentions"] = len(c["disease_mentions"])
out["a1"] = {"L": len(ids1), "hidden": list(h1.shape), "vocab": tok.vocab_size}
enc.resize_token_embeddings(len(tok2))
with torch.no_grad():
    h2 = enc(input_ids=torch.tensor([ids2])).last_hidden_state
out["a2"] = {"L": len(ids2), "hidden": list(h2.shape), "vocab": len(tok2), "markers_added": n_added,
             "evidence_tags_shape": [len(ids2), 2]}
# real trained weights of arch 2: head shapes
sd = torch.load("/home/enes/NER-pipeline/models_re/relation_ft_evidence/ev_lam1_selF1_10kpm_s42/model.pt", map_location="cpu")
out["a2"]["heads"] = {k: list(v.shape) for k, v in sd.items() if "head" in k}
out["a2"]["embeddings"] = [list(v.shape) for k, v in sd.items() if k.endswith("word_embeddings.weight")]
m2 = tr2.TwoHeadModel(HF, 5, [0.558, 4.838], 1.0, vocab_size=len(tok2)).eval()
m2.load_state_dict(sd)
with torch.no_grad():
    o2 = m2(input_ids=torch.tensor([ids2]), attention_mask=torch.ones(1, len(ids2), dtype=torch.long))
lab = ["upregulation","downregulation","association","no_association_stated","none"]
out["a2"]["logits"] = list(o2["logits"].shape); out["a2"]["ev_logits"] = list(o2["evidence_logits"].shape)
out["a2"]["pred"] = lab[int(o2["logits"].argmax())]
evp = o2["evidence_logits"][0].argmax(-1).tolist()
out["a2"]["pred_ev_tokens"] = sum(evp)
out["a2"]["pred_ev_text"] = tok2.decode([t for t, e in zip(ids2, evp) if e == 1])

# ---- architectures 3 and 4 (pathway-re-synth) ------------------------------
sys.path[:] = [x for x in sys.path if "NER-pipeline" not in x]
for k in [k for k in sys.modules if k in ("schema","train","encoders")]: del sys.modules[k]
sys.path.insert(0, "/home/enes/pathway-re-synth")
import os; os.chdir("/home/enes/pathway-re-synth")
from train.data import encode
from train.model import RelationModel, EvidenceHead, sentence_features
rec = [json.loads(l) for l in open("data/gold/gt100_demos.jsonl")]
rec = [r for r in rec if r["seed_pmid"] == PMID and r["pathway"]["canonical"] == PW and r["disease"]["canonical"] == DS][0]
for name, run in (("a3", "mixed"), ("a4", "mixed_v2v3_ctx_s13_micro")):
    tk = AutoTokenizer.from_pretrained(f"checkpoints/{run}/tokenizer")
    e = encode(rec, tk)
    head = "context_pool" if name == "a4" else "first_marker"
    m = RelationModel(HF, 5, tk, head=head).eval()
    m.load_state_dict(torch.load(f"checkpoints/{run}/mixed/model.pt", map_location="cpu"))
    ids = torch.tensor([e["input_ids"]]); am = torch.ones_like(ids)
    L = ids.shape[1]
    pm = torch.zeros(1, L, dtype=torch.bool); dm = torch.zeros(1, L, dtype=torch.bool)
    pm[0, e["p_all"]] = True; dm[0, e["d_all"]] = True
    with torch.no_grad():
        states, pair, feats = m.encode_pair(ids, am, torch.tensor([e["p_idx"]]), torch.tensor([e["d_idx"]]), pm, dm)
        logits = m.classifier(feats)
        ts = torch.tensor(e["token_sentence"])
        sf = sentence_features(states[0], pair[0], ts, e["n_sentences"])
        eh = EvidenceHead(states.size(-1)); eh.eval(); eh.load_state_dict(torch.load(f"checkpoints/{run}/mixed/evidence_head.pt", map_location="cpu"))
        ev = torch.sigmoid(eh(sf))
    info = {"L": L, "states": list(states.shape), "pair": list(pair.shape), "classifier_in": list(feats.shape),
            "classifier_W": list(m.classifier.weight.shape), "logits": list(logits.shape),
            "pred": ["upregulation","downregulation","association","no_association_stated","none"][int(logits.argmax())],
            "n_P_markers": len(e["p_all"]), "n_D_markers": len(e["d_all"]), "n_sentences": e["n_sentences"],
            "sentence_features": list(sf.shape), "evidence_W1": list(eh.net[0].weight.shape),
            "evidence_W2": list(eh.net[3].weight.shape), "evidence_p": [round(x, 2) for x in ev.tolist()], "sentences": rec["sentences"],
            "vocab": len(tk), "gold_evidence": rec["evidence_sentences"], "gold_class": rec["class"]}
    if name == "a4":
        with torch.no_grad():
            o = m.encoder(input_ids=ids, attention_mask=am, output_attentions=True)
        info["attention_last_layer"] = list(o.attentions[-1].shape)
    out[name] = info
print(json.dumps(out, indent=1))
