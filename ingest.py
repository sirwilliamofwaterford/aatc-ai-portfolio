"""
ingest.py — build the ChromaDB index for the Trailer Spec & Fit RAG Assistant.

Each PDF page is rendered as an image and read by Claude vision, rather than
extracted as raw text via pypdf. This avoids the column/layout-order problems
that come with plain text extraction on tables and multi-column spec sheets —
Claude reads the page the way a person would and returns clean, labeled text.
"""
import base64
from pathlib import Path

from dotenv import load_dotenv
import fitz  # PyMuPDF
import anthropic
import chromadb

load_dotenv()

DATA_DIR = Path("data/specs")
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150

client = anthropic.Anthropic()

EXTRACTION_PROMPT = (
    "This is a page from a trailer spec sheet or manual. Extract all the "
    "substantive text content as clean plain text, keeping every label "
    "directly next to its value (for example: 'GVWR: 7,000-9,990 lb', "
    "'Coupler: 2 5/16\" 30K Round GN'). If this page lists specs for one or "
    "more trailer models, output ONE LINE PER MODEL with all of that "
    "model's specs on that line, clearly labeled. Ignore color swatches, "
    "logos, and decorative graphics — only extract substantive spec/text "
    "content. If the page has no meaningful text, respond with exactly: BLANK"
)


def render_page(pdf_path, page_num, dpi=150):
    doc = fitz.open(pdf_path)
    pix = doc[page_num].get_pixmap(dpi=dpi)
    img_bytes = pix.tobytes("png")
    doc.close()
    return img_bytes


def extract_with_vision(img_bytes):
    img_b64 = base64.standard_b64encode(img_bytes).decode("utf-8")
    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": img_b64},
                },
                {"type": "text", "text": EXTRACTION_PROMPT},
            ],
        }],
    )
    text_block = next(b for b in message.content if b.type == "text")
    return text_block.text.strip()


def extract_pages(pdf_path):
    doc = fitz.open(pdf_path)
    num_pages = len(doc)
    doc.close()

    pages = []
    for page_num in range(num_pages):
        print(f"  page {page_num + 1}/{num_pages}...", flush=True)
        text = extract_with_vision(render_page(pdf_path, page_num))
        if text and text != "BLANK":
            pages.append((page_num + 1, text))
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

    for pdf_path in pdf_files:
        print(f"Processing {pdf_path.name}...", flush=True)
        for page_num, page_text in extract_pages(pdf_path):
            for chunk_idx, chunk in enumerate(chunk_page_text(page_text)):
                all_ids.append(f"{pdf_path.stem}_p{page_num}_c{chunk_idx}")
                all_docs.append(chunk)
                all_metadatas.append({
                    "source": pdf_path.name,
                    "page": page_num,
                })

    print(f"Adding {len(all_docs)} chunks to the index...", flush=True)
    collection.add(ids=all_ids, documents=all_docs, metadatas=all_metadatas)
    print("Done.", flush=True)


if __name__ == "__main__":
    build_index()