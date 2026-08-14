"""
ingest.py — build the ChromaDB vector index AND the structured trailer
catalog for the Trailer Spec & Fit RAG Assistant.

Each PDF page is rendered as an image and read once by Claude vision, which
returns both: (1) clean text for the vector index (used by the free-form
chat), and (2) structured per-model spec records for the catalog (used by
the trailer-matching engine, since numeric filtering needs real structured
data, not vector search).
"""
import base64
import json
from pathlib import Path

from dotenv import load_dotenv
import fitz  # PyMuPDF
import anthropic
import chromadb

load_dotenv()

DATA_DIR = Path("data/specs")
CATALOG_PATH = Path("data/catalog.json")
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150

client = anthropic.Anthropic()

EXTRACTION_TOOL = {
    "name": "record_page_content",
    "description": "Record both the readable text and any structured trailer-model specs found on this page.",
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": (
                    "All substantive text on the page as clean plain text, with "
                    "every label directly next to its value (e.g. 'GVWR: "
                    "7,000-9,990 lb'). If this page lists specs for one or more "
                    "trailer models, output ONE LINE PER MODEL. Ignore color "
                    "swatches, logos, and decorative graphics. 'BLANK' if there's "
                    "no meaningful text."
                ),
            },
            "models": {
                "type": "array",
                "description": (
                    "One structured record per distinct trailer model shown on "
                    "this page. Empty array if this page isn't a spec/model "
                    "listing (a manual page, wiring diagram, or cover page)."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "model_code": {"type": "string", "description": "Model code/name, e.g. 'D7', 'LPX', 'D6X'."},
                        "model_name": {"type": "string", "description": "Full descriptive name, e.g. '83\" Tandem Axle Dump'."},
                        "gvwr_min_lb": {"type": ["number", "null"]},
                        "gvwr_max_lb": {"type": ["number", "null"]},
                        "axle_capacity_options_lb": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Every axle-capacity configuration this model is available in, in lbs (e.g. [5200, 7000, 8000]). Empty array if not stated.",
                        },
                        "num_axles": {"type": ["integer", "null"]},
                        "deck_length_ft_min": {"type": ["number", "null"]},
                        "deck_length_ft_max": {"type": ["number", "null"]},
                        "deck_width_in": {"type": ["number", "null"]},
                        "empty_weight_lb": {"type": ["number", "null"], "description": "The trailer's own weight, if stated."},
                    },
                    "required": ["model_code"],
                },
            },
        },
        "required": ["text", "models"],
    },
}

EXTRACTION_PROMPT = (
    "This is a page from a trailer spec sheet or manual. Call "
    "record_page_content with: (1) the page's clean text, and (2) a "
    "structured record for every trailer model shown, if any. Some models "
    "are available in multiple axle-capacity configurations — capture ALL of "
    "them in axle_capacity_options_lb, not just one. Use null (or an empty "
    "array/'BLANK' as appropriate) for anything not stated — never guess or "
    "estimate a number that isn't shown on the page."
)


def render_page(pdf_path, page_num, dpi=150):
    doc = fitz.open(pdf_path)
    pix = doc[page_num].get_pixmap(dpi=dpi)
    img_bytes = pix.tobytes("png")
    doc.close()
    return img_bytes


def extract_page(img_bytes):
    img_b64 = base64.standard_b64encode(img_bytes).decode("utf-8")
    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=8000,
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "record_page_content"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_b64}},
                {"type": "text", "text": EXTRACTION_PROMPT},
            ],
        }],
    )
    if message.stop_reason == "max_tokens":
        print("  WARNING: response truncated at max_tokens on this page.", flush=True)
    tool_use_block = next(b for b in message.content if b.type == "tool_use")
    result = tool_use_block.input
    return result.get("text", "").strip(), result.get("models", [])


def extract_pages(pdf_path):
    doc = fitz.open(pdf_path)
    num_pages = len(doc)
    doc.close()

    pages = []
    for page_num in range(num_pages):
        print(f"  page {page_num + 1}/{num_pages}...", flush=True)
        text, models = extract_page(render_page(pdf_path, page_num))
        if text and text != "BLANK":
            pages.append((page_num + 1, text, models))
    return pages


def chunk_page_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    text = text.strip()
    if not text:
        return []

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Spec-sheet style: vision extraction returns one line per model/row.
    # Each line is already a complete, self-contained record.
    if len(lines) > 1 and all(len(l) > 60 for l in lines):
        return lines

    # Prose style: chunk by size with overlap, like a manual page.
    if len(text) <= size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        chunk = text[start:start + size].strip()
        if chunk:
            chunks.append(chunk)
        start += size - overlap
    return chunks


def build_index():
    chroma_client = chromadb.PersistentClient(path="chroma_db")
    try:
        chroma_client.delete_collection("trailer_specs")
    except Exception:
        pass
    collection = chroma_client.create_collection("trailer_specs")

    pdf_files = sorted(DATA_DIR.glob("*.pdf"))
    all_ids, all_docs, all_metadatas = [], [], []
    catalog = []

    for pdf_path in pdf_files:
        print(f"Processing {pdf_path.name}...", flush=True)
        for page_num, page_text, models in extract_pages(pdf_path):
            for chunk_idx, chunk in enumerate(chunk_page_text(page_text)):
                all_ids.append(f"{pdf_path.stem}_p{page_num}_c{chunk_idx}")
                all_docs.append(chunk)
                all_metadatas.append({
                    "source": pdf_path.name,
                    "page": page_num,
                })
            for model in models:
                model["source"] = pdf_path.name
                model["page"] = page_num
                catalog.append(model)

    print(f"Adding {len(all_docs)} chunks to the vector index...", flush=True)
    collection.add(ids=all_ids, documents=all_docs, metadatas=all_metadatas)

    print(f"Writing {len(catalog)} structured model records to {CATALOG_PATH}...", flush=True)
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2))

    print("Done.", flush=True)


if __name__ == "__main__":
    build_index()