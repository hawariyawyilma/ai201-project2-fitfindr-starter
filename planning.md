# FitFindr — Planning Document

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:** The agent parses the query using regex to extract: description = "vintage graphic tee", max_price = 30.0, size = None. It calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`, which loads all listings, filters to those priced at or under $30, scores each by keyword overlap with "vintage graphic tee", and returns them sorted by score. Result: 3 matching listings, top result is "Graphic Tee — 2003 Tour Bootleg Style" at $24 on Depop.

**Step 2:** The agent checks that results is non-empty (it is), sets `session["selected_item"]` to the top result, and calls `suggest_outfit(selected_item, wardrobe)`. The wardrobe contains baggy jeans, chunky sneakers, and other items. The LLM returns: "Pair this boxy bootleg tee with your wide-leg jeans and chunky sneakers for a lived-in 90s grunge look. Tuck the front corner slightly and leave the back out for shape. Or go baggier — layer it over a long-sleeve mesh top with the same jeans for extra texture."

**Step 3:** The agent calls `create_fit_card(outfit_suggestion, selected_item)`. The LLM generates: "found this faded bootleg tee on depop for $24 and it was made for my wide-legs 🖤 paired with chunky sneakers and it's giving exactly the 90s energy I needed. full look in stories"

**Final output to user:** Three panels populate — the listing details, the outfit suggestion, and the fit card caption.

---

## Tool Specifications

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset and returns items that match the user's description, size, and price constraints, sorted by keyword relevance.

**Input parameters:**
- `description` (str): Natural language description of the item (e.g., "vintage graphic tee"). Used to score listings by keyword overlap against title, description, category, style_tags, colors, and brand.
- `size` (str or None): Size string to filter by (e.g., "M", "S/M"). Case-insensitive partial match. Pass None to skip size filtering.
- `max_price` (float or None): Maximum price in dollars, inclusive. Pass None to skip price filtering.

**What it returns:**
A list of listing dicts sorted by relevance score (highest first). Each dict contains: id (str), title (str), description (str), category (str), style_tags (list[str]), size (str), condition (str), price (float), colors (list[str]), brand (str or None), platform (str). Returns an empty list if no matches — never raises an exception.

**What happens if it fails or returns nothing:**
The agent checks if results is empty immediately after calling this tool. If empty, it sets `session["error"]` to a helpful message explaining what filters were applied and suggesting how to broaden the search (e.g., remove size filter, try different keywords). It returns the session immediately and does NOT call suggest_outfit.

---

### Tool 2: suggest_outfit

**What it does:**
Given a thrifted item and the user's wardrobe, calls the Groq LLM to suggest 1–2 complete outfit combinations using specific wardrobe pieces.

**Input parameters:**
- `new_item` (dict): A listing dict representing the thrifted piece the user found.
- `wardrobe` (dict): A wardrobe dict with an 'items' key containing a list of wardrobe item dicts. May be empty.

**What it returns:**
A non-empty string (up to ~150 words) describing specific outfit combinations. If the wardrobe is empty, returns general styling advice for the item type instead of wardrobe-specific combinations.

**What happens if it fails or returns nothing:**
If the wardrobe is empty, the tool switches to a general styling prompt rather than crashing. If the LLM call fails, the tool catches the exception and returns a descriptive error string — never raises an exception or returns an empty string.

---

### Tool 3: create_fit_card

**What it does:**
Calls the Groq LLM to generate a 2–4 sentence Instagram/TikTok-style caption for the thrifted outfit. Designed to sound like a real OOTD post, not a product description.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by suggest_outfit.
- `new_item` (dict): The listing dict for the thrifted item (used for title, price, platform).

**What it returns:**
A 2–4 sentence caption string. Casual tone, mentions item name/price/platform once each, uses 1–2 emojis. Returns a descriptive error string if outfit is empty — never raises an exception.

**What happens if it fails or returns nothing:**
Guards against an empty or whitespace-only outfit string up front, returning a clear error message string. If the LLM call fails, catches the exception and returns a descriptive error string.

---

## Planning Loop

The planning loop in `run_agent()` uses the following conditional logic:

1. Parse the query with regex to extract description, size, and max_price. Store in `session["parsed"]`.
2. Call `search_listings()` with the parsed parameters. Store results in `session["search_results"]`.
3. **Branch:** If `results` is empty → set `session["error"]` with a helpful message (naming which filters were applied and suggesting adjustments) → return session immediately. Do NOT call suggest_outfit or create_fit_card.
4. If results is non-empty → set `session["selected_item"] = results[0]` (top-scored result).
5. Call `suggest_outfit(session["selected_item"], session["wardrobe"])`. Store result in `session["outfit_suggestion"]`.
6. Call `create_fit_card(session["outfit_suggestion"], session["selected_item"])`. Store result in `session["fit_card"]`.
7. Return the completed session.

The agent's behavior differs materially based on step 3: an impossible query (e.g., designer ballgown under $5 in XXS) terminates after search_listings and never reaches the LLM tools.

---

## State Management

All state lives in a single `session` dict initialized by `_new_session()`. Fields are written once per tool call and read by the next:

- `session["parsed"]` ← written after query parsing; read by search_listings call
- `session["search_results"]` ← written after search_listings; checked for emptiness before proceeding
- `session["selected_item"]` ← written as results[0]; passed directly into suggest_outfit and create_fit_card
- `session["outfit_suggestion"]` ← written after suggest_outfit; passed directly into create_fit_card
- `session["fit_card"]` ← written after create_fit_card; read by app.py for display
- `session["error"]` ← written on early termination; checked by app.py before reading other fields

No values are re-entered by the user between steps. The item found by search_listings flows into suggest_outfit as the exact same dict object.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Sets `session["error"]` with a message naming the applied filters (size, price) and suggesting how to broaden the search. Returns early — suggest_outfit is never called with empty input. |
| suggest_outfit | Wardrobe is empty | Switches prompt to request general styling advice for the item type (silhouettes, colors, vibes that work) rather than wardrobe-specific combinations. Returns a non-empty string either way. |
| create_fit_card | Outfit input is empty or whitespace | Returns a descriptive error message string immediately, without calling the LLM. Agent does not crash. |

---

## Architecture

```
User query
    │
    ▼
