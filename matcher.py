"""
matcher.py — deterministic trailer-matching logic. Given a load, filters
data/catalog.json for trailers that can actually handle it, and can check
tow-vehicle compatibility against data/tow_vehicles.json. No LLM involved in
the filtering itself -- this is real math against real (or honestly
estimated) numbers, not a language model's guess.
"""
import json
from pathlib import Path

CATALOG_PATH = Path("data/catalog.json")
CATALOG = json.loads(CATALOG_PATH.read_text()) if CATALOG_PATH.exists() else []

TOW_VEHICLES_PATH = Path("data/tow_vehicles.json")
TOW_VEHICLES = json.loads(TOW_VEHICLES_PATH.read_text()) if TOW_VEHICLES_PATH.exists() else []

# Rough category inference from model name -- good enough to filter out
# obviously wrong-shaped trailers (e.g. a pipe trailer for an excavator),
# not a precise engineering classification.
CATEGORY_RULES = [
    ("dump", ["dump"]),
    ("equipment", ["equipment", "deckover", "tilt", "scissor lift", "low profile", "lowboy", "multideck", "flatdeck"]),
    ("carhauler", ["carhauler", "car hauler"]),
    ("utility", ["utility", "buggy hauler"]),
    ("pipe", ["pipetop", "pipe trailer"]),
    ("cargo_enclosed", ["cargo"]),
]


def infer_category(model_name):
    name = (model_name or "").lower()
    for category, keywords in CATEGORY_RULES:
        if any(kw in name for kw in keywords):
            return category
    return "unknown"


def get_trailer_capacity(model):
    """
    Returns (capacity_lb, source):
      'stated_gvwr'          -- a real GVWR value from the source document (most reliable)
      'estimated_from_axles' -- num_axles x best axle-capacity option, a common
                                industry approximation -- NOT the same as true GVWR,
                                since it ignores the trailer's own empty weight
      (None, None)           -- not enough data to verify this model at all
    """
    gvwr_max = model.get("gvwr_max_lb")
    if gvwr_max:
        return gvwr_max, "stated_gvwr"

    num_axles = model.get("num_axles")
    axle_options = model.get("axle_capacity_options_lb") or []
    if num_axles and axle_options:
        return num_axles * max(axle_options), "estimated_from_axles"

    return None, None


def find_trailer_matches(load_weight_lb, load_length_ft=None, categories=None, catalog=None):
    """
    categories: optional iterable of category strings (see CATEGORY_RULES) to
    restrict results to -- e.g. {"dump", "equipment", "carhauler"} for heavy
    equipment. None means no category filtering (all types considered).
    """
    catalog = catalog if catalog is not None else CATALOG
    matches = []

    for model in catalog:
        category = infer_category(model.get("model_name"))
        if categories is not None and category not in categories:
            continue

        capacity_lb, source = get_trailer_capacity(model)
        if capacity_lb is None or capacity_lb < load_weight_lb:
            continue

        if load_length_ft is not None:
            max_len = model.get("deck_length_ft_max")
            if max_len is not None and max_len < load_length_ft:
                continue

        matches.append({
            "model_code": model.get("model_code"),
            "model_name": model.get("model_name"),
            "category": category,
            "source": model.get("source"),
            "capacity_lb": capacity_lb,
            "capacity_source": source,
            "margin_lb": capacity_lb - load_weight_lb,
            "deck_length_ft_max": model.get("deck_length_ft_max"),
            # Real per-listing AATC product page, set directly from the live
            # scrape (scrape_catalog.py -> normalize.py). Lets app.py link
            # straight to the exact trailer being recommended instead of a
            # same-category fallback page.
            "product_url": model.get("product_url"),
        })

    matches.sort(key=lambda m: m["margin_lb"])
    return matches


def get_tow_vehicle(class_name):
    for v in TOW_VEHICLES:
        if v["class_name"] == class_name:
            return v
    return None


