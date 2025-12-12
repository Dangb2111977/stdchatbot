# backend.py — FastAPI + MySQL + JWT + optional GraphRAG + Voice (TTS/STT) + Hybrid BM25/FAISS
import os
import uuid
import bcrypt
import datetime as dt
from pathlib import Path
from typing import Optional, List, Dict, Any, Literal
import base64
import time  # đo thời gian

from dotenv import load_dotenv, find_dotenv

# =========================
# Paths, .env, uploads
# =========================
# Thư mục app, root, và file .env mà bạn muốn dùng
BASE_DIR = Path(__file__).resolve().parent      # .../Thesis/app
ROOT_DIR = BASE_DIR.parent                      # .../Thesis
ENV_PATH = ROOT_DIR / "app" / ".env"            # .../Thesis/app/.env

print("[DEBUG] .env path (find_dotenv):", find_dotenv())
print("[DEBUG] ENV_PATH:", ENV_PATH)

# Load .env theo đường dẫn bạn muốn
load_dotenv(ENV_PATH, override=True)

# PROJECT_DIR dùng cho resolve_path và uploads
PROJECT_DIR = BASE_DIR

# Thư mục lưu file upload (ảnh, audio)
UPLOAD_DIR = PROJECT_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ĐỌC API KEY TỪ BIẾN MÔI TRƯỜNG (KHÔNG HARD-CODE)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
print("[DEBUG] OPENAI_API_KEY length:", len(OPENAI_API_KEY))

# Model mặc định cho chat text (cũng có thể dùng gpt-4o-mini)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

try:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except Exception:
    client = None


import pymysql
from pymysql.cursors import DictCursor

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse

from jose import jwt, JWTError
from pydantic import BaseModel, Field

# =========================
# Paths & Config helpers
# =========================
def resolve_path(p: Optional[str], default: Path) -> str:
    # Expand ~ and %VARS%, and make absolute (relative to PROJECT_DIR if needed).
    if not p:
        path = default
    else:
        p = os.path.expandvars(os.path.expanduser(p.strip()))
        path = Path(p)
        if not path.is_absolute():
            path = (PROJECT_DIR / path).resolve()
    return str(path)



DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "")
DB_NAME = os.getenv("DB_NAME", "medchat")

JWT_SECRET = os.getenv("JWT_SECRET", "dev_secret_change_me")
JWT_ALG = "HS256"
ACCESS_MIN = int(os.getenv("ACCESS_MIN", "30"))
REFRESH_DAYS = int(os.getenv("REFRESH_DAYS", "30"))

GRAPHRAG_ENABLED = os.getenv("GRAPHRAG_ENABLED", "false").lower() == "true"

# data/graph paths (mặc định data ở ../data; alias_map ở ../)
DATA_DIR = resolve_path(os.getenv("DATA_DIR"), PROJECT_DIR.parent / "data")
CHUNKS_PATH = resolve_path(os.getenv("CHUNKS_PATH"), Path(DATA_DIR) / "chunks.jsonl")
GRAPH_PATH = resolve_path(os.getenv("GRAPH_PATH"), Path(DATA_DIR) / "graph.json")
ALIAS_PATH = resolve_path(os.getenv("ALIAS_PATH"), PROJECT_DIR.parent / "alias_map.json")

print("[GraphRAG] DATA_DIR   =", DATA_DIR)
print("[GraphRAG] CHUNKS_PATH=", CHUNKS_PATH)
print("[GraphRAG] GRAPH_PATH =", GRAPH_PATH)
print("[GraphRAG] ALIAS_PATH =", ALIAS_PATH)

BASE_DIR = Path(__file__).resolve().parent      # .../Thesis/app
ROOT_DIR = BASE_DIR.parent  
ENV_PATH = ROOT_DIR / "app" / ".env"           # .../Thesis/app/.env

load_dotenv(ENV_PATH, override=True)
# ĐỌC API KEY TỪ BIẾN MÔI TRƯỜNG (KHÔNG HARD-CODE)
PROJECT_DIR = BASE_DIR

# Thư mục lưu file upload (ảnh, audio)
UPLOAD_DIR = PROJECT_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
print("[DEBUG] OPENAI_API_KEY length:", len(OPENAI_API_KEY))

# Model mặc định cho chat text (cũng có thể dùng gpt-4o-mini)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

try:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except Exception:
    client = None


# =========================
# DB helpers
# =========================
def db_conn():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        cursorclass=DictCursor,
        autocommit=True,
    )


def db_exec(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description:
                return list(cur.fetchall())
            return []


def db_exec_one(sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    rows = db_exec(sql, params)
    return rows[0] if rows else None


# =========================
# Auth helpers
# =========================
def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _verify(pw: str, hpw: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hpw.encode())
    except Exception:
        return False


def _issue_tokens(user_id: int, username: str) -> Dict[str, str]:
    now = dt.datetime.utcnow()
    access_claims = {
        "uid": user_id,
        "usr": username,
        "type": "access",
        "exp": now + dt.timedelta(minutes=ACCESS_MIN),
    }
    refresh_claims = {
        "uid": user_id,
        "usr": username,
        "type": "refresh",
        "exp": now + dt.timedelta(days=REFRESH_DAYS),
    }
    return {
        "access_token": jwt.encode(access_claims, JWT_SECRET, algorithm=JWT_ALG),
        "refresh_token": jwt.encode(refresh_claims, JWT_SECRET, algorithm=JWT_ALG),
    }


# Dependency: MUST be a callable
def get_current_user(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    token = auth.split(" ", 1)[1].strip()
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError:
        raise HTTPException(401, "Invalid token")
    if data.get("type") != "access":
        raise HTTPException(401, "Not an access token")
    uid = data.get("uid")
    user = db_exec_one("SELECT id, username FROM users WHERE id=%s", (uid,))
    if not user:
        raise HTTPException(401, "User not found")
    return {"user_id": user["id"], "username": user["username"]}


# =========================
# Schemas
# =========================
class AuthIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str


class RefreshIn(BaseModel):
    refresh_token: str


class ConvoIn(BaseModel):
    title: Optional[str] = ""


class ChatIn(BaseModel):
    question: str
    history: Optional[List[List[str]]] = None
    convo_id: str
    top_k: int = 6
    lang: Literal["vi", "en"] = "vi"
    trace: bool = False


class ChatOut(BaseModel):
    answer: str
    saved_image_url: Optional[str] = None
    convo_id: Optional[str] = None
    trace: Optional[Dict[str, Any]] = None


# Voice models
class TTSIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000, description="Văn bản cần đọc")
    voice: str = Field("alloy", description="Giọng đọc (alloy|verse|harper|coral|aria|sage, ...)")
    # thêm mp3 để tránh 422 khi test
    format: Literal["m4a", "mp3", "wav", "ogg"] = Field("m4a", description="Định dạng audio")
    speed: float = Field(1.0, ge=0.25, le=4.0, description="Tốc độ đọc")


# =========================
# Optional GraphRAG wiring
# =========================
ALIAS = CHUNKS = GRAPH = None
if GRAPHRAG_ENABLED:
    try:
        from .graph_retriever import (
            load_alias_map,
            load_chunks as graph_load_chunks,
            load_graph,
            entity_link,
            expand_and_collect,
            build_context,
            detect_intent_sections,
        )


        ALIAS = load_alias_map(ALIAS_PATH)
        CHUNKS = graph_load_chunks(CHUNKS_PATH)
        GRAPH = load_graph(GRAPH_PATH)
        print("GraphRAG enabled. alias_map entries:", len(ALIAS or {}))
    except Exception as e:
        print("GraphRAG init failed:", e)
        GRAPHRAG_ENABLED = False

# Stubs when disabled (vẫn giữ build_context để dùng cho BM25/FAISS)
if not GRAPHRAG_ENABLED:
    def entity_link(text: str, alias_map=None, *a, **k):
        return []

    def expand_and_collect(*a, **k):
        return []

    def build_context(hits: List[Dict[str, Any]]) -> str:
        blocks = []
        for h in hits or []:
            head = f"[{h.get('title','')}/{h.get('section','')}] ({h.get('source','')})"
            blocks.append(f"{head}\n{h.get('text','')}")
        return "\n\n---\n\n".join(blocks)

    def detect_intent_sections(query: str):
        return set()


SAFETY_RULES = (
    "You are a careful medical assistant for STDs/STIs. "
    "Do not provide definitive diagnoses. Communicate uncertainty clearly. "
    "Encourage professional care for red-flag symptoms. "
    "Respect privacy; avoid storing PHI; use neutral language."
)

# =========================
# Lexical / Vector stores (BM25 + FAISS + hybrid utils)
# =========================
from .hybrid_retriever import rrf_merge, dedup_by_source_section, filter_by_section  # noqa: E402

BM25_STORE = None
FAISS_STORE = None

try:
    from .bm25_index import BM25Store, load_chunks as bm25_load_chunks  # noqa: E402

    bm25_chunks = bm25_load_chunks(CHUNKS_PATH)
    BM25_STORE = BM25Store(bm25_chunks)
    print(f"[BM25] loaded {len(bm25_chunks)} chunks")
except Exception as e:
    print("[BM25] init failed:", e)
    BM25_STORE = None

try:
    from .vector_search import FaissStore  # noqa: E402

    faiss_index_path = resolve_path(os.getenv("FAISS_INDEX_PATH"), Path(DATA_DIR) / "faiss.index")
    faiss_ids_path = resolve_path(os.getenv("FAISS_IDS_PATH"), Path(DATA_DIR) / "faiss.ids.npy")
    FAISS_STORE = FaissStore(
        index_path=faiss_index_path,
        ids_path=faiss_ids_path,
        chunks_path=CHUNKS_PATH,
    )
    print("[FAISS] index loaded")
except Exception as e:
    print("[FAISS] init failed:", e)
    FAISS_STORE = None


# =========================
# FastAPI app
# =========================
TAGS = [
    {"name": "Auth", "description": "Register / Login / Refresh"},
    {"name": "Conversations", "description": "Manage conversations & messages"},
    {"name": "Chat", "description": "Ask questions (trace supported)"},
    {"name": "Voice", "description": "Text-to-Speech (TTS) & Speech-to-Text (STT)"},
]

app = FastAPI(
    title="MedChat (STDs) API",
    description="LLM chatbot with hybrid BM25/FAISS + optional GraphRAG, MySQL + JWT.",
    version="1.2.0",
    openapi_tags=TAGS,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title, version=app.version, description=app.description, routes=app.routes
    )
    comps = schema.setdefault("components", {}).setdefault("securitySchemes", {})
    comps["BearerAuth"] = {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    for path, methods in schema.get("paths", {}).items():
        for m in methods.values():
            tags = m.get("tags", [])
            if "Auth" in tags:  # Auth endpoints don't require bearer
                continue
            m.setdefault("security", [{"BearerAuth": []}])
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi

# =========================
# Auth endpoints
# =========================
@app.post("/auth/register", tags=["Auth"])
def register(body: AuthIn):
    if db_exec_one("SELECT id FROM users WHERE username=%s", (body.username,)):
        raise HTTPException(400, "Username already exists")
    hpw = _hash(body.password)
    db_exec(
        "INSERT INTO users (username, password_hash, created_at) VALUES (%s,%s,NOW())",
        (body.username, hpw),
    )
    u = db_exec_one("SELECT id, username FROM users WHERE username=%s", (body.username,))
    return _issue_tokens(u["id"], u["username"])


@app.post("/auth/login", response_model=TokenOut, tags=["Auth"])
def login(body: AuthIn):
    u = db_exec_one("SELECT id, username, password_hash FROM users WHERE username=%s", (body.username,))
    if not u or not _verify(body.password, u["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    return _issue_tokens(u["id"], u["username"])


@app.post("/auth/refresh", response_model=TokenOut, tags=["Auth"])
def refresh(body: RefreshIn):
    try:
        data = jwt.decode(body.refresh_token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError:
        raise HTTPException(401, "Invalid refresh token")
    if data.get("type") != "refresh":
        raise HTTPException(401, "Not a refresh token")
    uid = data.get("uid")
    u = db_exec_one("SELECT id, username FROM users WHERE id=%s", (uid,))
    if not u:
        raise HTTPException(401, "User not found")
    return _issue_tokens(u["id"], u["username"])


@app.get("/me", tags=["Auth"])
def me(user=Depends(get_current_user)):
    return {"id": user["user_id"], "username": user["username"]}


# =========================
# Conversations
# =========================
@app.get("/conversations", tags=["Conversations"])
def list_convos(user=Depends(get_current_user)):
    return db_exec(
        "SELECT id, user_id, title, created_at, updated_at "
        "FROM conversations WHERE user_id=%s ORDER BY updated_at DESC, created_at DESC",
        (user["user_id"],),
    )


@app.post("/conversations", tags=["Conversations"])
def create_convo(body: ConvoIn, user=Depends(get_current_user)):
    cid = uuid.uuid4().hex
    title = (body.title or "").strip() or "conversation"
    db_exec(
        "INSERT INTO conversations (id, user_id, title, created_at, updated_at) "
        "VALUES (%s,%s,%s,NOW(),NOW())",
        (cid, user["user_id"], title),
    )
    return {"id": cid, "title": title}


@app.patch("/conversations/{cid}", tags=["Conversations"])
def rename_convo(cid: str, body: ConvoIn, user=Depends(get_current_user)):
    db_exec(
        "UPDATE conversations SET title=%s, updated_at=NOW() WHERE id=%s AND user_id=%s",
        ((body.title or "").strip(), cid, user["user_id"]),
    )
    return {"ok": True}


@app.delete("/conversations/{cid}", tags=["Conversations"])
def delete_convo(cid: str, user=Depends(get_current_user)):
    db_exec("DELETE FROM chat_messages WHERE convo_id=%s AND user_id=%s", (cid, user["user_id"]))
    db_exec("DELETE FROM conversations WHERE id=%s AND user_id=%s", (cid, user["user_id"]))
    return {"ok": True}


@app.get("/conversations/{cid}/messages", tags=["Conversations"])
def list_messages(cid: str, user=Depends(get_current_user)):
    rows = db_exec(
        "SELECT role AS role, CASE WHEN image_path IS NULL THEN 'text' ELSE 'image' END AS mtype, "
        "question AS content, answer, image_path, created_at "
        "FROM chat_messages WHERE convo_id=%s AND user_id=%s ORDER BY id ASC",
        (cid, user["user_id"]),
    )
    msgs = []
    for r in rows:
        if r["mtype"] == "image":
            msgs.append(
                {
                    "role": "user",
                    "mtype": "image",
                    "image_path": r["image_path"],
                    "content": r.get("content") or "",
                }
            )
            if r.get("answer"):
                msgs.append({"role": "bot", "mtype": "text", "content": r["answer"]})
        else:
            if r.get("content"):
                msgs.append({"role": "user", "mtype": "text", "content": r["content"]})
            if r.get("answer"):
                msgs.append({"role": "bot", "mtype": "text", "content": r["answer"]})
    return msgs


# =========================
# Chat (TEXT) — hybrid BM25/FAISS + optional GraphRAG, with trace + timing
# =========================
@app.post("/chat", response_model=ChatOut, tags=["Chat"])
def chat(body: ChatIn, user=Depends(get_current_user)):
    # bắt đầu đo thời gian toàn pipeline
    t0 = time.perf_counter()

    user_input = (body.question or "").strip()
    if not user_input:
        raise HTTPException(400, "question is required")

    # ensure conversation exists
    if not db_exec_one(
        "SELECT id FROM conversations WHERE id=%s AND user_id=%s",
        (body.convo_id, user["user_id"]),
    ):
        db_exec(
            "INSERT INTO conversations (id, user_id, title, created_at, updated_at) "
            "VALUES (%s,%s,%s,NOW(),NOW())",
            (body.convo_id, user["user_id"], user_input[:200]),
        )

    # trace defaults
    trace_info: Dict[str, Any] = {
        "mode": "llm_only",
        "used_context": False,
        "candidates": [],
        "bm25_k": 0,
        "faiss_k": 0,
        "graph_k": 0,
    }

    # ---------- 1. Intent (section) ----------
    # dùng lại mapping từ graph_retriever nếu có, để ưu tiên Symptoms/Diagnosis/Treatment/Prevention
    try:
        intent_nodes = detect_intent_sections(user_input)
    except Exception:
        intent_nodes = set()
    intent_section_names = {
        node.split(":", 1)[1].capitalize()
        for node in (intent_nodes or [])
        if isinstance(node, str) and node.startswith("sec:")
    }

    # ---------- 2. BM25 + FAISS ----------
    context_block = None
    context_hits: List[Dict[str, Any]] = []

    bm25_hits: List[Dict[str, Any]] = []
    faiss_hits: List[Dict[str, Any]] = []
    hybrid_hits: List[Dict[str, Any]] = []

    if BM25_STORE:
        try:
            bm25_hits = BM25_STORE.search(user_input, k=max(body.top_k, 8))
            for h in bm25_hits:
                h["channel"] = "bm25"
        except Exception as e:
            print("[BM25] search error:", e)
            bm25_hits = []

    if FAISS_STORE:
        try:
            faiss_hits = FAISS_STORE.search(user_input, k=max(body.top_k, 8))
            for h in faiss_hits:
                h["channel"] = "faiss"
        except Exception as e:
            print("[FAISS] search error:", e)
            faiss_hits = []

    trace_info["bm25_k"] = len(bm25_hits)
    trace_info["faiss_k"] = len(faiss_hits)

    base_hits: List[Dict[str, Any]] = []

    if bm25_hits or faiss_hits:
        if bm25_hits and faiss_hits:
            # RRF fusion
            hybrid_hits = rrf_merge(bm25_hits, faiss_hits, k=max(body.top_k, 8), k_bias=60)
            # nếu người dùng hỏi rõ về "triệu chứng", "xét nghiệm", ... thì filter theo section
            if intent_section_names:
                filtered = filter_by_section(hybrid_hits, intent_section_names)
                if filtered:
                    hybrid_hits = filtered
            for h in hybrid_hits:
                h.setdefault("channel", "hybrid")
            base_hits = hybrid_hits
            trace_info["mode"] = "hybrid_bm25_faiss"
        elif bm25_hits:
            if intent_section_names:
                filtered = filter_by_section(bm25_hits, intent_section_names)
                if filtered:
                    bm25_hits = filtered
            base_hits = bm25_hits
            trace_info["mode"] = "bm25_only"
        else:
            if intent_section_names:
                filtered = filter_by_section(faiss_hits, intent_section_names)
                if filtered:
                    faiss_hits = filtered
            base_hits = faiss_hits
            trace_info["mode"] = "faiss_only"

    # ---------- 3. GraphRAG (optional) ----------
    graph_hits: List[Dict[str, Any]] = []
    seeds = None
    if GRAPHRAG_ENABLED:
        try:
            seeds = entity_link(user_input, ALIAS, topn=3)
            if seeds:
                graph_hits = expand_and_collect(
                    seeds,
                    GRAPH,
                    CHUNKS,
                    budget=30,
                    topk=min(5, body.top_k),
                    query=user_input,
                    intent_sections=intent_nodes,
                    allowed_sections=None,
                )
                for h in graph_hits:
                    h["channel"] = "graph"
        except Exception as e:
            print("[GraphRAG] error:", e)
            graph_hits = []

    trace_info["graph_k"] = len(graph_hits)

    # ---------- 4. Merge hits + build context ----------
    if base_hits or graph_hits:
        combined = base_hits + graph_hits
        combined = dedup_by_source_section(combined)
        # keep at most top_k passages
        context_hits = combined[: body.top_k]
        context_block = build_context(context_hits)
        trace_info["used_context"] = True

        trace_info["candidates"] = [
            {
                "chunk_id": h.get("id"),
                "title": h.get("title"),
                "section": h.get("section"),
                "source": h.get("source"),
                "score": h.get("score"),
                "rrf": h.get("rrf"),
                "channel": h.get("channel"),
            }
            for h in context_hits
        ]

        if GRAPHRAG_ENABLED and graph_hits:
            if seeds:
                trace_info["seeds"] = list(seeds)
            if trace_info["mode"] == "llm_only":
                trace_info["mode"] = "graph_only"
            elif "graph" not in (trace_info["mode"] or ""):
                trace_info["mode"] = f"{trace_info['mode']}+graph"
    else:
        context_block = None

    # ---------- 5. Build messages ----------
    messages = [{"role": "system", "content": SAFETY_RULES}]
    if context_block:
        messages += [
            {
                "role": "system",
                "content": "Use the medical context below if relevant; keep answers concise and cite titles/sections when helpful.",
            },
            {"role": "system", "content": context_block},
        ]
    for pair in (body.history or []):
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            messages.append({"role": "user", "content": pair[0] or ""})
            messages.append({"role": "assistant", "content": pair[1] or ""})
    messages.append({"role": "user", "content": user_input})

    # ---------- 6. Call LLM ----------
    if client:
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=0.2,
            )
            answer = (resp.choices[0].message.content or "").strip()
        except Exception as e:
            print("OpenAI error:", e)
            answer = "Xin lỗi, hệ thống đang gặp sự cố. Vui lòng thử lại sau."
    else:
        answer = "[demo] No OpenAI configured. This is a placeholder answer."

    # đo thời gian sau khi có answer
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    trace_info["elapsed_ms"] = round(elapsed_ms, 1)

    # persist single row (user question + assistant answer)
    db_exec(
        "INSERT INTO chat_messages (convo_id, user_id, role, message_type, question, answer, created_at) "
        "VALUES (%s,%s,'user','text',%s,%s,NOW())",
        (body.convo_id, user["user_id"], user_input, answer),
    )
    db_exec("UPDATE conversations SET updated_at=NOW() WHERE id=%s", (body.convo_id,))

    # Log trace ra terminal
    if body.trace:
        mode = trace_info.get("mode")
        used = trace_info.get("used_context")
        cands = trace_info.get("candidates") or []
        k = len(cands)
        top_titles = [c.get("title") or c.get("chunk_id") for c in cands[:3]]
        seeds = trace_info.get("seeds")

        print(
            f"[TRACE] mode={mode} used={used} k={k} "
            f"elapsed={trace_info['elapsed_ms']}ms "
            f"seeds={seeds} top={top_titles}"
        )

    return {
        "answer": answer,
        "saved_image_url": None,
        "convo_id": body.convo_id,
        "trace": trace_info if body.trace else None,
    }


# =========================
# Chat (IMAGE) — Vision với gpt-4o-mini
# =========================
# =========================
# Chat (IMAGE) — Vision với gpt-4o-mini
# =========================
@app.post("/chat-image", tags=["Chat"])
def chat_image(
    convo_id: str = Form(...),
    question: str = Form(""),
    image: UploadFile = File(...),
    user=Depends(get_current_user),
):
    # Lưu file ảnh
    ext = (Path(image.filename).suffix or ".jpg").lower()
    fname = uuid.uuid4().hex + ext
    dest = UPLOAD_DIR / fname
    img_bytes = image.file.read()
    with dest.open("wb") as f:
        f.write(img_bytes)

    # Mặc định: nếu không gọi được OpenAI thì trả câu này
    answer = (
        "Ảnh đã được nhận nhưng hệ thống chưa phân tích được "
        "(chưa cấu hình OpenAI hoặc đang gặp lỗi)."
    )

    # Debug: xem client có tồn tại không
    if client is None:
        print(
            "[chat-image] client is None → bỏ qua gọi OpenAI "
            f"(OPENAI_API_KEY length = {len(OPENAI_API_KEY)})"
        )
    else:
        try:
            print(f"[chat-image] chuẩn bị gửi ảnh lên OpenAI, size = {len(img_bytes)} bytes")

            # encode ảnh sang base64 để gửi kèm trong message
            b64 = base64.b64encode(img_bytes).decode("ascii")
            mime = "image/jpeg"
            if ext in [".png"]:
                mime = "image/png"

            user_content = []
            q = (question or "").strip()
            if q:
                user_content.append({"type": "text", "text": q})
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime};base64,{b64}",
                    },
                }
            )

            messages = [
                {
                    "role": "system",
                    "content": SAFETY_RULES
                    + " You also see images. "
                    + "Never chẩn đoán HIV/STD chỉ dựa trên hình. "
                    + "Chỉ cung cấp thông tin tổng quát và luôn khuyên gặp bác sĩ.",
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ]

            # DÙNG CỨNG gpt-4o-mini CHO VISION
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.2,
            )
            answer = (resp.choices[0].message.content or "").strip()
            print("[chat-image] OpenAI vision OK, answer length =", len(answer))
        except Exception as e:
            print("[chat-image] OpenAI vision error:", e)
            answer = (
                "Ảnh đã được nhận nhưng hệ thống gặp lỗi khi phân tích. "
                "Bạn có thể thử lại sau, hoặc mô tả vấn đề bằng chữ để chatbot hỗ trợ."
            )

    # Lưu vào DB như cũ
    db_exec(
        "INSERT INTO chat_messages (convo_id, user_id, role, message_type, question, answer, image_path, created_at) "
        "VALUES (%s,%s,'user','image',%s,%s,%s,NOW())",
        (convo_id, user["user_id"], question, answer, f"/uploads/{fname}"),
    )
    db_exec("UPDATE conversations SET updated_at=NOW() WHERE id=%s", (convo_id,))

    return {
        "answer": answer,
        "image_path": f"/uploads/{fname}",
        "convo_id": convo_id,
    }



# =========================
# Voice: Text → Speech (TTS)
# =========================
@app.post("/voice/tts", tags=["Voice"])
def voice_tts(
    body: TTSIn,
    download: bool = Query(False, description="Trả file trực tiếp thay vì JSON"),
):
    if not client:
        raise HTTPException(500, "OPENAI_API_KEY is not configured")

    # Chuẩn hoá format cho SDK (một số bản không hỗ trợ m4a trực tiếp)
    want_fmt = (body.format or "m4a").lower()
    # map cho SDK: m4a → mp3 để tương thích, các loại khác giữ nguyên
    api_fmt = "mp3" if want_fmt == "m4a" else want_fmt

    try:
        # 1) Thử với tham số 'format' (SDK mới)
        try:
            resp = client.audio.speech.create(
                model="gpt-4o-mini-tts",
                voice=body.voice,
                input=body.text,
                format=api_fmt,
                speed=body.speed,
            )
        except TypeError:
            # 2) Thử lại với 'response_format' (SDK cũ hơn)
            resp = client.audio.speech.create(
                model="gpt-4o-mini-tts",
                voice=body.voice,
                input=body.text,
                response_format=api_fmt,
                speed=body.speed,
            )

        # Lấy bytes âm thanh theo nhiều kiểu trả về
        audio_bytes = None
        if hasattr(resp, "read"):
            audio_bytes = resp.read()
        elif hasattr(resp, "content"):
            audio_bytes = resp.content
        elif hasattr(resp, "to_bytes"):
            audio_bytes = resp.to_bytes()

        if not audio_bytes:
            raise RuntimeError("Empty audio response")

        # Lưu file với đuôi đúng như user chọn (kể cả m4a → nội dung mp3)
        ext = want_fmt
        filename = f"tts_{uuid.uuid4().hex}.{ext}"
        out_path = UPLOAD_DIR / filename
        with open(out_path, "wb") as f:
            f.write(audio_bytes)

        if download:
            media_map = {
                "m4a": "audio/mpeg",
                "mp3": "audio/mpeg",
                "wav": "audio/wav",
                "ogg": "audio/ogg",
            }
            media = media_map.get(ext, "application/octet-stream")
            return FileResponse(path=str(out_path), filename=filename, media_type=media)

        return {
            "ok": True,
            "audio_path": f"/uploads/{filename}",
            "size": len(audio_bytes),
            "voice": body.voice,
            "format": ext,
            "speed": body.speed,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS error: {e}")


# =========================
# Voice: Speech → Text (STT)
# =========================
@app.post("/voice/transcribe", tags=["Voice"])
async def voice_transcribe(
    audio: UploadFile = File(..., description="Tệp âm thanh (mp3/wav/m4a/webm/ogg)")
):
    if not client:
        raise HTTPException(500, "OPENAI_API_KEY is not configured")

    try:
        suffix = Path(audio.filename).suffix.lower()
        if suffix not in {".mp3", ".wav", ".m4a", ".webm", ".ogg"}:
            raise HTTPException(status_code=400, detail="Định dạng audio không hỗ trợ")

        tmp_name = f"stt_{uuid.uuid4().hex}{suffix}"
        tmp_path = UPLOAD_DIR / tmp_name
        data = await audio.read()
        with open(tmp_path, "wb") as f:
            f.write(data)

        with open(tmp_path, "rb") as f:
            r = client.audio.transcriptions.create(
                model="gpt-4o-transcribe",  # hoặc 'whisper-1' nếu account chưa có model mới
                file=f,
            )
        text = getattr(r, "text", None) or getattr(r, "transcript", None) or ""
        return {"ok": True, "text": text.strip(), "audio_path": f"/uploads/{tmp_name}"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcribe error: {e}")


@app.get("/voice/voices", tags=["Voice"])
def voice_voices():
    return {"voices": ["alloy", "verse", "harper", "coral", "aria", "sage"], "default": "alloy"}


# =========================
# Health
# =========================
@app.get("/healthz")
def healthz():
    return {"ok": True}