_parse_query(query)
    │  → parsed: {description, size, max_price}
    ▼
search_listings(description, size, max_price)
    │
    ├── results = []
    │       │
    │       └──► session["error"] = "No listings found..." → return session
    │
    └── results = [item, ...]
            │
            ▼
        session["selected_item"] = results[0]
            │
            ▼
        suggest_outfit(selected_item, wardrobe)
            │  wardrobe empty? → general styling advice
            │  wardrobe has items? → specific outfit combinations
            ▼
        session["outfit_suggestion"] = "..."
            │
            ▼
        create_fit_card(outfit_suggestion, selected_item)
            │  outfit empty? → return error string
            │  outfit present? → LLM generates caption
            ▼
        session["fit_card"] = "..."
            │
            ▼
        return session
            │
            ▼
        app.py maps session fields → 3 Gradio output panels
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

I used Claude to implement all three tools. For each tool, I provided: the function stub from tools.py (docstring, args, returns, TODO steps), the listings.json field names, and the wardrobe schema structure. I asked Claude to implement one tool at a time. Before accepting each implementation, I verified that: (1) search_listings filters by all three parameters and handles the empty-results case by returning [], not raising; (2) suggest_outfit branches on empty wardrobe and catches LLM exceptions; (3) create_fit_card guards against empty outfit string before calling the LLM. I tested each tool in isolation using the CLI commands from Milestone 5 before wiring them together.

**Milestone 4 — Planning loop and state management:**

I provided Claude with the Architecture diagram above and the Planning Loop section. I asked it to implement `run_agent()` following the numbered steps exactly. I verified the generated code: (1) branches on empty results before calling suggest_outfit; (2) stores values in session rather than local variables; (3) does not call all three tools unconditionally. I tested the no-results branch explicitly with the designer ballgown query.

---

## Spec Reflection

**One way the spec helped:** Designing the planning loop logic in plain English before writing code made the branching condition obvious — "if results is empty, stop" is easy to miss when you're thinking in code but impossible to miss when you've written it out as a decision point in your diagram.

**One way implementation diverged from the spec:** The original spec implied the agent might use the LLM to parse the query. In practice, regex parsing was faster, cheaper (no LLM call), and more reliable for structured fields like price and size. The LLM was reserved for the tools that actually needed it — outfit suggestion and fit card generation.
