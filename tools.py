"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import json
import re
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "for", "from", "how", "i",
    "in", "is", "it", "like", "looking", "mostly", "of", "on", "or", "the",
    "this", "to", "under", "want", "wear", "what", "whats", "with", "would",
}

STYLE_KEYWORDS = {
    "90s", "2000s", "athletic", "baggy", "basics", "boho", "classic", "cozy",
    "cottagecore", "crochet", "dark academia", "denim", "earth tones",
    "feminine", "glam", "goth", "graphic", "graphic tee", "grunge",
    "layering", "minimal", "oversized", "platform", "preppy", "streetwear",
    "vintage", "western", "workwear", "y2k",
}

TREND_SIGNALS = {
    "graphic tee": {
        "trend": "lived-in graphic tees with loose denim",
        "source": "Curated resale tag scan: Depop/Poshmark-style tags in the mock dataset",
        "styling_note": "Lean into a relaxed grunge-streetwear read with baggy jeans, chunky shoes, and one intentional layer.",
    },
    "band tee": {
        "trend": "faded band tees styled as everyday statement basics",
        "source": "Curated resale tag scan: Depop/Poshmark-style tags in the mock dataset",
        "styling_note": "Keep the tee central and add worn denim, boots or chunky sneakers, and minimal accessories.",
    },
    "y2k": {
        "trend": "Y2K proportions: fitted tops, low-rise or wide-leg bottoms, and playful accessories",
        "source": "Curated public-fashion tag map modeled from common TikTok/Depop resale language",
        "styling_note": "Balance one fitted or shiny piece with a relaxed layer so the look feels current instead of costume-y.",
    },
    "cottagecore": {
        "trend": "soft natural textures with practical everyday styling",
        "source": "Curated public-fashion tag map modeled from common Pinterest/Depop styling language",
        "styling_note": "Ground delicate textures with denim, leather, or simple sneakers for a wearable thrifted look.",
    },
    "90s": {
        "trend": "90s sporty layers and boxy silhouettes",
        "source": "Curated resale tag scan: 90s, athletic, and streetwear tags in the mock dataset",
        "styling_note": "Use a boxy layer, straight-leg denim, and simple sneakers to keep the proportions easy.",
    },
    "minimal": {
        "trend": "quiet secondhand basics in clean color stories",
        "source": "Curated public-fashion tag map modeled from capsule-wardrobe resale language",
        "styling_note": "Keep the palette restrained and add texture through denim, linen, leather, or knitwear.",
    },
    "grunge": {
        "trend": "soft grunge with practical layers",
        "source": "Curated resale tag scan: grunge, denim, leather, and boot tags in the mock dataset",
        "styling_note": "Pair darker pieces with denim, boots, and one softened element so it still feels wearable.",
    },
    "streetwear": {
        "trend": "baggy streetwear proportions with vintage basics",
        "source": "Curated resale tag scan: streetwear, baggy, sneaker, and vintage tags in the mock dataset",
        "styling_note": "Prioritize relaxed silhouettes, a clean sneaker or boot, and one small accessory to finish the fit.",
    },
}


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _call_llm(prompt: str, temperature: float = 0.7, max_tokens: int = 260) -> str | None:
    """Call Groq if configured; return None so tools can use local fallbacks."""
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are FitFindr, a concise secondhand styling assistant. "
                        "Give specific, wearable styling advice without sounding like an ad."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = response.choices[0].message.content.strip()
        return text or None
    except Exception:
        return None


def _tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9']+", (text or "").lower())
        if token not in STOP_WORDS and len(token) > 1
    ]


def _listing_text(listing: dict) -> str:
    values = [
        listing.get("title", ""),
        listing.get("description", ""),
        listing.get("category", ""),
        listing.get("size", ""),
        listing.get("condition", ""),
        listing.get("brand") or "",
        listing.get("platform", ""),
        " ".join(listing.get("style_tags", [])),
        " ".join(listing.get("colors", [])),
    ]
    return " ".join(values).lower()


