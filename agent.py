"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Usage:
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

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """Initialize and return a fresh session dict for one user interaction."""
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
        "retry_note": None,
    }


# ── query parsing ─────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query.

    Returns a dict with keys: description (str), size (str|None), max_price (float|None).
    """
    text = query.strip()

    # Extract max_price: "under $30", "under 30", "max $25", "$40 or less", "less than $50"
    price_match = re.search(
        r"(?:under|max|less than|below|no more than)\s*\$?\s*(\d+(?:\.\d+)?)"
        r"|\$\s*(\d+(?:\.\d+)?)\s*(?:or less|max|maximum)",
        text,
        re.IGNORECASE,
    )
    max_price = None
    if price_match:
        raw = price_match.group(1) or price_match.group(2)
        max_price = float(raw)

    # Extract size: "size M", "size XL", "in size M", "in M", "XS", standalone sizes
    size_match = re.search(
        r"\b(?:in\s+)?size\s+([A-Z]{1,3}|\d+[A-Z]?)\b"
        r"|\bsize\s*:\s*([A-Z]{1,3})\b",
        text,
        re.IGNORECASE,
    )
    size = None
    if size_match:
        size = (size_match.group(1) or size_match.group(2)).upper()

    # Description: remove price and size phrases, clean up leftovers
    description = text
    if price_match:
        description = description[:price_match.start()] + description[price_match.end():]
    if size_match:
        description = description[:size_match.start()] + description[size_match.end():]

    # Strip common filler phrases that don't help search
    filler = re.compile(
        r"\b(I'?m?\s+looking\s+for|I\s+want|find\s+me|looking\s+for|can\s+you\s+find)"
        r"|\b(please|a\s+(?:good|nice|cute)|for\s+me)\b",
        re.IGNORECASE,
    )
    description = filler.sub(" ", description)
    description = re.sub(r"\s{2,}", " ", description).strip(" ,.")

    return {
        "description": description if description else query,
        "size": size,
        "max_price": max_price,
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
        wardrobe: User's wardrobe dict

    Returns:
        The session dict after the interaction completes.
        Check session["error"] first — if not None, the interaction ended early
        and outfit_suggestion / fit_card will be None.
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)

    # Step 2: Parse query into description, size, max_price
    parsed = _parse_query(query)
    session["parsed"] = parsed

    # Step 3: Search for listings
    results = search_listings(
        description=parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )
    session["search_results"] = results

    if not results:
        # Stretch: retry with fallback — if size was set, try without it
        retry_note = None
        if parsed["size"]:
            retry_results = search_listings(
                description=parsed["description"],
                size=None,
                max_price=parsed["max_price"],
            )
            if retry_results:
                results = retry_results
                retry_note = (
                    f"No listings found for size {parsed['size']}. "
                    f"Retrying without size filter — found {len(retry_results)} result(s). "
                    "Showing the closest match."
                )
                session["search_results"] = results
                session["retry_note"] = retry_note

        if not results:
            filters = []
            if parsed["size"]:
                filters.append(f"size {parsed['size']}")
            if parsed["max_price"] is not None:
                filters.append(f"under ${parsed['max_price']:.0f}")
            filter_str = " and ".join(filters)
            hint = f" (filtered by {filter_str})" if filter_str else ""

            session["error"] = (
                f"No listings found for \"{parsed['description']}\"{hint}. "
                "Try broadening your search — remove the size filter, raise your price, "
                "or use different keywords."
            )
            return session

    # Step 4: Select top result
    session["selected_item"] = results[0]

    # Step 5: Suggest outfit
    outfit = suggest_outfit(session["selected_item"], wardrobe)
    session["outfit_suggestion"] = outfit

    # Step 6: Create fit card
    fit_card = create_fit_card(outfit, session["selected_item"])
    session["fit_card"] = fit_card

    # Step 7: Return session
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
