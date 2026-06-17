# FitFindr

FitFindr is a multi-tool thrift styling agent. It takes a natural-language request, searches mock secondhand listings, compares price, checks a trend signal, suggests an outfit from the user's wardrobe, and creates a shareable fit-card caption.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional Groq support:

```bash
GROQ_API_KEY=your_key_here
```

If `GROQ_API_KEY` is not present, the creative tools use deterministic local fallbacks so the agent and tests still run.

Run tests:

```bash
pytest -q
```

Run the app:

```bash
python app.py
```

## Tool Inventory

### `search_listings(description: str, size: str | None = None, max_price: float | None = None) -> list[dict]`

Purpose: Searches `data/listings.json` for listings matching the item description, optional size, and optional price ceiling.

Inputs:
- `description` (str): Search keywords, such as `"vintage graphic tee"`.
- `size` (str | None): Optional size filter, such as `"M"`, `"US 8"`, or `"W30"`.
- `max_price` (float | None): Optional inclusive price ceiling.

Output: A list of listing dictionaries sorted by relevance. Each dict contains `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`. Returns `[]` when no matches are found.

### `suggest_outfit(new_item: dict, wardrobe: dict) -> str`

Purpose: Suggests 1-2 complete outfits using the selected thrift item and the user's wardrobe.

Inputs:
- `new_item` (dict): The exact listing dict selected from `search_listings`.
- `wardrobe` (dict): A wardrobe dict with an `items` list containing wardrobe item dicts.

Output: A non-empty outfit suggestion string. With a populated wardrobe, it names saved wardrobe pieces; with an empty wardrobe, it gives general styling advice.

### `create_fit_card(outfit: str, new_item: dict) -> str`

Purpose: Creates a short caption-style fit card from the outfit suggestion and selected listing.

Inputs:
- `outfit` (str): The suggestion returned by `suggest_outfit`.
- `new_item` (dict): The same selected listing dict stored in session state.

Output: A 2-4 sentence caption string that mentions the item title, platform, price, and outfit vibe. If `outfit` is empty, it returns an actionable error string instead of raising.

### Stretch: `compare_price(item: dict, listings: list[dict] | None = None) -> dict`

Purpose: Estimates whether the selected listing is a good deal, fair price, or pricey.

Output: A dict with `assessment`, `item_price`, `average_comparable_price`, `comparable_count`, and `reasoning`. Comparisons use same-category listings with overlapping style tags, then fall back to category-level comparisons if needed.

### Stretch: `get_trend_signal(item: dict, size: str | None = None) -> dict`

Purpose: Returns trend-aware styling guidance for the selected item.

Output: A dict with `trend`, `source`, `matched_tags`, and `styling_note`. The source is a curated trend map based on common public resale/fashion tags and the mock dataset's style tags.

### Stretch: `update_style_profile(query: str, wardrobe: dict, profile_path: str = ".fitfindr_profile.json") -> dict`

Purpose: Remembers style preferences across interactions.

Output: A profile dict with `preferred_tags`, `preferred_colors`, `notes`, and `interaction_count`. The profile is stored locally in `.fitfindr_profile.json`, which is ignored by git.

## Planning Loop

`run_agent()` uses conditional state, not a fixed unconditional sequence:

1. Initialize a session dict with the query, wardrobe, empty outputs, and `error=None`.
2. Parse the query into `description`, `size`, and `max_price`.
3. Load/update the style profile. If the new query has no explicit remembered style terms, append the top remembered tags to the search description.
4. Call `search_listings`.
5. If no results are found, retry once with loosened constraints: remove the size filter first, then raise the budget by 25% if needed.
6. If retry still finds nothing, set `session["error"]` and return early. The agent does not call `suggest_outfit` or `create_fit_card`.
7. If results exist, store `session["selected_item"] = session["search_results"][0]`.
8. Call `compare_price` and `get_trend_signal`.
9. Pass the exact selected listing and wardrobe into `suggest_outfit`.
10. Pass the exact outfit string and selected listing into `create_fit_card`.
11. Return the completed session.

This makes the no-results path behave differently from the happy path; it retries or stops instead of blindly calling every tool.

## State Management

The session dict is the single source of truth. It stores:

`query`, `parsed`, `style_profile`, `memory_note`, `search_results`, `retry_note`, `selected_item`, `price_assessment`, `trend_signal`, `wardrobe`, `outfit_suggestion`, `fit_card`, and `error`.

State flows forward without re-entry. The item returned by `search_listings` is stored as `selected_item`, and the code uses object identity (`selected_item is search_results[0]`) in tests to confirm the same dict is passed onward. The outfit string returned by `suggest_outfit` is stored in `outfit_suggestion` and then passed directly to `create_fit_card`.

Across sessions, style preferences are saved in `.fitfindr_profile.json`. A second interaction can reuse remembered tags, such as `baggy` or `streetwear`, without the user typing them again.

## Interaction Walkthrough

User query: `"vintage graphic tee under $30"`