def _size_matches(listing_size: str, requested_size: str | None) -> bool:
    if not requested_size:
        return True
    requested = requested_size.strip().lower()
    listed = (listing_size or "").strip().lower()
    if not requested:
        return True
    if requested == listed:
        return True
    if requested.startswith("us "):
        requested = requested.replace("us ", "", 1).strip()
    if requested.startswith("w") and requested in listed:
        return True
    if requested.isdigit():
        return re.search(rf"\b(us\s*)?{re.escape(requested)}(\.5)?\b", listed) is not None
    if len(requested) <= 3:
        return re.search(rf"(^|[^a-z]){re.escape(requested)}([^a-z]|$)", listed) is not None
    return requested in listed


def _format_item(item: dict) -> str:
    brand = item.get("brand") or "unbranded"
    tags = ", ".join(item.get("style_tags", []))
    colors = ", ".join(item.get("colors", []))
    return (
        f"{item.get('title')} ({item.get('category')}, {item.get('size')}, "
        f"{item.get('condition')} condition, ${item.get('price'):.2f}, "
        f"{brand}, {item.get('platform')}, colors: {colors}, tags: {tags})"
    )


def _wardrobe_by_category(wardrobe: dict, category: str) -> list[dict]:
    return [
        item for item in wardrobe.get("items", [])
        if item.get("category") == category
    ]


