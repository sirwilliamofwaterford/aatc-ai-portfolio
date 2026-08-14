"""
app.py — Streamlit chat interface for the Trailer Spec & Fit RAG Assistant.
Reuses the retrieval + Claude logic from ask.py so there's one source of truth.
"""
import streamlit as st
from ask import ask

st.set_page_config(page_title="Trailer Spec Assistant", page_icon="🚛")
st.title("🚛 Trailer Spec & Fit Assistant")
st.caption(
    "Ask about trailer specs, axle capacities, GVWR, and more. "
    "Answers are grounded in the spec sheets — if the info isn't there, "
    "it'll say so instead of guessing."
)

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

question = st.chat_input("Ask a question about trailer specs...")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Searching specs..."):
            result = ask(question)

        st.markdown(result["answer"])

        if not result["sufficient_information"]:
            st.warning(
                "The spec sheets don't have enough information to answer "
                "this confidently — take this with a grain of salt."
            )

        if result["sources"]:
            with st.expander("Sources"):
                for s in result["sources"]:
                    st.markdown(f"- **{s['file']}**, page {s['page']}")

    st.session_state.messages.append({"role": "assistant", "content": result["answer"]})