def check_tow_compatibility(trailer_capacity_lb, tow_vehicle):
    """
    Checks whether a tow vehicle can safely handle a trailer at its full
    rated capacity (GVWR) -- the standard conservative assumption, since a
    trailer should be safe to tow at any legal load, not just today's load.
    Tongue weight is estimated as 10-15% of trailer gross weight (a standard
    rule of thumb for conventional ball-hitch setups), checked against the
    tow vehicle's payload capacity. Every check reports its margin, not just
    pass/fail -- a check that barely passes deserves to be flagged as such.
    """
    tongue_min = trailer_capacity_lb * 0.10
    tongue_max = trailer_capacity_lb * 0.15
    required_gcwr = tow_vehicle["gvwr_lb"] + trailer_capacity_lb

    tow_rating_margin = tow_vehicle["max_tow_rating_lb"] - trailer_capacity_lb
    gcwr_margin = tow_vehicle["gcwr_lb"] - required_gcwr
    tongue_margin = tow_vehicle["payload_lb"] - tongue_max

    return {
        "tow_vehicle_class": tow_vehicle["class_name"],
        "trailer_capacity_lb": trailer_capacity_lb,
        "tow_rating_ok": tow_rating_margin >= 0,
        "tow_rating_lb": tow_vehicle["max_tow_rating_lb"],
        "tow_rating_margin_lb": tow_rating_margin,
        "gcwr_ok": gcwr_margin >= 0,
        "gcwr_lb": tow_vehicle["gcwr_lb"],
        "required_gcwr_lb": required_gcwr,
        "gcwr_margin_lb": gcwr_margin,
        "tongue_weight_range_lb": (round(tongue_min), round(tongue_max)),
        "tongue_ok": tongue_margin >= 0,
        "payload_lb": tow_vehicle["payload_lb"],
        "tongue_margin_lb": tongue_margin,
        "overall_ok": tow_rating_margin >= 0 and gcwr_margin >= 0 and tongue_margin >= 0,
    }


def annotate_tow_compatibility(matches, tow_vehicle_class):
    tow_vehicle = get_tow_vehicle(tow_vehicle_class)
    if tow_vehicle is None:
        raise ValueError(f"Unknown tow vehicle class: {tow_vehicle_class!r}")
    for m in matches:
        m["tow_check"] = check_tow_compatibility(m["capacity_lb"], tow_vehicle)
    return matches


if __name__ == "__main__":
    import sys
    load = float(sys.argv[1]) if len(sys.argv) > 1 else 8000
    categories = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None

    results = find_trailer_matches(load, categories=categories)
    print(f"Trailers that can handle a {load:g} lb load" + (f" (categories: {categories})" if categories else "") + ":\n")
    for m in results[:10]:
        print(
            f"  {m['model_code']} ({m['model_name']}, {m['category']}) -- capacity {m['capacity_lb']:g} lb "
            f"[{m['capacity_source']}], margin +{m['margin_lb']:g} lb, source: {m['source']}"
        )
    print(f"\n{len(results)} total matches.")

    if results:
        top = results[0]
        print(f"\nTow-vehicle compatibility for the top match, {top['model_code']} (rated capacity {top['capacity_lb']:g} lb):\n")
        for vehicle in TOW_VEHICLES:
            check = check_tow_compatibility(top["capacity_lb"], vehicle)
            verdict = "OK" if check["overall_ok"] else "NOT SAFE"
            print(
                f"  {vehicle['class_name']}: {verdict} "
                f"(tow rating {'OK' if check['tow_rating_ok'] else 'FAIL'} margin {check['tow_rating_margin_lb']:+.0f}, "
                f"GCWR {'OK' if check['gcwr_ok'] else 'FAIL'} margin {check['gcwr_margin_lb']:+.0f}, "
                f"tongue weight {'OK' if check['tongue_ok'] else 'FAIL'} margin {check['tongue_margin_lb']:+.0f})"
            )