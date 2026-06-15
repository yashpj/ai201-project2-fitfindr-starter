# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for secondhand items that match the user's description, optional size, and optional price ceiling. It scores each listing by keyword overlap and returns results ranked by relevance.

**Input parameters:**
- `description` (str): Natural language keywords describing the item the user wants (e.g., "vintage graphic tee"). Used to score listings by matching against title, description, style_tags, category, colors, and brand fields.
- `size` (str | None): Size string to filter by, or None to skip size filtering. Case-insensitive substring match — "M" will match "S/M", "M/L", "M", "One Size / M". Pass None to skip.
- `max_price` (float | None): Maximum price in dollars (inclusive). Listings with price > max_price are excluded. Pass None to skip price filtering.

**What it returns:**
A list of listing dicts sorted by relevance score (highest first). Each dict contains:
- `id` (str): unique listing identifier, e.g. "lst_006"
- `title` (str): short title of the item
- `description` (str): seller's description
- `category` (str): one of tops, bottoms, outerwear, shoes, accessories
- `style_tags` (list[str]): list of style descriptors (e.g. ["vintage", "graphic tee", "streetwear"])
- `size` (str): size as listed (e.g. "M", "S/M", "W28", "US 8")
- `condition` (str): one of excellent, good, fair
- `price` (float): price in USD
- `colors` (list[str]): list of color descriptors
- `brand` (str | None): brand name or None
- `platform` (str): one of depop, thredUp, poshmark

Returns an empty list `[]` if nothing matches — does NOT raise an exception.

**What happens if it fails or returns nothing:**
If the list is empty, the planning loop sets `session["error"]` to: "No listings found for '[description]'[size/price context]. Try broader keywords, a different size, or a higher price." The agent returns the session immediately and does NOT proceed to `suggest_outfit`.

---

### Tool 2: suggest_outfit

**What it does:**
Given a thrifted listing dict and the user's wardrobe dict, calls the Groq LLM to suggest 1–2 complete outfits. If the wardrobe is empty, it gives general styling advice for the item instead of specific combinations.

**Input parameters:**
- `new_item` (dict): A listing dict (same structure as returned by `search_listings`). The item the user is considering buying. Used to extract title, category, style_tags, colors, and price for the prompt.
- `wardrobe` (dict): A wardrobe dict with an `items` key containing a list of wardrobe item dicts. Each wardrobe item has: id (str), name (str), category (str), colors (list[str]), style_tags (list[str]), notes (str | None). May be an empty list — handled gracefully.

**What it returns:**
A non-empty string with outfit suggestions. If the wardrobe has items, the string names specific pieces from the wardrobe (e.g., "Pair with your baggy straight-leg jeans and chunky white sneakers..."). If the wardrobe is empty, the string gives general styling advice (e.g., what types of bottoms pair well, what vibe the item suits). The string is 2–4 sentences long.

**What happens if it fails or returns nothing:**
If `wardrobe['items']` is empty, the function does NOT raise an exception — it calls the LLM with a general styling prompt and returns the result. The agent stores the result in `session["outfit_suggestion"]` and continues to `create_fit_card`.

---

### Tool 3: create_fit_card

**What it does:**
Generates a short, casual, shareable social media caption (Instagram/TikTok OOTD style) for the thrifted find, using the outfit suggestion and the listing details. Calls the Groq LLM with a higher temperature for variety.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by `suggest_outfit`. Must be non-empty. If empty or whitespace-only, the function returns an error message string without calling the LLM.
- `new_item` (dict): The listing dict for the thrifted item. Used to extract title, price, and platform for natural mention in the caption.

**What it returns:**
A 2–4 sentence string styled as a casual OOTD caption — mentions the item name, price, and platform once each, captures the outfit vibe in specific terms, and sounds authentic (not like a product description). Output varies across runs because temperature is set high (0.9).

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, the function returns the string: "Could not generate fit card: outfit suggestion was empty." rather than raising an exception. The agent stores this message in `session["fit_card"]` and returns the session.

---

### Additional Tools (if any)

None beyond the required three.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop is a deterministic sequential pipeline with one early-exit branch:

1. **Parse the query** — use regex to extract `max_price` (pattern: `under\s*\$?(\d+(?:\.\d+)?)` or `\$(\d+(?:\.\d+)?)`), `size` (pattern: `(?:size|in)\s+([A-Za-z0-9/]+)`), and `description` (remaining text after stripping size/price patterns). Store in `session["parsed"]`.

