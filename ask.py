"""
ask.py — retrieve relevant chunks, then have Claude answer using only that
content, returning a structured (not just prose) response with real
source citations.
"""
from dotenv import load_dotenv
import chromadb
import anthropic

load_dotenv()

client = anthropic.Anthropic()

chroma_client = chromadb.PersistentClient(path="chroma_db")
collection = chroma_client.get_collection("trailer_specs")

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
    results = collection.query(query_texts=[question], n_results=n_results)
    context = "\n\n".join(
        f"[Source: {m['source']}, page {m['page']}]\n"
        + (f"{m['header']}\n" if m.get("header") else "")
        + c
        for c, m in zip(results["documents"][0], results["metadatas"][0])
    )

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
    return tool_use_block.input  # already-parsed structured data, not raw text


if __name__ == "__main__":
    result = ask("What axle capacity does a PJ tandem dual dump trailer have?")
    print("Answer:", result["answer"])
    print("Sufficient info:", result["sufficient_information"])
    print("Sources:")
    for s in result["sources"]:
        print(f"  - {s['file']}, page {s['page']}")