Step 1 - Tool called:
- Tool: `search_listings`
- Input: `description="vintage graphic tee"`, `size=None`, `max_price=30.0`
- Why this tool: The agent needs a concrete thrift listing before it can style anything.
- Output: Matching listings such as `"Graphic Tee - 2003 Tour Bootleg Style"` or `"Y2K Baby Tee - Butterfly Print"`.

Step 2 - Stretch tools called:
- Tool: `compare_price`
- Input: the selected listing dict
- Output: Example: `good deal`, `$18.00` vs `$22.00` average across comparable tops.
- Tool: `get_trend_signal`
- Input: the selected listing dict and parsed size
- Output: Trend guidance such as lived-in graphic tees with loose denim.

Step 3 - Tool called:
- Tool: `suggest_outfit`
- Input: the same selected listing dict and the example wardrobe
- Why this tool: The agent now has a specific item and can use saved closet pieces.
- Output: Example: pair the tee with baggy straight-leg jeans, chunky white sneakers, a vintage black denim jacket, and a brown leather belt.

Step 4 - Tool called:
- Tool: `create_fit_card`
- Input: the outfit string from Step 3 and the selected listing dict from Step 1
- Why this tool: The agent has enough state to produce the final shareable caption.
- Output: A short caption mentioning the selected item, platform, price, and outfit vibe.

Final output to user: The app shows a listing panel with listing details, price check, and trend note; an outfit idea panel; and a fit-card panel.

## Error Handling and Fail Points

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No results match the query | Retry with loosened constraints. If still empty, return: "I couldn't find matches for that exact search. Try a broader item name, removing the size, or raising the budget." |
| `suggest_outfit` | Wardrobe is empty | Return general styling advice based on the item category, colors, and tags instead of crashing. |
| `create_fit_card` | Outfit input is missing or incomplete | Return: "I need an outfit suggestion before I can make a fit card. Try running the outfit step again with a selected listing." |
| `compare_price` | Too few close comparable listings | Fall back to same-category comparisons and explain that broader comparison in `reasoning`. |
| `get_trend_signal` | No style tag matches the trend map | Return a classic category/color styling note so outfit generation can continue. |
| `update_style_profile` | Profile file is missing or unreadable | Start from an empty profile and continue; if writing fails, keep the in-memory profile and include a warning. |

Concrete tests:
- `search_listings("designer ballgown", size="XXS", max_price=5)` returns `[]`.
- `suggest_outfit(item, get_empty_wardrobe())` returns general styling advice.
- `create_fit_card("", item)` returns an actionable error message.
- `run_agent("90s track jacket size XS under $45", wardrobe)` retries without the size filter and finds the M track jacket.

## Stretch Features

Price comparison: `compare_price` returns an assessment with reasoning based on comparable listings. It first compares same-category listings with overlapping style tags, then falls back to all listings in the same category.

Style profile memory: `update_style_profile` stores preferences in `.fitfindr_profile.json`. In testing, the first interaction records preferences like `vintage`, `baggy`, and `streetwear`; the second interaction can use those tags without the user re-entering them.

Trend awareness: `get_trend_signal` uses a curated trend map derived from common public fashion/resale tags such as Y2K, graphic tee, grunge, cottagecore, 90s, minimal, and streetwear. The trend's `styling_note` is attached to the selected listing and visibly influences `suggest_outfit`.

Retry logic with fallback: If the first search is empty, the agent retries by removing size, then by raising budget 25% if needed. It records the adjustment in `session["retry_note"]` and displays it in the app.

## AI Usage Transparency

1. I directed Codex to implement `search_listings` from the Tool 1 section of `planning.md`, using `load_listings()` and the required failure behavior. I reviewed the generated logic for price filtering, flexible size matching, relevance scoring, and the empty-list return path, then revised the scoring helpers and tests to match the dataset.

2. I directed Codex to implement the planning loop from the Mermaid diagram plus the Planning Loop and State Management sections. I reviewed whether the generated code branched on empty search results, stored `selected_item`, passed state forward, and avoided calling outfit/card tools on no-results searches. I revised the retry note, profile-memory behavior, and stretch-tool session fields.

3. I used Codex to draft README sections from the completed implementation and rubric. I checked the documented function signatures against `tools.py`, added concrete command outputs from testing, and made the stretch-feature explanations more specific.

## Spec Reflection

One way `planning.md` helped during implementation: The planning loop section made the branch conditions clear before coding. Because the empty-search branch was written down first, it was easy to verify that `run_agent()` returns early and leaves `fit_card` as `None` instead of accidentally running all tools in sequence.

One divergence from the spec, and why: The assignment recommends Groq for `suggest_outfit` and `create_fit_card`, and this implementation does call Groq when `GROQ_API_KEY` is available. I added deterministic local fallbacks for missing keys or API failures so grading, tests, and demos can still run reliably without crashing.

## Verification

Latest local test run:

```text
11 passed in 0.70s
```
