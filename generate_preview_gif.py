"""
generate_preview_gif.py — Capture an animated GIF of the dashboard for README.md.

Usage:  python generate_preview_gif.py
Output: docs/dashboard-preview.gif
"""

import io
from pathlib import Path

from PIL import Image
from playwright.sync_api import FloatRect, ViewportSize, sync_playwright, Page

from generate_preview import write_preview_html

DOCS_OUT = Path(__file__).parent / "docs" / "dashboard-preview.gif"
VIEWPORT: ViewportSize = {"width": 1280, "height": 720}
INITIAL_WAIT_MS = 600   # Three.js CDN load + first render
FRAME_COUNT = 45
FRAME_INTERVAL_MS = 80  # ~12fps → 3.6s loop


def _bounding_box_center_offset(bbox: FloatRect, x_pct: float, y_pct: float) -> tuple[float, float]:
    return bbox["x"] + bbox["width"] * x_pct, bbox["y"] + bbox["height"] * y_pct


def capture_frames(page: Page) -> list[Image.Image]:
    frames: list[Image.Image] = []

    portfolio_bbox = page.locator("#chart-portfolio canvas").bounding_box()
    savings_bbox = page.locator("#chart-savings canvas").bounding_box()

    for i in range(FRAME_COUNT):
        # Hover into portfolio ring outer slice to trigger particle/glow effects
        if i == FRAME_COUNT // 3 and portfolio_bbox:
            page.mouse.move(*_bounding_box_center_offset(portfolio_bbox, 0.70, 0.50))
        # Shift hover to savings ring
        elif i == (FRAME_COUNT * 2) // 3 and savings_bbox:
            page.mouse.move(*_bounding_box_center_offset(savings_bbox, 0.30, 0.50))

        raw = page.screenshot()
        frames.append(Image.open(io.BytesIO(raw)).convert("RGB"))
        page.wait_for_timeout(FRAME_INTERVAL_MS)

    return frames


def assemble_gif(frames: list[Image.Image]) -> None:
    if not frames:
        raise ValueError("No frames captured — GIF assembly aborted")
    # Derive a single palette from the first frame; quantize all frames against it
    # so colors stay consistent across the loop (no per-frame palette flicker).
    palette_ref = frames[0].quantize(colors=200, method=Image.Quantize.MEDIANCUT)
    quantized = [palette_ref] + [f.quantize(palette=palette_ref) for f in frames[1:]]

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
    html_path = write_preview_html()  # animations enabled

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)
        page.goto(html_path.as_uri())
        page.wait_for_load_state("networkidle")  # ensure Three.js CDN script loads
        page.wait_for_timeout(INITIAL_WAIT_MS)
        frames = capture_frames(page)
        browser.close()

    assemble_gif(frames)
    size_kb = DOCS_OUT.stat().st_size // 1024
    print(f"GIF saved: {DOCS_OUT}  ({size_kb} KB, {FRAME_COUNT} frames @ {FRAME_INTERVAL_MS}ms)")


if __name__ == "__main__":
    main()
