# graph_retriever.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import json, re
from typing import Dict, Any, List, Tuple
from collections import deque, defaultdict
from rapidfuzz import fuzz

# ---------- Loaders ----------
def load_alias_map(path: str) -> Dict[str, Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_chunks(path: str) -> Dict[int, Dict[str, Any]]:
    chunks = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            chunks[int(obj["id"])] = obj
    return chunks

def load_graph(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ---------- Intent mapping (VI/EN) ----------
INTENT_SECTIONS = {
    # vi -> section
    "triệu chứng": "Symptoms", "dấu hiệu": "Symptoms",
    "xét nghiệm": "Diagnosis", "chẩn đoán": "Diagnosis", "test": "Diagnosis",
    "điều trị": "Treatment", "thuốc": "Treatment",
    "phòng ngừa": "Prevention", "ngừa": "Prevention", "vaccine": "Prevention",
    # en -> section
    "symptom": "Symptoms",
    "diagnosis": "Diagnosis", "testing": "Diagnosis", "test": "Diagnosis",
    "treatment": "Treatment", "therapy": "Treatment",
    "prevention": "Prevention", "vaccine": "Prevention"
}

def detect_intent_sections(query: str):
    """Trả về set các node section mong muốn, ví dụ {'sec:diagnosis'}."""
    q = (query or "").lower()
    secs = set()
    for kw, sec in INTENT_SECTIONS.items():
        if kw in q:
            secs.add(f"sec:{sec.lower()}")
    return secs

# ---------- Entity linking ----------
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()

def entity_link(query: str, alias_map: Dict[str, Dict[str, Any]], topn=3, thresh=82) -> List[Tuple[str, int]]:
    """Ghép thực thể từ query vào alias_map; trả về [(node_id, score), ...]."""
    q = _norm(query)
    cands: List[Tuple[str,int]] = []
    for nid, obj in alias_map.items():
        names = [obj.get("name", "")] + obj.get("aliases", [])
        if not any(names): 
            continue
        score = max(fuzz.token_set_ratio(q, _norm(a)) for a in names if a)
        if score >= thresh:
            cands.append((nid, score))
    cands.sort(key=lambda x: -x[1])
    return cands[:topn]

# ---------- Graph expand + collect evidence ----------
def expand_and_collect(
    seeds, graph, chunks, budget: int = 30, topk: int = 5, query: str = "",
    intent_sections: set | None = None,
    allowed_sections: set | None = None,     # <— MỚI
):
    if not seeds:
        return []
    adj = graph.get("adj", {})
    seen = set()
    q = deque((nid, 0, sc) for nid, sc in seeds)
    scores = defaultdict(float)

    def kw_overlap(txt: str, qtext: str) -> float:
        if not qtext: return 0.0
        qtoks = set(re.findall(r"[a-zA-Z0-9À-ỹ]+", qtext.lower()))
        ttoks = set(re.findall(r"[a-zA-Z0-9À-ỹ]+", (txt or "").lower()))
        return len(qtoks & ttoks) / (1 + len(qtoks)) if qtoks else 0.0

    steps = 0
    while q and steps < budget:
        nid, hop, seed_sc = q.popleft()
        if nid in seen: 
            continue
        seen.add(nid)
        for edge in adj.get(nid, []):
            dst = edge.get("dst")  # dạng "sec:diagnosis", "sec:symptoms", ...
            # nếu truyền allowed_sections thì chỉ xét edge vào các section cho phép
            if allowed_sections and dst not in allowed_sections:
                continue

            w = float(edge.get("weight", 1.0))
            hop_penalty = 1.0 / (1.0 + hop)

            for cid in edge.get("evidence", []):
                ch = chunks.get(int(cid))
                if not ch: 
                    continue
                base = (seed_sc/100.0) * w * hop_penalty
                base += 0.30 * kw_overlap(ch.get("text",""), query)
                if intent_sections and dst in intent_sections:
                    base *= 1.8
                scores[int(cid)] += base

            if hop < 1:
                q.append((dst, hop+1, seed_sc))
        steps += 1

    ranked = sorted(scores.items(), key=lambda x: -x[1])[:max(topk, 1)]
    out = []
    for rank, (cid, sc) in enumerate(ranked, start=1):
        ch = chunks[int(cid)]
        out.append({
            "rank": rank, "score": float(sc), "id": int(cid),
            "title": ch.get("title",""), "section": ch.get("section",""),
            "source": ch.get("source",""), "text": (ch.get("text","") or "").strip()
        })
    return out

# ---------- Context builder ----------
def build_context(hits: List[Dict[str, Any]]) -> str:
    """Ghép context có tiêu đề/section/nguồn để tiêm vào prompt."""
    blocks = []
    for h in hits:
        head = f"[{h.get('title','')}/{h.get('section','')}] ({h.get('source','')})"
        blocks.append(f"{head}\n{h.get('text','')}")
    return "\n\n---\n\n".join(blocks)
