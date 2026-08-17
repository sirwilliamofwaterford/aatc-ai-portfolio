"""
app.py -- Streamlit UI for the Trailer Spec & Fit Assistant. Two modes:
free-form spec Q&A (ask.py) and a conversational trailer matcher that can
ask follow-up questions and check tow-vehicle safety (match_chat.py).
"""
import html as html_lib

import streamlit as st
from ask import ask
from match_chat import match_chat

st.set_page_config(page_title="Trailer Spec Assistant", page_icon="🚛", layout="wide")

# ---------------------------------------------------------------------------
# Basic abuse/cost safeguards. This is a public demo billed against a real
# API key, so these caps exist to keep worst-case cost bounded per browsing
# session -- not a substitute for setting a hard spending limit on the API
# key itself in the Anthropic Console, which is the real financial backstop.
# Tune these based on real traffic once the app is live.
# ---------------------------------------------------------------------------
MAX_QA_MESSAGES_PER_SESSION = 30
MAX_MATCH_MESSAGES_PER_SESSION = 20
MAX_INPUT_CHARS = 800

SESSION_LIMIT_MSG = (
    "You've reached this demo's message limit for one browsing session "
    "(this cap exists to keep the demo's API costs in check, not because "
    "you did anything wrong). Refresh the page to start a fresh session."
)


def _too_long_warning(text):
    st.warning(
        f"That message is a bit long for this demo ({len(text):,} characters, "
        f"{MAX_INPUT_CHARS:,} max) -- try trimming it down and asking again."
    )


# ---------------------------------------------------------------------------
# Brand styling -- colors pulled from the actual AATC logo (navy / white / red).
# Everything visual lives in this one CSS block so the palette is easy to tweak
# later without hunting through the rest of the file.
# ---------------------------------------------------------------------------
AATC_CSS = """
:root{
  --aatc-navy:#0b1a33;
  --aatc-navy-2:#132745;
  --aatc-red:#d1272b;
  --aatc-red-dark:#a81f22;
  --aatc-white:#ffffff;
  --aatc-ink:#1c2430;
  --aatc-muted:#5b6470;
  --aatc-line:#e2e6ec;
  --aatc-good:#1a7f37;
  --aatc-bad:#c22b2b;
  --aatc-bg:#f5f6f8;
}

.stApp{ background: var(--aatc-bg); }

/* ---- Hero banner (mimics the AATC logo: navy field, bold italic white
   wordmark, red star + red underline) ---- */
.aatc-hero{
  background: linear-gradient(135deg, var(--aatc-navy) 0%, var(--aatc-navy-2) 100%);
  border-radius: 12px;
  padding: 22px 22px;
  margin-bottom: 16px;
  border-bottom: 4px solid var(--aatc-red);
  box-shadow: 0 4px 14px rgba(11,26,51,0.25);
  text-align: center;
}
.aatc-hero-title{
  color: var(--aatc-white); font-weight: 800; font-style: italic;
  font-size: 30px; letter-spacing: .02em; text-transform: uppercase; margin:0;
  display:flex; align-items:center; justify-content:center; gap:10px;
}
.aatc-hero-star{ color: var(--aatc-red); font-size: 24px; font-style: normal; }
.aatc-hero-title-accent{ color: var(--aatc-red); }
.aatc-hero-sub{ color:#c9d3e0; font-size:14px; margin:6px 0 0; font-style:normal; }

/* ---- Tabs ---- */
button[data-baseweb="tab"]{ font-weight:600; color: var(--aatc-muted); }
button[data-baseweb="tab"][aria-selected="true"]{ color: var(--aatc-navy); }
div[data-baseweb="tab-highlight"]{ background-color: var(--aatc-red) !important; }

/* ---- Chat messages ---- */
[data-testid="stChatMessage"]{
  background: var(--aatc-white);
  border: 1px solid var(--aatc-line);
  border-radius: 12px;
  padding: 4px 6px;
  box-shadow: 0 1px 3px rgba(11,26,51,0.06);
}

/* ---- Chat input: give it a clearly-bordered, unmistakable "type here" box ---- */
[data-testid="stChatInput"]{
  border: 2px solid var(--aatc-navy) !important;
  border-radius: 12px !important;
  box-shadow: 0 2px 10px rgba(11,26,51,0.15);
}
[data-testid="stChatInput"] textarea{ color: var(--aatc-ink) !important; }

/* ---- Match result cards (CSS grid = automatic side-by-side comparison) ---- */
.aatc-grid{
  display:grid;
  grid-template-columns: repeat(auto-fit, minmax(270px, 1fr));
  gap:14px;
  margin:12px 0 6px;
}
.aatc-card{
  background: var(--aatc-white);
  border: 1px solid var(--aatc-line);
  border-top: 4px solid var(--aatc-navy);
  border-radius: 12px;
  padding: 14px 16px 16px;
  box-shadow: 0 1px 4px rgba(11,26,51,0.08);
  display:flex; flex-direction:column; gap:10px;
}
.aatc-card-head{ display:flex; align-items:center; gap:10px; }
.aatc-card-icon{
  flex-shrink:0; width:34px; height:34px; border-radius:8px;
  background: var(--aatc-bg); color: var(--aatc-navy);
  display:flex; align-items:center; justify-content:center;
}
.aatc-card-title{ font-weight:700; color: var(--aatc-ink); font-size:14px; }
.aatc-card-name{ font-weight:500; color: var(--aatc-muted); }
.aatc-card-meta{ font-size:12px; color: var(--aatc-muted); margin-top:1px; }

.aatc-capacity{ border-top:1px solid var(--aatc-line); padding-top:8px; }
.aatc-capacity-label{ font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:var(--aatc-muted); }
.aatc-capacity-value{ font-size:19px; font-weight:700; color:var(--aatc-navy); }
.aatc-capacity-margin{ font-size:12px; color: var(--aatc-good); font-weight:600; }

.aatc-tow-checks{ border-top:1px solid var(--aatc-line); padding-top:8px; display:flex; flex-direction:column; gap:4px; }
.aatc-status{ display:flex; justify-content:space-between; font-size:12.5px; }
.aatc-status.ok{ color: var(--aatc-good); }
.aatc-status.bad{ color: var(--aatc-bad); font-weight:600; }

.aatc-card-link{
  margin-top:2px; display:inline-block; text-align:center;
  background: var(--aatc-navy); color: var(--aatc-white) !important;
  font-size:12.5px; font-weight:600; text-decoration:none;
  padding:8px 10px; border-radius:8px;
}
.aatc-card-link:hover{ background: var(--aatc-navy-2); }

/* ---- Disclaimer banner -- amber/caution, deliberately distinct from the
   brand navy/red so it doesn't get lost among the styled buttons ---- */
.aatc-disclaimer{
  background:#fff7ea; border:1px solid #f0c975; color:#6b4c14;
  border-radius:10px; padding:10px 14px; font-size:12.5px; margin:4px 0 14px;
  line-height:1.5;
}
.aatc-disclaimer b{ color:#4a3410; }
"""
st.markdown(f"<style>{AATC_CSS}</style>", unsafe_allow_html=True)

