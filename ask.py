"""
ask.py — retrieve relevant chunks, then have Claude answer using only that
content, with citations.
"""
from dotenv import load_dotenv
import chromadb
import anthropic

load_dotenv()

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from .env automatically

chroma_client = chromadb.PersistentClient(path="chroma_db")
collection = chroma_client.get_collection("trailer_specs")


def ask(question, n_results=5):
    results = collection.query(query_texts=[question], n_results=n_results)
    context = "\n\n".join(
        f"[Source: {m['source']}, page {m['page']}]\n{c}"
        for c, m in zip(results["documents"][0], results["metadatas"][0])
    )

    system_prompt = (
        "You are a trailer spec assistant for a trailer dealership. "
        "Answer using ONLY the provided source excerpts. Always cite which "
        "source (filename and page) your answer came from. If the excerpts "
        "don't have enough information, say so instead of guessing."
    )

    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=500,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Source excerpts:\n\n{context}\n\nQuestion: {question}"}],
    )
    return message.content[0].text


if __name__ == "__main__":
    print(ask("What axle capacity does a PJ tandem dual dump trailer have?"))