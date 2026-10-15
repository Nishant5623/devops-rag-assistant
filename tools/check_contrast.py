#!/usr/bin/env python3
"""Check the front-end design tokens against WCAG AA contrast.

Parses the colour tokens straight out of static/style.css (so it cannot drift
from the stylesheet) and reports the contrast ratio of every foreground /
background pair the page actually renders, in both the dark and the
prefers-color-scheme: light themes.

WCAG 2.2: 4.5:1 for normal text (1.4.3, AA), 3:1 for large text and for
non-text UI/state indicators (1.4.11, AA).

Exits non-zero if any pair fails, so CI enforces it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CSS_PATH = Path(__file__).resolve().parent.parent / "static" / "style.css"

HEX = re.compile(r"(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;")


def tokens(block: str) -> dict[str, str]:
    return {
        name.removeprefix("--"): value.lower() for name, value in HEX.findall(block)
    }


def luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(fg: str, bg: str) -> float:
    lighter, darker = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


# (foreground token, background token, minimum ratio, what it styles)
PAIRS: list[tuple[str, str, float, str]] = [
    ("text", "bg", 4.5, "body text on the page"),
    ("text", "surface", 4.5, "body text on panel"),
    ("text", "surface-2", 4.5, "body text on raised surface"),
    ("text-muted", "bg", 4.5, "subtitle / hints on the page"),
    ("text-muted", "surface", 4.5, "subtitle / hints on panel"),
    ("text-muted", "surface-2", 4.5, "source chunk text"),
    ("text", "bubble-user", 4.5, "user message text"),
    ("text", "bubble-bot", 4.5, "assistant message text"),
    ("accent", "bg", 4.5, "links on the page"),
    ("accent", "surface", 4.5, "links / source summary on panel"),
    ("accent", "surface-2", 4.5, "source file badge text"),
    ("accent-ink", "accent", 4.5, "Send button label"),
    ("text-faint", "surface", 4.5, "timestamps, counts, placeholder"),
    ("text-faint", "surface-2", 4.5, "input placeholder"),
    ("ok", "surface", 4.5, "ready / live state text"),
    ("warn", "surface", 4.5, "degraded and refusal text"),
    ("danger", "surface", 4.5, "error text"),
]


def main() -> int:
    css = CSS_PATH.read_text(encoding="utf-8")
    dark_block, _, light_block = css.partition("@media (prefers-color-scheme: light)")
    if not light_block:
        print("::error::no light theme block found in style.css")
        return 1

    themes = {"dark": tokens(dark_block), "light": tokens(light_block)}
    failures = 0

    for theme, values in themes.items():
        print(f"\n=== {theme} theme ({len(values)} colour tokens)")
        print(f"{'ratio':>6}  {'min':>4}  {'pair':<28} purpose")
        for fg_name, bg_name, minimum, purpose in PAIRS:
            fg = values.get(fg_name)
            bg = values.get(bg_name)
            if fg is None or bg is None:
                print(
                    f"{'?':>6}  {minimum:>4}  {fg_name} / {bg_name:<12} MISSING TOKEN"
                )
                failures += 1
                continue
            ratio = contrast(fg, bg)
            status = "ok" if ratio >= minimum else "FAIL"
            print(
                f"{ratio:>6.2f}  {minimum:>4.1f}  "
                f"{fg_name + ' / ' + bg_name:<28} {purpose}  [{status}]"
            )
            if ratio < minimum:
                failures += 1

    print()
    if failures:
        print(f"::error::{failures} contrast pair(s) below WCAG AA")
        return 1
    print("All contrast pairs meet WCAG AA.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
