"""
app.py — Streamlit UI for the Trailer Spec & Fit Assistant. Two modes:
free-form spec Q&A (ask.py) and a conversational trailer matcher that can
ask follow-up questions and check tow-vehicle safety (match_chat.py).
"""
import streamlit as st
from ask import ask
from match_chat import match_chat

st.set_page_config(page_title="Trailer Spec Assistant", page_icon="🚛")
st.title("🚛 Trailer Spec & Fit Assistant")

tab_qa, tab_match = st.tabs(["💬 Ask About Specs", "🔍 Find My Trailer"])

with tab_qa:
    st.caption(
        "Ask about trailer specs, axle capacities, GVWR, and more. "
        "Answers are grounded in the spec sheets -- if the info isn't there, "
        "it'll say so instead of guessing."
    )

    if "qa_messages" not in st.session_state:
        st.session_state.qa_messages = []

    for msg in st.session_state.qa_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    question = st.chat_input("Ask a question about trailer specs...", key="qa_input")

    if question:
        st.session_state.qa_messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Searching specs..."):
                result = ask(question)

            st.markdown(result["answer"])

            if not result["sufficient_information"]:
                st.warning(
                    "The spec sheets don't have enough information to answer "
                    "this confidently -- take this with a grain of salt."
                )

            if result["sources"]:
                with st.expander("Sources"):
                    for s in result["sources"]:
                        st.markdown(f"- **{s['file']}**, page {s['page']}")

        st.session_state.qa_messages.append({"role": "assistant", "content": result["answer"]})

with tab_match:
    st.caption(
        "Tell me what you're hauling and what you're towing with, and I'll "
        "find trailers that actually fit -- checked against real capacity "
        "and tow-vehicle safety math, not a guess."
    )

    if "match_messages" not in st.session_state:
        st.session_state.match_messages = []

    if st.session_state.match_messages and st.button("Start Over", key="match_reset"):
        st.session_state.match_messages = []
        st.rerun()

    for msg in st.session_state.match_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    load_question = st.chat_input("Describe what you need to haul...", key="match_input")

    if load_question:
        st.session_state.match_messages.append({"role": "user", "content": load_question})
        with st.chat_message("user"):
            st.markdown(load_question)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                reply = match_chat(st.session_state.match_messages)
            st.markdown(reply)

        st.session_state.match_messages.append({"role": "assistant", "content": reply})