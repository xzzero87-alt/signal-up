#!/usr/bin/env python3
"""UI screenshot regression + token contrast check (collaboration-prd.md Phase 3).

Usage:
    python scripts/ui_snapshot.py contrast                 # WCAG contrast table from app.css tokens
    python scripts/ui_snapshot.py capture --tag before     # screenshot all pages (needs server + playwright)
    python scripts/ui_snapshot.py diff before after        # pixel-diff two capture sets

Playwright is a dev-machine-only tool (NOT a project dependency):
    pip install playwright && playwright install chromium

Screenshots go to state/ui_snapshots/<tag>/ (gitignored area).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS_PATH = ROOT / "src" / "signal_program" / "web" / "static" / "css" / "app.css"
SNAP_DIR = ROOT / "state" / "ui_snapshots"

BASE_URL = "http://127.0.0.1:8000"
PAGES = ["/", "/settings", "/backtest", "/failures", "/system", "/_styleguide"]
THEMES = ["dark", "light"]

# ---------- contrast ----------

AA_NORMAL = 4.5
AA_LARGE = 3.0

TEXT_TOKENS = ["color-text", "color-muted", "color-muted-2", "color-primary",
               "color-buy", "color-sell", "color-strong", "color-success"]
BG_TOKENS = ["color-bg", "color-surface", "color-surface-2"]


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def f(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast_ratio(fg: str, bg: str) -> float:
    l1, l2 = _luminance(fg), _luminance(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def parse_tokens(css: str) -> dict[str, dict[str, str]]:
    """Return {'dark': {token: hex}, 'light': {token: hex}} for #hex tokens only."""
    out: dict[str, dict[str, str]] = {"dark": {}, "light": {}}

    def grab(block: str, store: dict[str, str]) -> None:
        for m in re.finditer(r"--([\w-]+):\s*(#[0-9a-fA-F]{3,8})\s*;", block):
            store[m.group(1)] = m.group(2)

    root = re.search(r":root\s*\{(.*?)\}", css, re.DOTALL)
    light = re.search(r'\[data-theme="light"\]\s*\{(.*?)\}', css, re.DOTALL)
    if root:
        grab(root.group(1), out["dark"])
    if light:
        # light inherits dark then overrides
        out["light"] = dict(out["dark"])
        grab(light.group(1), out["light"])
    return out


def cmd_contrast() -> int:
    css = CSS_PATH.read_text(encoding="utf-8")
    themes = parse_tokens(css)
    failures = 0
    for theme in ("dark", "light"):
        tokens = themes[theme]
        print(f"--- {theme.upper()} ---")
        header = f"{'fg':14s}" + "".join(f"{b.replace('color-', ''):>11s}" for b in BG_TOKENS)
        print(header)
        for fg in TEXT_TOKENS:
            if fg not in tokens:
                continue
            row = f"{fg.replace('color-', ''):14s}"
            for bg in BG_TOKENS:
                if bg not in tokens:
                    row += f"{'n/a':>11s}"
                    continue
                r = contrast_ratio(tokens[fg], tokens[bg])
                mark = "" if r >= AA_NORMAL else ("*" if r >= AA_LARGE else "!!")
                if r < AA_LARGE:
                    failures += 1
                row += f"{r:8.2f}{mark:<3s}"
            print(row)
        print()
    print("legend: blank=AA normal text, *=AA large text only, !!=below 3.0")
    print("docs/ui/a11y-responsive.md has per-token guidance.")
    return 0  # informational, never blocks


# ---------- capture / diff ----------

def cmd_capture(tag: str) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed (dev tool, not a project dep):", file=sys.stderr)
        print("  pip install playwright && playwright install chromium", file=sys.stderr)
        return 2

    out_dir = SNAP_DIR / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        for theme in THEMES:
            for route in PAGES:
                name = route.strip("/").replace("/", "_") or "index"
                page.goto(BASE_URL + route, wait_until="networkidle")
                page.evaluate(
                    "t => { document.documentElement.setAttribute('data-theme', t);"
                    " localStorage.setItem('signal-theme', t); }",
                    theme,
                )
                page.wait_for_timeout(300)
                path = out_dir / f"{name}.{theme}.png"
                page.screenshot(path=str(path), full_page=True)
                count += 1
                print(f"  captured {path.relative_to(ROOT)}")
        browser.close()
    print(f"done: {count} screenshots -> {out_dir.relative_to(ROOT)}")
    return 0


def cmd_diff(tag_a: str, tag_b: str, threshold: float = 0.5) -> int:
    """Compare two capture sets. threshold = % of differing pixels to report."""
    try:
        from PIL import Image, ImageChops
    except ImportError:
        print("Pillow not installed (dev tool): pip install Pillow", file=sys.stderr)
        return 2

    dir_a, dir_b = SNAP_DIR / tag_a, SNAP_DIR / tag_b
    if not dir_a.is_dir() or not dir_b.is_dir():
        print(f"missing capture dir: {dir_a} or {dir_b}", file=sys.stderr)
        return 2

    changed = []
    for png_a in sorted(dir_a.glob("*.png")):
        png_b = dir_b / png_a.name
        if not png_b.exists():
            changed.append((png_a.name, "missing in " + tag_b))
            continue
        im_a, im_b = Image.open(png_a).convert("RGB"), Image.open(png_b).convert("RGB")
        if im_a.size != im_b.size:
            changed.append((png_a.name, f"size {im_a.size} -> {im_b.size}"))
            continue
        diff = ImageChops.difference(im_a, im_b)
        bbox = diff.getbbox()
        if bbox is None:
            continue
        hist = diff.convert("L").histogram()
        nonzero = sum(hist[8:])  # ignore near-identical pixels (antialiasing noise)
        pct = 100.0 * nonzero / (im_a.size[0] * im_a.size[1])
        if pct >= threshold:
            changed.append((png_a.name, f"{pct:.2f}% pixels differ, bbox={bbox}"))

    if changed:
        print(f"CHANGED - {len(changed)} screenshot(s) differ ({tag_a} vs {tag_b}):")
        for name, why in changed:
            print(f"  {name}: {why}")
        print("review visually - this is informational, not a blocker.")
        return 1
    print(f"UNCHANGED - no visual differences above {threshold}% ({tag_a} vs {tag_b}).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("contrast")
    cap = sub.add_parser("capture")
    cap.add_argument("--tag", required=True)
    dif = sub.add_parser("diff")
    dif.add_argument("tag_a")
    dif.add_argument("tag_b")
    dif.add_argument("--threshold", type=float, default=0.5)
    args = ap.parse_args()

    if args.cmd == "contrast":
        return cmd_contrast()
    if args.cmd == "capture":
        return cmd_capture(args.tag)
    return cmd_diff(args.tag_a, args.tag_b, args.threshold)


if __name__ == "__main__":
    raise SystemExit(main())
