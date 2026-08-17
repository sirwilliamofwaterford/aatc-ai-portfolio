"""
match_chat.py -- conversational trailer-matching layer. Unlike ask.py (which
answers each question independently), this holds the full conversation and
lets Claude choose between asking a clarifying follow-up question and
calling the find_trailer_match tool once it has enough information. The
actual matching math is never done by Claude -- matcher.py runs the real,
deterministic filtering and safety checks; Claude's job is gathering the
right inputs and explaining the results in plain language.
"""
import json

from dotenv import load_dotenv
import anthropic

from matcher import find_trailer_matches, annotate_tow_compatibility, TOW_VEHICLES

load_dotenv()

client = anthropic.Anthropic()

TOW_VEHICLE_CLASS_NAMES = [v["class_name"] for v in TOW_VEHICLES]

# Hard cap on tool-call iterations within a single match_chat() call. This is
# a public demo billed against a real API key -- normal usage resolves in 1-2
# iterations (ask a follow-up and stop, or call the tool once and explain the
# result), so this cap only ever matters as a backstop against a pathological
# case where the model keeps calling the tool instead of answering, which
# would otherwise burn an unbounded number of API calls on one user message.
MAX_TOOL_ITERATIONS = 6

FALLBACK_MESSAGE = (
    "I'm having trouble narrowing this down after a few tries -- let's reset. "
    "Can you tell me in one message: what you're hauling, roughly how much it "
    "weighs, and what you're towing with?"
)

FIND_MATCH_TOOL = {
    "name": "find_trailer_match",
    "description": (
        "Search the trailer catalog and, if a tow vehicle is known, check "
        "tow-vehicle compatibility for a specific load. Only call this once "
        "you actually know the load's weight from the conversation -- never "
        "estimate or guess a weight. If you don't have enough information "
        "yet, respond in plain text asking the user instead of calling this."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "load_weight_lb": {
                "type": "number",
                "description": "The weight of what's being hauled, in lbs. Required -- never estimate this yourself.",
            },
            "load_description": {
                "type": "string",
                "description": "Brief description of what's being hauled, e.g. 'mini excavator'.",
            },
            "suitable_categories": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["dump", "equipment", "carhauler", "utility", "pipe", "cargo_enclosed"],
                },
                "description": (
                    "Which trailer categories are actually usable for this load, based on your "
                    "own judgment of the load type. E.g. heavy equipment like an excavator needs "
                    "'dump', 'equipment', or 'carhauler' style trailers with a flat deck or ramps "
                    "-- NOT 'pipe' or 'cargo_enclosed'. Omit or leave empty to consider all types."
                ),
            },
            "load_length_ft": {
                "type": "number",
                "description": "Length of the load in feet, if known and relevant. Omit if not stated.",
            },
            "tow_vehicle_class": {
                "type": "string",
                "enum": TOW_VEHICLE_CLASS_NAMES,
                "description": (
                    "The tow vehicle's class, matched to the closest option in this list, if the "
                    "user has described their tow vehicle. Omit if not yet known -- it's fine to "
                    "run the trailer match without it, but mention that adding their tow vehicle "
                    "would let you verify the whole rig is safe, not just the trailer."
                ),
            },
        },
        "required": ["load_weight_lb"],
    },
}

SYSTEM_PROMPT = f"""You help customers and staff at a trailer dealership find a trailer that can safely handle a specific load, optionally checked against their tow vehicle. You have access to a real catalog and real safety math through the find_trailer_match tool -- never invent capacities, weights, or a "yes it'll work" answer yourself.

Ask short, specific follow-up questions when you're missing information you'd need to call the tool confidently -- especially the load's weight, which is required. Don't ask for everything up front; ask for what's actually missing, one or two things at a time. Once you have enough to call find_trailer_match, call it. After you get results, explain them in plain language, mention which trailers are top picks and why, and if a tow vehicle was checked, be explicit about which combinations are actually safe. If nothing in the catalog fits, say so honestly rather than stretching a bad match.

Known tow vehicle classes you can match a user's description to: {', '.join(TOW_VEHICLE_CLASS_NAMES)}."""


def run_match_tool(tool_input):
    load_weight_lb = tool_input["load_weight_lb"]
    categories = set(tool_input["suitable_categories"]) if tool_input.get("suitable_categories") else None
    load_length_ft = tool_input.get("load_length_ft")

    matches = find_trailer_matches(
        load_weight_lb,
        load_length_ft=load_length_ft,
        categories=categories,
    )

    tow_vehicle_class = tool_input.get("tow_vehicle_class")
    if tow_vehicle_class:
        matches = annotate_tow_compatibility(matches, tow_vehicle_class)

    return {
        "load_weight_lb": load_weight_lb,
        "tow_vehicle_class": tow_vehicle_class,
        "match_count": len(matches),
        "matches": matches[:8],
    }


def match_chat(messages):
    """
    messages: list of {"role": "user"|"assistant", "content": ...} dicts,
    the full conversation so far including the user's latest message.
    Returns (reply_text, last_result) -- last_result is the structured
    find_trailer_match output from the most recent tool call this turn, or
    None if no tool was called (e.g. Claude just asked a follow-up question).
    The caller is responsible for appending both the user's message and the
    reply to their own history.

    Bounded to MAX_TOOL_ITERATIONS tool-call rounds -- see the constant's
    comment above. If that cap is ever hit without a plain-text reply, this
    returns a fallback message asking the user to restate things, rather
    than looping indefinitely.
    """
    working_messages = list(messages)
    last_result = None

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            tools=[FIND_MATCH_TOOL],
            tool_choice={"type": "auto"},
            messages=working_messages,
        )

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if not tool_use_blocks:
            text_block = next((b for b in response.content if b.type == "text"), None)
            return (text_block.text if text_block else "", last_result)

        working_messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in tool_use_blocks:
            result = run_match_tool(block.input)
            last_result = result
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })
        working_messages.append({"role": "user", "content": tool_results})

    # Exhausted MAX_TOOL_ITERATIONS without ever getting a plain-text reply --
    # stop here instead of looping indefinitely.
    return (FALLBACK_MESSAGE, last_result)


if __name__ == "__main__":
    history = []
    print("Trailer matcher chat. Type 'quit' to exit.\n")
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break
        history.append({"role": "user", "content": user_input})
        reply, _ = match_chat(history)
        history.append({"role": "assistant", "content": reply})
        print(f"\nAssistant: {reply}\n")