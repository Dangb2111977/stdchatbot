#!/usr/bin/env python
# eval_retrieval.py
# Gọi backend /chat với trace=true cho bộ eval_queries.csv
# và tính Hit@1/3/6 theo section + intent, có mapping Testing/Transmission.

import csv
import json
import time
import collections
from typing import List, Dict, Any

import requests

# =========================
# CONFIG
# =========================
API_BASE = "http://127.0.0.1:8000"

# User dùng riêng cho eval (có thể chưa tồn tại trong DB)
USERNAME = "eval_user"
PASSWORD = "Eval123!@#"

CSV_PATH = "eval_queries.csv"
RESULT_JSON = "eval_results.json"

# Nếu muốn vẽ hình bar Hit@k by intent thì đặt True
MAKE_FIGURE = True

# =========================
# SECTION MAP
# =========================
# Map nhãn expected_section (trong CSV) sang các nhãn section thật trong corpus.
# Nếu không có trong map, sẽ dùng chính tên đó.
SECTION_MAP = {
    "Symptoms": {"Symptoms"},
    "Treatment": {"Treatment"},
    "Prevention": {"Prevention"},
    # Testing: content thường nằm ở Diagnosis hoặc General
    "Testing": {"Diagnosis", "General"},
    # Transmission: content thường nằm ở General hoặc Definition
    "Transmission": {"General", "Definition"},
}


