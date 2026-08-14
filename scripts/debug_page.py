"""
debug_page.py — dump the raw extracted text of one page, to check whether
pypdf actually captured everything on it (or silently lost table content).
"""
from pypdf import PdfReader

reader = PdfReader("data/specs/pj_trailers_owners_manual-2.pdf")
page = reader.pages[126]  # zero-indexed, so this is page 127
print(page.extract_text())