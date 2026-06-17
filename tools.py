"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


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
        A list of matching listing dicts sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    """
    try:
        listings = load_listings()
    except Exception:
        return []

    # Hard filters: price and size
    candidates = []
    for item in listings:
        if max_price is not None and item.get("price", 0) > max_price:
            continue
        if size is not None:
            item_size = (item.get("size") or "").upper()
            query_size = size.upper()
            # Accept exact match or substring (e.g., "M" matches "S/M")
            if query_size not in item_size and item_size not in query_size:
                continue
        candidates.append(item)

    # Score by keyword overlap with description
    keywords = set(re.sub(r"[^a-z0-9\s]", "", description.lower()).split())

    def score(item):
        searchable = " ".join([
            item.get("title", ""),
            item.get("description", ""),
            item.get("category", ""),
            " ".join(item.get("style_tags", [])),
            item.get("brand", "") or "",
        ]).lower()
        return sum(1 for kw in keywords if kw in searchable)

    scored = [(score(item), item) for item in candidates]
    scored = [(s, item) for s, item in scored if s > 0]
    scored.sort(key=lambda x: x[0], reverse=True)

    return [item for _, item in scored]


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
        If the wardrobe is empty, offers general styling advice for the item.
    """
    try:
        client = _get_groq_client()
    except ValueError as e:
        return f"Error: {e}"

    item_name = new_item.get("title", "this item")
    item_desc = new_item.get("description", "")
    item_tags = ", ".join(new_item.get("style_tags", []))
    item_colors = ", ".join(new_item.get("colors", []))
    item_condition = new_item.get("condition", "")
    item_price = new_item.get("price", "")
    item_platform = new_item.get("platform", "")

    item_summary = (
        f"{item_name} — ${item_price} on {item_platform}. "
        f"Condition: {item_condition}. Colors: {item_colors}. "
        f"Style: {item_tags}. Details: {item_desc}"
    )

    wardrobe_items = (wardrobe or {}).get("items", [])

    if not wardrobe_items:
        prompt = (
            f"A user just found this thrifted item: {item_summary}\n\n"
            "They have no wardrobe items listed yet. Suggest 1–2 outfit ideas that would work "
            "well with this piece. Describe what kinds of bottoms, shoes, or layers would "
            "complement it. Keep it casual, specific, and practical — think real outfits, "
            "not mood boards. 3–5 sentences total."
        )
    else:
        wardrobe_text = "\n".join(
            f"- {w.get('name', 'unknown')} ({w.get('category', '')}): "
            f"colors {', '.join(w.get('colors', []))}, style {', '.join(w.get('style_tags', []))}"
            for w in wardrobe_items
        )
        prompt = (
            f"A user just found this thrifted item: {item_summary}\n\n"
            f"Their current wardrobe includes:\n{wardrobe_text}\n\n"
            "Suggest 1–2 complete outfit combinations using the new item and specific pieces "
            "from their wardrobe. Name the pieces by their exact names. Keep it casual and "
            "specific — include brief styling notes like tucking or layering. 4–6 sentences total."
        )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a knowledgeable personal stylist who specializes in "
                        "thrifted and secondhand fashion. Give direct, specific outfit advice."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=400,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Could not generate outfit suggestion: {e}"


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, returns a descriptive error message string.
    """
    if not outfit or not outfit.strip():
        return (
            "Error: Cannot generate a fit card without an outfit suggestion. "
            "Please provide an outfit description first."
        )

    item_name = new_item.get("title", "this thrifted find")
    item_price = new_item.get("price", "")
    item_platform = new_item.get("platform", "")
    item_tags = ", ".join(new_item.get("style_tags", []))

    price_str = f"${item_price}" if item_price else "a steal"
    platform_str = item_platform if item_platform else "online"

    prompt = (
        f"Write a 2–4 sentence Instagram caption for this outfit:\n\n"
        f"Thrifted item: {item_name} — {price_str} from {platform_str}\n"
        f"Style tags: {item_tags}\n"
        f"Outfit: {outfit}\n\n"
        "Rules:\n"
        "- Sound like a real person posting an OOTD, not a brand\n"
        "- Mention the item name, price, and platform naturally (once each)\n"
        "- Capture the vibe in specific terms — reference colors, textures, or the era\n"
        "- Keep it casual, lowercase where it feels right, maybe one emoji\n"
        "- Do NOT use hashtags\n"
        "- Make it feel unique to this specific outfit"
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write authentic, casual social media captions for thrift hauls "
                        "and outfit posts. Your captions sound like a real person, not marketing copy."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=1.0,
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Could not generate fit card: {e}"
