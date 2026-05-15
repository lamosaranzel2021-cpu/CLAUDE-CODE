---
name: static-remix
description: Turn a PDF of winning competitor static ads into on-brand recreations for the user's product. Extracts and labels source images by ad framework (US VS THEM, BOLD CLAIM, Before & After, TESTIMONIAL, etc.), fetches the user's product page and actual product photo, and generates new statics with the Higgsfield MCP (marketing_studio_image / nano_banana_2 / soul_2). Trigger when the user runs /static-remix or asks to "remix", "recreate", or "build statics from" a competitor ad PDF.
---

# static-remix

Pipeline that converts a PDF of winning competitor static ads into on-brand statics for the user's product using the **Higgsfield MCP** (`mcp__41e13fd3-0f42-483a-b467-2a47082f2e92__*`).

This skill is opinionated. Follow the steps in order. Do not skip user questions and do not silently default any answer.

---

## 0. Locate the skill and inputs

Skill root: `~/.claude/skills/static-remix/`
Scripts:
- `scripts/extract_images.py` — PyMuPDF extraction + heading labeling
- `scripts/fetch_product.py` — fetch product page + product photo (Shopify-aware)

No image-gen API key needed — all generation goes through the Higgsfield MCP. Verify the MCP is connected by listing workspaces:

```
mcp__41e13fd3-0f42-483a-b467-2a47082f2e92__list_workspaces
```

If multiple workspaces are returned, ask the user which one to use and call `select_workspace` with that `workspace_id`. If only one is returned, proceed.

The user will give you a PDF path in their message. If they don't, ask for it.

---

## 1. Create the dated run folder

```bash
RUN_DIR="$HOME/.claude/skills/static-remix/runs/$(date +%Y%m%d-%H%M)"
mkdir -p "$RUN_DIR"/{sources,product,concepts,outputs}
```

Save this path; every subsequent artifact goes here.

---

## 2. Extract and label every PDF image

```bash
python3 ~/.claude/skills/static-remix/scripts/extract_images.py "<PDF_PATH>" "$RUN_DIR/sources"
```

The script:
- Auto-detects the heading font by picking the (font, size) pair that appears on the most pages in short (<=80 char) text spans. Ties break on larger font size.
- Walks every image placement in reading order and labels it with the nearest heading **above** it on the same or earlier page.
- Writes images as `<framework_slug>_NN.png` and a `manifest.json` with `{file, framework, framework_slug, page, bbox}` per image.

Read `manifest.json` and confirm which frameworks were detected before continuing.

---

## 3. REQUIRED user questions — never skip, never default

Ask all four via **one** `AskUserQuestion` call (multi-question form). Every question is required on every run.

**a. Product URL** — required, no default. If the user gives a non-URL, ask again.

**b. Total images** — common values: 10, 25, 50, 100. Free-text via "Other" allowed.

**c. Variations per concept** — usually 2. One axis changes between `var_01` and `var_02` (camera angle, overlay wording, color treatment, model, etc.).

**d. Per-framework counts** — list the frameworks you detected from `manifest.json` and ask the user how many to produce of each. Offer:
   - **Even split across all detected frameworks**
   - **Custom split** (user enters e.g. "20 US VS THEM, 10 BOLD CLAIM, 10 Before & After, 10 TESTIMONIAL")

### Validation

Let `T` = total images, `V` = variations per concept, `f_i` = count for framework i.

- Each `f_i` must be a multiple of `V` (so it divides cleanly into concepts).
- `sum(f_i) == T` must hold exactly.

If validation fails, show the user the mismatch (e.g. "you asked for 50 total but the per-framework counts sum to 48; 2 short") and ask them to fix it. Do not silently adjust.

### Compute concepts and preflight credits

```
concepts = T / V
```

Print a summary table:
```
Total images:        T
Variations/concept:  V
Concepts:            T/V
Per framework:       {...}
```

Then call the Higgsfield credit check:

