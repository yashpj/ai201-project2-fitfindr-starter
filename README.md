# FitFindr

FitFindr is an AI-powered secondhand shopping assistant that finds thrifted items matching your description, suggests outfit combinations based on your wardrobe, and generates a shareable social media caption — all in one interaction.

---

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Add your GROQ API key** (get a free key at [console.groq.com](https://console.groq.com)):
   ```bash
   cp .env.example .env
   # Edit .env and set GROQ_API_KEY=your_key_here
   ```

3. **Run the app:**
   ```bash
   python3 app.py
   ```
   Open the URL shown in the terminal (usually http://localhost:7860).

4. **Run tests:**
   ```bash
   pytest tests/ -v
   ```

---

## Project Structure

```
fitfindr/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
├── tools.py                   # Three standalone tools
├── agent.py                   # Planning loop (run_agent)
├── app.py                     # Gradio interface
├── tests/
│   └── test_tools.py          # 18 pytest tests
├── planning.md                # Spec written before implementation
└── requirements.txt
```

---

## Tool Inventory

### Tool 1: `search_listings(description, size, max_price)`

| Parameter | Type | Description |
|---|---|---|
| `description` | `str` | Natural language keywords (e.g. `"vintage graphic tee"`) |
| `size` | `str \| None` | Size filter — case-insensitive substring match; `None` skips filtering |
| `max_price` | `float \| None` | Inclusive price ceiling in USD; `None` skips filtering |

**Returns:** `list[dict]` — matching listing dicts sorted by relevance score (empty list if no matches, never raises).

**Purpose:** Searches the 40-item mock dataset by scoring each listing's keyword overlap with `description` across title, description, style_tags, category, colors, and brand. Filters by price and size first, drops zero-score listings, sorts highest-score first.

---

### Tool 2: `suggest_outfit(new_item, wardrobe)`

| Parameter | Type | Description |
|---|---|---|
| `new_item` | `dict` | A listing dict — the item being considered |
| `wardrobe` | `dict` | Dict with an `items` key (list of wardrobe item dicts, may be empty) |

**Returns:** `str` — 2–4 sentence outfit suggestion, never empty.

**Purpose:** Calls the Groq LLM (`llama-3.3-70b-versatile`) to suggest 1–2 outfit combinations. If the wardrobe has items, names specific wardrobe pieces. If empty, gives general styling advice for the item type. Handles the empty wardrobe case internally — never raises.

---

### Tool 3: `create_fit_card(outfit, new_item)`

| Parameter | Type | Description |
|---|---|---|
| `outfit` | `str` | Outfit suggestion from `suggest_outfit`; empty string returns an error string |
| `new_item` | `dict` | Listing dict — used for title, price, and platform in the caption |

**Returns:** `str` — 2–4 sentence casual OOTD caption mentioning item name, price, and platform; or an error string if `outfit` is empty.

**Purpose:** Calls the Groq LLM at temperature 0.9 to generate an authentic Instagram/TikTok caption. Output varies across runs due to higher temperature. Guards against empty `outfit` without raising.

---

## How the Planning Loop Works

The planning loop (`run_agent()` in `agent.py`) is a **deterministic sequential pipeline** with a single early-exit branch:

```
Step 1  Parse query with regex → extract description, size, max_price
Step 2  search_listings(description, size, max_price)
            │
            ├─ results == []  →  session["error"] = "No listings found..."
            │                    return session  ◄── early exit, no LLM called
            │
            └─ results found  →  session["selected_item"] = results[0]
Step 3  suggest_outfit(selected_item, wardrobe)
            → session["outfit_suggestion"] = result
Step 4  create_fit_card(outfit_suggestion, selected_item)
            → session["fit_card"] = result
Step 5  return session
```

**Key conditional:** After `search_listings`, the loop checks `if not results`. If empty, it sets a descriptive error message in `session["error"]` (naming what was searched and suggesting alternatives) and returns immediately. `suggest_outfit` and `create_fit_card` are never called. This prevents passing empty input to LLM tools.

---

## State Management

All state lives in a single `session` dict initialized per call to `run_agent()`. No global state; each interaction is fully isolated.

| Field | Type | Set by | Consumed by |
|---|---|---|---|
| `query` | str | initialization | `_parse_query` |
| `parsed` | dict | `_parse_query` | `search_listings` arguments |
| `search_results` | list[dict] | `search_listings` | early-exit check, `selected_item` |
| `selected_item` | dict \| None | planning loop | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | dict | initialization | `suggest_outfit` |
| `outfit_suggestion` | str \| None | `suggest_outfit` | `create_fit_card` argument |
| `fit_card` | str \| None | `create_fit_card` | final output panel |
| `error` | str \| None | early-exit branch | caller checks first |

Each tool's live return value is stored in `session` immediately, and the next tool reads from `session` — no re-querying, no hardcoded intermediate values.

---

## Error Handling

### `search_listings` — no results match

**Trigger:** All listings filtered out by price/size/keywords, or query describes something not in the dataset.

**Agent response:** Sets `session["error"]`:
> "No listings found for 'designer ballgown' (size: XXS, under $5). Try broader keywords, a different size, or raise your price ceiling."

Returns early. The Gradio UI shows this in the listing panel; outfit and fit card panels stay empty.

**Verified with:**
```bash
python3 -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
# []
```

---

### `suggest_outfit` — empty wardrobe

**Trigger:** User selects "Empty wardrobe (new user)" or `wardrobe['items'] == []`.

**Agent response:** Calls the LLM with a general styling prompt (no specific wardrobe pieces to reference). Returns a string like "This piece works great with straight-leg jeans and chunky sneakers for a 90s streetwear vibe." Never raises, never returns empty string.

**Verified with:**
```bash
python3 -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(suggest_outfit(results[0], get_empty_wardrobe()))
"
# Non-empty general styling advice
```

---

### `create_fit_card` — empty outfit string

**Trigger:** `outfit` argument is `""` or whitespace-only.

**Agent response:** Returns `"Could not generate fit card: outfit suggestion was empty."` without calling the LLM. No exception raised.

**Verified with:**
```bash
python3 -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', results[0]))
"
# "Could not generate fit card: outfit suggestion was empty."
```

---

## Spec Reflection

**One way the spec helped:** Writing the planning loop's conditional logic explicitly in `planning.md` before writing any code made `run_agent()` nearly mechanical to implement. The exact branch condition and the exact error message format were already decided, so there was no ambiguity when writing the actual function — I just translated prose into code.

**One way implementation diverged from spec:** The query parser was planned as a simple two-regex solution (one for price, one for size). In practice, users write queries in many forms — "I'm looking for a vintage tee under $30, what's out there?" — so I had to add a `filler_patterns` list with 7 regex substitutions to strip conversational phrases before building the description keyword string. The spec captured the right approach but underestimated how much cleanup real queries require.

---

## AI Tool Usage

### Instance 1: `search_listings` scoring logic

**Given to Claude:** The Tool 1 spec block from `planning.md` (inputs, return values, failure mode), plus `load_listings()` signature, with the instruction to score by keyword overlap across multiple listing fields and drop zero-score results.

**Claude produced:** The filter chain and scoring loop structure. The generated code correctly called `load_listings()`, applied price/size filters first, then scored.

**What I changed:** The initial version joined `style_tags` as a single comma-separated string before searching, which would miss "graphic tee" as a two-word tag if split incorrectly. I changed it to check each tag/color as an independent substring against the full searchable text, which is more robust.

---

### Instance 2: Planning loop in `agent.py`

**Given to Claude:** The full Architecture ASCII diagram from `planning.md` and the Planning Loop and State Management sections describing the exact step sequence and branch condition.

**Claude produced:** The `run_agent()` function with the correct early-exit branch and sequential tool calls.

**What I changed:** The generated version wrapped each tool call in `try/except Exception` blocks that silently returned empty strings on any error. I removed these — the tools handle their own failure modes via return values, and blanket exception catching would hide real bugs during development. Only the tools' own internal guards remain.

---

### Instance 3: Query parser regex

**Given to Claude:** Six sample queries from the Gradio examples and the instruction to write a regex parser extracting price, size, and description from natural language.

**Claude produced:** The two core regex patterns for price and size extraction.

**What I changed:** Added the `filler_patterns` list to strip conversational phrases ("I'm looking for", "What's out there", "how would I style it") that would otherwise pollute the description keyword string and reduce search quality.
