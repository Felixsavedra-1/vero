#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT_GIF = ROOT / "vr02-equity.gif"

CSS_W = 256
CSS_H = 160
SCALE = 2
FPS = 20
# The equity curve is a continuous left-scroll (scroll = t * 1.5). Its exact
# fundamental period is 200*pi units (≈14 screen-widths) — too long for a
# compact GIF — so we loop over ~2 screen-widths, the standard tradeoff for a
# scrolling line chart.
SCROLL_D = 87.0
PERIOD = SCROLL_D / 1.5
FRAMES = 110
OUT_W = CSS_W * SCALE
MAX_COLORS = 256

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
  html,body{margin:0;background:#0A0A0B;}
  #stage{width:256px;height:160px;}
  canvas{
    width:256px;height:160px;display:block;
    border:1px solid #26262B;border-radius:2px;
    background:linear-gradient(180deg,#111113,#0A0A0B);
  }
</style></head><body>
<div id="stage"><canvas id="c" width="512" height="320"></canvas></div>
<script>
  var GOLD='178,58,58', GREY='140,140,147', BONE='#E8E3D6';

  function grid(ctx,W,H){
    ctx.strokeStyle='rgba(38,38,43,0.85)'; ctx.lineWidth=1;
    for(var x=0;x<=W;x+=W/8){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,H);ctx.stroke();}
    for(var y=0;y<=H;y+=H/8){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(W,y);ctx.stroke();}
  }
  function dot(ctx,x,y,r,fill){ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fillStyle=fill;ctx.fill();}
  function ring(ctx,x,y,r,s){ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.strokeStyle=s;ctx.lineWidth=1;ctx.stroke();}
  function glow(ctx,x,y,r,rgb,a){
    var g=ctx.createRadialGradient(x,y,0,x,y,r);
    g.addColorStop(0,'rgba('+rgb+','+a+')'); g.addColorStop(1,'rgba('+rgb+',0)');
    ctx.fillStyle=g; ctx.beginPath(); ctx.arc(x,y,r,0,Math.PI*2); ctx.fill();
  }

  function fPort(x){return 0.5+0.18*Math.sin(x*0.15)+0.10*Math.sin(x*0.37+1.3)+0.06*Math.sin(x*0.8+2.1);}
  function fBench(x){return 0.5+0.12*Math.sin(x*0.13+0.5)+0.05*Math.sin(x*0.3+0.7);}
  function drawEquity(ctx,W,H,t){
    grid(ctx,W,H);
    var topY=H*0.16,botY=H*0.84;
    function mapY(v){return botY-v*(botY-topY);}
    var span=44, scroll=t*1.5, step=Math.max(3,W/64);
    ctx.setLineDash([4,4]);ctx.beginPath();
    for(var px=0;px<=W;px+=step){var u=px/W,s=u*span+scroll,y=mapY(fBench(s));if(px===0)ctx.moveTo(px,y);else ctx.lineTo(px,y);}
    ctx.strokeStyle='rgba('+GREY+',0.40)';ctx.lineWidth=1.1;ctx.stroke();ctx.setLineDash([]);
    var path=[];
    for(var p2=0;p2<=W;p2+=step){var u2=p2/W,s2=u2*span+scroll;path.push({x:p2,y:mapY(fPort(s2))});}
    var grad=ctx.createLinearGradient(0,topY,0,botY);
    grad.addColorStop(0,'rgba('+GOLD+',0.32)');grad.addColorStop(1,'rgba('+GOLD+',0)');
    ctx.beginPath();ctx.moveTo(path[0].x,botY);
    for(var i=0;i<path.length;i++)ctx.lineTo(path[i].x,path[i].y);
    ctx.lineTo(path[path.length-1].x,botY);ctx.closePath();ctx.fillStyle=grad;ctx.fill();
    ctx.beginPath();for(var j=0;j<path.length;j++){if(j===0)ctx.moveTo(path[j].x,path[j].y);else ctx.lineTo(path[j].x,path[j].y);}
    ctx.strokeStyle='rgba('+GOLD+',0.18)';ctx.lineWidth=4;ctx.lineJoin='round';ctx.stroke();
    ctx.beginPath();for(var k=0;k<path.length;k++){if(k===0)ctx.moveTo(path[k].x,path[k].y);else ctx.lineTo(path[k].x,path[k].y);}
    ctx.strokeStyle='rgba('+GOLD+',0.92)';ctx.lineWidth=1.8;ctx.stroke();
    var mx=W*0.88, my=mapY(fPort((mx/W)*span+scroll));
    glow(ctx,mx,my,10,GOLD,0.5);ring(ctx,mx,my,6,'rgba(232,227,214,0.35)'); dot(ctx,mx,my,2.8,BONE);
  }

  var ctx=document.getElementById('c').getContext('2d');
  ctx.scale(2,2);
  window.renderEquity=function(t){
    ctx.clearRect(0,0,256,160);
    drawEquity(ctx,256,160,t);
  };
  window.renderEquity(0);
</script></body></html>"""


def capture_frames(frame_dir: Path) -> int:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": CSS_W, "height": CSS_H},
            device_scale_factor=SCALE,
        )
        page.set_content(PAGE, wait_until="networkidle")
        canvas = page.locator("#c")
        for k in range(FRAMES):
            t = (k / FRAMES) * PERIOD
            page.evaluate(f"window.renderEquity({t})")
            canvas.screenshot(path=str(frame_dir / f"frame_{k:04d}.png"))
        browser.close()
    return FRAMES


def build_gif(frame_dir: Path) -> None:
    palette = frame_dir / "palette.png"
    vf = f"fps={FPS},scale={OUT_W}:-1:flags=lanczos"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(FPS),
            "-i",
            str(frame_dir / "frame_%04d.png"),
            "-vf",
            f"{vf},palettegen=max_colors={MAX_COLORS}:stats_mode=diff",
            str(palette),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(FPS),
            "-i",
            str(frame_dir / "frame_%04d.png"),
            "-i",
            str(palette),
            "-lavfi",
            f"{vf}[x];[x][1:v]paletteuse=dither=sierra2_4a",
            "-loop",
            "0",
            str(OUT_GIF),
        ],
        check=True,
        capture_output=True,
    )


def main() -> None:
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found on PATH.")
    frame_dir = Path(tempfile.mkdtemp(prefix="vr02_gif_"))
    try:
        n = capture_frames(frame_dir)
        print(f"Captured {n} frames → assembling GIF…")
        build_gif(frame_dir)
        size_mb = OUT_GIF.stat().st_size / 1e6
        print(f"Wrote {OUT_GIF.name} ({size_mb:.2f} MB)")
    finally:
        shutil.rmtree(frame_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
