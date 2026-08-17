"""
app.py -- Streamlit UI for the Trailer Spec & Fit Assistant. Two modes:
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


AATC_CATEGORY_URLS = {
    "dump": "https://allamericantrailer.com/product-category/dump-trailer-inventory-for-sale/",
    "tilt": "https://allamericantrailer.com/product-category/equipment-tilt/",
    "deckover": "https://allamericantrailer.com/product-category/flat-bed/",
    "carhauler": "https://allamericantrailer.com/product-category/open-car-hauler/",
    "utility": "https://allamericantrailer.com/product-category/open-utility/",
    "cargo_enclosed": "https://allamericantrailer.com/product-category/enclosed-cargo-car/",
}

SOURCE_TO_AATC_BRAND_URL = {
    "pj_trailers_owners_manual-2.pdf": "https://allamericantrailer.com/shop/trailerbrand-pj/",
    "pj_trailers_products_specs.pdf": "https://allamericantrailer.com/shop/trailerbrand-pj/",
    "Diamond_C_GDT-brochure-12-05-2022.pdf": "https://allamericantrailer.com/shop/trailerbrand-diamond-c/",
    "Diamond_C_LPX-brochure-12-05-2022-1.pdf": "https://allamericantrailer.com/shop/trailerbrand-diamond-c/",
    "Big-Tex-Trailers_Owners-Manual_2020-Dump-Trailers-2.pdf": "https://allamericantrailer.com/shop/trailerbrand-big-tex/",
    "Big-Tex-Trailers_Owners-Manual_2020.pdf": "https://allamericantrailer.com/shop/trailerbrand-big-tex/",
    "Big-Tex-Trailers_plug-contacts.pdf": "https://allamericantrailer.com/shop/trailerbrand-big-tex/",
    "Big-Tex-Trailers_wiring-diagram.pdf": "https://allamericantrailer.com/shop/trailerbrand-big-tex/",
    "MAXX_D_trailer_specs_print_sheet_-_individual_d6x.pdf": "https://allamericantrailer.com/shop/trailerbrand-maxx-d/",
    "MAXX_D_trailer_specs_print_sheet_-_individual_dhx.pdf": "https://allamericantrailer.com/shop/trailerbrand-maxx-d/",
    "Covered_Wagon_WEBSITE_CARGO_6_WIDE.pdf": "https://allamericantrailer.com/shop/trailerbrand-covered-wagon/",
}


def get_aatc_link(m):
    """
    Prefer a category-specific AATC page (more relevant, often multi-brand);
    fall back to the brand's general page if no matching category exists
    (e.g. 'pipe' trailers aren't a category AATC carries).
    """
    category = m.get("category")
    name = (m.get("model_name") or "").lower()

    if category == "dump":
        return AATC_CATEGORY_URLS["dump"], "dump trailer"
    if category == "equipment":
        if "tilt" in name:
            return AATC_CATEGORY_URLS["tilt"], "equipment/tilt trailer"
        return AATC_CATEGORY_URLS["deckover"], "flatbed/deckover trailer"
    if category == "carhauler":
        return AATC_CATEGORY_URLS["carhauler"], "car hauler"
    if category == "utility":
        return AATC_CATEGORY_URLS["utility"], "utility trailer"
    if category == "cargo_enclosed":
        return AATC_CATEGORY_URLS["cargo_enclosed"], "enclosed cargo trailer"

    brand_url = SOURCE_TO_AATC_BRAND_URL.get(m.get("source"))
    if brand_url:
        return brand_url, "brand"
    return None, None


def render_match_results(result):
    matches = result.get("matches") or []
    if not matches:
        return

    for m in matches[:5]:
        with st.container(border=True):
            top_cols = st.columns([3, 2])
            with top_cols[0]:
                st.markdown(f"**{m['model_code']}** -- {m['model_name']}")
                st.caption(f"{m.get('category', 'unknown').replace('_', ' ').title()} · {m['source']}")
            with top_cols[1]:
                st.metric(
                    "Capacity",
                    f"{m['capacity_lb']:,.0f} lb",
                    delta=f"+{m['margin_lb']:,.0f} lb margin",
                )

            tow_check = m.get("tow_check")
            if tow_check:
                status_cols = st.columns(3)
                status_cols[0].markdown(
                    ("✅" if tow_check["tow_rating_ok"] else "❌")
                    + f" Tow rating ({tow_check['tow_rating_margin_lb']:+,.0f} lb)"
                )
                status_cols[1].markdown(
                    ("✅" if tow_check["gcwr_ok"] else "❌")
                    + f" GCWR ({tow_check['gcwr_margin_lb']:+,.0f} lb)"
                )
                status_cols[2].markdown(
                    ("✅" if tow_check["tongue_ok"] else "❌")
                    + f" Tongue weight ({tow_check['tongue_margin_lb']:+,.0f} lb)"
                )

            link, link_kind = get_aatc_link(m)
            if link:
                label = "See current inventory for this brand at AATC →" if link_kind == "brand" \
                    else f"See current {link_kind} inventory at AATC →"
                st.markdown(f"[{label}]({link})")


with tab_match:
    st.caption(
        "Tell me what you're hauling and what you're towing with, and I'll "
        "find trailers that actually fit -- checked against real capacity "
        "and tow-vehicle safety math, not a guess."
    )

    if "match_messages" not in st.session_state:
        st.session_state.match_messages = []
    if "match_results" not in st.session_state:
        st.session_state.match_results = []

    if st.session_state.match_messages and st.button("Start Over", key="match_reset"):
        st.session_state.match_messages = []
        st.session_state.match_results = []
        st.rerun()

    for msg, result in zip(st.session_state.match_messages, st.session_state.match_results):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if result:
                render_match_results(result)

    load_question = st.chat_input("Describe what you need to haul...", key="match_input")

    if load_question:
        st.session_state.match_messages.append({"role": "user", "content": load_question})
        st.session_state.match_results.append(None)
        with st.chat_message("user"):
            st.markdown(load_question)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                reply, match_result = match_chat(st.session_state.match_messages)
            st.markdown(reply)
            if match_result:
                render_match_results(match_result)

        st.session_state.match_messages.append({"role": "assistant", "content": reply})
        st.session_state.match_results.append(match_result)