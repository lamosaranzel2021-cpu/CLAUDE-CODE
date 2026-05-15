# static-remix

Claude Code skill that turns a PDF of winning competitor static ads into
on-brand recreations for your product using the **Higgsfield MCP**
(`marketing_studio_image`, `nano_banana_2`, `soul_2`).

## Install

The canonical install location is `~/.claude/skills/static-remix/`. To
install from this repo:

```bash
mkdir -p ~/.claude/skills
cp -r skills/static-remix ~/.claude/skills/
chmod +x ~/.claude/skills/static-remix/scripts/*.py
```

Requirements:

- Python 3 with `PyMuPDF` (`pip install PyMuPDF`)
- `curl` (used to PUT the product photo to Higgsfield's presigned URL)
- The **Higgsfield MCP** connected to Claude Code (no env vars / API
  keys needed in your shell; auth is handled by the MCP)

## Run

```
/static-remix
```

…and follow the prompts. See `skills/static-remix/SKILL.md` for the full
pipeline.

## Layout

```
skills/static-remix/
├── SKILL.md                       # playbook Claude follows
└── scripts/
    ├── extract_images.py          # PyMuPDF extraction + heading labeling
    └── fetch_product.py           # product page + photo (Shopify-aware)
```

Image generation goes through MCP tool calls
(`generate_image`, `media_upload`, `media_confirm`, `job_display`) — no
bash helper.

Run artifacts land under `~/.claude/skills/static-remix/runs/<YYYYMMDD-HHMM>/`
and are not tracked by git.
