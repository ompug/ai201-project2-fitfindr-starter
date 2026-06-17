"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import (
    compare_price,
    create_fit_card,
    get_trend_signal,
    search_listings,
    suggest_outfit,
    update_style_profile,
)


PROFILE_PATH = ".fitfindr_profile.json"


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "style_profile": {},         # remembered preferences across sessions
        "profile_warning": None,      # set if profile storage fails
        "search_results": [],        # list of matching listing dicts
        "retry_note": None,           # explanation if fallback search is used
        "selected_item": None,       # top result, passed into suggest_outfit
        "price_assessment": None,     # stretch: comparable-listing price check
        "trend_signal": None,         # stretch: trend signal for styling
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


def _parse_query(query: str) -> dict:
    """Extract search parameters from a natural-language query."""
    text = (query or "").strip()
    working = text
    max_price = None
    size = None

    price_match = re.search(
        r"(?:under|below|less than|up to|budget(?: of)?|for)\s*\$?\s*(\d+(?:\.\d+)?)",
        working,
        flags=re.IGNORECASE,
    )
    if not price_match:
        price_match = re.search(r"\$(\d+(?:\.\d+)?)", working)
    if price_match:
        max_price = float(price_match.group(1))
        working = working[:price_match.start()] + " " + working[price_match.end():]

    size_match = re.search(
        r"(?:size|sz|in size)\s*(us\s*)?([a-z]{1,3}|\d+(?:\.\d+)?|w\d{2}(?:\s*l\d{2})?)",
        working,
        flags=re.IGNORECASE,
    )
    if not size_match:
        size_match = re.search(r"\b(us\s*\d+(?:\.\d+)?|w\d{2}(?:\s*l\d{2})?)\b", working, flags=re.IGNORECASE)
    if size_match:
        size = size_match.group(0)
        size = re.sub(r"^(size|sz|in size)\s*", "", size, flags=re.IGNORECASE).strip()
        working = working[:size_match.start()] + " " + working[size_match.end():]

    cleanup_patterns = [
        r"\bi'?m\b", r"\blooking for\b", r"\bcan you find\b", r"\bfind me\b",
        r"\bwhat'?s out there\b", r"\bhow would i style it\b", r"\bhow do i style it\b",
        r"\bi mostly wear\b", r"\bplease\b",
    ]
    description = working.lower()
    for pattern in cleanup_patterns:
        description = re.sub(pattern, " ", description, flags=re.IGNORECASE)
    description = re.sub(r"[^a-z0-9\s'/.-]", " ", description)
    description = re.sub(r"\s+", " ", description).strip()
    if not description:
        description = text

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }


def _has_explicit_style(query: str, remembered_tags: list[str]) -> bool:
    query_l = (query or "").lower()
    return any(tag.lower() in query_l for tag in remembered_tags)


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    session = _new_session(query, wardrobe)

    parsed = _parse_query(query)
    session["parsed"] = parsed

    profile = update_style_profile(query, wardrobe, PROFILE_PATH)
    session["style_profile"] = profile
    session["profile_warning"] = profile.get("warning")

    remembered_tags = profile.get("preferred_tags", [])
    if remembered_tags and not _has_explicit_style(query, remembered_tags):
        remembered = " ".join(remembered_tags[:3])
        parsed["description"] = f"{parsed['description']} {remembered}".strip()
        session["memory_note"] = f"Used remembered style preferences: {', '.join(remembered_tags[:3])}."
    else:
        session["memory_note"] = None

    results = search_listings(
        parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )
    session["search_results"] = results

    if not results:
        retry_steps = []
        retry_size = parsed["size"]
        retry_price = parsed["max_price"]

        if retry_size is not None:
            retry_size = None
            retry_steps.append("removed the size filter")
            results = search_listings(parsed["description"], size=retry_size, max_price=retry_price)

        if not results and retry_price is not None:
            retry_price = round(retry_price * 1.25, 2)
            retry_steps.append(f"raised the budget to ${retry_price:.2f}")
            results = search_listings(parsed["description"], size=retry_size, max_price=retry_price)

        if results:
            session["retry_note"] = "No exact matches, so FitFindr retried and " + " and ".join(retry_steps) + "."
            session["search_results"] = results
            session["parsed"]["retry_size"] = retry_size
            session["parsed"]["retry_max_price"] = retry_price
        else:
            tried = " and ".join(retry_steps) if retry_steps else "broader matching"
            session["retry_note"] = f"FitFindr tried {tried}, but still found no matches."
            session["error"] = (
                "I couldn't find matches for that exact search. Try a broader item name, "
                "removing the size, or raising the budget."
            )
            return session

    selected_item = session["search_results"][0]
    session["selected_item"] = selected_item

    price_assessment = compare_price(selected_item)
    session["price_assessment"] = price_assessment

    trend_signal = get_trend_signal(selected_item, parsed.get("size"))
    session["trend_signal"] = trend_signal
    selected_item["_trend_signal"] = trend_signal
    selected_item["_price_assessment"] = price_assessment

    outfit = suggest_outfit(selected_item, wardrobe)
    session["outfit_suggestion"] = outfit
    if not outfit or not outfit.strip():
        session["error"] = (
            "I found a listing, but could not create an outfit suggestion. "
            "Try again with a wardrobe that has at least one item or a broader search."
        )
        return session

    session["fit_card"] = create_fit_card(outfit, selected_item)
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
