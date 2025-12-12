import json, re
from collections import defaultdict
from typing import Dict, Any, List

DISEASE_KEYS = {
    "d:chlamydia": ["chlamydia"],
    "d:gonorrhea": ["gonorrhea", "gonorrhoea", "lậu"],
    "d:syphilis": ["syphilis", "giang mai"],
    "d:trichomoniasis": ["trichomoniasis", "trichomonas", "trich"],
    "d:genital_herpes": ["genital herpes", "hsv-2", "herpes simplex"],
    "d:hpv": ["hpv", "genital warts", "papillomavirus"],
    "d:hiv": ["hiv"],
    "d:hepatitis_b": ["hepatitis b", "hbv"],
}

SEC2REL = {
    "Symptoms": "has_symptom",
    "Diagnosis": "diagnosed_by",
    "Testing": "diagnosed_by",
    "Treatment": "treated_by",
    "Prevention": "prevents",
    "General": "related_to",
    "Definition": "related_to"
}

def detect_disease(title: str, url: str, text: str) -> List[str]:
    s = " ".join([title or "", url or "", text or ""]).lower()
    match = []
    for nid, keys in DISEASE_KEYS.items():
        if any(k in s for k in keys):
            match.append(nid)
    return match

def main():
    # input/output
    chunks_path = "data/chunks.jsonl"
    graph_path  = "data/graph.json"
    nodes = {}
    for nid in DISEASE_KEYS.keys():
        nodes[nid] = {"type": "Disease", "name": nid.split(":")[1]}

    adj = defaultdict(list)  # src -> List[edge]

    # read chunks
    with open(chunks_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            ch = json.loads(line)
            diseases = detect_disease(ch.get("title",""), ch.get("source",""), ch.get("text",""))
            if not diseases: 
                continue
            sec = ch.get("section","General")
            rel = SEC2REL.get(sec, "related_to")
            # For simplicity, dst is a pseudo-node encoding section name
            dst = f"sec:{sec.lower()}"
            nodes.setdefault(dst, {"type":"Section","name":sec})
            for d in diseases:
                # append evidence chunk_id
                edge = {"dst": dst, "rel": rel, "weight": 1.0, "evidence": [int(ch["id"])]}
                adj[d].append(edge)

    graph = {"nodes": nodes, "adj": adj}
    # convert defaultdict to normal dict
    graph["adj"] = {k:v for k,v in graph["adj"].items()}

    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    print(f"Graph saved -> {graph_path} | nodes={len(nodes)} | srcs={len(graph['adj'])}")

if __name__ == "__main__":
    main()
