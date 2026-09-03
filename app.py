import streamlit as st
import json
import os
import re
import urllib.parse
from simple_salesforce import Salesforce

# -----------------------------------------------------------------------------
# PAGE CONFIGURATION
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="AATC Trailer Configurator & Quote Builder",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# -----------------------------------------------------------------------------
# ACCESS CONTROL & GATEKEEPER
# -----------------------------------------------------------------------------
query_params = st.query_params
embed_token = query_params.get("embed_auth")
dealer_pin = st.secrets.get("access", {}).get("dealer_pin", "aatc2026")
web_token = st.secrets.get("access", {}).get("embed_token", "aatc_live_embed_99")

if "is_authenticated" not in st.session_state:
    st.session_state.is_authenticated = False

if embed_token == web_token:
    st.session_state.is_authenticated = True

if not st.session_state.is_authenticated:
    st.markdown("""
    <div style="max-width: 480px; margin: 5rem auto; background: white; padding: 2.5rem; border-radius: 16px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1); text-align: center; border: 1px solid #e2e8f0;">
        <h3 style="margin-top:0; color: #0f172a;">🔒 AATC Staff & Partner Portal</h3>
        <p style="color: #64748b; font-size: 0.9rem;">Direct access to this tool is restricted to authorized dealership personnel. For public customer access, visit our official inventory page.</p>
    </div>
    """, unsafe_allow_html=True)
    
    col_k1, col_k2, col_k3 = st.columns([1, 2, 1])
    with col_k2:
        pin_input = st.text_input("Enter Dealership Access PIN:", type="password", placeholder="Enter PIN")
        if st.button("Unlock Wizard", type="primary", use_container_width=True):
            if pin_input == dealer_pin:
                st.session_state.is_authenticated = True
                st.rerun()
            else:
                st.error("Invalid Access PIN.")
    st.stop()

