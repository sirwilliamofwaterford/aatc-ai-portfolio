"""
query_test.py — quick sanity check: ask a question, see what chunks come back.
Not the real app yet — just proving retrieval actually works before we build any UI.
"""
import chromadb

client = chromadb.PersistentClient(path="chroma_db")
collection = client.get_collection("trailer_specs")

question = "What axle capacity does a PJ tandem dual dump trailer have?"
results = collection.query(query_texts=[question], n_results=3)

for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
    print(f"\n--- {meta['source']} (page {meta['page']}) — distance {dist:.3f} ---")
    print(doc[:400])