2. **Call `search_listings(description, size, max_price)`** — store the result list in `session["search_results"]`.
   - **Branch A (empty results):** If `len(session["search_results"]) == 0`, set `session["error"]` to a helpful message describing what to try differently, and `return session` immediately. `suggest_outfit` and `create_fit_card` are never called.
   - **Branch B (results found):** Set `session["selected_item"] = session["search_results"][0]` (top result by relevance score).

3. **Call `suggest_outfit(selected_item, wardrobe)`** — store result string in `session["outfit_suggestion"]`. Always proceeds (wardrobe emptiness is handled inside the tool).

4. **Call `create_fit_card(outfit_suggestion, selected_item)`** — store result string in `session["fit_card"]`.

5. **Return `session`** — `session["error"]` is None on success.

The loop never re-prompts the user, never uses hardcoded values between steps, and passes live values from `session` at each step.

---

## State Management

**How does information from one tool get passed to the next?**

All state lives in a single `session` dict initialized by `_new_session(query, wardrobe)`. Fields:

| Field | Type | Set by | Used by |
|---|---|---|---|
| `query` | str | initialization | parse step |
| `parsed` | dict | parse step | `search_listings` call |
| `search_results` | list[dict] | `search_listings` return | branch check, `selected_item` assignment |
| `selected_item` | dict \| None | planning loop (results[0]) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | dict | initialization | `suggest_outfit` |
| `outfit_suggestion` | str \| None | `suggest_outfit` return | `create_fit_card` |
| `fit_card` | str \| None | `create_fit_card` return | final output |
| `error` | str \| None | early-exit branch | caller checks this first |

No global state, no side effects between runs. Each call to `run_agent()` creates a fresh `session` dict. Tool outputs are stored immediately after the call returns, and the next tool reads directly from the session rather than re-computing.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No listings match the query (returns empty list) | Sets `session["error"]` = "No listings found for '[description]' (size: [size], under $[price]). Try broader keywords, a different size, or raise your price ceiling." Returns session immediately — `suggest_outfit` is never called. User sees this message in the first output panel. |
| suggest_outfit | Wardrobe is empty (`wardrobe['items'] == []`) | Calls the LLM with a general styling prompt (no wardrobe items to reference). Returns general advice like "This piece works well with straight-leg jeans and chunky sneakers for a 90s streetwear look." Does NOT raise an exception or return an empty string. |
| create_fit_card | Outfit input is empty or whitespace-only | Returns the string "Could not generate fit card: outfit suggestion was empty." without calling the LLM. Does NOT raise an exception. Agent stores this in `session["fit_card"]` and returns. |

---

## Architecture

