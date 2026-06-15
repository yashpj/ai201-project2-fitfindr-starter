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
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.
    """
    listings = load_listings()

    # Step 1: Filter by max_price
    if max_price is not None:
        listings = [item for item in listings if item["price"] <= max_price]

    # Step 2: Filter by size (case-insensitive substring match)
    if size is not None:
        size_lower = size.lower()
        listings = [
            item for item in listings
            if size_lower in item["size"].lower()
        ]

    # Step 3: Score each listing by keyword overlap with description
    keywords = [kw.lower() for kw in description.split() if len(kw) > 1]

    def score_listing(item: dict) -> int:
        # Build a set of all text from searchable fields
        searchable_parts = [
            item.get("title", ""),
            item.get("description", ""),
            item.get("category", ""),
            item.get("brand") or "",
        ]
        searchable_parts += item.get("style_tags", [])
        searchable_parts += item.get("colors", [])
        searchable_text = " ".join(searchable_parts).lower()

        return sum(1 for kw in keywords if kw in searchable_text)

    scored = [(item, score_listing(item)) for item in listings]

    # Step 4: Drop listings with score 0
    scored = [(item, score) for item, score in scored if score > 0]

    # Step 5: Sort by score descending
    scored.sort(key=lambda x: x[1], reverse=True)

    return [item for item, _ in scored]


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
    client = _get_groq_client()

    item_title = new_item.get("title", "this item")
    item_category = new_item.get("category", "clothing")
    item_tags = ", ".join(new_item.get("style_tags", []))
    item_colors = ", ".join(new_item.get("colors", []))
    item_description = new_item.get("description", "")

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        # Empty wardrobe: give general styling advice
        prompt = (
            f"A user just found this secondhand item: '{item_title}'. "
            f"It's a {item_category} with these style tags: {item_tags}. "
            f"Colors: {item_colors}. Description: {item_description}\n\n"
            "They don't have a saved wardrobe yet. Give 2–3 sentences of general "
            "styling advice: what types of bottoms, tops, or shoes pair well with this item, "
            "what vibe or aesthetic it suits, and one specific styling tip. "
            "Be casual and specific — like advice from a stylish friend, not a fashion magazine."
        )
    else:
        # Format wardrobe items for the prompt
        wardrobe_lines = []
        for w_item in wardrobe_items:
            name = w_item.get("name", "unknown piece")
            category = w_item.get("category", "")
            colors = ", ".join(w_item.get("colors", []))
            tags = ", ".join(w_item.get("style_tags", []))
            notes = w_item.get("notes") or ""
            line = f"- {name} ({category}, {colors}"
            if tags:
                line += f", style: {tags}"
            if notes:
                line += f", note: {notes}"
            line += ")"
            wardrobe_lines.append(line)

        wardrobe_text = "\n".join(wardrobe_lines)

        prompt = (
            f"A user just found this secondhand item: '{item_title}'. "
            f"It's a {item_category} with these style tags: {item_tags}. "
            f"Colors: {item_colors}. Description: {item_description}\n\n"
            f"Here's what's already in their wardrobe:\n{wardrobe_text}\n\n"
            "Suggest 1–2 specific outfit combinations using the new item and pieces from their wardrobe. "
            "Name the exact wardrobe pieces by name. Be casual and specific — like advice from a stylish friend. "
            "Keep it to 2–4 sentences total."
        )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=300,
    )

    result = response.choices[0].message.content.strip()
    return result if result else "This piece has a great vintage vibe — try pairing it with straight-leg jeans and chunky sneakers for an easy streetwear look."


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message string.
    """
    # Guard against empty or whitespace-only outfit string
    if not outfit or not outfit.strip():
        return "Could not generate fit card: outfit suggestion was empty."

    client = _get_groq_client()

    item_title = new_item.get("title", "this thrifted piece")
    item_price = new_item.get("price", 0)
    item_platform = new_item.get("platform", "a thrift platform")

    prompt = (
        f"Write a 2–4 sentence Instagram/TikTok OOTD caption for this thrifted find.\n\n"
        f"Item: {item_title}\n"
        f"Price: ${item_price:.2f}\n"
        f"Platform: {item_platform}\n"
        f"Outfit: {outfit}\n\n"
        "Style rules for the caption:\n"
        "- Sound casual and authentic, like a real person posting their fit — not a product description\n"
        "- Mention the item name, price, and platform once each, naturally woven in\n"
        "- Capture the outfit vibe in specific terms\n"
        "- Keep it 2–4 sentences, conversational tone\n"
        "- No hashtags needed"
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
        max_tokens=200,
    )

    result = response.choices[0].message.content.strip()
    return result if result else f"just thrifted this {item_title} off {item_platform} for ${item_price:.2f} and i'm obsessed 🖤"
