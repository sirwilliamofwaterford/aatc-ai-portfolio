"""
scrape_catalog.py -- Stage 1 of building data/catalog.json directly from
AATC's live website instead of the manufacturer PDFs. Each catalog entry
represents a real, currently-listed trailer with a real, working AATC
product URL -- this is what lets app.py eventually link straight to the
exact trailer being recommended, instead of the category/brand fallback
links it uses today.

STAGE 1 (this file): scrape every product page's THREE distinct content
tabs -- "Standard Features" (bulleted list), "Specifications" (axle/
frame/tire/suspension/coupler/hitch/finish table), and "Additional
information" (WooCommerce's native attributes tab: Trailer Brand,
Trailer Type, Length, GVWR, Load Capacity, Color, Tongue Type, Brake
Type) -- and save the RAW label/value pairs as-is to
data/catalog_raw.json. Deliberately not yet normalized into the
stated_gvwr / num_axles / axle_capacity_options_lb schema matcher.py
expects -- that mapping should be built from a look at real scraped
labels, not guessed blind. Run this once (with --limit for a quick test),
share the output, and the normalization step (Stage 2) gets built from
real evidence, same as the PDF pipeline was.

NOTE ON FIELD NAMES: an earlier version of this script only captured one
of the three tabs under a field called raw_specs. Confirmed via a real
page fetch (16OT-24 Big Tex deckover tilt) that what raw_specs was
actually capturing is the "Additional information" tab specifically --
Specifications is a separate tab with entirely different data (only
G.V.W.R. overlaps, under slightly different spelling). The output schema
below now has additional_information and specifications as distinct
fields, so any catalog_raw.json produced by the earlier version needs a
fresh re-run.

Deliberately NOT captured: price, store ID/stock number. This produces a
catalog of specs suitable for a publicly-deployable demo -- real
pricing/inventory identifiers stay out of it, same principle already
applied to the AATC links elsewhere in this app.

Usage:
    python scrape_catalog.py --limit 5     # quick test run, do this first
    python scrape_catalog.py               # full scrape of every listing

Not scheduled by this script itself -- run it manually anytime (that's the
on-demand path), and set up a weekly Windows Task Scheduler job pointing at
the exact same command for the recurring path. See the README section this
was delivered with for the schtasks command.
"""
import argparse
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import anthropic

load_dotenv()

SITEMAP_URL = "https://allamericantrailer.com/product-sitemap.xml"
CRAWL_DELAY_SECONDS = 5  # matches robots.txt's Crawl-delay for this site
OUTPUT_PATH = Path("data/catalog_raw.json")
USER_AGENT = "AATC-internal-catalog-tool/1.0"

client = anthropic.Anthropic()

# Fallback for pages that don't match the standard specs-table structure --
# e.g. custom/bundle listings rather than a single standard trailer page.
# Forced tool-use, same pattern as ask.py/ingest.py: never free-text guess.
EXTRACT_TOOL = {
    "name": "record_product_specs",
    "description": (
        "Record whatever trailer specs can be found on this product page. "
        "If this page isn't actually a single standard trailer listing with "
        "real spec data (e.g. it's a multi-item bundle, a custom-build page, "
        "or a page with no meaningful specs), set found_specs to false "
        "instead of guessing at values."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "found_specs": {
                "type": "boolean",
                "description": "False if this page doesn't have real, extractable single-trailer specs.",
            },
            "title": {"type": "string"},
            "raw_specs": {
                "type": "object",
                "description": "Whatever label/value spec pairs are present, using the page's own labels verbatim as keys (e.g. 'GVWR', 'Axles').",
            },
            "standard_features": {
                "type": "array",
                "items": {"type": "string"},
                "description": "The standard features / included items list, if present.",
            },
        },
        "required": ["found_specs"],
    },
}


def get_product_urls():
    """
    Fetch and parse the product sitemap; return the list of real product
    page URLs.

    Confirmed via a real test run: this sitemap mixes in the /shop/ listing
    page and, for every product, an <image:loc> tag nested inside
    <image:image> pointing at that product's photo -- a naive
    find_all("loc") grabs those right alongside the real page URLs, which
    then get requested and fed to the HTML parser as if they were pages
    (hence "characters could not be decoded" -- that's raw JPEG bytes being
    parsed as text). Scoping to each <url> element's own direct <loc> child
    (recursive=False) skips the nested image tag entirely, and the
    "/product/" filter drops /shop/ and anything else non-product as a
    second layer of defense.
    """
    resp = requests.get(SITEMAP_URL, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "xml")

    urls = []
    for url_el in soup.find_all("url"):
        loc_el = url_el.find("loc", recursive=False)
        if loc_el is None:
            continue
        loc = loc_el.text.strip()
        if "/product/" in loc:
            urls.append(loc)
    return urls


