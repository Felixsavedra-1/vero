"""
generate_preview_gif.py — Capture an animated GIF of the dashboard for README.md.

Usage:  python generate_preview_gif.py
Output: docs/dashboard-preview.gif
"""

import io
import math
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright, Page

from generate_preview import write_preview_html

DOCS_OUT = Path(__file__).parent / "docs" / "dashboard-preview.gif"
VIEWPORT = {"width": 1280, "height": 720}
INITIAL_WAIT_MS = 600   # Three.js CDN load + first render
FRAME_INTERVAL_MS = 100  # ~10fps → 8s loop

# Phase lengths in frames. FRAME_COUNT is derived so the sum is the single
# source of truth — changing any phase automatically updates the total.
_TOP_HOLD, _SCROLL_DOWN, _WATCHLIST_HOLD, _REVEAL, _ANALYSIS_HOLD, _SCROLL_UP = 12, 25, 6, 10, 16, 11
FRAME_COUNT = _TOP_HOLD + _SCROLL_DOWN + _WATCHLIST_HOLD + _REVEAL + _ANALYSIS_HOLD + _SCROLL_UP

_P1 = _TOP_HOLD
_P2 = _P1 + _SCROLL_DOWN
_P3 = _P2 + _WATCHLIST_HOLD
_P4 = _P3 + _REVEAL
_P5 = _P4 + _ANALYSIS_HOLD


def _ease(t: float) -> float:
    return (1 - math.cos(math.pi * t)) / 2


def _scroll_y(frame: int, total_scroll: int, analysis_top: int) -> int:
    if frame < _P1:
        return 0
    elif frame < _P2:
        return int(_ease((frame - _P1) / _SCROLL_DOWN) * total_scroll)
    elif frame < _P3:
        return total_scroll
    elif frame < _P4:
        return -1  # scrollIntoView is driving; don't interfere
    elif frame < _P5:
        return analysis_top
    else:
        t = (frame - _P5) / _SCROLL_UP
        return int(analysis_top * (1 - _ease(t)))


def _bbox_at(bbox: dict, x_pct: float, y_pct: float) -> tuple[float, float]:
    return bbox["x"] + bbox["width"] * x_pct, bbox["y"] + bbox["height"] * y_pct


def capture_frames(page: Page) -> list[Image.Image]:
    total_scroll: int = page.evaluate(
        "document.documentElement.scrollHeight - window.innerHeight"
    )
    analysis_top: int = page.evaluate(
        "document.getElementById('analysis-panel').offsetTop"
    )
    portfolio_bbox = page.locator("#chart-portfolio canvas").bounding_box()
    savings_bbox   = page.locator("#chart-savings canvas").bounding_box()

    frames  = []
    clicked = False
    for i in range(FRAME_COUNT):
        y = _scroll_y(i, total_scroll, analysis_top)
        if y >= 0:
            page.evaluate("(y) => window.scrollTo(0, y)", y)

        if i == _P1 // 3 and portfolio_bbox:
            page.mouse.move(*_bbox_at(portfolio_bbox, 0.7, 0.5))
        elif i == (_P1 * 2) // 3 and savings_bbox:
            page.mouse.move(*_bbox_at(savings_bbox, 0.3, 0.5))

        if i == _P2 and not clicked:
            wl_locator = page.locator('.wl-name')
            if wl_locator.count() > 0:
                wl_locator.first.click()
                clicked = True

        raw = page.screenshot()
        frames.append(Image.open(io.BytesIO(raw)).convert("RGB"))
        page.wait_for_timeout(FRAME_INTERVAL_MS)

    return frames


def assemble_gif(frames: list[Image.Image]) -> None:
    if not frames:
        raise ValueError("at least one frame required")
    # Derive palette from the midpoint frame so both the top (3D rings) and
    # bottom (watchlist / analysis) color ranges are represented; all frames
    # share one palette so there is no per-frame flicker across the loop.
    palette = frames[len(frames) // 2].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    quantized = [f.quantize(palette=palette) for f in frames]

    DOCS_OUT.parent.mkdir(parents=True, exist_ok=True)
    quantized[0].save(
        DOCS_OUT,
        save_all=True,
        append_images=quantized[1:],
        duration=FRAME_INTERVAL_MS,
        loop=0,
        optimize=True,
    )


def main() -> None:
    html_path = write_preview_html()

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)
        page.goto(html_path.as_uri())
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(INITIAL_WAIT_MS)
        frames = capture_frames(page)
        browser.close()

    assemble_gif(frames)
    size_kb = DOCS_OUT.stat().st_size // 1024
    print(f"GIF saved: {DOCS_OUT}  ({size_kb} KB, {FRAME_COUNT} frames @ {FRAME_INTERVAL_MS}ms)")


if __name__ == "__main__":
    main()
