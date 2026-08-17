"""
normalize.py -- Stage 2 of building data/catalog.json from the live
website. Reads the raw label/value data scrape_catalog.py wrote to
data/catalog_raw.json and maps it into matcher.py's actual schema
(model_code, model_name, source, gvwr_max_lb, num_axles,
axle_capacity_options_lb, deck_length_ft_max), built from real labels
observed across 5 real product pages (4 standardized Big Tex listings +
1 sparser custom/bundle listing) -- not guessed blind.

Also carries product_url through onto every normalized entry (not part
of matcher.py's matching logic, but exactly what app.py needs to link
straight to the real listing being recommended, replacing today's
category/brand fallback links).

Run scrape_catalog.py first, then this:
    python scrape_catalog.py
    python normalize.py
"""
import json
import re
from pathlib import Path

RAW_PATH = Path("data/catalog_raw.json")
OUTPUT_PATH = Path("data/catalog.json")

# Matches a leading model-code-looking token -- the whole first
# whitespace-delimited token, as long as it contains at least one dash
# somewhere in it. Real evidence from a full 209-listing scrape: many real
# AATC codes have TWO dashes, not one -- "90SR-12-SIR", "D3-122-P4",
# "L6-162-SIR", "99DT-12-P4" -- which an earlier version of this pattern
# (exactly one dash) missed entirely, silently returning None for real
# coded listings alongside the genuinely code-less ones (confirmed by
# comparing a real matcher.py run: "90SR-10" extracted fine, but its
# sibling listing "90SR-12-SIR" came back None even though the code is
# right there in the title). \S*-\S* backtracks to find any dash in the
# token, however many there are, and captures the whole token around it.
# Titles with no dash in their first token at all (Custom Trailers,
# Jobsite Office Trailer listings) correctly still find no match here and
# fall back to model_code=None rather than a fabricated one.
MODEL_CODE_PATTERN = re.compile(r"^(\S*-\S*)\s")

# Any comma-grouped number followed by # or lb(s) -- covers both real
# formats seen in the Specifications tab's AXLE field: "8,000#" and
# "5,200lb - 7,000 lb".
AXLE_WEIGHT_PATTERN = re.compile(r"([\d,]+)\s*(?:#|lbs?\b)", re.I)
AXLE_COUNT_PATTERN = re.compile(r"^\((\d+)\)")

# Products that aren't actually trailers -- pickup truck bed replacements
# (CM/NXG brand) and standalone roll-off bins (explicitly titled "BIN
# ONLY", no frame or axles of their own). Confirmed via a real full-catalog
# scrape (209 listings): every one of the 32 entries with neither a GVWR
# nor axle data matched one of these two title patterns -- not a scraping
# gap, these products genuinely have no GVWR concept (a truck bed isn't
# towed; a bin-only unit has no frame). Excluded here so it's a visible,
# explained decision in this script's own output, not silent data loss or
# a confusing "unverifiable" warning about products this matcher was never
# meant to evaluate in the first place.
NON_TRAILER_TITLE_PATTERNS = [
    re.compile(r"truck bed", re.I),
    re.compile(r"bin only", re.I),
]


def is_non_trailer_accessory(title):
    return any(p.search(title or "") for p in NON_TRAILER_TITLE_PATTERNS)

LENGTH_PATTERN = re.compile(r"([\d.]+)\s*'")


def _to_int(text):
    if not text:
        return None
    cleaned = str(text).replace(",", "").strip()
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def extract_model_code(title):
    if not title:
        return None
    match = MODEL_CODE_PATTERN.match(title.strip() + " ")
    return match.group(1) if match else None


def extract_axle_info(specifications):
    """
    Returns (num_axles, axle_capacity_options_lb) parsed from the
    Specifications tab's AXLE field, e.g.:
      "(2) 8,000# Oil Bath w/Electric Brakes" -> (2, [8000])
      "(2) 5,200lb - 7,000 lb"                -> (2, [5200, 7000])
    Real evidence: every one of the 5 test entries' AXLE field starts with
    a "(N)" count and lists one or more weight values. Returns
    (None, []) if the field is missing or doesn't match -- never guesses
    a count or capacity that isn't actually in the text.
    """
    axle_text = (specifications or {}).get("AXLE", "")
    count_match = AXLE_COUNT_PATTERN.match(axle_text.strip())
    num_axles = int(count_match.group(1)) if count_match else None

    weights = [_to_int(w) for w in AXLE_WEIGHT_PATTERN.findall(axle_text)]
    weights = [w for w in weights if w]

    return num_axles, weights


def extract_deck_length_ft(additional_information):
    length_text = (additional_information or {}).get("Length")
    if not length_text:
        return None
    match = LENGTH_PATTERN.search(length_text)
    return float(match.group(1)) if match else None


def extract_gvwr_max_lb(additional_information, specifications):
    """
    Prefer Additional Information's clean "GVWR" value (no # suffix, e.g.
    "17,600") over Specifications' "G.V.W.R." (same number, "#"-suffixed)
    -- both present and numerically identical on every real entry that has
    either, so this is picking the cleaner-to-parse of two equally
    reliable real fields, not a fallback of last resort.
    """
    gvwr = (additional_information or {}).get("GVWR") or (specifications or {}).get("G.V.W.R.")
    return _to_int(gvwr)


def normalize_entry(raw):
    additional_information = raw.get("additional_information") or {}
    specifications = raw.get("specifications") or {}

    num_axles, axle_capacity_options_lb = extract_axle_info(specifications)

    return {
        "model_code": extract_model_code(raw.get("title")),
        "model_name": raw.get("title"),
        "source": additional_information.get("Trailer Brand"),
        "gvwr_max_lb": extract_gvwr_max_lb(additional_information, specifications),
        "num_axles": num_axles,
        "axle_capacity_options_lb": axle_capacity_options_lb,
        "deck_length_ft_max": extract_deck_length_ft(additional_information),
        "product_url": raw.get("product_url"),
        "standard_features": raw.get("standard_features") or [],
    }


def main():
    raw_entries = json.loads(RAW_PATH.read_text())

    trailer_entries = [r for r in raw_entries if not is_non_trailer_accessory(r.get("title"))]
    excluded_titles = [r.get("title") for r in raw_entries if is_non_trailer_accessory(r.get("title"))]

    normalized = [normalize_entry(r) for r in trailer_entries]

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(normalized, indent=2))

    print(f"Wrote {len(normalized)} normalized entries to {OUTPUT_PATH}")

    if excluded_titles:
        print(f"\n  Excluded {len(excluded_titles)} non-trailer accessory listing(s) (truck beds / "
              f"bin-only units -- no GVWR concept applies, out of scope for a trailer-fit matcher):")
        for name in excluded_titles:
            print(f"    - {name}")

    unverifiable = [
        n["model_name"] for n in normalized
        if n["gvwr_max_lb"] is None and not (n["num_axles"] and n["axle_capacity_options_lb"])
    ]
    if unverifiable:
        print(f"\n  WARNING: {len(unverifiable)} real trailer entries have neither a usable GVWR "
              f"nor an axle-based estimate -- matcher.py can't verify these at all:")
        for name in unverifiable:
            print(f"    - {name}")
    else:
        print("  Every remaining entry has at least one usable capacity figure.")


if __name__ == "__main__":
    main()