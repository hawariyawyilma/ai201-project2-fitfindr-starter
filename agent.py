"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.
"""

import re
import os
from groq import Groq
from tools import search_listings, suggest_outfit, create_fit_card

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"


# ── session state ──────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
    }


# ── query parser ───────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query.
    Uses regex for price/size, then cleans the remainder as the description.
    """
    text = query.lower()

    # Extract price: "under $30", "$30", "30 dollars", "max $25"
    price = None
    price_match = re.search(r"(?:under|max|below|less than)?\s*\$?(\d+(?:\.\d+)?)\s*(?:dollars?)?", text)
    if price_match:
        price = float(price_match.group(1))

    # Extract size: "size M", "size XL", "in M", standalone size tokens
    size = None
    size_match = re.search(
        r"(?:size\s+)?(?:\b)(xxs|xs|s/m|m/l|l/xl|xl/xxl|xxl|xxxxxl|xxxxl|xxxl|xxl|xl|[lmsx]{1,2})(?:\b)",
        text,
        re.IGNORECASE,
    )
    if size_match:
        size = size_match.group(1).upper()

    # Clean description: remove price and size fragments
    desc = re.sub(r"(?:under|max|below|less than)?\s*\$?\d+(?:\.\d+)?\s*(?:dollars?)?", "", query, flags=re.IGNORECASE)
    desc = re.sub(r"\bsize\s+\S+", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"\bin\s+(xxs|xs|s/m|m/l|l/xl|xl/xxl|xxl|xl|[lmsx]{1,2})\b", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"\s+", " ", desc).strip(" ,.")

    return {
        "description": desc or query,
        "size": size,
        "max_price": price,
    }


# ── planning loop ──────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Planning loop logic:
      1. Parse query → extract description, size, max_price
      2. Call search_listings() → if empty, set error and return early
      3. Select top result → store as selected_item
      4. Call suggest_outfit() with selected_item and wardrobe
      5. Call create_fit_card() with outfit suggestion and selected_item
      6. Return session
    """
    session = _new_session(query, wardrobe)

    # Step 1: Parse query
    parsed = _parse_query(query)
    session["parsed"] = parsed

    # Step 2: Search listings
    results = search_listings(
        description=parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )
    session["search_results"] = results

    # If no results, stop here — do not call suggest_outfit with empty input
    if not results:
        filters = []
        if parsed["size"]:
            filters.append(f"size {parsed['size']}")
        if parsed["max_price"]:
            filters.append(f"under ${parsed['max_price']:.0f}")
        filter_str = " and ".join(filters)
        hint = f" with {filter_str}" if filter_str else ""

        session["error"] = (
            f"No listings found for \"{parsed['description']}\"{hint}. "
            "Try broadening your search — remove the size or price filter, "
            "or use different keywords (e.g. 'band tee' instead of 'graphic tee')."
        )
        return session

    # Step 3: Select top result
    session["selected_item"] = results[0]

    # Step 4: Suggest outfit
    outfit = suggest_outfit(session["selected_item"], wardrobe)
    session["outfit_suggestion"] = outfit

    # Step 5: Create fit card
    fit_card = create_fit_card(outfit, session["selected_item"])
    session["fit_card"] = fit_card

    # Step 6: Return completed session
    return session


# ── CLI test ───────────────────────────────────────────────────────────────────

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
