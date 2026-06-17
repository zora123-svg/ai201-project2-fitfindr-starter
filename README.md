# FitFindr

A multi-tool AI agent that helps users find secondhand clothing and figure out how to wear it. The agent takes a natural language query, searches a mock thrift listings dataset, suggests outfit combinations using the user's wardrobe, and generates a shareable caption — all in one flow.

---

## Setup

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
# or: .venv\Scripts\activate    # Windows Command Prompt

pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_key_here
```

Run the app:

```bash
python app.py
```

Run tests:

```bash
pytest tests/
```

---

## What's Included

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # Mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # Helper functions for loading the data
├── tools.py                   # The three required tools
├── agent.py                   # Planning loop and session state
├── app.py                     # Gradio web interface
├── tests/
│   └── test_tools.py          # pytest tests for all three tools
└── planning.md                # Planning spec (filled out before coding)
```

---

## Tool Inventory

### `search_listings(description: str, size: str | None, max_price: float | None) → list[dict]`

**Purpose:** Searches the mock listings dataset and returns items matching the description, filtered by optional size and price ceiling.

**Inputs:**
- `description` (str): Keywords describing the item (e.g., `"vintage graphic tee"`). Used to score each listing by keyword overlap across title, description, category, style_tags, and brand fields.
- `size` (str | None): Size filter (e.g., `"M"`, `"XL"`). Matching is case-insensitive and substring-based — `"M"` matches `"S/M"`. Pass `None` to skip size filtering.
- `max_price` (float | None): Maximum price inclusive (e.g., `30.0`). Pass `None` to skip price filtering.

**Returns:** A list of listing dicts sorted by relevance score, highest first. Each dict contains: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str or None), `platform` (str). Returns `[]` if no matches — never raises an exception.

---

### `suggest_outfit(new_item: dict, wardrobe: dict) → str`

**Purpose:** Given the thrifted item and the user's wardrobe, asks the Groq LLM (llama-3.3-70b-versatile) to suggest 1–2 complete outfits. Falls back to general styling advice when the wardrobe is empty.

**Inputs:**
- `new_item` (dict): A listing dict returned by `search_listings`. The tool uses `title`, `price`, `platform`, `colors`, `condition`, `style_tags`, and `description` to build the prompt.
- `wardrobe` (dict): A wardrobe dict with an `items` key containing a list of wardrobe item dicts (each has `name`, `category`, `colors`, `style_tags`). The `items` list may be empty.

**Returns:** A non-empty string (4–6 sentences) with outfit suggestions. If the wardrobe is empty, returns general styling advice for the item type. If the API call fails, returns an error string prefixed with `"Could not generate outfit suggestion:"`.

---

### `create_fit_card(outfit: str, new_item: dict) → str`

**Purpose:** Generates a 2–4 sentence casual Instagram/TikTok-style caption for the outfit. Uses `temperature=1.0` to ensure varied output for different inputs.

**Inputs:**
- `outfit` (str): The outfit suggestion from `suggest_outfit`. Must be non-empty — if empty or whitespace-only, the function returns an error string immediately without calling the LLM.
- `new_item` (dict): The listing dict for the thrifted item. Used to include the item's `title`, `price`, and `platform` in the caption naturally.

**Returns:** A 2–4 sentence string written in casual first-person, mentioning the item name, price, and platform once each. No hashtags. Sounds like a real OOTD post. Returns a descriptive error string (starting with `"Error:"`) if `outfit` is empty, or `"Could not generate fit card: ..."` if the API call fails.

---

## How the Planning Loop Works

The planning loop in `run_agent()` (`agent.py`) runs sequentially with conditional branches — it does not call all tools in a fixed sequence regardless of results.

**Step-by-step conditional logic:**

1. **Parse the query.** `_parse_query()` uses regex to extract `description`, `size` (e.g., `"M"`), and `max_price` (e.g., `30.0`) from natural language. Stored in `session["parsed"]`.

2. **Call `search_listings`.** Store results in `session["search_results"]`.
   - **Branch A — results are empty AND a size filter was applied:** Automatically retry with `size=None` (stretch: retry with fallback). If this returns results, inform the user the size filter was relaxed and continue. If still empty, go to Branch B.
   - **Branch B — results are empty (no retry possible):** Set `session["error"]` to a message naming what was searched, what filters were used, and what to try differently. Return the session immediately. `suggest_outfit` and `create_fit_card` are **never called**.
   - **Branch C — results found:** Set `session["selected_item"] = results[0]`. Continue to step 3.

