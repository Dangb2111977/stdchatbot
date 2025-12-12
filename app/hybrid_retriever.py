
from typing import List, Dict, Any, Tuple

def rrf_merge(a: List[Dict[str,Any]], b: List[Dict[str,Any]], k=5, k_bias=60):
    """Reciprocal Rank Fusion — hợp nhất 2 danh sách hits theo thứ hạng."""
    ranks = {}
    meta = {}
    for lst in (a, b):
        for r, h in enumerate(lst, 1):
            cid = int(h["id"])
            ranks[cid] = ranks.get(cid, 0.0) + 1.0 / (k_bias + r)
            if cid not in meta:
                meta[cid] = h
    ids = sorted(ranks.keys(), key=lambda cid: -ranks[cid])[:k]
    return [meta[i] | {"rrf": ranks[i]} for i in ids]

def dedup_by_source_section(hits: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
    seen, out = set(), []
    for h in hits:
        key = (h.get("source",""), h.get("section",""))
        if key not in seen:
            seen.add(key); out.append(h)
    return out

def filter_by_section(hits: List[Dict[str,Any]], allowed_sections_names: set | None):
    """allowed_sections_names = {'Diagnosis','Symptoms',...}"""
    if not allowed_sections_names:
        return hits
    return [h for h in hits if h.get("section","").title() in allowed_sections_names]
