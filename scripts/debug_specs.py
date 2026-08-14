"""
debug_specs.py — dump every page of the actual spec-sheet PDF,
to check whether pypdf can read its tables at all.
"""
from pypdf import PdfReader

reader = PdfReader("data/specs/pj_trailers_products_specs.pdf")
for i, page in enumerate(reader.pages):
    print(f"--- Page {i+1} ---")
    print(page.extract_text())
    print()