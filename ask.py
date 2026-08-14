"""
ask.py — retrieve relevant chunks, then have Claude answer using only that
content, returning a structured (not just prose) response with real
source citations.

Retrieval combines two things: a literal keyword match against the
structured catalog (data/catalog.json) for precise "which model" questions
— vector search alone struggles here when many models share near-identical
phrasing — plus the usual vector search over chunked text for everything
else. Also brand-aware: if the question names a known brand, vector search
is restricted to that brand's source files first.
"""
import json
import re
from pathlib import Path

from dotenv import load_dotenv
import chromadb
import anthropic

load_dotenv()

client = anthropic.Anthropic()

chroma_client = chromadb.PersistentClient(path="chroma_db")
collection = chroma_client.get_collection("trailer_specs")

CATALOG_PATH = Path("data/catalog.json")
CATALOG = json.loads(CATALOG_PATH.read_text()) if CATALOG_PATH.exists() else []

STOPWORDS = {
    "the", "a", "an", "on", "in", "at", "for", "of", "is", "are", "what",
    "whats", "with", "and", "or", "to", "does", "do", "have", "has", "i",
    "my", "me", "you", "your",
}

BRAND_SOURCES = {
    "diamond c": [
        "Diamond_C_GDT-brochure-12-05-2022.pdf",
        "Diamond_C_LPX-brochure-12-05-2022-1.pdf",
    ],
    "pj": [
        "pj_trailers_owners_manual-2.pdf",
        "pj_trailers_products_specs.pdf",
    ],
    "big tex": [
        "Big-Tex-Trailers_Owners-Manual_2020-Dump-Trailers-2.pdf",
        "Big-Tex-Trailers_Owners-Manual_2020.pdf",
        "Big-Tex-Trailers_plug-contacts.pdf",
        "Big-Tex-Trailers_wiring-diagram.pdf",
    ],
    "maxx d": [
        "MAXX_D_trailer_specs_print_sheet_-_individual_d6x.pdf",
        "MAXX_D_trailer_specs_print_sheet_-_individual_dhx.pdf",
    ],
    "covered wagon": [
        "Covered_Wagon_WEBSITE_CARGO_6_WIDE.pdf",
    ],
}


def detect_brand_filter(question):
    normalized = question.lower().replace("-", " ")
    for brand, sources in BRAND_SOURCES.items():
        if brand in normalized:
            return sources
    return None


def find_catalog_matches(question, brand_sources=None, top_n=3):
    q_lower = question.lower()
    q_words = set(re.findall(r"[a-z0-9]+", q_lower)) - STOPWORDS

    candidates = CATALOG
    if brand_sources:
        candidates = [m for m in CATALOG if m.get("source") in brand_sources]

    scored = []
    for model in candidates:
        name_words = set(re.findall(r"[a-z0-9]+", (model.get("model_name") or "").lower()))
        score = len(q_words & name_words)
        code = (model.get("model_code") or "").lower()
        if code and re.search(rf"\b{re.escape(code)}\b", q_lower):
            score += 5
        if score > 0:
            scored.append((score, model))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:top_n]]


def format_catalog_match(m):
    parts = [f"{m.get('model_code', '')} — {m.get('model_name', '')}"]
    if m.get("axle_capacity_options_lb"):
        opts = ", ".join(f"{x:g} lb" for x in m["axle_capacity_options_lb"])
        parts.append(f"Axle capacity options: {opts}")
    if m.get("num_axles") is not None:
        parts.append(f"Axles: {m['num_axles']}")
    if m.get("gvwr_min_lb") is not None or m.get("gvwr_max_lb") is not None:
        parts.append(f"GVWR: {m.get('gvwr_min_lb')}\u2013{m.get('gvwr_max_lb')} lb")
    if m.get("deck_length_ft_min") is not None:
        parts.append(f"Deck length: {m.get('deck_length_ft_min')}\u2013{m.get('deck_length_ft_max')} ft")
    if m.get("deck_width_in") is not None:
        parts.append(f"Deck width: {m['deck_width_in']} in")
    if m.get("empty_weight_lb") is not None:
        parts.append(f"Empty weight: {m['empty_weight_lb']} lb")
    parts.append(f"[Source: {m.get('source')}, page {m.get('page')}]")
    return "; ".join(parts)


ANSWER_TOOL = {
    "name": "provide_answer",
    "description": "Provide a grounded answer to a trailer spec question, with source citations.",
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "description": "The answer, in plain language. If the excerpts don't contain enough information, say so here instead of guessing.",
            },
            "sufficient_information": {
                "type": "boolean",
                "description": "True only if the source excerpts actually contain enough information to answer confidently.",
            },
            "sources": {
                "type": "array",
                "description": "The specific source excerpts actually used. Empty if sufficient_information is false.",
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "page": {"type": "integer"},
                    },
                    "required": ["file", "page"],
                },
            },
        },
        "required": ["answer", "sufficient_information", "sources"],
    },
}


def ask(question, n_results=5):
    brand_sources = detect_brand_filter(question)

    query_kwargs = {"query_texts": [question], "n_results": n_results}
    if brand_sources:
        query_kwargs["where"] = {"source": {"$in": brand_sources}}
    results = collection.query(**query_kwargs)

    context_parts = [
        f"[Source: {m['source']}, page {m['page']}]\n{c}"
        for c, m in zip(results["documents"][0], results["metadatas"][0])
    ]

    catalog_matches = find_catalog_matches(question, brand_sources)
    if catalog_matches:
        catalog_block = "Structured catalog matches (verified spec data):\n" + "\n".join(
            format_catalog_match(m) for m in catalog_matches
        )
        context_parts.insert(0, catalog_block)

    context = "\n\n".join(context_parts)

    system_prompt = (
        "You are a trailer spec assistant for a trailer dealership. "
        "Answer using ONLY the provided source excerpts. Always call the "
        "provide_answer tool with your response — never answer in plain text."
    )

    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=500,
        system=system_prompt,
        tools=[ANSWER_TOOL],
        tool_choice={"type": "tool", "name": "provide_answer"},
        messages=[{"role": "user", "content": f"Source excerpts:\n\n{context}\n\nQuestion: {question}"}],
    )

    tool_use_block = next(b for b in message.content if b.type == "tool_use")
    return tool_use_block.input


if __name__ == "__main__":
    result = ask("What axle capacity does a PJ tandem dual dump trailer have?")
    print("Answer:", result["answer"])
    print("Sufficient info:", result["sufficient_information"])
    print("Sources:")
    for s in result["sources"]:
        print(f"  - {s['file']}, page {s['page']}")