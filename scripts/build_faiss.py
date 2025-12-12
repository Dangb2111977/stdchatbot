import os, json, numpy as np, faiss
from openai import OpenAI
from dotenv import load_dotenv

# Load .env từ thư mục app (local của bạn)
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))   # .../Thesis
ENV_PATH = os.path.join(ROOT_DIR, "app", ".env")        # .../Thesis/app/.env
load_dotenv(ENV_PATH, override=True)

EMB_MODEL = os.getenv("EMB_MODEL", "text-embedding-3-small")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY for build_faiss.py")

client = OpenAI(api_key=OPENAI_API_KEY)

def load_chunks(path="data/chunks.jsonl"):
    ids, texts, metas = [], [], []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                obj = json.loads(ln)
                ids.append(int(obj["id"]))
                texts.append(obj.get("text", ""))
                metas.append(obj)
    return ids, texts, metas

def embed_batches(texts, batch=256):
    vecs = []
    for i in range(0, len(texts), batch):
        batch_texts = texts[i:i+batch]
        resp = client.embeddings.create(
            model=EMB_MODEL,
            input=batch_texts,
        )
        vecs.extend([item.embedding for item in resp.data])
    X = np.array(vecs, dtype="float32")
    faiss.normalize_L2(X)
    return X

if __name__ == "__main__":
    ids, texts, _ = load_chunks()
    X = embed_batches(texts)
    index = faiss.IndexFlatIP(X.shape[1])  # cosine ~ inner product
    index.add(X)

    # ✅ GHI ĐÚNG CÁCH: truyền cả index lẫn đường dẫn
    faiss.write_index(index, "data/faiss.index")
    np.save("data/faiss.ids.npy", np.array(ids, dtype="int64"))

    print("Saved: data/faiss.index & data/faiss.ids.npy | dim:", X.shape[1], "| nvecs:", X.shape[0])
