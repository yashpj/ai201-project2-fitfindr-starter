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

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from the user's natural language query.

    Uses regex patterns:
    - max_price: "under $30", "under 30", "less than $40", "$25 or less", "max $50"
    - size: "size M", "size XS", "in M", "in size L"
    - description: remaining text after stripping price and size clauses

    Returns a dict with keys: description (str), size (str|None), max_price (float|None)
    """
    text = query.strip()

    # Extract max_price — try several common patterns
    price_patterns = [
        r'(?:under|below|less\s+than|max|no\s+more\s+than)\s*\$?\s*(\d+(?:\.\d+)?)',
        r'\$\s*(\d+(?:\.\d+)?)\s*(?:or\s+less|max|maximum)',
    ]
    max_price = None
    price_span = None
    for pattern in price_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            max_price = float(m.group(1))
            price_span = m.span()
            break

    # Extract size — patterns like "size M", "in size XL", "in M"
    size_patterns = [
        r'(?:in\s+)?size\s+([A-Za-z0-9/]+)',
        r'\bin\s+([XSML]+)\b',
    ]
    size = None
    size_span = None
    for pattern in size_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            size = m.group(1).upper()
            size_span = m.span()
            break

    # Build description by removing price and size clauses from the query
    clean = text
    # Remove size span first (higher index first to avoid offset shift)
    spans_to_remove = []
    if price_span:
        spans_to_remove.append(price_span)
    if size_span:
        spans_to_remove.append(size_span)

    # Sort by start position descending so we can remove without shifting
    spans_to_remove.sort(key=lambda s: s[0], reverse=True)
    for start, end in spans_to_remove:
        clean = clean[:start] + " " + clean[end:]

    # Remove common filler phrases that aren't search keywords
    filler_patterns = [
        r"i'?m\s+(?:looking|searching)\s+for",
        r"i\s+(?:want|need|would\s+like)\s+(?:a|an|some)?",
        r"looking\s+for\s+(?:a|an)?",
        r"find\s+me\s+(?:a|an)?",
        r"what(?:'s|\s+is)\s+out\s+there",
        r"how\s+would\s+i\s+style\s+it",
        r"i\s+mostly\s+wear.*",
        r"[,;]\s*$",
    ]
    for fp in filler_patterns:
        clean = re.sub(fp, " ", clean, flags=re.IGNORECASE)

    description = " ".join(clean.split()).strip(" ,.")
    if not description:
        description = query.strip()

    return {
        "description": description,
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
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.
    """
    # Step 1: Initialize the session
    session = _new_session(query, wardrobe)

    # Step 2: Parse the query to extract description, size, max_price
    parsed = _parse_query(query)
    session["parsed"] = parsed

    description = parsed["description"]
    size = parsed["size"]
    max_price = parsed["max_price"]

    # Step 3: Call search_listings
    results = search_listings(description, size=size, max_price=max_price)
    session["search_results"] = results

    # Branch: no results → set error and return early
    if not results:
        parts = [f"No listings found for '{description}'"]
        if size:
            parts.append(f"size: {size}")
        if max_price is not None:
            parts.append(f"under ${max_price:.0f}")
        context = " (" + ", ".join(parts[1:]) + ")" if len(parts) > 1 else ""
        session["error"] = (
            f"No listings found for '{description}'{context}. "
            "Try broader keywords, a different size, or raise your price ceiling."
        )
        return session

    # Step 4: Select the top result
    session["selected_item"] = results[0]

    # Step 5: Call suggest_outfit
    outfit_suggestion = suggest_outfit(session["selected_item"], wardrobe)
    session["outfit_suggestion"] = outfit_suggestion

    # Step 6: Call create_fit_card
    fit_card = create_fit_card(outfit_suggestion, session["selected_item"])
    session["fit_card"] = fit_card

    # Step 7: Return the completed session
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
