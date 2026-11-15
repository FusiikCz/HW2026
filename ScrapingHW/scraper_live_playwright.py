#!/usr/bin/env python3
"""Live-DOM scraper for a Discourse topic using Playwright (selectors from blueprint section 3).

Why this path exists: the server HTML gives no global post id, so only the live DOM exposes
`article[data-post-id]`. Discourse virtualizes the post stream, therefore records must be
collected incrementally while scrolling and de-duplicated by the global post id.

Install:
    pip install playwright && playwright install chromium

Usage:
    python3 scraper_live_playwright.py --url https://discuss.python.org/t/error-installing-libcst/109739 --out posts_live.json

NOTE: this script was NOT executed in the assessment sandbox (no Playwright browser build there;
browser launches are routed through the managed Chromium). The identical extraction JavaScript
was executed and validated against the live DOM in that managed Chromium - see
devtools_paste_section4.js, live_extract_css.js, live_extract_xpath.js and posts_live.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

EXTRACT_JS = r"""
() => {
  const posts = Array.from(document.querySelectorAll('article[data-post-id]'));
  return posts.map(post => {
    const author = post.querySelector('.names a[data-user-card]');
    const time = post.querySelector('.post-date .relative-date');
    const link = post.querySelector('a.post-date');
    const rawTime = time ? time.getAttribute('data-time') : null;
    const body = post.querySelector('.cooked');
    return {
      post_id: post.getAttribute('data-post-id'),
      dom_id: post.id,
      author: author ? author.getAttribute('data-user-card') : null,
      author_name: author ? author.innerText.trim() : null,
      profile: author ? new URL(author.getAttribute('href'), location.href).href : null,
      time_text: time ? time.innerText.trim() : null,
      timestamp: rawTime && Number.isFinite(Number(rawTime))
        ? new Date(Number(rawTime)).toISOString() : null,
      text: body ? body.innerText.trim() : null,
      url: link ? new URL(link.getAttribute('href'), location.href).href : null
    };
  });
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", default="posts_live.json")
    ap.add_argument("--max-passes", type=int, default=40)
    ap.add_argument("--settle", type=float, default=1.5)
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    collected: dict[str, dict] = {}
    passes: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 1800})
        page.goto(args.url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_selector("article[data-post-id]", timeout=30_000)

        stall = 0
        last_unique = 0
        for i in range(args.max_passes):
            for rec in page.evaluate(EXTRACT_JS):
                if rec["post_id"] and rec["post_id"] not in collected:
                    collected[rec["post_id"]] = rec  # first sighting wins, dedupe by global id
            state = page.evaluate(
                "() => ({y: window.scrollY, h: document.body.scrollHeight,"
                " vh: window.innerHeight, n: document.querySelectorAll('article[data-post-id]').length})"
            )
            # zero increment on one pass is not proof of the end; require settled bottom
            stall = stall + 1 if len(collected) == last_unique else 0
            last_unique = len(collected)
            passes.append({"pass": i, **state, "unique": len(collected), "stall": stall})
            at_bottom = state["y"] + state["vh"] >= state["h"] - 5
            if at_bottom and stall >= 2:
                break
            page.evaluate("() => window.scrollTo(0, window.scrollY + window.innerHeight * 0.8)")
            time.sleep(args.settle)

        title = page.title()
        browser.close()

    records = sorted(collected.values(), key=lambda r: int(r["post_id"]))
    data = {
        "source_url": args.url,
        "topic_title": title,
        "render": "live DOM (Playwright/Chromium, virtualized stream collected by scrolling)",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "post_count": len(records),
        "complete": True,
        "collection_passes": passes,
        "records": records,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print(f"[i] posts={len(records)} passes={len(passes)} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
