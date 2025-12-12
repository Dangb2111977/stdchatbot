# build_chunks.py — corpus builder with Normalization for VI/EN medical texts
# Normalization covered:
#   • Unicode & Vietnamese diacritics normalization; remove boilerplate/navigation text
#   • Sentence & paragraph fixes; strip tables that cannot be parsed reliably

import re
import json
import time
import hashlib
import unicodedata
import requests
from bs4 import BeautifulSoup

# ---------------------------
# Section heuristics
# ---------------------------
SECTIONS = {
    "definition": ["what is", "overview", "about", "định nghĩa", "tổng quan"],
    "symptoms": ["symptom", "triệu chứng", "signs"],
    "diagnosis": ["diagnosis", "testing", "test", "xét nghiệm", "chẩn đoán"],
    "treatment": ["treatment", "điều trị", "therapy", "antibiotic", "antiviral"],
    "prevention": ["prevention", "phòng ngừa", "vaccine", "condom", "tiêm chủng"]
}

def guess_section(h: str, p: str) -> str:
    hlow = (h or "").lower()
    plow = (p or "").lower()
    for sec, keys in SECTIONS.items():
        if any(k in hlow for k in keys) or any(k in plow[:200] for k in keys):
            return sec.title()
    return "General"

# ---------------------------
# NORMALIZATION HELPERS
# ---------------------------

# Phrases typical of footers/menus on health portals (extend as needed)
STOP_PHRASES = [
    "privacy policy", "terms of use", "terms and conditions", "cookies",
    "subscribe", "share this page", "print page", "site navigation",
    "trang chủ", "điều khoản sử dụng", "chính sách quyền riêng tư",
    "bản quyền", "liên hệ", "về chúng tôi"
]

def normalize_unicode(text: str) -> str:
    t = text.replace("\u00A0", " ")
    t = unicodedata.normalize("NFC", t)
    return t

def strip_tables(text: str) -> str:
    # Markdown table rows and header separators
    t = re.sub(r"(?m)^\s*\|.*\|\s*$", " ", text)
    t = re.sub(r"(?m)^\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+$", " ", t)
    # ASCII-art tables
    t = re.sub(r"(?m)^\s*\+\-[-\+]+\+\s*$", " ", t)
    return t

def remove_boilerplate(text: str) -> str:
    t = text
    for p in STOP_PHRASES:
        t = re.sub(re.escape(p), " ", t, flags=re.IGNORECASE)
    # Remove long menu-like chains (e.g., Home | A | B | C ...)
    t = re.sub(r"(home|trang chủ)(\s*[•|>\-]\s*\w+){3,}", " ", t, flags=re.I)
    return t

def fix_sentences_and_paragraphs(text: str) -> str:
    t = text
    t = t.replace("•", "- ").replace("–", "- ").replace("—", "- ")
    t = re.sub(r"[ \t]+", " ", t)             # collapse spaces
    t = re.sub(r"\r\n|\r", "\n", t)           # unify line breaks
    t = re.sub(r"\n{3,}", "\n\n", t)          # max one blank line
    t = re.sub(r"([A-Za-zÀ-ỹ0-9])( +)\n", r"\1.\n", t)  # ensure period at paragraph end
    return t.strip()

def clean_text(raw: str) -> str:
    t = normalize_unicode(raw)
    t = strip_tables(t)
    t = remove_boilerplate(t)
    t = fix_sentences_and_paragraphs(t)
    return t

def split_paragraphs(text: str):
    parts = [re.sub(r"\s+", " ", t).strip() for t in re.split(r"\n{2,}", text)]
    return [p for p in parts if len(p) > 60]

# HTML fetch & robust text extraction
def fetch_and_parse(url: str):
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    title = (soup.title.text if soup.title else url).strip()
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript", "form", "button", "svg"]):
        tag.decompose()
    for tb in soup.find_all("table"):
        tb.decompose()
    raw_text = "\n".join(
        el.get_text(" ", strip=True)
        for el in soup.find_all(["h1", "h2", "h3", "p", "li"])
    )
    text = clean_text(raw_text)
    return title, text

# Chunking with section guess
def to_chunks(url: str, next_id: int):
    title, text = fetch_and_parse(url)
    paras = split_paragraphs(text)
    out = []
    date_accessed = time.strftime("%Y-%m-%d")

    for p in paras:
        # Detect local "Heading: body" pattern
        m = re.match(r"^\s*([A-ZÀ-Ỹ][A-Za-zÀ-ỹ \-/]+)\s*:\s*(.+)$", p)
        heading = m.group(1) if m else ""
        body = m.group(2) if m else p

        section = guess_section(heading, body)
        body_trim = body[:1800]  # keep prompt budget friendly

        # Simple content hash for traceability
        h = hashlib.sha1((title + url + body_trim).encode("utf-8")).hexdigest()[:16]

        out.append({
            "id": next_id,
            "title": title,
            "source": url,
            "section": section,
            "date_accessed": date_accessed,
            "hash": h,
            "text": body_trim
        })
        next_id += 1
    return out, next_id

def main():
    import pathlib
    src = pathlib.Path("data/sources_urls.txt")
    dst = pathlib.Path("data/chunks.jsonl")
    dst.parent.mkdir(parents=True, exist_ok=True)

    urls = [
        u.strip()
        for u in src.read_text(encoding="utf-8").splitlines()
        if u.strip() and not u.strip().startswith("#")
    ]

    next_id = 0
    with dst.open("w", encoding="utf-8") as f:
        for u in urls:
            try:
                chunks, next_id = to_chunks(u, next_id)
                for c in chunks:
                    f.write(json.dumps(c, ensure_ascii=False) + "\n")
                print(f"[OK] {u} -> {len(chunks)} chunks")
            except Exception as e:
                print(f"[SKIP] {u}: {e}")
    print("Done. Output -> data/chunks.jsonl")

if __name__ == "__main__":
    main()
