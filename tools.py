"""
tools.py

The three core tools for FitFindr:
  - search_listings: filters mock data by keyword, size, and price
  - suggest_outfit: uses Groq LLM to suggest outfit combinations
  - create_fit_card: uses Groq LLM to generate a shareable caption
"""

import os
import re
from groq import Groq
from dotenv import load_dotenv
from utils.data_loader import load_listings

load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"


# ── Tool 1: search_listings ────────────────────────────────────────────────────

def search_listings(description: str, size: str | None, max_price: float | None) -> list[dict]:
    """
    Search mock listings by keyword relevance, size, and price.

    Args:
        description: Natural language description of the item being searched
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.
    """
    try:
        listings = load_listings()
    except Exception:
        return []

    # Filter by price
    if max_price is not None:
        listings = [l for l in listings if l["price"] <= max_price]

    # Filter by size (case-insensitive, partial match)
    if size is not None:
        size_lower = size.lower()
        listings = [
            l for l in listings
            if size_lower in l["size"].lower()
        ]

    # Score by keyword overlap with description
    keywords = set(re.sub(r"[^\w\s]", "", description.lower()).split())

    def score(listing):
        text = " ".join([
            listing["title"],
            listing["description"],
            listing["category"],
            " ".join(listing["style_tags"]),
            " ".join(listing["colors"]),
            listing.get("brand") or "",
        ]).lower()
        return sum(1 for kw in keywords if kw in text)

    scored = [(score(l), l) for l in listings]
    scored = [(s, l) for s, l in scored if s > 0]
    scored.sort(key=lambda x: x[0], reverse=True)

    return [l for _, l in scored]


# ── Tool 2: suggest_outfit ─────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key. May be empty.

    Returns:
        A non-empty string with outfit suggestions.
    """
    try:
        item_desc = (
            f"{new_item['title']} — {new_item['description']} "
            f"(Colors: {', '.join(new_item['colors'])}; "
            f"Style: {', '.join(new_item['style_tags'])})"
        )

        wardrobe_items = wardrobe.get("items", [])

        if not wardrobe_items:
            prompt = (
                f"A thrifter just found this item: {item_desc}\n\n"
                "They don't have a saved wardrobe yet. Give them 1-2 outfit ideas "
                "using general wardrobe staples that would pair well with this piece. "
                "Be specific about silhouettes, colors, and vibe. Keep it conversational "
                "and under 150 words."
            )
        else:
            wardrobe_text = "\n".join(
                f"- {item['name']}: {item.get('description', '')} "
                f"(colors: {', '.join(item.get('colors', []))})"
                for item in wardrobe_items
            )
            prompt = (
                f"A thrifter found this item: {item_desc}\n\n"
                f"Their current wardrobe includes:\n{wardrobe_text}\n\n"
                "Suggest 1-2 complete outfit combinations using the new item and "
                "specific pieces from their wardrobe. Name the wardrobe pieces directly. "
                "Be specific about how to style it — tucking, layering, proportions. "
                "Keep it conversational and under 150 words."
            )

        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"Couldn't generate outfit suggestion: {str(e)}. Try describing the item differently."


# ── Tool 3: create_fit_card ────────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
    """
    if not outfit or not outfit.strip():
        return "Error: No outfit suggestion available to generate a fit card. Please try searching again."

    try:
        prompt = (
            f"Write a 2-4 sentence Instagram/TikTok caption for this thrifted outfit.\n\n"
            f"The thrifted piece: {new_item['title']} — found on {new_item['platform']} for ${new_item['price']}\n"
            f"Outfit idea: {outfit}\n\n"
            "Rules:\n"
            "- Sound like a real person posting an OOTD, not a brand or product description\n"
            "- Mention the item name, price, and platform naturally (once each)\n"
            "- Capture the specific vibe of the outfit\n"
            "- Use casual language, maybe 1-2 emojis\n"
            "- Do NOT use generic phrases like 'slaying' or 'obsessed'\n"
            "Just write the caption, nothing else."
        )

        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=1.0,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"Couldn't generate fit card: {str(e)}. The outfit suggestion was saved above."