```
User query (natural language)
    │
    ▼
run_agent(query, wardrobe)
    │
    ▼
Step 1: _new_session(query, wardrobe)
    │   → session dict initialized with empty fields
    │
    ▼
Step 2: parse_query(query)
    │   → regex extracts description, size, max_price
    │   → stored in session["parsed"]
    │
    ▼
Step 3: search_listings(description, size, max_price)
    │   → loads listings, filters by price/size, scores by keywords
    │
    ├── results == []  ──────────────────────────────────────────────┐
    │       │                                                        │
    │       ▼                                                        │
    │   session["error"] = "No listings found..."                   │
    │   return session  ◄─────────────────────────────── early exit ─┘
    │
    │   results = [item, ...]
    │       │
    │       ▼
    │   session["search_results"] = results
    │   session["selected_item"]  = results[0]
    │
    ▼
Step 4: suggest_outfit(selected_item, wardrobe)
    │   → calls Groq LLM (llama-3.3-70b-versatile)
    │   → if wardrobe empty: general styling advice
    │   → if wardrobe has items: specific outfit combinations
    │   → stored in session["outfit_suggestion"]
    │
    ▼
Step 5: create_fit_card(outfit_suggestion, selected_item)
    │   → guards empty outfit string (returns error string, no exception)
    │   → calls Groq LLM at temperature=0.9
    │   → stored in session["fit_card"]
    │
    ▼
Return session
    session["error"]            → None (success) or error message
    session["selected_item"]    → the listing dict used
    session["outfit_suggestion"]→ styling advice string
    session["fit_card"]         → OOTD caption string
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

**Tool 1 (search_listings):** I'll give Claude the Tool 1 spec block above (inputs, return value, failure mode) plus the `load_listings()` signature from `utils/data_loader.py`, and ask it to implement `search_listings()` using keyword overlap scoring. I'll verify the generated code: (a) calls `load_listings()` not a raw file read, (b) filters by both price and size before scoring, (c) returns `[]` not an exception when nothing matches, (d) drops zero-score listings. Then I'll run 3 manual queries to confirm results make sense.

**Tool 2 (suggest_outfit):** I'll give Claude the Tool 2 spec block and the wardrobe schema structure, asking it to implement with two prompt branches (empty vs. populated wardrobe). I'll verify: (a) empty wardrobe does not raise, (b) wardrobe items are formatted into the prompt by name (not just IDs), (c) the model used is `llama-3.3-70b-versatile`. I'll test with both `get_example_wardrobe()` and `get_empty_wardrobe()`.

**Tool 3 (create_fit_card):** I'll give Claude the Tool 3 spec and a sample outfit string, asking it to implement with temperature=0.9 and the empty-outfit guard. I'll verify: (a) empty string input returns the error message not an exception, (b) caption mentions item name, price, and platform, (c) running the same input twice produces different output (temperature test).

**Milestone 4 — Planning loop and state management:**

I'll share the full Architecture diagram (ASCII) and the Planning Loop + State Management sections with Claude, asking it to implement `run_agent()` in `agent.py`. Before running it, I'll check: (a) the code branches on `len(results) == 0`, not just truthiness, (b) `selected_item` is set from `results[0]` not hardcoded, (c) `outfit_suggestion` is passed into `create_fit_card` from `session`, not re-requested. Then I'll run both the happy-path and no-results test cases from the CLI test block.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Query parsing:**
The agent runs regex over the query. It extracts `max_price=30.0` from "under $30", no size pattern found so `size=None`, and `description="vintage graphic tee"` (the price clause is stripped). These are stored in `session["parsed"] = {"description": "vintage graphic tee", "size": None, "max_price": 30.0}`.

**Step 2 — search_listings called:**
`search_listings("vintage graphic tee", size=None, max_price=30.0)` is called. It loads 40 listings, drops those with price > 30, then scores by keyword overlap. Keywords "vintage", "graphic", "tee" are checked against each listing's title, description, style_tags, category, colors, and brand. Listings with score 0 are dropped. Results are sorted by score descending. The function returns 3 matches including "Vintage Band Tee — Faded Grey" ($19, score 3), "Graphic Tee — 2003 Tour Bootleg Style" ($24, score 2), and "Y2K Baby Tee — Butterfly Print" ($18, score 1). These are stored in `session["search_results"]`. `session["selected_item"]` is set to the first result: the Faded Grey Band Tee at $19.

**Step 3 — suggest_outfit called:**
`suggest_outfit(selected_item=<band_tee_dict>, wardrobe=<example_wardrobe>)` is called. The wardrobe has 10 items, so the non-empty branch runs. The LLM is prompted with the band tee's details (faded grey, vintage, grunge, band tee) and the wardrobe items (baggy straight-leg jeans, chunky white sneakers, black combat boots, etc.). The LLM returns: "Pair this faded grey band tee with your baggy straight-leg jeans and chunky white sneakers for effortless 90s streetwear. For a grungier look, swap the sneakers for your black combat boots and throw your vintage denim jacket on top." Stored in `session["outfit_suggestion"]`.

**Step 4 — create_fit_card called:**
`create_fit_card(outfit=<suggestion_string>, new_item=<band_tee_dict>)` is called. The outfit string is non-empty, so the LLM is called at temperature=0.9 with a caption prompt referencing the item (Vintage Band Tee, $19, depop) and the outfit. The LLM returns: "thrifted this faded grey band tee off depop for $19 and it literally goes with everything 🖤 baggy jeans + chunky sneakers = done. this is the outfit i will wear every day forever." Stored in `session["fit_card"]`.

**Final output to user:**
Three panels populate in the Gradio UI:
- **Top listing found:** "Vintage Band Tee — Faded Grey | $19.00 | depop | Size: L | Condition: fair | Category: tops | Faded grey band-style tee with distressed graphic..."
- **Outfit idea:** "Pair this faded grey band tee with your baggy straight-leg jeans and chunky white sneakers for effortless 90s streetwear. For a grungier look, swap the sneakers for your black combat boots..."
- **Your fit card:** "thrifted this faded grey band tee off depop for $19 and it literally goes with everything 🖤 baggy jeans + chunky sneakers = done..."
