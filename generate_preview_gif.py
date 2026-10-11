"""Capture an animated GIF tour of the dashboard for the README.

Tours the ring boot-up, hover callouts on both rings, the watchlist, and a
company's deep-analysis chart with the HUD crosshair.

Time is driven by Playwright's fake clock: each frame advances the page exactly
FRAME_MS, so every requestAnimationFrame animation plays at true speed no matter
how slowly the headless WebGL renderer captures. A fake cursor is drawn into the
page so viewers can follow what is being hovered and clicked.

Output: docs/dashboard-preview.gif
"""

import io
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image
from playwright.sync_api import Page, ViewportSize, sync_playwright

from dashboard import OUT_FILE
from generate_preview import PAYLOAD, SEED_COLORS_JS, write_preview_html

DOCS_OUT = Path(__file__).parent / "docs" / "dashboard-preview.gif"
VIEWPORT: ViewportSize = {"width": 1200, "height": 560}
FRAME_MS = 50              # 20 fps
CSS_PLAYBACK_RATE = 0.2    # CSS transitions run on wall time; slow them to match capture speed
OUTPUT_WIDTH = 880         # README column renders ~880px wide
GIFSICLE_LOSSY = 30        # mild; higher values smear the dark background
LOOP_FADE_FRAMES = 12      # crossfade from the last frame back to the first for a seamless loop
DEMO_TICKER = "JPM"

# Arrow cursor injected into the page (screenshots never include the OS cursor).
CURSOR_JS = """
(() => {
  const c = document.createElement('div');
  c.id = '__demo_cursor';
  c.innerHTML = `<svg width="22" height="22" viewBox="0 0 22 22">
    <path d="M3 2 L3 17 L7 13.2 L9.8 19.5 L12.3 18.4 L9.6 12.3 L15 12.3 Z"
      fill="#e6e1dc" stroke="#0a0a0a" stroke-width="1.3" stroke-linejoin="round"/></svg>`;
  Object.assign(c.style, {position: 'fixed', left: '0', top: '0', zIndex: 99999,
    pointerEvents: 'none', transform: 'translate(-100px,-100px)',
    filter: 'drop-shadow(0 1px 2px rgba(0,0,0,.6))'});
  const r = document.createElement('div');
  Object.assign(r.style, {position: 'fixed', zIndex: 99998, pointerEvents: 'none',
    width: '28px', height: '28px', borderRadius: '50%', border: '1.5px solid #a03828',
    opacity: '0', left: '0', top: '0'});
  document.body.append(r, c);
  window.__demoCursor = (x, y) => { c.style.transform = `translate(${x - 3}px,${y - 2}px)`; };
  window.__demoRipple = (x, y, p) => {   // p: 0..1 progress of the click ripple
    const s = 0.4 + p * 1.2;
    r.style.transform = `translate(${x - 14}px,${y - 14}px) scale(${s})`;
    r.style.opacity = String(p >= 1 ? 0 : 0.9 * (1 - p));
  };
})();
"""


def _ease(t: float) -> float:
    """easeInOutCubic — gentle start and stop for every scroll and glide."""
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def _frames(seconds: float) -> int:
    return max(1, round(seconds * 1000 / FRAME_MS))


class Recorder:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.frames: list[Image.Image] = []
        self.mouse = (VIEWPORT["width"] * 0.5, -40.0)   # parked off-screen

    def shoot(self) -> None:
        self.page.clock.run_for(FRAME_MS)
        raw = self.page.screenshot()
        self.frames.append(Image.open(io.BytesIO(raw)).convert("RGB"))

    def hold(self, seconds: float) -> None:
        # Sub-pixel nudges keep re-firing mousemove the way a resting hand does, so ring
        # hover re-raycasts while the parallax camera settles.
        x, y = self.mouse
        for i in range(_frames(seconds)):
            if y >= 0:
                self.page.mouse.move(x, y + (0.3 if i % 2 else 0))
            self.shoot()

    def _place_mouse(self, x: float, y: float) -> None:
        self.mouse = (x, y)
        self.page.mouse.move(x, y)
        self.page.evaluate("([x, y]) => window.__demoCursor(x, y)", [x, y])

    def glide(self, x: float, y: float, seconds: float, scroll_to: float | None = None) -> None:
        """Ease the cursor (and optionally the scroll position) to a target together."""
        x0, y0 = self.mouse
        s0 = self.page.evaluate("window.scrollY")
        n = _frames(seconds)
        for i in range(1, n + 1):
            k = _ease(i / n)
            if scroll_to is not None:
                self.page.evaluate("y => window.scrollTo(0, y)", s0 + (scroll_to - s0) * k)
            self._place_mouse(x0 + (x - x0) * k, y0 + (y - y0) * k)
            self.shoot()

    def click(self) -> None:
        x, y = self.mouse
        self.page.mouse.down()
        self.page.mouse.up()
        n = _frames(0.4)
        for i in range(1, n + 1):
            self.page.evaluate("([x, y, p]) => window.__demoRipple(x, y, p)", [x, y, i / n])
            self.shoot()

    def doc_top(self, selector: str) -> float:
        return self.page.evaluate(
            "s => document.querySelector(s).getBoundingClientRect().top + window.scrollY", selector
        )

    def ring_point(self, selector: str, angle_deg: float, scroll_y: float) -> tuple[float, float]:
        """Viewport point on a ring's slice band at `angle_deg` (0 = right, counter-clockwise)
        once the page is scrolled to `scroll_y`."""
        box = self.page.locator(f"{selector} canvas").first.bounding_box()
        assert box, f"{selector} canvas not found"
        cx = box["x"] + box["width"] / 2
        cy = box["y"] + self.page.evaluate("window.scrollY") - scroll_y + box["height"] / 2
        r = min(box["width"], box["height"]) * 0.37
        a = math.radians(angle_deg)
        return cx + r * math.cos(a), cy - r * math.sin(a) * 0.92


