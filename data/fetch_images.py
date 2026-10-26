"""Fetch a product photo for every registry item from the retailer's own page.

An authoring tool, run by hand, never at request time. It reads each
`registry.url`, takes the picture the shop publishes for link previews
(`og:image`, then `twitter:image`, then the largest `<img>` on the page),
downloads it, resizes it to 800px wide, saves it as WebP under
`frontend/public/registry/{id}.webp`, and writes that path into
`registry.image_url`.

    backend/.venv/bin/python data/fetch_images.py            # dry run
    backend/.venv/bin/python data/fetch_images.py --write    # save

The files are committed to the repo, so a fresh clone shows a registry full of
photographs with no network and no API key. Items that fail keep their drawn
thumbnail (see GiftImage.tsx) — nothing ever renders a broken image.

A caveat worth knowing before you add a link: this works on a **product page**
and not on a search or category page, which publishes the shop's logo instead.
Several large retailers also refuse scripted requests outright — Etsy,
KitchenAid, John Lewis, GetYourGuide and Waterstones all answered 403 or
hung up — so their items stay illustrated.
"""

from __future__ import annotations

import html as html_mod
import io
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from PIL import Image

DATA_DIR = Path(__file__).resolve().parent
REPO_ROOT = DATA_DIR.parent
DB_PATH = DATA_DIR / "bells.db"
OUT_DIR = REPO_ROOT / "frontend" / "public" / "registry"
PUBLIC_PREFIX = "/registry"

WIDTH = 800
TIMEOUT = 10.0

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

META_PATTERNS = (
    r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
)

# Share cards and logos are worse than the drawing they would replace.
JUNK = re.compile(r"(share[-_]?image|logo|placeholder|default|untitled|banner|social)", re.I)


def absolutise(src: str, page_url: str) -> str:
    # Shops entity-encode these more than you would expect: ferm living
    # publishes "https&#58;//...", so unescape before anything else.
    src = html_mod.unescape(src).strip()
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("http://"):
        return "https://" + src[len("http://"):]
    if src.startswith("/"):
        return urljoin(page_url, src)
    return src


def largest_img(html: str, page_url: str) -> str | None:
    """Last resort: the widest <img> the page declares a width for."""
    best: tuple[int, str] | None = None
    for tag in re.findall(r"<img\b[^>]*>", html, re.I):
        src = re.search(r'\bsrc=["\']([^"\']+)', tag, re.I)
        if not src or src.group(1).startswith("data:"):
            continue
        w = re.search(r'\bwidth=["\']?(\d{2,4})', tag, re.I)
        width = int(w.group(1)) if w else 0
        if JUNK.search(src.group(1)):
            continue
        if best is None or width > best[0]:
            best = (width, src.group(1))
    return absolutise(best[1], page_url) if best else None


def find_image_url(html: str, page_url: str) -> tuple[str | None, str]:
    for pattern in META_PATTERNS:
        m = re.search(pattern, html, re.I)
        if m:
            url = absolutise(m.group(1), page_url)
            if JUNK.search(url):
                return None, f"meta tag is a logo or share card ({Path(urlparse(url).path).name})"
            return url, "og:image"
    fallback = largest_img(html, page_url)
    if fallback:
        return fallback, "largest <img>"
    return None, "no image on the page"


def save_webp(raw: bytes, dest: Path) -> tuple[int, int]:
    img = Image.open(io.BytesIO(raw))
    if img.mode in ("P", "LA", "RGBA"):
        flat = Image.new("RGB", img.size, (246, 239, 229))  # --paper-warm
        flat.paste(img, mask=img.convert("RGBA").split()[-1])
        img = flat
    else:
        img = img.convert("RGB")
    if img.width > WIDTH:
        img = img.resize((WIDTH, round(img.height * WIDTH / img.width)), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "WEBP", quality=82, method=6)
    return img.size


def main() -> int:
    write = "--write" in sys.argv
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, item, url FROM registry ORDER BY id").fetchall()

    ok = 0
    with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True, http2=True) as client:
        for r in rows:
            label = f"{r['id']:>3}  {r['item'][:32]:<32}"
            if not r["url"]:
                print(f"{label}  — no link")
                continue
            try:
                page = client.get(r["url"])
                if page.status_code >= 400:
                    print(f"{label}  — page said {page.status_code}")
                    continue

                img_url, how = find_image_url(page.text, str(page.url))
                if not img_url:
                    print(f"{label}  — {how}")
                    continue

                shot = client.get(img_url)
                if shot.status_code >= 400:
                    print(f"{label}  — image said {shot.status_code}")
                    continue

                dest = OUT_DIR / f"{r['id']}.webp"
                w, h = save_webp(shot.content, dest)
                kb = dest.stat().st_size // 1024
                ok += 1
                print(f"{label}  ✓ {w}×{h} {kb}kB  via {how}")

                if write:
                    conn.execute(
                        "UPDATE registry SET image_url = ? WHERE id = ?",
                        (f"{PUBLIC_PREFIX}/{r['id']}.webp", r["id"]),
                    )
            except Exception as exc:  # one bad shop never stops the run
                print(f"{label}  — {type(exc).__name__}: {str(exc)[:60]}")

    if write:
        conn.commit()
    conn.close()

    print(f"\n{ok} of {len(rows)} items have a photo.")
    print("Items without one keep their drawn thumbnail.")
    if write:
        print(f"Saved to {OUT_DIR} and written to registry.image_url.")
        print("Re-running seed.py resets the database — put the paths in IMAGES in")
        print("seed.py so they survive a re-seed.")
    else:
        print("Dry run: files written, database untouched. Pass --write to save paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