HERO_HTML = """
<div class="aatc-hero">
  <p class="aatc-hero-title">ALL AMERICAN <span class="aatc-hero-star">&#9733;</span> <span class="aatc-hero-title-accent">TRAILER</span></p>
  <p class="aatc-hero-sub">Spec &amp; Fit Assistant</p>
</div>
"""
st.markdown(HERO_HTML, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Simple line-icon SVGs per trailer category. Hand-drawn, brand-tinted
# (currentColor), fully self-contained -- no external/real trailer photos,
# so nothing here can go stale or raise image-sourcing questions later.
# ---------------------------------------------------------------------------
_ICON_ATTRS = 'viewBox="0 0 32 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'

CATEGORY_ICONS = {
    "dump": f'<svg {_ICON_ATTRS}><line x1="2" y1="18" x2="26" y2="18"/><polyline points="4,18 4,10 20,6 20,18"/><circle cx="8" cy="20.5" r="2"/><circle cx="22" cy="20.5" r="2"/></svg>',
    "equipment": f'<svg {_ICON_ATTRS}><line x1="2" y1="14" x2="28" y2="14"/><line x1="2" y1="14" x2="4" y2="18"/><line x1="28" y1="14" x2="26" y2="18"/><circle cx="9" cy="19.5" r="2"/><circle cx="21" cy="19.5" r="2"/></svg>',
    "carhauler": f'<svg {_ICON_ATTRS}><line x1="2" y1="16" x2="28" y2="16"/><path d="M8 16v-3.5c0-.8.7-1.5 1.5-1.5h9c.8 0 1.5.7 1.5 1.5V16"/><line x1="8" y1="13" x2="20" y2="13"/><circle cx="9" cy="19.5" r="2"/><circle cx="21" cy="19.5" r="2"/></svg>',
    "utility": f'<svg {_ICON_ATTRS}><path d="M4 10h20v6H4z"/><line x1="4" y1="10" x2="4" y2="6"/><line x1="24" y1="10" x2="24" y2="6"/><circle cx="9" cy="19.5" r="2"/><circle cx="21" cy="19.5" r="2"/></svg>',
    "cargo_enclosed": f'<svg {_ICON_ATTRS}><rect x="3" y="5" width="22" height="11" rx="1.5"/><line x1="20" y1="5" x2="20" y2="16"/><circle cx="9" cy="19.5" r="2"/><circle cx="21" cy="19.5" r="2"/></svg>',
}
DEFAULT_ICON = f'<svg {_ICON_ATTRS}><line x1="2" y1="15" x2="26" y2="15"/><line x1="2" y1="15" x2="2" y2="11"/><circle cx="9" cy="19.5" r="2"/><circle cx="21" cy="19.5" r="2"/></svg>'

tab_qa, tab_match = st.tabs(["💬 Ask About Specs", "🔍 Find My Trailer"])

with tab_qa:
    st.caption(
        "Ask about trailer specs, axle capacities, GVWR, and more. "
        "Answers are grounded in the spec sheets -- if the info isn't there, "
        "it'll say so instead of guessing."
    )
    st.markdown(
        '<div class="aatc-disclaimer"><b>Demo notice:</b> Answers are generated '
        "from spec-sheet excerpts and may be incomplete or out of date. Verify "
        "critical specs directly with All American Trailer Connection or the "
        "manufacturer before making a purchase or towing decision.</div>",
        unsafe_allow_html=True,
    )

    if "qa_messages" not in st.session_state:
        st.session_state.qa_messages = []

    for msg in st.session_state.qa_messages:
        avatar = "🚛" if msg["role"] == "assistant" else None
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

    question = st.chat_input("Ask a question about trailer specs...", key="qa_input")

    if question:
        qa_user_turns = sum(1 for m in st.session_state.qa_messages if m["role"] == "user")

        if len(question) > MAX_INPUT_CHARS:
            _too_long_warning(question)
        elif qa_user_turns >= MAX_QA_MESSAGES_PER_SESSION:
            st.session_state.qa_messages.append({"role": "user", "content": question})
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant", avatar="🚛"):
                st.info(SESSION_LIMIT_MSG)
            st.session_state.qa_messages.append({"role": "assistant", "content": SESSION_LIMIT_MSG})
        else:
            st.session_state.qa_messages.append({"role": "user", "content": question})
            with st.chat_message("user"):
                st.markdown(question)

            with st.chat_message("assistant", avatar="🚛"):
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
    Prefer the exact real product page for this trailer -- product_url is
    set directly from the live site scrape (scrape_catalog.py ->
    normalize.py), so this links straight to the precise listing being
    recommended rather than a same-category page. Falls back to a
    category-specific AATC page, then the brand's general page, only for
    matches that didn't come from the scraped catalog and so have no
    product_url of their own (e.g. older PDF-derived data, or a 'pipe'
    trailer -- not a category AATC carries a dedicated page for).
    """
    product_url = m.get("product_url")
    if product_url:
        return product_url, "listing"

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


def _status_row(ok, label, margin):
    icon = "✅" if ok else "❌"
    cls = "ok" if ok else "bad"
    sign = "+" if margin >= 0 else ""
    return (
        f'<div class="aatc-status {cls}"><span>{icon} {html_lib.escape(label)}</span>'
        f'<span>{sign}{margin:,.0f} lb</span></div>'
    )


def build_match_card_html(m):
    # `or ""` rather than a .get() default -- real scraped listings can have
    # model_code/source present in the dict but set to None (e.g. the
    # "Custom Trailers" listing has no single model code and no listed
    # Trailer Brand), and a plain default only kicks in when the key is
    # missing entirely, not when it's there with a None value. Without this,
    # a None renders as the literal text "None" in the card.
    code = html_lib.escape(str(m.get("model_code") or ""))
    name = html_lib.escape(str(m.get("model_name") or ""))
    category = m.get("category") or "other"
    cat_label = html_lib.escape(category.replace("_", " ").title())
    icon_svg = CATEGORY_ICONS.get(category, DEFAULT_ICON)
    source = html_lib.escape(str(m.get("source") or ""))
    capacity = m.get("capacity_lb")
    margin = m.get("margin_lb")

    capacity_html = ""
    if capacity is not None:
        margin_html = ""
        if margin is not None:
            sign = "+" if margin >= 0 else ""
            margin_html = f'<div class="aatc-capacity-margin">{sign}{margin:,.0f} lb margin</div>'
        capacity_html = (
            '<div class="aatc-capacity">'
            '<div class="aatc-capacity-label">Capacity</div>'
            f'<div class="aatc-capacity-value">{capacity:,.0f} lb</div>'
            f'{margin_html}'
            '</div>'
        )

    tow_html = ""
    tow_check = m.get("tow_check")
    if tow_check:
        rows = (
            _status_row(tow_check["tow_rating_ok"], "Tow rating", tow_check["tow_rating_margin_lb"])
            + _status_row(tow_check["gcwr_ok"], "GCWR", tow_check["gcwr_margin_lb"])
            + _status_row(tow_check["tongue_ok"], "Tongue weight", tow_check["tongue_margin_lb"])
        )
        tow_html = f'<div class="aatc-tow-checks">{rows}</div>'

    link, link_kind = get_aatc_link(m)
    link_html = ""
    if link:
        if link_kind == "listing":
            label = "View this exact listing at AATC"
        elif link_kind == "brand":
            label = "See current inventory for this brand at AATC"
        else:
            label = f"See current {link_kind} inventory at AATC"
        link_html = f'<a class="aatc-card-link" href="{link}" target="_blank" rel="noopener">{html_lib.escape(label)} &rarr;</a>'

    # code/source can legitimately be empty (real example: the "Custom
    # Trailers" listing has no single model code and no listed Trailer
    # Brand) -- skip the leading code space / the middot separator rather
    # than rendering "  Custom Trailers..." or "Carhauler &middot; ".
    title_html = f'{code} <span class="aatc-card-name">{name}</span>' if code else f'<span class="aatc-card-name">{name}</span>'
    meta_html = f'{cat_label} &middot; {source}' if source else cat_label

    # Built as one unbroken string with no blank lines anywhere in it.
    # Streamlit's markdown renderer treats a blank line inside a raw <div>
    # block as the end of that HTML block (CommonMark HTML-block rules) --
    # that's what caused everything after the first blank line to show up
    # as literal, unrendered HTML text instead of a styled card.
    return (
        '<div class="aatc-card">'
        '<div class="aatc-card-head">'
        f'<div class="aatc-card-icon">{icon_svg}</div>'
        '<div>'
        f'<div class="aatc-card-title">{title_html}</div>'
        f'<div class="aatc-card-meta">{meta_html}</div>'
        '</div>'
        '</div>'
        f'{capacity_html}'
        f'{tow_html}'
        f'{link_html}'
        '</div>'
    )


def render_match_results(result):
    matches = result.get("matches") or []
    if not matches:
        return
    cards = "".join(build_match_card_html(m) for m in matches[:6])
    st.markdown(f'<div class="aatc-grid">{cards}</div>', unsafe_allow_html=True)


with tab_match:
    st.caption(
        "Tell me what you're hauling and what you're towing with, and I'll "
        "find trailers that actually fit -- checked against real capacity "
        "and tow-vehicle safety math, not a guess."
    )
    st.markdown(
        '<div class="aatc-disclaimer"><b>Demo notice:</b> This tool is for '
        "demonstration purposes. Trailer capacities are pulled from publicly "
        "available spec sheets, and tow-vehicle figures are representative "
        "example values &#8212; not a certified rating for your specific truck. "
        "Always verify exact GVWR, GCWR, and tow-rating figures against your "
        "vehicle&#39;s door-jamb sticker/owner&#39;s manual and the trailer&#39;s "
        "official spec sheet, and consult a qualified professional before "
        "towing. All American Trailer Connection is not responsible for "
        "decisions made based on this tool.</div>",
        unsafe_allow_html=True,
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
        avatar = "🚛" if msg["role"] == "assistant" else None
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            if result:
                render_match_results(result)

    load_question = st.chat_input("Describe what you need to haul...", key="match_input")

    if load_question:
        match_user_turns = sum(1 for m in st.session_state.match_messages if m["role"] == "user")

        if len(load_question) > MAX_INPUT_CHARS:
            _too_long_warning(load_question)
        elif match_user_turns >= MAX_MATCH_MESSAGES_PER_SESSION:
            st.session_state.match_messages.append({"role": "user", "content": load_question})
            st.session_state.match_results.append(None)
            with st.chat_message("user"):
                st.markdown(load_question)
            with st.chat_message("assistant", avatar="🚛"):
                st.info(SESSION_LIMIT_MSG)
            st.session_state.match_messages.append({"role": "assistant", "content": SESSION_LIMIT_MSG})
            st.session_state.match_results.append(None)
        else:
            st.session_state.match_messages.append({"role": "user", "content": load_question})
            st.session_state.match_results.append(None)
            with st.chat_message("user"):
                st.markdown(load_question)

            with st.chat_message("assistant", avatar="🚛"):
                with st.spinner("Thinking..."):
                    reply, match_result = match_chat(st.session_state.match_messages)
                st.markdown(reply)
                if match_result:
                    render_match_results(match_result)

            st.session_state.match_messages.append({"role": "assistant", "content": reply})
            st.session_state.match_results.append(match_result)