def capture_frames(page: Page) -> list[Image.Image]:
    """Choreograph the tour: boot → ring callouts → watchlist → deep analysis."""
    rec = Recorder(page)
    page.evaluate(CURSOR_JS)
    header_h = page.evaluate("document.querySelector('header')?.offsetHeight || 0")
    W, H = VIEWPORT["width"], VIEWPORT["height"]

    # 1. Rings boot up.
    rec.hold(2.4)

    # 2. Hover callouts — a portfolio slice, then a savings slice.
    rec.glide(*rec.ring_point("#chart-portfolio", 45, 0), seconds=1.0)
    rec.hold(1.6)
    rec.glide(*rec.ring_point("#chart-savings", 215, 0), seconds=1.2)
    rec.hold(1.6)

    # 3. Ease down to the watchlist, cursor drifting onto the demo company.
    wl_y = rec.doc_top("#watchlist-panel") - header_h - 12
    name_sel = f'.wl-row[data-ticker="{DEMO_TICKER}"] .wl-name'
    rec.glide(W * 0.55, H * 0.8, seconds=1.5, scroll_to=wl_y)
    nb = page.locator(name_sel).bounding_box()
    assert nb, "demo ticker row not found"
    rec.glide(nb["x"] + min(nb["width"], 90) * 0.5, nb["y"] + nb["height"] / 2, seconds=0.9)
    rec.hold(0.9)

    # 4. Open deep analysis and glide down while the chart scans in.
    rec.click()
    an_y = rec.doc_top("#analysis-panel") - header_h - 12
    wrap = page.locator("#an-chart-wrap").bounding_box()
    assert wrap, "analysis chart not found"
    wrap_y = wrap["y"] + page.evaluate("window.scrollY") - an_y   # chart top after scrolling
    chart_mid = wrap_y + wrap["height"] * 0.55
    rec.glide(wrap["x"] + wrap["width"] * 0.08, chart_mid, seconds=1.5, scroll_to=an_y)
    rec.hold(0.5)

    # 5. Sweep the HUD crosshair across the price history.
    rec.glide(wrap["x"] + wrap["width"] * 0.9, chart_mid, seconds=2.6)
    rec.hold(0.4)

    # 6. Switch to the 5Y view and let it redraw.
    tf = page.locator('#analysis-panel [data-an-tf="5Y"]').bounding_box()
    assert tf, "5Y button not found"
    rec.glide(tf["x"] + tf["width"] / 2, tf["y"] + tf["height"] / 2, seconds=1.0)
    rec.click()
    rec.hold(1.6)

    return rec.frames


def assemble_gif(frames: list[Image.Image]) -> None:
    """Encode with ffmpeg's two-pass palette (far cleaner than per-frame quantizing),
    then squeeze with gifsicle when available."""
    if not frames:
        raise ValueError("No frames captured — GIF assembly aborted")
    first, last = frames[0], frames[-1]
    frames = frames + [
        Image.blend(last, first, (i + 1) / (LOOP_FADE_FRAMES + 1)) for i in range(LOOP_FADE_FRAMES)
    ]
    DOCS_OUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for i, f in enumerate(frames):
            f.save(Path(tmp) / f"f{i:05d}.png")
        scale = f"scale={OUTPUT_WIDTH}:-1:flags=lanczos"
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-framerate", str(1000 / FRAME_MS),
             "-i", str(Path(tmp) / "f%05d.png"),
             "-vf", f"{scale},split[a][b];[a]palettegen=max_colors=256:stats_mode=diff[p];"
                    "[b][p]paletteuse=dither=none:diff_mode=rectangle",
             "-loop", "0", str(DOCS_OUT)],
            check=True,
        )
    if shutil.which("gifsicle"):
        subprocess.run(["gifsicle", "-O3", f"--lossy={GIFSICLE_LOSSY}", "--no-warnings", "-b", str(DOCS_OUT)], check=True)


def main() -> None:
    # write_preview_html() overwrites the real dashboard with demo data — restore it afterwards.
    original = OUT_FILE.read_bytes() if OUT_FILE.exists() else None
    try:
        html_path = write_preview_html()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--use-gl=swiftshader", "--ignore-gpu-blocklist"])
            page = browser.new_page(viewport=VIEWPORT)
            page.add_init_script(SEED_COLORS_JS)
            # Freeze time a couple of minutes after the demo payload was "generated".
            page.clock.install(time=str(PAYLOAD["generated"]).replace("08:02", "08:04"))
            page.goto(html_path.as_uri())
            page.wait_for_load_state("networkidle")   # Three.js CDN
            cdp = page.context.new_cdp_session(page)
            cdp.send("Animation.enable")
            cdp.send("Animation.setPlaybackRate", {"playbackRate": CSS_PLAYBACK_RATE})
            frames = capture_frames(page)
            browser.close()
    finally:
        if original is not None:
            OUT_FILE.write_bytes(original)

    assemble_gif(frames)
    size_kb = DOCS_OUT.stat().st_size // 1024
    print(f"GIF saved: {DOCS_OUT}  ({size_kb} KB, {len(frames) + LOOP_FADE_FRAMES} frames @ {FRAME_MS}ms)")


if __name__ == "__main__":
    main()
