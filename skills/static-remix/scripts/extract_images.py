#!/usr/bin/env python3
"""Extract every image from a PDF and label each by the nearest section
heading above it.

Heading font is auto-detected: pick the (font, size) pair that appears
on the most pages in short (<=80 char) text spans. Ties break on larger
font size.

Usage:
    extract_images.py <pdf_path> <out_dir>

Writes:
    out_dir/<framework_slug>_NN.png   one file per extracted image
    out_dir/manifest.json             {pdf, heading_font, frameworks, images:[...]}
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict

import fitz  # PyMuPDF


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
    return s[:40] or "unknown"


def detect_heading_font(doc: fitz.Document) -> tuple[str, float]:
    """(font_name, size) that appears on the most pages in short spans."""
    font_pages: dict[tuple[str, float], set[int]] = defaultdict(set)
    for i, page in enumerate(doc):
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for line in b.get("lines", []):
                for span in line.get("spans", []):
                    text = span["text"].strip()
                    if len(text) == 0 or len(text) > 80:
                        continue
                    key = (span["font"], round(span["size"], 1))
                    font_pages[key].add(i)
    if not font_pages:
        raise SystemExit("no text spans found in PDF")
    best = max(font_pages.items(), key=lambda kv: (len(kv[1]), kv[0][1]))
    return best[0]


def collect_headings(
    doc: fitz.Document, heading_font: tuple[str, float]
) -> list[tuple[int, float, str]]:
    """List of (page_index, y_top, text) for every heading-font span."""
    out: list[tuple[int, float, str]] = []
    for i, page in enumerate(doc):
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for line in b.get("lines", []):
                # Merge spans on the same line that share the heading font.
                line_text_parts: list[str] = []
                line_y: float | None = None
                for span in line.get("spans", []):
                    text = span["text"].strip()
                    if not text:
                        continue
                    key = (span["font"], round(span["size"], 1))
                    if key == heading_font:
                        line_text_parts.append(text)
                        if line_y is None:
                            line_y = span["bbox"][1]
                if line_text_parts and line_y is not None:
                    out.append((i, line_y, " ".join(line_text_parts)))
    out.sort(key=lambda r: (r[0], r[1]))
    return out


def nearest_heading_above(
    headings: list[tuple[int, float, str]], page_idx: int, y_top: float
) -> str:
    candidate = None
    for h_page, h_y, h_text in headings:
        if (h_page, h_y) <= (page_idx, y_top):
            candidate = h_text
        else:
            break
    return candidate or "unknown"


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: extract_images.py <pdf_path> <out_dir>")
    pdf_path, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    heading_font = detect_heading_font(doc)
    headings = collect_headings(doc, heading_font)

    manifest: list[dict] = []
    counts: dict[str, int] = defaultdict(int)
    seen_xrefs: set[tuple[int, int]] = set()  # (page, xref) to dedupe placements

    for page_idx, page in enumerate(doc):
        for img in page.get_image_info(xrefs=True):
            xref = img.get("xref", 0)
            if not xref:
                continue
            bbox = img.get("bbox") or (0, 0, 0, 0)
            key = (page_idx, xref)
            if key in seen_xrefs:
                # Same image rendered twice on the same page — keep both
                # placements distinct by including bbox in dedupe.
                pass
            seen_xrefs.add(key)

            heading = nearest_heading_above(headings, page_idx, bbox[1])
            slug = slugify(heading)
            counts[slug] += 1
            fname = f"{slug}_{counts[slug]:02d}.png"

            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.n - pix.alpha >= 4:  # CMYK -> RGB
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                pix.save(os.path.join(out_dir, fname))
            except Exception as e:
                print(f"skip xref {xref} on page {page_idx + 1}: {e}", file=sys.stderr)
                counts[slug] -= 1
                continue

            manifest.append(
                {
                    "file": fname,
                    "framework": heading,
                    "framework_slug": slug,
                    "page": page_idx + 1,
                    "bbox": [round(v, 2) for v in bbox],
                }
            )

    frameworks = sorted({m["framework"] for m in manifest})
    out = {
        "pdf": pdf_path,
        "heading_font": [heading_font[0], heading_font[1]],
        "frameworks": frameworks,
        "framework_counts": {fw: sum(1 for m in manifest if m["framework"] == fw) for fw in frameworks},
        "images": manifest,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(out, f, indent=2)

    print(
        json.dumps(
            {
                "extracted": len(manifest),
                "frameworks": frameworks,
                "framework_counts": out["framework_counts"],
                "heading_font": out["heading_font"],
                "out_dir": out_dir,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
