# vector_search.py
# -*- coding: utf-8 -*-
import os
import json
from typing import Dict, Any, List
from pathlib import Path

import numpy as np
import faiss
from openai import OpenAI
from dotenv import load_dotenv

# =============================
# Load .env giống build_faiss
# =============================
# backend.py và file này đều nằm trong: .../Thesis/app
# ROOT_DIR = .../Thesis
BASE_DIR = Path(__file__).resolve().parent      # .../Thesis/app
ROOT_DIR = BASE_DIR.parent                      # .../Thesis
ENV_PATH = ROOT_DIR / "app" / ".env"           # .../Thesis/app/.env

load_dotenv(ENV_PATH, override=True)
EMB_MODEL = os.getenv("EMB_MODEL", "text-embedding-3-small")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

def _resolve_path(p: str) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


def load_chunks_map(path: str) -> Dict[int, Dict[str, Any]]:
    """
    Đọc chunks.jsonl thành dict: {id: obj}
    """
    fpath = _resolve_path(path)
    m: Dict[int, Dict[str, Any]] = {}
    with fpath.open("r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            obj = json.loads(ln)
            m[int(obj["id"])] = obj
    return m


# =============================
# FaissStore
# =============================
class FaissStore:
    def __init__(
        self,
        index_path: str = "data/faiss.index",
        ids_path: str = "data/faiss.ids.npy",
        chunks_path: str = "data/chunks.jsonl",
    ):
        self.index_path = str(_resolve_path(index_path))
        self.ids_path = str(_resolve_path(ids_path))
        self.chunks_path = chunks_path  # để load bằng helper (tự resolve)

        # Load index + ids + chunks
        self.index = faiss.read_index(self.index_path)
        self.ids = np.load(self.ids_path)
        self.chunks = load_chunks_map(self.chunks_path)

        print(
            f"[FAISS] store ready | dim={self.index.d}, "
            f"nvecs={self.index.ntotal}, "
            f"ids={self.ids.shape[0]}"
        )

    def _embed(self, q: str) -> np.ndarray:
        """
        Embed một câu query → vector 1 x dim, đã normalize L2.
        """
        if not client:
            raise RuntimeError("OpenAI client is not configured (missing OPENAI_API_KEY)")

        resp = client.embeddings.create(
            model=EMB_MODEL,
            input=[q],
        )
        x = np.array(resp.data[0].embedding, dtype="float32").reshape(1, -1)
        faiss.normalize_L2(x)
        return x

    def search(self, query: str, k: int = 8) -> List[Dict[str, Any]]:
        """
        Tìm k chunks gần nhất cho query.
        Trả về list các dict: id, score, title, section, source, text.
        """
        x = self._embed(query)
        D, I = self.index.search(x, k)

        out: List[Dict[str, Any]] = []
        for score, idx in zip(D[0], I[0]):
            cid = int(self.ids[idx])
            ch = self.chunks.get(cid, {})
            out.append(
                {
                    "id": cid,
                    "score": float(score),
                    "title": ch.get("title", ""),
                    "section": ch.get("section", ""),
                    "source": ch.get("source", ""),
                    "text": (ch.get("text", "") or "").strip(),
                }
            )
        return out
