# static-remix

Claude Code skill that turns a PDF of winning competitor static ads into
on-brand recreations for your product using **Nano Banana Pro**
(`gemini-3-pro-image-preview`).

## Install

The canonical install location is `~/.claude/skills/static-remix/`. To
install from this repo:

```bash
mkdir -p ~/.claude/skills
cp -r skills/static-remix ~/.claude/skills/
chmod +x ~/.claude/skills/static-remix/scripts/*.sh \
         ~/.claude/skills/static-remix/scripts/*.py
```

Requirements:

- Python 3 with `PyMuPDF` (`pip install PyMuPDF`)
- `curl`
- `GEMINI_API_KEY` exported in your shell

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
    ├── fetch_product.py           # product page + photo (Shopify-aware)
    └── gemini-image-ref.sh        # Nano Banana Pro caller
```

Run artifacts land under `~/.claude/skills/static-remix/runs/<YYYYMMDD-HHMM>/`
and are not tracked by git.
