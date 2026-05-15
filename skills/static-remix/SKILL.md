---
name: static-remix
description: Turn a PDF of winning competitor static ads into on-brand recreations for the user's product. Extracts and labels source images by ad framework (US VS THEM, BOLD CLAIM, Before & After, TESTIMONIAL, etc.), fetches the user's product page and actual product photo, and generates new statics with Nano Banana Pro (gemini-3-pro-image-preview). Trigger when the user runs /static-remix or asks to "remix", "recreate", or "build statics from" a competitor ad PDF.
---

# static-remix

Pipeline that converts a PDF of winning competitor static ads into on-brand statics for the user's product using **Nano Banana Pro** (`gemini-3-pro-image-preview`).

This skill is opinionated. Follow the steps in order. Do not skip user questions and do not silently default any answer.

---

## 0. Locate the skill and inputs

Skill root: `~/.claude/skills/static-remix/`
Scripts:
- `scripts/extract_images.py` — PyMuPDF extraction + heading labeling
- `scripts/fetch_product.py` — fetch product page + product photo (Shopify-aware)
- `scripts/gemini-image-ref.sh` — Nano Banana Pro caller (text + optional reference image)

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

### Compute concepts and cost

```
concepts = T / V
cost_usd = T * 0.25
```

Print a summary table:
```
Total images:        T
Variations/concept:  V
Concepts:            T/V
Per framework:       {...}
Estimated cost:      $X.XX  (T × $0.25, Nano Banana Pro)
```

If `cost_usd > 10`, ask the user to confirm before proceeding. Use `AskUserQuestion` (yes / no).

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

Keep each teardown under ~120 words. The goal is a usable creative directive, not a literature review.

---

## 6. Production brief per concept

Write one brief per concept to `$RUN_DIR/concepts/concept_<NN>_<framework_slug>.md`:

```
Concept ID:        <NN>
Framework:         <name>
Source reference:  sources/<file>.png
Scene:             <camera, subject, composition, lighting>
Product placement: <how the user's product appears, anchored in visual_description.md>
Headline:          "<exact quoted overlay copy>"
Sub / overlay:     "<exact quoted overlay copy>"
Caption (paid):    "<feed caption>"
Pricing / offer:   <pulled verbatim from product page — leave blank if none>
Variation axis:    <ONE thing that changes between var_01 and var_02, e.g. "camera angle: 3/4 hero vs flat-lay" or "overlay wording: 'X kills your gut' vs 'Stop poisoning your gut'">
Aspect ratio:      <1:1 for feed, 4:5 for IG portrait, 9:16 for story — pick what matches the source>
```

Always cite pricing/claim copy from the fetched product data. If a claim does not appear on the product page, do not invent one.

---

## 7. Generate with Nano Banana Pro

For each concept × variation, call the helper:

```bash
~/.claude/skills/static-remix/scripts/gemini-image-ref.sh \
  --prompt "$(cat $RUN_DIR/concepts/concept_01_us_vs_them.md | <build the final prompt>)" \
  --aspect-ratio "1:1" \
  --output "$RUN_DIR/outputs/concept_01_us_vs_them_var_01.png" \
  --reference "$RUN_DIR/product/product_01.jpg"
```

### Prompt construction (per variation)

The final prompt sent to Nano Banana Pro must include, in order:

1. One-line creative direction ("Static ad in the US VS THEM framework, 1:1 feed format.")
2. Scene + composition from the brief
3. **Product visual block** copied from `visual_description.md` so the model preserves package identity
4. **Exact overlay copy**, in quotes, with placement hints ("top-left, bold sans-serif, white text on red panel")
5. The variation-axis modifier for var_01 vs var_02 (only the one axis changes)
6. Negative constraints ("no extra text, no watermarks, no distorted labels, no off-brand colors")

Always pass `--reference` pointing at the user's product photo. The reference image is what locks the package on-brand; the source PDF image informs the brief but is generally not attached as a reference unless the user opts in.

### Environment

Require `GEMINI_API_KEY` to be set. If unset, stop and ask the user to export it (`export GEMINI_API_KEY=...`) before continuing.

### Throughput

Run generations sequentially (one curl call per variation) and log a one-line status per file:
```
[03/40] concept_02_bold_claim_var_01.png ✓
```

If a single call fails, write the raw JSON response to `$RUN_DIR/outputs/<name>.error.json`, continue with the next, and report failures in the final summary.

---

## 8. Final summary

Print a compact report:
- Run folder path
- Source images extracted (count, per framework)
- Concepts written
- Images generated successfully / failed
- Total cost (`generated × $0.25`)
- Open command suggestion: `open "$RUN_DIR/outputs"` (mac) or `xdg-open` (linux)

---

## Notes for re-runs

- The skill is idempotent per run folder. Re-running creates a new dated folder; nothing in earlier runs is touched.
- If the user wants more variations of a single concept later, re-invoke just step 7 against an existing brief file.
- Do not commit `runs/` to git — it contains downloaded product imagery and API output that may be large.