def _pick_name(items: list[dict], fallback: str) -> str:
    return items[0]["name"] if items else fallback


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()
    query_tokens = _tokenize(description)
    if not query_tokens:
        return []

    phrase = (description or "").lower().strip()
    scored: list[tuple[int, float, dict]] = []

    for listing in listings:
        price = float(listing.get("price", 0))
        if max_price is not None and price > float(max_price):
            continue
        if not _size_matches(listing.get("size", ""), size):
            continue

        haystack = _listing_text(listing)
        haystack_tokens = Counter(_tokenize(haystack))
        score = 0
        for token in query_tokens:
            if token in haystack_tokens:
                score += 2 + min(haystack_tokens[token], 3)

        for tag in listing.get("style_tags", []):
            tag_l = tag.lower()
            if tag_l in phrase:
                score += 5
            elif any(token in tag_l for token in query_tokens):
                score += 2

        title = listing.get("title", "").lower()
        if phrase and phrase in haystack:
            score += 6
        if any(token in title for token in query_tokens):
            score += 2
        if score > 0:
            scored.append((score, -price, listing))

    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [listing for _, _, listing in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    if not new_item:
        return "I need a selected listing before I can suggest an outfit."

    items = wardrobe.get("items", []) if isinstance(wardrobe, dict) else []
    trend = new_item.get("_trend_signal") or {}
    trend_note = trend.get("styling_note", "")

    if items:
        wardrobe_lines = "\n".join(
            "- "
            + item.get("name", "Unnamed item")
            + f" ({item.get('category', 'unknown')}; colors: {', '.join(item.get('colors', []))}; "
            + f"tags: {', '.join(item.get('style_tags', []))})"
            for item in items
        )
        prompt = (
            f"New thrift find: {_format_item(new_item)}\n"
            f"Trend signal to use if relevant: {trend_note or 'none'}\n"
            f"User wardrobe:\n{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfits using the new item and specific named wardrobe pieces. "
            "Mention why the pieces work together. Keep it under 140 words."
        )
        llm_text = _call_llm(prompt, temperature=0.65)
        if llm_text:
            return llm_text

        bottoms = _pick_name(_wardrobe_by_category(wardrobe, "bottoms"), "relaxed straight-leg denim")
        shoes = _pick_name(_wardrobe_by_category(wardrobe, "shoes"), "simple sneakers or broken-in boots")
        outerwear = _pick_name(_wardrobe_by_category(wardrobe, "outerwear"), "a light vintage jacket")
        accessory = _pick_name(_wardrobe_by_category(wardrobe, "accessories"), "a small everyday bag or belt")
        return (
            f"Build the look around {new_item['title']} with {bottoms}, {shoes}, "
            f"and {outerwear}. Finish with {accessory}. "
            f"{trend_note or 'The mix keeps the thrifted piece wearable while still feeling intentional.'}"
        )

    prompt = (
        f"New thrift find: {_format_item(new_item)}\n"
        f"Trend signal to use if relevant: {trend_note or 'none'}\n"
        "The user has no saved wardrobe yet. Give general styling advice: what categories, colors, "
        "and silhouettes should they pair with this item? Keep it under 120 words."
    )
    llm_text = _call_llm(prompt, temperature=0.65)
    if llm_text:
        return llm_text

    colors = ", ".join(new_item.get("colors", [])) or "its main color"
    tags = ", ".join(new_item.get("style_tags", [])[:3]) or "secondhand"
    return (
        f"No saved wardrobe yet, so style {new_item['title']} with pieces that echo its {colors} palette "
        f"and {tags} mood. Try relaxed denim or a clean trouser, a simple base layer, and shoes with enough "
        f"weight to balance the silhouette. {trend_note or 'Keep one piece understated so the thrift find stays central.'}"
    )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    if not outfit or not outfit.strip():
        return (
            "I need an outfit suggestion before I can make a fit card. "
            "Try running the outfit step again with a selected listing."
        )
    if not new_item:
        return "I need the selected thrift listing before I can make a fit card."

    prompt = (
        f"Selected item: {_format_item(new_item)}\n"
        f"Outfit suggestion: {outfit}\n\n"
        "Write a casual 2-4 sentence fit-card caption for an OOTD post. Mention the item title, "
        "price, and platform naturally once each. Make it specific, stylish, and not salesy."
    )
    llm_text = _call_llm(prompt, temperature=0.95, max_tokens=180)
    if llm_text:
        return llm_text

    price = f"${float(new_item.get('price', 0)):.0f}"
    return (
        f"Found {new_item.get('title')} on {new_item.get('platform')} for {price}, and it instantly pulled the whole fit together. "
        f"{outfit.strip()} "
        "Very thrifted, very wearable, and exactly the kind of piece that makes an old closet feel new again."
    )


# ── Stretch Tool: price comparison ────────────────────────────────────────────

def compare_price(item: dict, listings: list[dict] | None = None) -> dict:
    """
    Estimate whether an item is priced well compared with similar mock listings.

    Args:
        item: A listing dict to assess.
        listings: Optional list of listing dicts. If omitted, loads all listings.

    Returns:
        A dict with assessment, item_price, average_comparable_price,
        comparable_count, and reasoning.
    """
    if not item:
        return {
            "assessment": "fair price",
            "item_price": 0.0,
            "average_comparable_price": 0.0,
            "comparable_count": 0,
            "reasoning": "No item was provided, so FitFindr cannot compare prices confidently.",
        }

    all_listings = listings if listings is not None else load_listings()
    item_tags = set(item.get("style_tags", []))
    item_id = item.get("id")

    comparables = [
        listing for listing in all_listings
        if listing.get("id") != item_id
        and listing.get("category") == item.get("category")
        and (item_tags & set(listing.get("style_tags", [])))
    ]

    basis = "same category and overlapping style tags"
    if len(comparables) < 2:
        comparables = [
            listing for listing in all_listings
            if listing.get("id") != item_id
            and listing.get("category") == item.get("category")
        ]
        basis = "same category because there were too few close style matches"

    if not comparables:
        return {
            "assessment": "fair price",
            "item_price": float(item.get("price", 0)),
            "average_comparable_price": float(item.get("price", 0)),
            "comparable_count": 0,
            "reasoning": "The dataset has no useful comparable listings, so this is treated as a fair price by default.",
        }

    avg_price = sum(float(listing.get("price", 0)) for listing in comparables) / len(comparables)
    item_price = float(item.get("price", 0))
    if item_price <= avg_price * 0.85:
        assessment = "good deal"
    elif item_price >= avg_price * 1.15:
        assessment = "pricey"
    else:
        assessment = "fair price"

    sample_titles = ", ".join(listing["title"] for listing in comparables[:3])
    return {
        "assessment": assessment,
        "item_price": round(item_price, 2),
        "average_comparable_price": round(avg_price, 2),
        "comparable_count": len(comparables),
        "reasoning": (
            f"Compared against {len(comparables)} listings with {basis}. "
            f"Average comparable price is ${avg_price:.2f}; examples include {sample_titles}."
        ),
    }


# ── Stretch Tool: trend awareness ─────────────────────────────────────────────

def get_trend_signal(item: dict, size: str | None = None) -> dict:
    """
    Return a trend signal that can influence the outfit suggestion.

    Args:
        item: A selected listing dict.
        size: Optional parsed user size.

    Returns:
        A dict with trend, source, matched_tags, and styling_note.
    """
    tags = [tag.lower() for tag in item.get("style_tags", [])] if item else []
    title = (item.get("title", "") if item else "").lower()
    description = (item.get("description", "") if item else "").lower()
    matched = []
    selected = None

    for key, signal in TREND_SIGNALS.items():
        if key in tags or key in title or key in description:
            matched.append(key)
            selected = signal
            break

    if selected is None:
        color = ", ".join(item.get("colors", [])[:2]) if item else "neutral"
        category = item.get("category", "piece") if item else "piece"
        selected = {
            "trend": "classic thrift styling",
            "source": "Fallback based on item category and color fields in the mock dataset",
            "styling_note": f"Style this {category} around its {color} palette and keep the rest of the look grounded.",
        }

    if size:
        selected = {
            **selected,
            "styling_note": selected["styling_note"] + f" Fit note: search results were checked against size {size}.",
        }

    return {
        "trend": selected["trend"],
        "source": selected["source"],
        "matched_tags": matched,
        "styling_note": selected["styling_note"],
    }


# ── Stretch Tool: style profile memory ────────────────────────────────────────

def update_style_profile(
    query: str,
    wardrobe: dict,
    profile_path: str = ".fitfindr_profile.json",
) -> dict:
    """
    Remember user style preferences across interactions in a local JSON file.

    Args:
        query: The user's natural-language request.
        wardrobe: The current wardrobe dict.
        profile_path: Path to the JSON profile file.

    Returns:
        A profile dict with preferred_tags, preferred_colors, notes, and
        interaction_count. If saving fails, includes a warning key.
    """
    path = Path(profile_path)
    profile = {
        "preferred_tags": [],
        "preferred_colors": [],
        "notes": [],
        "interaction_count": 0,
    }

    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                profile.update({
                    "preferred_tags": list(loaded.get("preferred_tags", [])),
                    "preferred_colors": list(loaded.get("preferred_colors", [])),
                    "notes": list(loaded.get("notes", [])),
                    "interaction_count": int(loaded.get("interaction_count", 0)),
                })
        except Exception:
            profile["notes"].append("Started fresh because the saved style profile could not be read.")

    query_l = (query or "").lower()
    tags = set(profile["preferred_tags"])
    colors = set(profile["preferred_colors"])
    for keyword in STYLE_KEYWORDS:
        if keyword in query_l:
            tags.add(keyword)

    for item in wardrobe.get("items", []) if isinstance(wardrobe, dict) else []:
        tags.update(tag.lower() for tag in item.get("style_tags", []))
        colors.update(color.lower() for color in item.get("colors", []))

    for color in [
        "black", "white", "grey", "charcoal", "blue", "indigo", "khaki", "tan",
        "brown", "cream", "green", "navy", "red", "pink", "purple",
    ]:
        if color in query_l:
            colors.add(color)

    if query.strip():
        profile["notes"] = (profile["notes"] + [query.strip()])[-5:]
    profile["preferred_tags"] = sorted(tags)[:20]
    profile["preferred_colors"] = sorted(colors)[:20]
    profile["interaction_count"] = profile.get("interaction_count", 0) + 1

    try:
        path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    except Exception as exc:
        profile["warning"] = f"Could not save style profile: {exc}"

    return profile
