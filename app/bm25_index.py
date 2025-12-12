
import json, re
from typing import List, Dict, Any
from rank_bm25 import BM25Okapi

def load_chunks(path="data/chunks.jsonl") -> List[Dict[str, Any]]:
    chunks = []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                chunks.append(json.loads(ln))
    return chunks

def _tok(s: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9À-ỹ]+", (s or "").lower())

class BM25Store:
    def __init__(self, chunks: List[Dict[str, Any]]):
        self.chunks = chunks
        corpus = [_tok(c.get("text","")) for c in chunks]
        self.bm25 = BM25Okapi(corpus)

    def search(self, query: str, k=8) -> List[Dict[str, Any]]:
        scores = self.bm25.get_scores(_tok(query))
        ids = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        out = []
        for rank, i in enumerate(ids, 1):
            ch = self.chunks[i]
            out.append({
                "id": int(ch["id"]),
                "score": float(scores[i]),
                "title": ch.get("title",""),
                "section": ch.get("section",""),
                "source": ch.get("source",""),
                "text": (ch.get("text","") or "").strip()
            })
        return out