3. **Call `suggest_outfit`** with `session["selected_item"]` and `session["wardrobe"]`. Store result in `session["outfit_suggestion"]`.

4. **Call `create_fit_card`** with `session["outfit_suggestion"]` and `session["selected_item"]`. Store result in `session["fit_card"]`.

5. **Return the session.**

The agent's behavior changes based on what `search_listings` returns. A zero-result query produces a different output (an error with retry advice) than a matching query (a full three-tool flow). The LLM tools are only invoked when a real item has been found.

---

## Interaction Walkthrough

**User query:** `"I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"`

**Step 1 — `search_listings` called**
- Input: `description="vintage graphic tee baggy jeans chunky sneakers"`, `size=None`, `max_price=30.0`
- Why this tool: The user asked for a specific item type with a price ceiling. This is the entry point — no other tool can run without a concrete listing to work from.
- Output: A list of listings under $30 scored by keyword overlap. Top result: `"Y2K Baby Tee — $18, Depop, Good condition"` (high overlap on "vintage", "tee"). Stored in `session["selected_item"]`.

**Step 2 — `suggest_outfit` called**
- Input: `new_item=session["selected_item"]` (the Y2K Baby Tee dict), `wardrobe=get_example_wardrobe()` (10 items including baggy straight-leg jeans, chunky white sneakers, denim jacket)
- Why this tool: A listing was found. The agent now knows what item to style and what the user already owns — it passes both directly without asking the user to re-enter anything.
- Output: "Pair the Y2K Baby Tee with your Baggy straight-leg jeans for a casual streetwear look. Tuck the front slightly for shape. Layer your Vintage black denim jacket over the top for cooler days. Finish with the Chunky white sneakers." Stored in `session["outfit_suggestion"]`.

**Step 3 — `create_fit_card` called**
- Input: `outfit=session["outfit_suggestion"]`, `new_item=session["selected_item"]`
- Why this tool: An outfit suggestion exists. The agent generates the shareable caption as the final deliverable.
- Output: `"found this y2k baby tee on depop for $18 and it honestly went straight into rotation 🤍 baggy jeans, half-tuck, white chunkies — effortless."` Stored in `session["fit_card"]`.

**Final output to user:**
- **Listing panel:** Title, price, platform, size, condition, colors, style tags, and description of the Y2K Baby Tee.
- **Outfit idea panel:** The 4-sentence LLM suggestion naming specific wardrobe pieces.
- **Fit card panel:** The 1–2 sentence Instagram caption.

---

## State Management

All state lives in a single `session` dict initialized at the start of each `run_agent()` call. No global variables — each call is independent.

| Field | Set when | Passed to |
|---|---|---|
| `session["query"]` | Init | `_parse_query` |
| `session["parsed"]` | After `_parse_query` | `search_listings` call arguments |
| `session["search_results"]` | After `search_listings` | Agent checks for empty results |
| `session["selected_item"]` | After non-empty search | `suggest_outfit`, `create_fit_card` |
| `session["wardrobe"]` | Init | `suggest_outfit` |
| `session["outfit_suggestion"]` | After `suggest_outfit` | `create_fit_card` |
| `session["fit_card"]` | After `create_fit_card` | Returned to UI |
| `session["error"]` | On early exit | UI: shown in listing panel |