def _parse_label_value_table(table):
    """
    Shared row-parser for any label/value table (both the Additional
    Information tab and the Specifications tab render this way). Takes the
    first two cells of each row as label/value, accepting th or td for
    either position since Specifications' rows are plain manually-authored
    <td>/<td> pairs (confirmed via a real fetch) rather than the
    th-for-label/td-for-value convention WooCommerce's own attributes
    table uses.
    """
    if table is None:
        return None

    pairs = {}
    for row in table.select("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) >= 2:
            label = cells[0].get_text(" ", strip=True)
            value = cells[1].get_text(" ", strip=True)
            if label and value:
                pairs[label] = value

    return pairs or None


def parse_additional_information(soup):
    """
    The native WooCommerce "Additional information" tab -- Trailer Brand,
    Trailer Type, Length, Width, GVWR, Load Capacity, Color, Tongue Type,
    Brake Type. Free, fast, deterministic, no API call. Returns {label:
    value} if the table is found, else None so the caller can fall back.

    Confirmed via a real page fetch (16OT-24 Big Tex deckover tilt) that
    these selectors are correct for this site's actual markup -- this is
    the same table the earlier version of this script captured under the
    (misleading) name raw_specs.
    """
    table = (
        soup.select_one("table.woocommerce-product-attributes")
        or soup.select_one(".shop_attributes")
        or soup.select_one(".woocommerce-product-attributes")
    )
    return _parse_label_value_table(table)


def _find_tab_panel_by_nav_label(soup, label_pattern):
    """
    Tab nav links point at their panel via a #fragment href that matches
    the panel element's id (e.g. <a href="#tab-section_name_2">
    SPECIFICATIONS</a> -> <div id="tab-section_name_2">...</div>) -- this
    href/id pairing is how the tab-toggle JS itself works, so it holds
    regardless of which tab-manager plugin/theme generated the ids.
    Confirmed via a real fetch that this site's custom tabs use generic
    ids like tab-section_name_1/2 rather than id="tab-specifications", so
    guessing at the id directly wouldn't work -- following the nav link's
    own href does.
    """
    nav_link = soup.find("a", string=label_pattern, href=re.compile(r"^#"))
    if nav_link is None:
        return None
    return soup.find(id=nav_link["href"].lstrip("#"))


def parse_specifications(soup):
    """
    The separate "SPECIFICATIONS" tab -- axle, jack, tire, frame, wheel,
    finish, coupler, suspension, hitch type, G.A.W.R., etc. Confirmed via
    a real page fetch to be entirely distinct data from Additional
    Information (different labels; only G.V.W.R. overlaps, under
    slightly different spelling).

    Primary approach: follow the tab nav link's own #fragment href to its
    panel id (see _find_tab_panel_by_nav_label). Fallback: text-proximity
    from a heading that repeats the tab's own label inside its panel, the
    same approach already proven out for parse_features_list()'s
    "Standard Features" heading, in case a given page's tabs aren't built
    with plain #anchor links.

    IMPORTANT: this panel renders its specs as TWO side-by-side tables,
    not one -- confirmed by comparing a real scrape (11 fields: AXLE
    through FENDERS) against a separate real fetch of the exact same page
    that saw 20 fields, with the missing 9 (GVWR, UPRIGHTS, ELEC. PLUG,
    HITCH TYPE, SUSPENSION, CROSSMEMBERS, FINISH (Prep), SAFETY CHAINS,
    G.A.W.R.) picking up right where the scrape's 11 left off, same
    order. That's a two-table split, not a scraping error on individual
    rows -- so this pulls every <table> inside the panel and merges them,
    rather than just the first.
    """
    label_pattern = re.compile(r"^\s*specifications\s*$", re.I)
    panel = _find_tab_panel_by_nav_label(soup, label_pattern)
    tables = panel.find_all("table") if panel else []

    if not tables:
        heading = soup.find(string=label_pattern)
        if heading:
            container = heading.find_parent()
            if container:
                next_table = container.find_next("table")
                if next_table:
                    tables = [next_table]

    merged = {}
    for table in tables:
        parsed = _parse_label_value_table(table)
        if parsed:
            merged.update(parsed)

    return merged or None


def parse_features_list(soup):
    """Same caveat as parse_specs_table -- verify against the real page structure."""
    heading = soup.find(string=re.compile(r"Standard Features", re.I))
    if not heading:
        return []
    container = heading.find_parent()
    if container:
        container = container.find_next(["ul", "ol"])
    if not container:
        return []
    return [li.get_text(" ", strip=True) for li in container.find_all("li") if li.get_text(strip=True)]


def get_title(soup):
    h1 = soup.select_one("h1.product_title") or soup.find("h1")
    return h1.get_text(strip=True) if h1 else None


def extract_with_claude(page_text, url):
    """Fallback for pages the structured parser above couldn't handle."""
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1500,
        tools=[EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "record_product_specs"},
        messages=[{
            "role": "user",
            "content": (
                f"Extract trailer specs from this product page (URL: {url}). "
                f"If it isn't a single standard trailer listing with real "
                f"spec data, set found_specs to false rather than guessing."
                f"\n\n{page_text[:6000]}"
            ),
        }],
    )
    tool_use = next(b for b in response.content if b.type == "tool_use")
    return tool_use.input