# -----------------------------------------------------------------------------
# MODERN STYLING
# -----------------------------------------------------------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; color: #0f172a; }
    .stApp { background: linear-gradient(180deg, #f1f5f9 0%, #e2e8f0 100%); }
    .wizard-header { text-align: center; max-width: 800px; margin: 0 auto 2rem auto; padding-top: 1.5rem; }
    .wizard-badge { display: inline-block; background: #dbeafe; border: 1px solid #93c5fd; color: #1e40af; font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px; padding: 6px 14px; border-radius: 9999px; margin-bottom: 0.75rem; }
    .wizard-title { font-size: 2.35rem; font-weight: 800; color: #0f172a; margin-bottom: 0.5rem; letter-spacing: -0.5px; }
    .wizard-sub { font-size: 1.05rem; color: #475569; line-height: 1.5; }
    .step-bar { display: flex; justify-content: space-between; max-width: 850px; margin: 0 auto 2.5rem auto; padding: 0.75rem 1.5rem; background: #ffffff; border-radius: 9999px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); border: 1px solid #e2e8f0; }
    .step-node { display: flex; flex-direction: column; align-items: center; }
    .step-circle { width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.9rem; }
    .step-active { background: #1d4ed8; color: #ffffff; box-shadow: 0 0 0 4px #bfdbfe; }
    .step-done { background: #059669; color: #ffffff; }
    .step-todo { background: #f1f5f9; color: #64748b; border: 1px solid #cbd5e1; }
    .step-text { font-size: 0.75rem; font-weight: 600; margin-top: 5px; color: #334155; }
    .step-header-banner { text-align: center; margin: 1rem auto 1.75rem auto; max-width: 680px; }
    .step-banner-title { font-size: 1.6rem; font-weight: 800; color: #0f172a; margin: 0 0 0.35rem 0; }
    .step-banner-sub { font-size: 0.95rem; color: #475569; margin: 0; line-height: 1.4; }
    .result-summary-box { background: linear-gradient(135deg, #091e3a 0%, #1e293b 100%); color: white; border-radius: 16px; padding: 2rem; margin-bottom: 1.5rem; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.25); }
    .trailer-result-card { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 14px; padding: 1.75rem; margin-bottom: 1.5rem; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.04); transition: transform 0.2s ease; }
    .trailer-result-card:hover { transform: translateY(-2px); box-shadow: 0 10px 20px -3px rgba(0, 0, 0, 0.08); }
    .spec-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 1rem; margin-top: 1.25rem; padding: 1rem 0; border-top: 1px solid #f1f5f9; border-bottom: 1px solid #f1f5f9; }
    .spec-item { display: flex; flex-direction: column; }
    .spec-label { font-size: 0.7rem; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }
    .spec-val { font-size: 1.15rem; font-weight: 700; color: #0f172a; margin-top: 2px; }
    .fit-badge { display: inline-block; padding: 6px 12px; border-radius: 9999px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; }
    .fit-safe { background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; }
    .fit-warn { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; }
    .build-box { background: #ffffff; border: 2px solid #2563eb; border-radius: 14px; padding: 1.75rem; margin-bottom: 1.5rem; }
    .price-total-badge { background: #059669; color: white; padding: 6px 14px; border-radius: 8px; font-size: 1.3rem; font-weight: 800; }
    .accessory-group { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1.25rem; margin-bottom: 1.25rem; }
    .disclaimer-card { background: #f8fafc; border: 1px solid #cbd5e1; border-left: 4px solid #64748b; border-radius: 8px; padding: 1rem 1.25rem; margin: 1.5rem 0; font-size: 0.8rem; color: #475569; line-height: 1.5; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# PARSING & HELPERS
# -----------------------------------------------------------------------------
def clean_int(val, default=0):
    if isinstance(val, (int, float)): return int(val)
    if isinstance(val, str):
        digits = re.sub(r"[^\d]", "", val)
        if digits: return int(digits)
    return default

def sanitize_brakes(brakes_str, gvwr):
    if not brakes_str or brakes_str.strip() in ["–", "-", "None", ""]:
        return "Idler Axle (Non-Brake < 3K)" if gvwr <= 3000 else "Standard Electric Brakes"
    return brakes_str.strip()

def get_labor_hours(item_name):
    name_u = item_name.upper()
    if "TARP" in name_u:
        return 1.0
    elif "LADDER RACK" in name_u:
        return 1.25
    elif "E TRACK" in name_u:
        return 1.0
    elif "TRIMMER" in name_u or "WEEDEATER" in name_u:
        return 0.75
    elif "BLOWER" in name_u or "TOOL RACK" in name_u or "COOLER" in name_u:
        return 0.5
    elif "WINCH" in name_u:
        return 0.5
    elif "SPARE" in name_u or "MOUNT" in name_u:
        return 0.25
    return 0.5

# -----------------------------------------------------------------------------
# SALESFORCE CLIENT & INVENTORY LOADER
# -----------------------------------------------------------------------------
@st.cache_resource
def get_salesforce_connection():
    try:
        sf_sec = st.secrets.get("salesforce", {})
        if sf_sec.get("username"):
            return Salesforce(
                username=sf_sec["username"],
                password=sf_sec["password"],
                security_token=sf_sec["security_token"],
                domain=sf_sec.get("domain", "login")
            )
    except Exception:
        pass
    return None

@st.cache_data(ttl=600)
def load_live_catalog():
    sf = get_salesforce_connection()
    if sf:
        try:
            pbe_query = """
                SELECT Product2.Id, Product2.Name, Product2.Make__c, Product2.SKU_Model__c,
                       Product2.StockKeepingUnit, Product2.Family, Product2.GVWR__c,
                       Product2.Load_Capacity__c, Product2.Length__c, Product2.Brake_Type__c,
                       Product2.Tongue_Type__c, Product2.Total_Stock__c, Product2.In_Stock__c,
                       Product2.Used_Sku__c, UnitPrice
                FROM PricebookEntry
                WHERE IsActive = True
                  AND Product2.Make__c != null
                  AND (Product2.Total_Stock__c > 0 OR Product2.In_Stock__c > 0)
            """
            records = sf.query_all(pbe_query).get("records", [])
            if records:
                standardized = []
                for r in records:
                    p = r.get("Product2", {})
                    title = p.get("Name") or p.get("SKU_Model__c") or "Trailer Unit"
                    brand = p.get("Make__c") or "AATC Stock"
                    family = p.get("Family") or "Utility / Equipment"
                    gvwr = clean_int(p.get("GVWR__c"), default=0)
                    payload = clean_int(p.get("Load_Capacity__c"), default=0)
                    empty = gvwr - payload if (gvwr > 0 and payload > 0 and gvwr > payload) else int(gvwr * 0.28)
                    sku = p.get("SKU_Model__c") or p.get("StockKeepingUnit") or ""
                    retail_price = float(r.get("UnitPrice") or 0.0)

                    # Route by SKU or fall back to main category archive
                    # Match exact product page from local catalog
                    url = "https://allamericantrailer.com/shop/"
                    if os.path.exists("data/catalog_raw.json"):
                        try:
                            with open("data/catalog_raw.json", "r", encoding="utf-8", errors="replace") as f_cat:
                                cat_data = json.load(f_cat)
                                s_clean = sku.replace("-BK", "").strip().lower() if sku else ""
                                t_clean = title.strip().lower() if title else ""
                                for item in cat_data:
                                    it_title = str(item.get("title") or item.get("name") or "").lower()
                                    if (s_clean and s_clean in it_title) or (t_clean and t_clean in it_title):
                                        direct_url = item.get("url") or item.get("product_url")
                                        if direct_url:
                                            url = direct_url
                                            break
                        except Exception:
                            pass

                    standardized.append({
                        "id": p.get("Id"),
                        "brand": brand,
                        "model_name": title,
                        "sku": sku,
                        "category": family,
                        "condition": "Used" if p.get("Used_Sku__c") else "New",
                        "gvwr": gvwr,
                        "payload": payload,
                        "empty_weight": empty,
                        "dimensions": p.get("Length__c") or "Standard Size",
                        "axles": sanitize_brakes(p.get("Brake_Type__c"), gvwr),
                        "price": retail_price,
                        "in_stock": int(p.get("Total_Stock__c") or p.get("In_Stock__c") or 1),
                        "url": url
                    })
                return standardized
        except Exception:
            pass

    for fn in ["data/catalog_raw.json", "data/normalized_catalog.json"]:
        if os.path.exists(fn):
            for enc in ["utf-8", "cp1252", "latin-1"]:
                try:
                    with open(fn, "r", encoding=enc, errors="replace") as f:
                        data = json.load(f)
                        standardized = []
                        for item in data:
                            title = str(item.get("title") or item.get("name") or "")
                            url = str(item.get("url") or item.get("product_url") or "https://allamericantrailer.com")
                            add_info = item.get("additional_information", {})
                            specs = item.get("specifications", {})
                            brand = str(item.get("brand") or add_info.get("Trailer Brand") or "AATC Stock").strip()
                            category = str(item.get("category") or add_info.get("Trailer Type") or "Equipment").strip()
                            gvwr = clean_int(add_info.get("GVWR") or specs.get("G.V.W.R."), default=0)
                            payload = clean_int(add_info.get("Load Capacity"), default=0)
                            empty = gvwr - payload if (gvwr > 0 and payload > 0) else int(gvwr * 0.28)
                            if "truck bed" in title.lower() or "bin only" in title.lower() or gvwr < 2000:
                                continue
                            standardized.append({
                                "brand": brand,
                                "model_name": title,
                                "category": category,
                                "condition": "New",
                                "gvwr": gvwr,
                                "payload": payload,
                                "empty_weight": empty,
                                "dimensions": add_info.get("Length") or "Standard Length",
                                "axles": sanitize_brakes(add_info.get("Brake Type"), gvwr),
                                "price": 5495.00,
                                "in_stock": 1,
                                "url": url
                            })
                        return standardized
                except Exception:
                    continue
    return []

@st.cache_data(ttl=600)
def load_live_accessories():
    sf = get_salesforce_connection()
    if sf:
        try:
            query = """
                SELECT Id, Product2.Id, Product2.Name, Product2.StockKeepingUnit, UnitPrice
                FROM PricebookEntry
                WHERE IsActive = True
                  AND (Product2.Name LIKE '%TARP%'
                    OR Product2.Name LIKE '%RACK%'
                    OR Product2.Name LIKE '%COOLER%'
                    OR Product2.Name LIKE '%E TRACK%'
                    OR Product2.Name LIKE '%STRAP%'
                    OR Product2.Name LIKE '%SPARE%')
                  AND Product2.Make__c = null
                ORDER BY UnitPrice ASC
            """
            results = sf.query_all(query).get("records", [])
            acc_list = []
            for r in results:
                p = r.get("Product2", {})
                name = p.get("Name")
                price = float(r.get("UnitPrice") or 0.0)
                if price <= 0:
                    continue
                cat = "Universal"
                name_u = name.upper()
                if "DUMP" in name_u or "TARP" in name_u:
                    cat = "Dump"
                elif "ENCLOSED" in name_u or "E TRACK" in name_u or "LADDER RACK" in name_u:
                    cat = "Enclosed"
                elif "OPEN" in name_u or "WEEDEATER" in name_u or "TRIMMER" in name_u or "BLOWER" in name_u or "COOLER" in name_u:
                    cat = "Landscape"

                acc_list.append({
                    "id": p.get("Id"),
                    "name": name,
                    "price": price,
                    "category": cat,
                    "labor_hours": get_labor_hours(name)
                })
            return acc_list
        except Exception:
            pass

    return [
        {"name": "5 X 12 DUMP TARP INSTALLED", "price": 315.00, "category": "Dump", "labor_hours": 1.0},
        {"name": "6 X 14 DUMP TARP INSTALLED", "price": 315.00, "category": "Dump", "labor_hours": 1.0},
        {"name": "8 X 22 STANDARD TARP MECHANISM INSTALLED", "price": 350.00, "category": "Dump", "labor_hours": 1.25},
        {"name": "LOCKABLE 4 TRIMMER RACKS WITH PADLOCKS INSTALLED OPEN TRAILER", "price": 290.00, "category": "Landscape", "labor_hours": 0.75},
        {"name": "6 POSITION TOOL RACK INSTALLED OPEN TRAILER", "price": 150.00, "category": "Landscape", "labor_hours": 0.5},
        {"name": "BACKPACK LOCKABLE BLOWER RACK INSTALLED OPEN/ENCL", "price": 310.00, "category": "Landscape", "labor_hours": 0.5},
        {"name": "(2) LADDER RACKS INSTALLED ON TOP ENCLOSED", "price": 350.00, "category": "Enclosed", "labor_hours": 1.25},
        {"name": "(3) LADDER RACKS INSTALLED ON TOP ENCLOSED", "price": 475.00, "category": "Enclosed", "labor_hours": 1.5},
        {"name": "INSTALL 2 STRIPS OF E TRACK ON FLOOR, UP TO 20FT", "price": 235.00, "category": "Enclosed", "labor_hours": 1.0},
        {"name": "2 PAIR AATC WEEDEATER RACKS INSTALLED IN ENCLOSED TRAILER", "price": 180.00, "category": "Enclosed", "labor_hours": 0.75},
        {"name": "ALUMINUM STUD STYLE SPARE TIRE MOUNT", "price": 26.00, "category": "Universal", "labor_hours": 0.25},
        {"name": "1 WELD ON STRAP WINCHES INSTALLED WITH 4X30 STRAPS", "price": 200.00, "category": "Universal", "labor_hours": 0.5},
        {"name": "2 WELD ON STRAP WINCHES INSTALLED WITH 4X30 STRAPS", "price": 270.00, "category": "Universal", "labor_hours": 0.75}
    ]

# -----------------------------------------------------------------------------
# CONSTANTS & CONFIGS
# -----------------------------------------------------------------------------
CARGO_PRESETS = {
    "🚜 Compact Tractor / Mowers (Under 3,500 lbs)": 3500,
    "🚗 Car / Small SUV / Light Equipment (4,000 - 6,000 lbs)": 5500,
    "🚧 Skid Steer / Mini Excavator (7,500 - 10,000 lbs)": 9000,
    "🪨 Heavy Equipment / Full Dump Load (11,000 - 16,000 lbs)": 14000,
    "📦 General Cargo / Moving / Landscaping (1,500 - 3,500 lbs)": 2500,
    "⚙️ Custom Weight Entry": 0
}

TOW_VEHICLES = {
    "Mid-Size SUV / Light Truck (Tacoma, Explorer, Colorado)": {"tow_cap": 5000, "class": "Class III"},
    "Half-Ton Truck (F-150, Silverado 1500, Ram 1500, Tundra)": {"tow_cap": 9500, "class": "Class IV"},
    "Three-Quarter Ton Truck (F-250, 2500 HD)": {"tow_cap": 15000, "class": "Class V"},
    "One-Ton Heavy Duty (F-350 / 3500 Single / Dually)": {"tow_cap": 24000, "class": "Heavy Commercial"},
    "Commercial Medium Duty (F-450 / F-550 / Cab Chassis)": {"tow_cap": 35000, "class": "Commercial"}
}

ALL_TRAILERS = load_live_catalog()
ALL_ACCESSORIES = load_live_accessories()

if "step" not in st.session_state:
    st.session_state.step = 1
if "selected_trailer" not in st.session_state:
    st.session_state.selected_trailer = None

# -----------------------------------------------------------------------------
# HEADER & STEPPER
# -----------------------------------------------------------------------------
st.markdown("""
<div class="wizard-header">
    <div class="wizard-badge">AATC Live Salesforce Rig Builder</div>
    <div class="wizard-title">Right-Size & Custom-Build Your Trailer</div>
    <p class="wizard-sub">Find the exact right trailer matched to your truck, and customize it with commercial add-ons for a complete drive-away quote.</p>
</div>
""", unsafe_allow_html=True)

s1_cls = "step-done" if st.session_state.step > 1 else ("step-active" if st.session_state.step == 1 else "step-todo")
s2_cls = "step-done" if st.session_state.step > 2 else ("step-active" if st.session_state.step == 2 else "step-todo")
s3_cls = "step-done" if st.session_state.step > 3 else ("step-active" if st.session_state.step == 3 else "step-todo")
s4_cls = "step-done" if st.session_state.step > 4 else ("step-active" if st.session_state.step == 4 else "step-todo")
s5_cls = "step-active" if st.session_state.step == 5 else "step-todo"

st.markdown(f"""
<div class="step-bar">
    <div class="step-node"><div class="step-circle {s1_cls}">1</div><span class="step-text">Tow Vehicle</span></div>
    <div class="step-node"><div class="step-circle {s2_cls}">2</div><span class="step-text">Cargo & Weight</span></div>
    <div class="step-node"><div class="step-circle {s3_cls}">3</div><span class="step-text">Style & Budget</span></div>
    <div class="step-node"><div class="step-circle {s4_cls}">4</div><span class="step-text">Select Unit</span></div>
    <div class="step-node"><div class="step-circle {s5_cls}">5</div><span class="step-text">Custom Add-Ons</span></div>
</div>
""", unsafe_allow_html=True)

col_l, col_center, col_r = st.columns([1, 6, 1])

with col_center:
    # STEP 1: Tow Vehicle
    if st.session_state.step == 1:
        st.markdown('<div class="step-header-banner"><div class="step-banner-title">Step 1: Select Your Tow Vehicle</div><div class="step-banner-sub">Your vehicle rating determines the safe gross trailer weight (GVWR) limit.</div></div>', unsafe_allow_html=True)
        selected_veh = st.selectbox("Select Your Vehicle Class:", list(TOW_VEHICLES.keys()))
        veh_data = TOW_VEHICLES[selected_veh]
        st.info(f"💡 **Estimated Towing Limit:** **{veh_data['tow_cap']:,} lbs** ({veh_data['class']})")
        st.session_state.tow_vehicle = selected_veh
        st.session_state.tow_cap = veh_data["tow_cap"]
        if st.button("Continue to Cargo Selection ➔", type="primary", use_container_width=True):
            st.session_state.step = 2
            st.rerun()

    # STEP 2: Cargo & Payload
    elif st.session_state.step == 2:
        st.markdown('<div class="step-header-banner"><div class="step-banner-title">Step 2: What do you plan to haul?</div><div class="step-banner-sub">Select your typical payload profile or enter an exact cargo requirement.</div></div>', unsafe_allow_html=True)
        preset = st.radio("Choose Primary Cargo Type:", list(CARGO_PRESETS.keys()))
        if preset == "⚙️ Custom Weight Entry":
            payload_target = st.number_input("Enter exact cargo weight needed (lbs):", min_value=500, max_value=25000, value=5000, step=500)
        else:
            payload_target = CARGO_PRESETS[preset]
            st.caption(f"Target payload calculated at **{payload_target:,} lbs**")
        st.session_state.payload_target = payload_target
        c1, c2 = st.columns(2)
        with c1:
            if st.button("⬅ Back"):
                st.session_state.step = 1
                st.rerun()
        with c2:
            if st.button("Continue to Style & Budget ➔", type="primary", use_container_width=True):
                st.session_state.step = 3
                st.rerun()

    # STEP 3: Style & Budget Preferences
    elif st.session_state.step == 3:
        st.markdown('<div class="step-header-banner"><div class="step-banner-title">Step 3: Style & Budget Preferences</div><div class="step-banner-sub">Pick your preferred trailer configuration and target investment tier.</div></div>', unsafe_allow_html=True)
        category_choice = st.selectbox(
            "Preferred Trailer Category:",
            ["All Compatible Styles (Recommended)", "Dump Trailer", "Equipment Trailer", "Tilt Trailer", "Utility Trailer", "Car Hauler", "Cargo Trailer / Enclosed", "Gooseneck Trailer"]
        )
        budget_choice = st.selectbox(
            "Target Investment Range / Budget Tier:",
            [
                "Any Price Point / Explore All Tiers",
                "Entry-Level / Utility Tier (Under $4,000)",
                "Mid-Duty / Pro-Hauler Tier ($4,000 - $7,500)",
                "Commercial Workhorse Tier ($7,500 - $12,000)",
                "Heavy-Duty / High-Cap Tier ($12,000+)"
            ]
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("⬅ Back"):
                st.session_state.step = 2
                st.rerun()
        with c2:
            if st.button("🎯 Find My Top Matches", type="primary", use_container_width=True):
                st.session_state.step = 4
                st.session_state.category_choice = category_choice
                st.session_state.budget_choice = budget_choice
                st.rerun()

    # STEP 4: Matching Units & Unit Selection
    elif st.session_state.step == 4:
        tow_cap = st.session_state.get("tow_cap", 10000)
        tow_veh = st.session_state.get("tow_vehicle", "Standard Truck")
        target_payload = st.session_state.get("payload_target", 2500)
        pref_cat = st.session_state.get("category_choice", "All Compatible Styles (Recommended)")
        initial_budget = st.session_state.get("budget_choice", "Any Price Point / Explore All Tiers")

        def matches_cat(trailer_cat, user_pref):
            if user_pref == "All Compatible Styles (Recommended)": return True
            tc = trailer_cat.lower()
            up = user_pref.lower()
            if "dump" in up and "dump" in tc: return True
            if "equipment" in up and "equipment" in tc: return True
            if "tilt" in up and "tilt" in tc: return True
            if "utility" in up and "util" in tc: return True
            if "car" in up and ("car" in tc or "auto" in tc): return True
            if "cargo" in up and ("cargo" in tc or "enclosed" in tc): return True
            if "gooseneck" in up and "gooseneck" in tc: return True
            return up in tc

        raw_candidates = [t for t in ALL_TRAILERS if t["payload"] >= target_payload and matches_cat(t["category"], pref_cat)]

        st.markdown(f"""
        <div class="result-summary-box">
            <h3 style="margin: 0 0 0.5rem 0; font-size: 1.5rem; color: #ffffff;">Fitment Analysis Summary</h3>
            <p style="color: #94a3b8; margin-bottom: 1.25rem;">Based on your <strong>{tow_veh}</strong> ({tow_cap:,} lbs limit) and <strong>{target_payload:,} lbs</strong> target payload:</p>
            <div style="display: flex; gap: 2.5rem; flex-wrap: wrap;">
                <div><span style="font-size: 0.75rem; text-transform: uppercase; color: #94a3b8; font-weight: 600;">Tow Rating Cap</span><br><strong style="font-size: 1.4rem; color: #ffffff;">{tow_cap:,} lbs</strong></div>
                <div><span style="font-size: 0.75rem; text-transform: uppercase; color: #94a3b8; font-weight: 600;">Target Payload</span><br><strong style="font-size: 1.4rem; color: #34d399;">{target_payload:,} lbs</strong></div>
                <div><span style="font-size: 0.75rem; text-transform: uppercase; color: #94a3b8; font-weight: 600;">Matching Units</span><br><strong style="font-size: 1.4rem; color: #60a5fa;">{len(raw_candidates)} In Stock</strong></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if not raw_candidates:
            st.warning("No in-stock trailers match those criteria. Try adjusting your target weight or selecting another category.")
        else:
            st.markdown("#### 🔍 Narrow Down & Sort Your Results")
            c_use, c_budget, c_brand, c_sort = st.columns([3, 3, 2, 3])
            
            with c_use:
                use_case = st.selectbox(
                    "What are you primarily hauling?",
                    ["Any / All Usages", "🚗 Vehicles, Cars & UTVs", "📦 Weather-Protected Freight & Tools", "🪨 Dirt, Rock & Debris (Dump)", "🚜 Lawn, Farm & General Utility"]
                )

            with c_budget:
                budget_options = [
                    "All Budget Tiers",
                    "Under $4,000 (Entry/Utility)",
                    "$4,000 - $7,500 (Mid-Range Pro)",
                    "$7,500 - $12,000 (Commercial Workhorse)",
                    "$12,000+ (Heavy Equipment / Tilt)"
                ]
                default_idx = 0
                if "Under $4,000" in initial_budget: default_idx = 1
                elif "$4,000 - $7,500" in initial_budget: default_idx = 2
                elif "$7,500 - $12,000" in initial_budget: default_idx = 3
                elif "$12,000+" in initial_budget: default_idx = 4
                selected_tier = st.selectbox("Budget Bracket:", budget_options, index=default_idx)

            with c_brand:
                available_brands = sorted(list({t["brand"] for t in raw_candidates if t["brand"]}))
                filter_brand = st.selectbox("Brand:", ["All Brands"] + available_brands)

            with c_sort:
                sort_option = st.selectbox("Sort By:", [
                    "🎯 Best Fit (Closest to Payload Target)",
                    "💵 Price: Low to High",
                    "💎 Price: High to Low",
                    "💪 Highest Payload Capacity",
                    "🪶 Lightest Empty Weight",
                    "🛡️ Maximum Safety Margin"
                ])

            filtered = []
            for t in raw_candidates:
                cat_lower = t["category"].lower()
                name_lower = t["model_name"].lower()
                price = t.get("price", 0.0)

                if use_case == "🚗 Vehicles, Cars & UTVs" and not ("car" in cat_lower or "car" in name_lower or "auto" in cat_lower or "tilt" in cat_lower):
                    continue
                if use_case == "📦 Weather-Protected Freight & Tools" and not ("cargo" in cat_lower or "enclosed" in cat_lower or "cargo" in name_lower):
                    continue
                if use_case == "🪨 Dirt, Rock & Debris (Dump)" and not ("dump" in cat_lower or "dump" in name_lower):
                    continue
                if use_case == "🚜 Lawn, Farm & General Utility" and not ("util" in cat_lower or "util" in name_lower or "equipment" in cat_lower):
                    continue
                if filter_brand != "All Brands" and t["brand"] != filter_brand:
                    continue

                if price > 0:
                    if selected_tier == "Under $4,000 (Entry/Utility)" and price >= 4000:
                        continue
                    elif selected_tier == "$4,000 - $7,500 (Mid-Range Pro)" and (price < 4000 or price >= 7500):
                        continue
                    elif selected_tier == "$7,500 - $12,000 (Commercial Workhorse)" and (price < 7500 or price >= 12000):
                        continue
                    elif selected_tier == "$12,000+ (Heavy Equipment / Tilt)" and price < 12000:
                        continue

                filtered.append(t)

            if not filtered:
                st.info("No exact units match that specific budget and use-case combination. Showing all compatible models:")
                filtered = raw_candidates

            if "Best Fit" in sort_option:
                filtered.sort(key=lambda x: abs(x["payload"] - target_payload))
            elif "Price: Low to High" in sort_option:
                filtered.sort(key=lambda x: x["price"])
            elif "Price: High to Low" in sort_option:
                filtered.sort(key=lambda x: x["price"], reverse=True)
            elif "Highest Payload" in sort_option:
                filtered.sort(key=lambda x: x["payload"], reverse=True)
            elif "Lightest Empty" in sort_option:
                filtered.sort(key=lambda x: x["empty_weight"])
            elif "Maximum Safety" in sort_option:
                filtered.sort(key=lambda x: x["gvwr"])

            display_limit = 5
            total_matches = len(filtered)
            st.markdown(f"### 🎯 Top Recommended Matches ({min(display_limit, total_matches)} of {total_matches} units)")
            st.caption("Click **'Select & Customize Build'** on any trailer to configure options, add accessories, and get an itemized quote.")

            for idx, t in enumerate(filtered[:display_limit]):
                margin = tow_cap - t["gvwr"]
                badge_html = f'<span class="fit-badge fit-safe">✓ Safe Tow Match ({margin:,} lbs safety margin)</span>'
                cond_badge = '<span style="background: #fef3c7; color: #92400e; font-weight: 700; font-size: 0.75rem; padding: 4px 8px; border-radius: 4px; text-transform: uppercase;">Pre-Owned Deal</span>' if t.get("condition") == "Used" else '<span style="background: #eff6ff; color: #1d4ed8; font-weight: 700; font-size: 0.75rem; padding: 4px 8px; border-radius: 4px; text-transform: uppercase;">New Unit</span>'
                price_display = f"${t['price']:,.2f}" if t['price'] > 0 else "$5,495.00"

                st.markdown(f"""
                <div class="trailer-result-card">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 0.5rem;">
                        <div>
                            {cond_badge}
                            <span style="margin-left: 6px; background: #f8fafc; color: #0f172a; font-weight: 700; font-size: 0.75rem; padding: 4px 8px; border-radius: 4px; border: 1px solid #cbd5e1; text-transform: uppercase;">{t['brand']}</span>
                            <span style="margin-left: 6px; background: #f8fafc; color: #64748b; font-size: 0.75rem; padding: 4px 8px; border-radius: 4px; border: 1px solid #e2e8f0;">{t['category']}</span>
                            <h3 style="margin: 8px 0 2px 0; font-size: 1.3rem; font-weight: 800; color: #0f172a;">{t['model_name']}</h3>
                        </div>
                        <div>{badge_html}</div>
                    </div>
                    <div class="spec-grid">
                        <div class="spec-item"><span class="spec-label">Payload Capacity</span><span class="spec-val" style="color: #059669;">{t['payload']:,} lbs</span></div>
                        <div class="spec-item"><span class="spec-label">Gross GVWR</span><span class="spec-val">{t['gvwr']:,} lbs</span></div>
                        <div class="spec-item"><span class="spec-label">Estimated Empty</span><span class="spec-val">{t['empty_weight']:,} lbs</span></div>
                        <div class="spec-item"><span class="spec-label">Deck / Length</span><span class="spec-val">{t['dimensions']}</span></div>
                        <div class="spec-item"><span class="spec-label">Base Retail Price</span><span class="spec-val" style="color: #2563eb;">{price_display}</span></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                col_b1, col_b2 = st.columns([3, 2])
                with col_b1:
                    if st.button(f"🛠️ Select & Customize Build: {t['model_name'][:30]}...", key=f"sel_{idx}", type="primary", use_container_width=True):
                        st.session_state.selected_trailer = t
                        st.session_state.step = 5
                        st.rerun()
                with col_b2:
                    st.link_button("View Live AATC Listing ➔", t["url"], use_container_width=True)

            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("⬅ Back / Change Fitment Specs"):
                st.session_state.step = 3
                st.rerun()

    # STEP 5: Add-On Configurator & Full Build Quote
    elif st.session_state.step == 5:
        trailer = st.session_state.get("selected_trailer")
        if not trailer:
            st.warning("No trailer currently selected. Returning to inventory.")
            st.session_state.step = 4
            st.rerun()

        base_price = trailer.get("price", 5495.00)
        cat_lower = trailer.get("category", "").lower()

        st.markdown(f"""
        <div class="build-box">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                <div>
                    <span style="background: #eff6ff; color: #1d4ed8; font-weight: 700; font-size: 0.75rem; padding: 4px 8px; border-radius: 4px; text-transform: uppercase;">Selected Base Unit</span>
                    <h2 style="margin: 6px 0; color: #0f172a;">{trailer['brand']} {trailer['model_name']}</h2>
                    <p style="color: #64748b; margin: 0;">GVWR: <strong>{trailer['gvwr']:,} lbs</strong> | Payload: <strong>{trailer['payload']:,} lbs</strong> | Deck / Length: <strong>{trailer['dimensions']}</strong></p>
                </div>
                <div style="text-align: right; margin-top: 8px;">
                    <span style="font-size: 0.8rem; color: #64748b; font-weight: 600; text-transform: uppercase;">Base Unit Price</span><br>
                    <strong style="font-size: 1.6rem; color: #0f172a;">${base_price:,.2f}</strong>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("### 🔧 Installed Equipment, Upgrades & Accessories")
        st.caption("Pricing below reflects full turnkey installed packages including parts, mounting hardware, and dedicated technician labor hours.")

        selected_addons = []

        if "dump" in cat_lower:
            dump_items = [a for a in ALL_ACCESSORIES if a["category"] == "Dump"]
            if dump_items:
                st.markdown('<div class="accessory-group"><h4>🪨 Verified Dump Trailer Add-Ons</h4>', unsafe_allow_html=True)
                for idx, item in enumerate(dump_items):
                    hrs = item.get("labor_hours", 1.0)
                    label = f"{item['name']} — **${item['price']:,.2f}** (Includes shop install ~{hrs:.1f} hr labor)"
                    if st.checkbox(label, key=f"dump_{idx}"):
                        selected_addons.append(item)
                st.markdown('</div>', unsafe_allow_html=True)

        elif "cargo" in cat_lower or "enclosed" in cat_lower:
            cargo_items = [a for a in ALL_ACCESSORIES if a["category"] == "Enclosed"]
            if cargo_items:
                st.markdown('<div class="accessory-group"><h4>📦 Verified Enclosed Cargo Add-Ons</h4>', unsafe_allow_html=True)
                for idx, item in enumerate(cargo_items):
                    hrs = item.get("labor_hours", 1.0)
                    label = f"{item['name']} — **${item['price']:,.2f}** (Includes shop install ~{hrs:.1f} hr labor)"
                    if st.checkbox(label, key=f"cargo_{idx}"):
                        selected_addons.append(item)
                st.markdown('</div>', unsafe_allow_html=True)

        elif "util" in cat_lower or "landscape" in cat_lower:
            land_items = [a for a in ALL_ACCESSORIES if a["category"] == "Landscape"]
            if land_items:
                st.markdown('<div class="accessory-group"><h4>🌿 Verified Commercial Landscape Add-Ons</h4>', unsafe_allow_html=True)
                for idx, item in enumerate(land_items):
                    hrs = item.get("labor_hours", 0.5)
                    label = f"{item['name']} — **${item['price']:,.2f}** (Includes shop install ~{hrs:.1f} hr labor)"
                    if st.checkbox(label, key=f"land_{idx}"):
                        selected_addons.append(item)
                st.markdown('</div>', unsafe_allow_html=True)

        univ_items = [a for a in ALL_ACCESSORIES if a["category"] == "Universal"]
        if univ_items:
            st.markdown('<div class="accessory-group"><h4>🛡️ Universal Straps, Winches & Road Essentials</h4>', unsafe_allow_html=True)
            col_u1, col_u2 = st.columns(2)
            half = (len(univ_items) + 1) // 2
            with col_u1:
                for idx, item in enumerate(univ_items[:half]):
                    hrs = item.get("labor_hours", 0.5)
                    label = f"{item['name']} — **${item['price']:,.2f}** (~{hrs:.1f} hr)"
                    if st.checkbox(label, key=f"univ1_{idx}"):
                        selected_addons.append(item)
            with col_u2:
                for idx, item in enumerate(univ_items[half:]):
                    hrs = item.get("labor_hours", 0.5)
                    label = f"{item['name']} — **${item['price']:,.2f}** (~{hrs:.1f} hr)"
                    if st.checkbox(label, key=f"univ2_{idx}"):
                        selected_addons.append(item)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="accessory-group">', unsafe_allow_html=True)
        st.markdown("#### ✍️ Custom Equipment, Welding or Special Requests")
        st.caption("Need specific D-ring placement, toolboxes, custom side extensions, or custom wiring? Detail your requested modifications below:")
        custom_request_text = st.text_area(
            "Custom Rigging & Fabrication Notes:",
            placeholder="e.g. Please add 4 recessed D-rings welded at 4-foot intervals along the outer deck, and quote an aluminum tongue-mounted toolbox.",
            height=90
        )
        st.markdown('</div>', unsafe_allow_html=True)

        addon_total = sum(item["price"] for item in selected_addons)
        total_labor_hours = sum(item.get("labor_hours", 0.0) for item in selected_addons)
        grand_total = base_price + addon_total

        st.markdown("---")
        st.markdown(f"""
        <div style="background: #f1f5f9; border-radius: 12px; padding: 1.5rem; margin: 1rem 0;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                <div>
                    <h3 style="margin: 0; color: #0f172a;">Estimated Total Drive-Away Investment</h3>
                    <p style="color: #64748b; margin: 4px 0 0 0;">
                        Base Trailer: <strong>${base_price:,.2f}</strong> + {len(selected_addons)} Upgrades (<strong>${addon_total:,.2f}</strong>) | Total Shop Labor Included: <strong>~{total_labor_hours:.1f} hrs</strong>
                    </p>
                </div>
                <div class="price-total-badge">
                    ${grand_total:,.2f}
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="disclaimer-card">
            <strong>⚠️ AATC Pricing & Quotation Disclaimer:</strong><br>
            All prices and equipment configurations are estimates based on live yard inventory and standard installation parameters. Quoted prices do not include applicable state sales tax, county surcharges, title, registration/tag transfer fees, electronic filing fees, or dealer pre-delivery service documentation charges. In-stock units are subject to prior sale. Installation turnaround times depend on shop scheduling and technician bay availability at time of contract execution.
        </div>
        """, unsafe_allow_html=True)

        st.markdown("### 📋 Lock In Your Build Quote & Check Yard Availability")
        st.caption("Submit your customized configuration to our sales desk. We'll hold the unit for 24 hours and verify installation scheduling.")
        
        c_name, c_phone, c_email = st.columns(3)
        with c_name:
            cust_name = st.text_input("Your Full Name *", placeholder="John Smith")
        with c_phone:
            cust_phone = st.text_input("Phone Number *", placeholder="(772) 555-0199")
        with c_email:
            cust_email = st.text_input("Email Address", placeholder="john@example.com")

        col_back4, col_sub = st.columns([1, 2])
        with col_back4:
            if st.button("⬅ Back to Matches"):
                st.session_state.step = 4
                st.rerun()
        with col_sub:
            if st.button("🚀 Lock In Quote & Send to Sales Desk", type="primary", use_container_width=True):
                if not cust_name or not cust_phone:
                    st.error("Please enter your name and phone number so the sales team can confirm your reservation.")
                else:
                    st.success(f"🎉 Thank you, {cust_name}! Your custom build quote for the **{trailer['brand']} {trailer['model_name']}** (${grand_total:,.2f}) has been logged.")
                    if custom_request_text.strip():
                        st.info(f"📝 **Special Request Logged:** \"{custom_request_text.strip()}\" — A technician will review this note prior to calling.")
                    st.balloons()