The item returned by `search_listings` is stored in `session["selected_item"]` and passed directly into `suggest_outfit` — the user never re-enters it. The string returned by `suggest_outfit` is stored in `session["outfit_suggestion"]` and passed directly into `create_fit_card` — again, no re-entry.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No listings match the query (filters too strict, wrong keywords, or item doesn't exist in mock data) | Sets `session["error"]` to: `"No listings found for '{description}' (filtered by size {size} and under ${price}). Try broadening your search — remove the size filter, raise your price, or use different keywords."` Returns session immediately. `suggest_outfit` and `create_fit_card` are never called. |
| `suggest_outfit` | Wardrobe is empty (`wardrobe["items"] == []`) | Sends a different LLM prompt asking for general styling advice (what kinds of pieces pair well, what era/vibe the item suits) rather than wardrobe-specific combinations. Always returns a non-empty string — never raises or returns `""`. |
| `create_fit_card` | `outfit` argument is empty string or whitespace-only | Returns: `"Error: Cannot generate a fit card without an outfit suggestion. Please provide an outfit description first."` — no LLM call, no exception raised. |

### Concrete examples from testing

**`search_listings` — no results:**
```bash
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
# Output: []
```
Running through the full agent:
```
No listings found for "designer ballgown" (filtered by size XXS and under $5).
Try broadening your search — remove the size filter, raise your price, or use different keywords.
```
Outfit and fit card panels are blank.

**`create_fit_card` — empty outfit:**
```bash
python -c "from tools import search_listings, create_fit_card; r = search_listings('vintage tee', None, 50); print(create_fit_card('', r[0]))"
# Output: Error: Cannot generate a fit card without an outfit suggestion...
```

**`suggest_outfit` — empty wardrobe:**
```bash
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe
r = search_listings('vintage graphic tee', None, 50)
print(suggest_outfit(r[0], get_empty_wardrobe()))
"
# Output: General styling advice for the item type — no crash, no empty string.
```

---

## Stretch Feature: Retry Logic with Fallback

When `search_listings` returns no results **and** a size filter was applied, the agent automatically retries with `size=None`. If the relaxed search finds items, the agent proceeds normally and informs the user:

> "No listings found for size M. Retrying without size filter — found 3 results. Showing the closest match."

If the retry also returns nothing, the full no-results error is shown. Implemented in `run_agent()` in [agent.py](agent.py).

---

## Spec Reflection

**One way planning.md helped during implementation:**

Writing the tool specs in planning.md before any code forced me to decide upfront exactly what `search_listings` would return — a list of full listing dicts, not just titles or IDs. That single decision propagated cleanly through the entire system: `suggest_outfit` and `create_fit_card` could reference `item["title"]`, `item["price"]`, and `item["platform"]` directly without any translation layer. If I had started coding without specifying the return value, I would have likely built a thin return format and refactored twice.

**One divergence from the spec, and why:**

The spec described parsing the user query with either regex or an LLM call. I initially planned to use the LLM (simpler to prompt than to write regex), but switched to regex because: (1) it's deterministic — the same query always produces the same parsed output, which makes the planning loop easier to debug; (2) it avoids an extra API round-trip that would add latency to every single search; and (3) size/price patterns in natural language are regular enough that regex handles the common cases reliably. The tradeoff is that unusual phrasing like "I've got forty dollars to spend" won't parse a price — but the agent degrades gracefully by searching without a price filter rather than crashing.

---

## AI Usage

### Instance 1: Implementing `suggest_outfit` prompt paths

**What I directed:** I gave Claude the Tool 2 spec from planning.md (inputs, return value, empty-wardrobe failure mode) and the wardrobe schema structure showing the fields on each wardrobe item. I asked it to implement the function with two separate prompt paths — one for empty wardrobe (general styling advice) and one for populated wardrobe (named-piece outfit combinations).

**What I reviewed and revised:** The generated code used a single `if/else` branch, which was structurally correct, but the wardrobe formatting loop produced a dense comma-separated string on one line. I rewrote the wardrobe formatting to a newline-separated bullet list — `"- Name (category): colors ..., style ..."` — which is clearer for the LLM to parse when the wardrobe has 10 items. I also reduced `max_tokens` from 600 to 400 to keep outfit suggestions concise and actionable rather than verbose.

### Instance 2: Implementing the planning loop

**What I directed:** I gave Claude the Architecture diagram from planning.md (ASCII art showing the full sequential flow including the early-exit branch on empty results) alongside the Planning Loop and State Management spec sections. I asked it to implement `run_agent()` following the numbered steps in the file.

**What I reviewed and revised:** The generated code placed the empty-results check after calling `suggest_outfit`, which would have passed `None` as the item into that function. I moved the early-exit branch to immediately after `search_listings` returns, before any LLM tool is called — matching the diagram. I also added the retry-with-fallback logic (stretch feature) myself, since it wasn't in the diagram at the time; the generated code had no retry mechanism.