def scrape_product(url):
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "html.parser")

    additional_information = parse_additional_information(soup)
    specifications = parse_specifications(soup)
    standard_features = parse_features_list(soup)

    if additional_information or specifications:
        # At least one of the two table-based tabs parsed structurally --
        # no API call spent on this page. If only one came through, that's
        # visible in the output (the other field is just {}) rather than
        # silently escalating a mostly-successful page to the paid
        # fallback -- worth checking on a real run, but not worth $ for.
        return {
            "product_url": url,
            "title": get_title(soup),
            "additional_information": additional_information or {},
            "specifications": specifications or {},
            "standard_features": standard_features,
            "extraction_method": "structured",
        }

    # Neither table-based tab was found -- fall back to Claude for this
    # one page. Custom/bundle listings (like the multi-item Custom
    # Trailers page) don't necessarily have this clean three-tab
    # structure, so the fallback tool doesn't try to split
    # specifications from additional_information -- everything it finds
    # lands in additional_information, same as before.
    page_text = soup.get_text(" ", strip=True)
    extracted = extract_with_claude(page_text, url)
    if not extracted.get("found_specs"):
        return None
    return {
        "product_url": url,
        "title": extracted.get("title"),
        "additional_information": extracted.get("raw_specs") or {},
        "specifications": {},
        "standard_features": extracted.get("standard_features") or [],
        "extraction_method": "claude_fallback",
    }


def main():
    parser = argparse.ArgumentParser(description="Scrape AATC's live site into data/catalog_raw.json (Stage 1, raw/unnormalized)")
    parser.add_argument("--limit", type=int, default=None, help="Only scrape the first N products -- use this for a test run first")
    args = parser.parse_args()

    print("Fetching product sitemap...", flush=True)
    urls = get_product_urls()
    if args.limit:
        urls = urls[: args.limit]
    print(f"Found {len(urls)} product URL(s) to scrape.", flush=True)

    catalog = []
    structured_count = 0
    fallback_count = 0
    skipped_count = 0

    for i, url in enumerate(urls, 1):
        print(f"  [{i}/{len(urls)}] {url}", flush=True)
        try:
            record = scrape_product(url)
            if record:
                catalog.append(record)
                if record["extraction_method"] == "structured":
                    structured_count += 1
                else:
                    fallback_count += 1
            else:
                skipped_count += 1
                print("    skipped (not a standard product listing)", flush=True)
        except Exception as e:
            skipped_count += 1
            print(f"    ERROR: {e}", flush=True)
        time.sleep(CRAWL_DELAY_SECONDS)

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(catalog, indent=2))

    print(f"\nWrote {len(catalog)} entries to {OUTPUT_PATH}", flush=True)
    print(f"  {structured_count} parsed via the free structured-table path", flush=True)
    print(f"  {fallback_count} needed the Claude fallback", flush=True)
    print(f"  {skipped_count} skipped (errors or non-standard pages)", flush=True)
    if urls and structured_count == 0 and fallback_count > 0:
        print(
            "\n  NOTE: every page fell back to Claude -- the structured-table "
            "selectors in parse_specs_table() likely need adjusting for this "
            "site's actual markup. Share a few entries from the output and "
            "I'll fix the selectors.",
            flush=True,
        )


if __name__ == "__main__":
    main()