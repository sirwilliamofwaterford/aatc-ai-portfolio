"""
ingest.py — Reads all PDFs in data/specs/, extracts and chunks their text,
and loads them into a local ChromaDB collection for retrieval.

Run this any time you add or remove PDFs from data/specs/.
"""

from pathlib import Path
from pypdf import PdfReader
import chromadb

SPECS_DIR = Path("data/specs")
CHROMA_DIR = "chroma_db"
COLLECTION_NAME = "trailer_specs"
CHUNK_SIZE = 800       # target characters per chunk
CHUNK_OVERLAP = 150    # overlap so we don't cut off context mid-sentence


def extract_pages(pdf_path):
    """Yield (page_number, text) for every page in a PDF."""
    reader = PdfReader(str(pdf_path))
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        yield i + 1, text


import re

def looks_like_table_row(line):
    """A line packed with 3+ numbers reads like a spec-table row, not prose."""
    return len(re.findall(r"\d+", line)) >= 3


def is_tabular_page(text):
    """A page is 'tabular' if most of its lines look like table rows."""
    lines = [l for l in text.split("\n") if l.strip()]
    if len(lines) < 8:
        return False
    row_like = sum(1 for l in lines if looks_like_table_row(l))
    return row_like / len(lines) > 0.5


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    text = text.strip()
    if not text:
        return []

    if is_tabular_page(text):
        # One chunk per row, with the header lines repeated for context,
        # so a single model's spec doesn't get buried in one giant table blob.
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        header = "\n".join(lines[:2])
        return [f"{header}\n{line}" for line in lines[2:] if looks_like_table_row(line)]

    if len(text) <= size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        chunk = text[start:start + size]
        chunks.append(chunk.strip())
        start += size - overlap
    return [c for c in chunks if c]

def build_index():
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # Rebuild fresh every run, so re-running after adding/removing PDFs
    # always matches exactly what's in data/specs
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(COLLECTION_NAME)

    pdf_files = sorted(SPECS_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDFs found in {SPECS_DIR}/ — add some spec sheets first.")
        return

    all_ids, all_docs, all_metadatas = [], [], []

    for pdf_path in pdf_files:
        print(f"Processing {pdf_path.name}...")
        for page_num, page_text in extract_pages(pdf_path):
            for chunk_idx, chunk in enumerate(chunk_text(page_text)):
                all_ids.append(f"{pdf_path.stem}_p{page_num}_c{chunk_idx}")
                all_docs.append(chunk)
                all_metadatas.append({"source": pdf_path.name, "page": page_num})

    print(f"Adding {len(all_docs)} chunks to the collection...")
    collection.add(ids=all_ids, documents=all_docs, metadatas=all_metadatas)
    print(f"Done. Indexed {len(pdf_files)} PDFs into {len(all_docs)} chunks.")


if __name__ == "__main__":
    build_index()