```
mcp__41e13fd3-0f42-483a-b467-2a47082f2e92__balance
mcp__41e13fd3-0f42-483a-b467-2a47082f2e92__show_plans_and_credits
```

Show the user current credit balance and the planned image count. If the balance looks low for `T` images, warn them and ask to confirm before generating. (Higgsfield charges in credits and per-model cost varies — `marketing_studio_image` does not support `get_cost` preflight, so use `balance` as the budget gate.)

---

## 4. Fetch the product page **and** the product photo

```bash
python3 ~/.claude/skills/static-remix/scripts/fetch_product.py "<PRODUCT_URL>" "$RUN_DIR/product"
```

This:
- Downloads the HTML page.
- If the URL looks like a Shopify product (`/products/<handle>`), fetches `<base>/products/<handle>.json` and saves authoritative image URLs from `product.images[].src`.
- Falls back to `og:image` otherwise.
- Saves the first 5 images as `product_01.<ext>` … and writes a `product_summary.json` with `{title, price, images_saved}`.

### CRITICAL — view the photo, do not guess

Open `product_01.<ext>` with the **Read tool** (Claude must actually look at the image). Then write `$RUN_DIR/product/visual_description.md` covering at minimum:

- Bottle / container color and material (glass, frosted, opaque plastic, etc.)
- Cap color and finish
- Label background color, dominant accent colors, brand palette in hex if obvious
- Label typography — serif vs sans, weight, hierarchy of the brand name vs claim
- Visible pill / softgel / liquid color if applicable
- Any iconography or seals
- Overall mood (clinical, premium, playful, earthy, …)

This description is what later prompts will use to keep generations on-brand. Pull pricing, claims, and offer copy **verbatim** from `product_summary.json` and the HTML — never invent numbers.

### Upload the product photo to Higgsfield as a reusable reference

The product photo needs a Higgsfield media UUID before `generate_image` can use it as a reference. One time per run:

1. Get a presigned upload URL:
   ```
   mcp__41e13fd3-0f42-483a-b467-2a47082f2e92__media_upload
       filename: "product_01.jpg" (or .png/.webp matching the actual file)
       content_type: "image/jpeg" (or "image/png", "image/webp")
   ```
   Response contains `media_id` and `upload_url`.

2. PUT the bytes to that URL:
   ```bash
   curl -X PUT --data-binary @"$RUN_DIR/product/product_01.jpg" \
        -H "Content-Type: image/jpeg" \
        "<upload_url>"
   ```

3. Confirm:
   ```
   mcp__41e13fd3-0f42-483a-b467-2a47082f2e92__media_confirm
       media_id: "<from step 1>"
       type: "image"
   ```

Save the confirmed `media_id` (UUID) to `$RUN_DIR/product/product_media_id.txt`. This is the reference you'll pass on every generation.

---

## 5. Teardowns of each selected source example

For each concept you're about to produce, pick the best matching source image for that framework from `manifest.json` (you can reuse a source across concepts within the same framework when needed).

For each unique source you'll reference, open it with the Read tool and write a short teardown to `$RUN_DIR/sources/teardowns/<framework_slug>_<NN>.md`:

```
Framework: <name>
What it does: <1-2 sentences on the psychological hook>
Why it works: <pattern interrupt / social proof / loss aversion / curiosity gap / etc.>
Keep:  <specific visual or copy elements to preserve>
Swap:  <what to replace with the user's brand>
```

Keep each teardown under ~120 words.

---

## 6. Production brief per concept

Write one brief per concept to `$RUN_DIR/concepts/concept_<NN>_<framework_slug>.md`:

```
Concept ID:        <NN>
Framework:         <name>
Source reference:  sources/<file>.png
Model:             marketing_studio_image  (default; switch to nano_banana_2 if heavy text/diagrams; soul_2 for portrait/UGC/testimonial)
Scene:             <camera, subject, composition, lighting>
Product placement: <how the user's product appears, anchored in visual_description.md>
Headline:          "<exact quoted overlay copy>"
Sub / overlay:     "<exact quoted overlay copy>"
Caption (paid):    "<feed caption>"
Pricing / offer:   <pulled verbatim from product page — leave blank if none>
Variation axis:    <ONE thing that changes between var_01 and var_02>
Aspect ratio:      <1:1 for feed, 4:5 for IG portrait, 9:16 for story>
```

Pricing/claim copy must come from the fetched product data. If a claim does not appear on the product page, do not invent one.

### Model selection cheat sheet

- `marketing_studio_image` — default for commercial/product/ad statics
- `nano_banana_2` — when the static is dominated by big-text overlays, diagrams, or "before/after" labels (sharpest text rendering)
- `soul_2` — when the static features a person / UGC / testimonial framing

Before generating, optionally call `models_explore action=get model_id=<id>` once per model you'll use, to confirm the supported `aspect_ratios` and the `medias[].roles` value to pass for the product reference.

---

## 7. Generate with the Higgsfield MCP

For each concept × variation, call:

```
mcp__41e13fd3-0f42-483a-b467-2a47082f2e92__generate_image
    params:
      model: "marketing_studio_image"        # or nano_banana_2 / soul_2 per brief
      prompt: "<final assembled prompt>"
      aspect_ratio: "1:1"                    # from the brief
      count: 1
      medias:
        - value: "<product_media_id UUID>"
          role: "<role string from models_explore — usually 'reference' or 'product'>"
```

### Prompt construction (per variation)

The final `prompt` must include, in order:

1. One-line creative direction ("Static ad in the US VS THEM framework, 1:1 feed format.")
2. Scene + composition from the brief
3. **Product visual block** copied from `visual_description.md` so the model preserves package identity
4. **Exact overlay copy**, in quotes, with placement hints ("top-left, bold sans-serif, white text on red panel")
5. The variation-axis modifier for var_01 vs var_02 (only the one axis changes)
6. Negative constraints ("no extra text, no watermarks, no distorted labels, no off-brand colors")

Always pass the product `media_id` in `medias[]`. The reference image is what locks the package on-brand.

### Saving and tracking results

`generate_image` returns one or more `job_id`s and asset URLs. For each call:

1. Append a row to `$RUN_DIR/outputs/manifest.jsonl`:
   ```json
   {"file":"concept_01_us_vs_them_var_01","concept":"01","framework":"us_vs_them","variation":1,"model":"marketing_studio_image","job_id":"<uuid>","status":"submitted"}
   ```
2. If the response includes a direct asset URL, download with curl to `$RUN_DIR/outputs/concept_<NN>_<slug>_var_<MM>.png`.
3. If only a job id is returned, call:
   ```
   mcp__41e13fd3-0f42-483a-b467-2a47082f2e92__job_display ids: ["<uuid>"]
   ```
   to surface the result in the UI, then update the manifest row with the final URL once available.

Log one status line per variation:
```
[03/40] concept_02_bold_claim_var_01  job=<short-uuid>  ✓
```

If a call errors, append `{"status":"error","error":"<message>"}` to the manifest row, continue with the next, and surface failures in the final summary.

### Throughput

Run generations sequentially. Higgsfield jobs are async; do not fire them all in parallel without a queue check.

---

## 8. Final summary

Print a compact report:
- Run folder path
- Source images extracted (count, per framework)
- Concepts written
- Images generated successfully / failed
- Remaining Higgsfield credit balance (call `balance` again)
- Open command suggestion: `open "$RUN_DIR/outputs"` (mac) or `xdg-open` (linux)

---

## Notes for re-runs

- The skill is idempotent per run folder. Re-running creates a new dated folder; nothing in earlier runs is touched.
- If the user wants more variations of a single concept later, re-invoke just step 7 against an existing brief file (the product `media_id` from `product_media_id.txt` is still valid).
- Do not commit `runs/` to git — it contains downloaded product imagery and API output that may be large.