# =========================
# Helper: lấy access_token
# =========================
def get_access_token() -> str:
    payload = {"username": USERNAME, "password": PASSWORD}

    # 1) Thử login
    url_login = f"{API_BASE}/auth/login"
    resp = requests.post(url_login, json=payload, timeout=30)

    print(f"[DEBUG] /auth/login status={resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError("Không nhận được access_token từ /auth/login")
        return token

    # 2) Nếu 401 thì cố gắng đăng ký user mới
    if resp.status_code == 401:
        url_reg = f"{API_BASE}/auth/register"
        print("[INFO] /auth/login 401 → thử /auth/register ...")
        reg = requests.post(url_reg, json=payload, timeout=30)
        print(f"[DEBUG] /auth/register status={reg.status_code} body={reg.text}")
        if reg.status_code not in (200, 201):
            raise RuntimeError(
                f"/auth/login 401 và /auth/register thất bại: {reg.status_code} {reg.text}"
            )
        data = reg.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError("Không nhận được access_token từ /auth/register")
        print("[INFO] Đã đăng ký user eval thành công.")
        return token

    # 3) Các lỗi khác
    print(f"[DEBUG] /auth/login body={resp.text}")
    resp.raise_for_status()
    raise RuntimeError("Không lấy được access_token")


# =========================
# Load CSV
# =========================
def load_queries(path: str) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


# =========================
# Gọi /chat cho từng câu hỏi
# =========================
def run_evaluation() -> List[Dict[str, Any]]:
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    queries = load_queries(CSV_PATH)
    results: List[Dict[str, Any]] = []

    for idx, row in enumerate(queries, start=1):
        qid = row["id"]
        query = row["query"]
        lang = row["lang"]
        expected = row["expected_section"]
        intent = row["intent"]

        payload = {
            "question": query,
            "history": [],
            "convo_id": f"eval_{qid}",
            "top_k": 6,
            "lang": lang,
            "trace": True,
        }

        url = f"{API_BASE}/chat"
        t0 = time.perf_counter()
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[ERROR] {qid}: {e}")
            results.append(
                {
                    "id": qid,
                    "intent": intent,
                    "expected_section": expected,
                    "query": query,
                    "ok": False,
                    "error": str(e),
                    "top_sections": [],
                    "mode": None,
                    "elapsed_ms": None,
                }
            )
            continue

        trace = data.get("trace") or {}
        cands = trace.get("candidates") or []
        top_sections = [c.get("section") for c in cands]

        elapsed_ms = trace.get("elapsed_ms", round(latency_ms, 1))

        results.append(
            {
                "id": qid,
                "intent": intent,
                "expected_section": expected,
                "query": query,
                "ok": True,
                "top_sections": top_sections,
                "mode": trace.get("mode"),
                "bm25_k": trace.get("bm25_k"),
                "faiss_k": trace.get("faiss_k"),
                "graph_k": trace.get("graph_k"),
                "used_context": trace.get("used_context"),
                "elapsed_ms": elapsed_ms,
            }
        )

        print(f"[{idx:03d}/{len(queries)}] {qid} done, sections={top_sections[:3]}")

    with open(RESULT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nĐã lưu kết quả vào {RESULT_JSON}")
    return results


# =========================
# Tính Hit@k theo section (có SECTION_MAP)
# =========================
def compute_metrics(results: List[Dict[str, Any]]) -> None:
    overall = {"n": 0, "h1": 0, "h3": 0, "h6": 0}
    per_intent: Dict[str, Dict[str, int]] = collections.defaultdict(
        lambda: {"n": 0, "h1": 0, "h3": 0, "h6": 0}
    )

    latencies: List[float] = []

    for r in results:
        if not r.get("ok"):
            continue

        exp = r["expected_section"]
        top = r.get("top_sections") or []
        intent = r["intent"]

        # dùng mapping: Testing/Transmission → Diagnosis/General/Definition
        targets = SECTION_MAP.get(exp, {exp})

        hit1 = len(top) >= 1 and top[0] in targets
        hit3 = any(s in targets for s in top[:3])
        hit6 = any(s in targets for s in top[:6])

        overall["n"] += 1
        overall["h1"] += int(hit1)
        overall["h3"] += int(hit3)
        overall["h6"] += int(hit6)

        per_intent[intent]["n"] += 1
        per_intent[intent]["h1"] += int(hit1)
        per_intent[intent]["h3"] += int(hit3)
        per_intent[intent]["h6"] += int(hit6)

        if r.get("elapsed_ms") is not None:
            latencies.append(float(r["elapsed_ms"]))

    def ratio(x: int, n: int) -> float:
        return 0.0 if n == 0 else x / n

    print("\n===== OVERALL RETRIEVAL METRICS (with section mapping) =====")
    n = overall["n"]
    if n == 0:
        print("Không có bản ghi hợp lệ.")
    else:
        print(f"Total queries: {n}")
        print(f"Hit@1: {overall['h1']}/{n} = {ratio(overall['h1'], n):.3f}")
        print(f"Hit@3: {overall['h3']}/{n} = {ratio(overall['h3'], n):.3f}")
        print(f"Hit@6: {overall['h6']}/{n} = {ratio(overall['h6'], n):.3f}")

    print("\n===== METRICS PER INTENT (with section mapping) =====")
    for intent, c in per_intent.items():
        n_i = c["n"]
        if n_i == 0:
            continue
        print(f"\nIntent: {intent}")
        print(f"  Queries: {n_i}")
        print(f"  Hit@1: {c['h1']}/{n_i} = {ratio(c['h1'], n_i):.3f}")
        print(f"  Hit@3: {c['h3']}/{n_i} = {ratio(c['h3'], n_i):.3f}")
        print(f"  Hit@6: {c['h6']}/{n_i} = {ratio(c['h6'], n_i):.3f}")

    if latencies:
        lat_sorted = sorted(latencies)
        p50 = lat_sorted[int(0.5 * (len(lat_sorted) - 1))]
        p95 = lat_sorted[int(0.95 * (len(lat_sorted) - 1))]
        print("\n===== LATENCY (ms) =====")
        print(f"p50: {p50:.1f} ms")
        print(f"p95: {p95:.1f} ms")
    else:
        print("\nKhông có số liệu latency.")

    # Option: save figure Hit@k by intent cho luận văn
    if MAKE_FIGURE:
        try:
            import numpy as np
            import matplotlib.pyplot as plt

            intents = sorted(per_intent.keys())
            hit1_vals, hit3_vals, hit6_vals = [], [], []
            for intent in intents:
                c = per_intent[intent]
                n_i = c["n"] or 1
                hit1_vals.append(c["h1"] / n_i)
                hit3_vals.append(c["h3"] / n_i)
                hit6_vals.append(c["h6"] / n_i)

            x = np.arange(len(intents))
            width = 0.25

            plt.figure()
            plt.bar(x - width, hit1_vals, width, label="Hit@1")
            plt.bar(x,         hit3_vals, width, label="Hit@3")
            plt.bar(x + width, hit6_vals, width, label="Hit@6")
            plt.xticks(x, intents)
            plt.ylim(0, 1.05)
            plt.ylabel("Accuracy")
            plt.title("Section-level Hit@k by Intent (with section mapping)")
            plt.legend()
            plt.tight_layout()

            fig_path = "figure_4_hit_by_intent_mapped.png"
            plt.savefig(fig_path, dpi=300)
            plt.close()
            print(f"\n[INFO] Đã lưu hình Hit@k by intent: {fig_path}")
        except Exception as e:
            print(f"[WARN] Không vẽ được hình: {e}")


# =========================
# Main
# =========================
if __name__ == "__main__":
    print("=== Chạy evaluation retrieval ===")
    res = run_evaluation()
    compute_metrics(res)
