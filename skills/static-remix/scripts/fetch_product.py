#!/usr/bin/env python3
"""Fetch a product page and download the primary product photo(s).

For Shopify product URLs (path matches `/products/<handle>`), uses
`<base>/products/<handle>.json` to get authoritative image URLs and
pricing. Falls back to `og:image` for non-Shopify pages.

Usage:
    fetch_product.py <product_url> <out_dir>
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from urllib.parse import urlparse

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36 static-remix/1.0"
)


def fetch(url: str, binary: bool = False) -> bytes | str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", errors="replace")


def shopify_handle(url: str) -> tuple[str, str] | None:
    p = urlparse(url)
    m = re.search(r"/products/([a-zA-Z0-9\-_]+)", p.path)
    if not m:
        return None
    return f"{p.scheme}://{p.netloc}", m.group(1)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: fetch_product.py <product_url> <out_dir>")
    url, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)

    page_html = fetch(url)
    assert isinstance(page_html, str)
    with open(os.path.join(out_dir, "product_page.html"), "w") as f:
        f.write(page_html)

    image_urls: list[str] = []
    shopify_data = None
    sh = shopify_handle(url)
    if sh:
        base, handle = sh
        try:
            j = fetch(f"{base}/products/{handle}.json")
            assert isinstance(j, str)
            shopify_data = json.loads(j)
            with open(os.path.join(out_dir, "product.json"), "w") as f:
                f.write(j)
            for img in shopify_data.get("product", {}).get("images", []):
                src = img.get("src")
                if src:
                    image_urls.append(src)
        except Exception as e:
            print(f"shopify .json fetch failed: {e}", file=sys.stderr)

    if not image_urls:
        for pat in (
            r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        ):
            for m in re.finditer(pat, page_html, re.I):
                if m.group(1) not in image_urls:
                    image_urls.append(m.group(1))

    saved: list[dict] = []
    for i, img_url in enumerate(image_urls[:5], 1):
        # Shopify image CDN often serves protocol-relative URLs.
        if img_url.startswith("//"):
            img_url = "https:" + img_url
        try:
            data = fetch(img_url, binary=True)
            assert isinstance(data, bytes)
            ext = os.path.splitext(urlparse(img_url).path)[1].lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                ext = ".jpg"
            fname = f"product_{i:02d}{ext}"
            with open(os.path.join(out_dir, fname), "wb") as f:
                f.write(data)
            saved.append({"file": fname, "url": img_url})
        except Exception as e:
            print(f"image fetch failed {img_url}: {e}", file=sys.stderr)

    title = None
    price = None
    vendor = None
    body_html = None
    if shopify_data:
        p = shopify_data.get("product", {})
        title = p.get("title")
        vendor = p.get("vendor")
        body_html = p.get("body_html")
        variants = p.get("variants", [])
        if variants:
            price = variants[0].get("price")
    if not title:
        m = re.search(r"<title>([^<]+)</title>", page_html, re.I)
        if m:
            title = m.group(1).strip()

    summary = {
        "url": url,
        "title": title,
        "vendor": vendor,
        "price": price,
        "shopify": bool(shopify_data),
        "body_html_excerpt": (body_html or "")[:2000] if body_html else None,
        "images_saved": saved,
    }
    with open(os.path.join(out_dir, "product_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
