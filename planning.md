# FitFindr — planning.md

---

## Tools

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for items that match a keyword description, an optional size filter, and an optional maximum price. Returns a ranked list of matching items sorted by relevance (keyword overlap), or an empty list if nothing matches.

**Input parameters:**
- `description` (str): Keywords describing what the user wants (e.g., "vintage graphic tee"). Used to score items by keyword overlap against title, description, category, style_tags, and brand.
- `size` (str | None): Size to filter by (e.g., "M", "XL"). Matching is case-insensitive and substring-based so "M" matches "S/M". Pass None to skip size filtering.
- `max_price` (float | None): Maximum price inclusive (e.g., 30.0). Pass None to skip price filtering.

**What it returns:**
A list of listing dicts sorted by relevance score, highest first. Each dict has: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str or None), `platform` (str). Returns `[]` on no match — never raises.

**What happens if it fails or returns nothing:**
The agent sets `session["error"]` to a message like: "No listings found for 'designer ballgown' (filtered by size XXS and under $5). Try broadening your search — remove the size filter, raise your price, or use different keywords." The agent returns the session immediately and does not proceed to `suggest_outfit`.

---

### Tool 2: suggest_outfit

**What it does:**
Uses the Groq LLM (llama-3.3-70b-versatile) to suggest 1–2 complete outfits combining the new thrifted item with pieces from the user's existing wardrobe. If the wardrobe is empty, it provides general styling advice instead.

**Input parameters:**
- `new_item` (dict): The listing dict for the item the user is considering (from `search_listings`). Used to describe the item's name, price, platform, colors, condition, and style tags in the prompt.
- `wardrobe` (dict): A wardrobe dict with an `items` key containing a list of wardrobe item dicts (each with `name`, `category`, `colors`, `style_tags`). May have an empty `items` list.

**What it returns:**
A non-empty string (4–6 sentences) describing 1–2 outfits. If the wardrobe is empty, it describes general styling directions for the new piece. If the LLM call fails, returns an error string prefixed with "Could not generate outfit suggestion:".

**What happens if it fails or returns nothing:**
If `wardrobe['items']` is empty, the LLM is prompted for general styling advice rather than wardrobe-specific combinations — so the tool always returns a useful string. If the API call itself fails, the function returns an error string; the agent displays this in the outfit panel without crashing.

---

### Tool 3: create_fit_card

**What it does:**
Uses the Groq LLM to generate a 2–4 sentence casual Instagram/TikTok-style caption for the outfit. Each call uses temperature=1.0 to ensure varied output. Guards against an empty outfit string.

**Input parameters:**
- `outfit` (str): The outfit suggestion string from `suggest_outfit()`. Must be non-empty; if it is empty or whitespace-only, the function returns an error string immediately without calling the LLM.
- `new_item` (dict): The listing dict for the thrifted item, used to include the item name, price, and platform in the caption naturally.

**What it returns:**
A 2–4 sentence string that sounds like a real OOTD post — casual tone, specific styling details, item name/price/platform mentioned once each, no hashtags. Returns a descriptive error string (starting with "Error:") if `outfit` is empty, or "Could not generate fit card: ..." if the API call fails.

**What happens if it fails or returns nothing:**
If `outfit` is empty/whitespace, returns: "Error: Cannot generate a fit card without an outfit suggestion. Please provide an outfit description first." If the LLM API call raises an exception, returns the exception message as a string. The agent never crashes — the error string is displayed in the fit card panel.

---

### Additional Tools (if any)

None for the required implementation.

---

## Planning Loop

The agent runs a strict sequential loop with a single early-exit branch:

1. **Parse** the raw query with regex to extract `description`, `size`, and `max_price`. Store in `session["parsed"]`.
2. **Call `search_listings`** with parsed parameters. Store results in `session["search_results"]`.
   - **Branch: empty results** → set `session["error"]` with a helpful retry message and `return session` immediately. Do NOT proceed.
   - **Branch: results found** → set `session["selected_item"] = results[0]` and continue.
3. **Call `suggest_outfit`** with `session["selected_item"]` and the wardrobe. Store in `session["outfit_suggestion"]`.
4. **Call `create_fit_card`** with `session["outfit_suggestion"]` and `session["selected_item"]`. Store in `session["fit_card"]`.
5. **Return session.**

The loop does not call all tools unconditionally — step 3 and 4 are only reached if `search_listings` returns at least one result. If `suggest_outfit` returns an error string (API failure), `create_fit_card` will guard against that since an error message is still a non-empty string with real content; however the fit card will be based on the error text, which is acceptable since the user sees both panels.

---

## State Management

All state is held in a single `session` dict initialized by `_new_session()`. Fields and their lifecycle:

| Field | Set when | Used by |
|---|---|---|
| `query` | Initialization | `_parse_query` |
| `parsed` | After `_parse_query` | `search_listings` call |
| `search_results` | After `search_listings` | Agent to check for empty results |
| `selected_item` | After non-empty search | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | Initialization | `suggest_outfit` |
| `outfit_suggestion` | After `suggest_outfit` | `create_fit_card` |
| `fit_card` | After `create_fit_card` | Returned to UI |
| `error` | On early exit | UI: displayed in listing panel |

The session dict is passed into `run_agent` and returned at the end. `app.py` reads `session["error"]`, `session["selected_item"]`, `session["outfit_suggestion"]`, and `session["fit_card"]` to populate the three Gradio output panels.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No results match the query (wrong size, price too low, irrelevant keywords) | Sets `session["error"]` to: "No listings found for '{description}' (filtered by size {size} and under ${price}). Try broadening your search — remove the size filter, raise your price, or use different keywords." Returns session immediately; `suggest_outfit` and `create_fit_card` are never called. |
| `suggest_outfit` | Wardrobe is empty (`wardrobe['items'] == []`) | Sends a different LLM prompt asking for general styling advice rather than wardrobe-specific outfits. Always returns a non-empty string; never raises or returns `""`. |
| `create_fit_card` | `outfit` is empty or whitespace-only | Returns the string: "Error: Cannot generate a fit card without an outfit suggestion. Please provide an outfit description first." — no LLM call is made, no exception is raised. |

---

## Architecture

```
User query (natural language)
        │
        ▼
  _parse_query()
  ┌──────────────────────────────────────────┐
  │  Regex extracts:                         │
  │  description, size, max_price            │
  └──────────────────────────────────────────┘
        │
        │  session["parsed"]
        ▼
  search_listings(description, size, max_price)
        │
        ├─── results == [] ──────────────────────────────────────────────┐
        │                                                                │
        │  results != []                                                 │
        ▼                                                                │
  session["search_results"] = results                                   │
  session["selected_item"]  = results[0]                                │
        │                                                                │
        ▼                                                                │
  suggest_outfit(selected_item, wardrobe)                               │
        │                                                                │
        ├─── wardrobe["items"] == []                                     │
        │         └─► LLM: general styling advice                       │
        │                                                                │
        ├─── wardrobe["items"] != []                                     │
        │         └─► LLM: outfit using named wardrobe pieces            │
        │                                                                │
  session["outfit_suggestion"] = "..."                                  │
        │                                                                │
        ▼                                                                │
  create_fit_card(outfit_suggestion, selected_item)                     │
        │                                                                │
        ├─── outfit is empty/whitespace ──► return error string         │
        │                                                                │
        └─── LLM generates caption (temperature=1.0)                    │
                                                                        │
  session["fit_card"] = "..."                                           │
        │                                                                │
        ▼                                                                ▼
  Return session ◄──────────────────── session["error"] = helpful msg
                                        session["fit_card"] = None
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

- **search_listings**: Gave Claude the Tool 1 spec (description, input parameters, return value, failure mode) and the `load_listings()` signature from `data_loader.py`. Asked it to implement the function using keyword overlap scoring. Verified the generated code: checked that all three parameters are used, that `load_listings()` is called (not reimplemented), that empty results return `[]` not an exception, and that scoring uses multi-field search. Tested with 3 queries: "vintage graphic tee" (should return items), "designer ballgown size XXS under $5" (should return []), "jacket under $25" (all results must be ≤$25).

- **suggest_outfit**: Gave Claude the Tool 2 spec and the wardrobe schema structure. Asked it to write two separate prompt paths: one for empty wardrobe, one for populated wardrobe that references specific item names. Verified that `wardrobe['items']` is checked before building the prompt, that the LLM model is `llama-3.3-70b-versatile`, and that exceptions are caught and returned as strings.

- **create_fit_card**: Gave Claude the Tool 3 spec and the Instagram caption style guidelines. Asked it to use `temperature=1.0` and include a guard on empty outfit strings. Verified the empty-input guard returns an error string (not raises), that the prompt includes item name, price, and platform, and ran it 3 times on the same input to confirm varied output.

**Milestone 4 — Planning loop and state management:**

- Gave Claude the Architecture diagram above plus the Planning Loop and State Management sections. Asked it to implement `run_agent()` in `agent.py` following the exact step numbering. Verified: the function returns early when `search_results` is empty, `selected_item` is set before calling `suggest_outfit`, `outfit_suggestion` is stored before `create_fit_card`, and the returned session contains all expected keys.

- For `_parse_query`, chose regex over LLM to avoid an extra API call for a deterministic task. Verified with 5 sample queries that size and price are extracted correctly.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Parse query:**
`_parse_query` extracts: `description="I'm looking for a vintage graphic tee. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it"` (after removing price/size phrases), `size=None`, `max_price=30.0`. Stored in `session["parsed"]`.

**Step 2 — Search listings:**
`search_listings("vintage graphic tee...", size=None, max_price=30.0)` is called. All listings over $30 are dropped. Remaining items are scored by keyword overlap with "vintage", "graphic", "tee". Items with score > 0 are returned sorted highest first. The top result might be "Faded Band Tee — $22, Depop, Good condition." Stored in `session["search_results"]`; `session["selected_item"]` = first result.

**Step 3 — Suggest outfit:**
`suggest_outfit(selected_item, example_wardrobe)` is called. The wardrobe has 10 items including baggy jeans, a denim jacket, and chunky sneakers. The LLM prompt includes the item details and all wardrobe items by name. The LLM returns something like: "Pair this faded band tee with your wide-leg jeans and platform Docs for a 90s grunge look. Roll the sleeves once and give the front a slight half-tuck for shape. Add the denim jacket over the top on cooler days."

**Step 4 — Create fit card:**
`create_fit_card(outfit_suggestion, selected_item)` is called. `outfit` is non-empty, so the LLM is called at temperature=1.0. Returns: "thrifted this faded band tee off depop for $22 and it slotted right into my rotation 🖤 wide-legs, half-tuck, a lil grunge. full look later."

**Final output to user:**
- **Listing panel**: Title, price ($22), platform (Depop), size, condition, colors, style tags, and description.
- **Outfit idea panel**: The 3-sentence LLM suggestion referencing specific wardrobe pieces by name.
- **Fit card panel**: The 2-sentence Instagram caption with the casual tone and the item's price/platform.

**Error path (no results):** If the user searched "designer ballgown size XXS under $5", `search_listings` returns `[]`. The agent sets `session["error"]` = "No listings found for 'designer ballgown' (filtered by size XXS and under $5). Try broadening your search..." and returns immediately. The listing panel shows the error; outfit and fit card panels are blank.
