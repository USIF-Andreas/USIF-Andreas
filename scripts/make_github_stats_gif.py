#!/usr/bin/env python3
"""Render assets/github_stats.gif from live GitHub profile data.

Usage:
    python3 scripts/make_github_stats_gif.py            # fetch via `gh api`
    python3 scripts/make_github_stats_gif.py stats.json # use cached GraphQL response
"""

from __future__ import annotations

import json
import math
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 900, 460
S = 2  # supersample factor
FPS = 14
FRAMES = 64
DURATION = int(1000 / FPS)

BG = "#0D1117"
CARD = "#161B22"
CARD_BORDER = "#21262D"
TEXT = "#E6EDF3"
MUTED = "#8B949E"
DIM = "#6E7681"
CYAN = "#00D9FF"
PURPLE = "#A855F7"
ORANGE = "#F59E0B"
GREEN = "#3FB950"

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"
MONO = FONT_DIR / "DejaVuSansMono.ttf"
MONO_BOLD = FONT_DIR / "DejaVuSansMono-Bold.ttf"

QUERY = """
query {
  user(login: "USIF-Andreas") {
    login
    followers { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount } }
      }
    }
  }
}
"""


def fetch_data() -> dict:
    out = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={QUERY}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(out)


def summarize(payload: dict) -> dict:
    user = payload["data"]["user"]
    repos = user["repositories"]
    stars = sum(r["stargazerCount"] for r in repos["nodes"])

    sizes: Counter[str] = Counter()
    colors: dict[str, str] = {}
    for repo in repos["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            sizes[name] += edge["size"]
            colors[name] = edge["node"]["color"] or MUTED

    total = sum(sizes.values()) or 1
    languages = [
        {"name": name, "pct": size / total * 100, "color": colors[name]}
        for name, size in sizes.most_common(5)
    ]

    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = [d["contributionCount"] for week in weeks for d in week["contributionDays"]]

    return {
        "login": user["login"],
        "repos": repos["totalCount"],
        "stars": stars,
        "followers": user["followers"]["totalCount"],
        "commits": user["contributionsCollection"]["totalCommitContributions"],
        "contributions": user["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        "languages": languages,
        "days": days,
    }


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size * S)


def ease_out(p: float) -> float:
    p = max(0.0, min(1.0, p))
    return 1 - (1 - p) ** 3


def progress(frame: int, start: int, end: int) -> float:
    return ease_out((frame - start) / (end - start))


def rounded(draw: ImageDraw.ImageDraw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(
        [v * S for v in box],
        radius=radius * S,
        fill=fill,
        outline=outline,
        width=width * S,
    )


def draw_text(draw, xy, text, fnt, fill, anchor="la"):
    draw.text((xy[0] * S, xy[1] * S), text, font=fnt, fill=fill, anchor=anchor)


HEAT_X, HEAT_Y, HEAT_W, HEAT_H, HEAT_GAP = 52, 344, 13, 10, 2


def heat_cells(count: int) -> list[tuple[int, int, int, int]]:
    cells = []
    for i in range(count):
        col, row = divmod(i, 7)
        cells.append(
            (
                HEAT_X + col * (HEAT_W + HEAT_GAP),
                HEAT_Y + row * (HEAT_H + HEAT_GAP),
                HEAT_W,
                HEAT_H,
            )
        )
    return cells


def build_static_layer(data: dict) -> Image.Image:
    img = Image.new("RGB", (W * S, H * S), BG)
    draw = ImageDraw.Draw(img)

    # Soft glows behind the header.
    glow = Image.new("RGB", img.size, BG)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([120 * S, -130 * S, 620 * S, 210 * S], fill="#0B1E2E")
    gd.ellipse([560 * S, -160 * S, 1040 * S, 180 * S], fill="#1A1030")
    glow = glow.filter(ImageFilter.GaussianBlur(70 * S))
    img = Image.blend(img, glow, 0.55)
    draw = ImageDraw.Draw(img)

    # Starfield.
    rng = random.Random(7)
    palette = [TEXT, TEXT, "#4B5563", CYAN, PURPLE, ORANGE]
    for _ in range(85):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        r = rng.choice([0.7, 1.0, 1.0, 1.4, 2.0])
        color = rng.choice(palette)
        alpha = rng.uniform(0.12, 0.5)
        draw.ellipse(
            [(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S],
            fill=_blend(BG, color, alpha),
        )

    # Header.
    draw_text(draw, (40, 28), data["login"], font(BOLD, 32), TEXT)
    draw_text(
        draw,
        (42, 74),
        "GitHub Stats  ·  AI Engineering  ·  Agentic Systems",
        font(MONO, 12),
        MUTED,
    )

    pill = [742, 32, 860, 60]
    rounded(draw, pill, 14, fill="#0D2818", outline="#1F6F3D", width=1)
    draw.ellipse([756 * S, 42 * S, 766 * S, 52 * S], fill=GREEN)
    draw_text(draw, (774, 39), "LIVE  ·  API", font(MONO_BOLD, 10), "#7EE787")

    # Cards.
    left = [32, 110, 430, 282]
    right = [446, 110, 868, 282]
    bottom = [32, 298, 868, 432]
    for card in (left, right, bottom):
        rounded(draw, card, 12, fill=CARD, outline=CARD_BORDER, width=1)

    draw_text(draw, (52, 124), "OVERVIEW", font(MONO_BOLD, 10), DIM)
    draw_text(draw, (466, 124), "TOP LANGUAGES", font(MONO_BOLD, 10), DIM)

    accents = [CYAN, ORANGE, PURPLE, GREEN]
    labels = [
        ("Repositories", "repos"),
        ("Total Stars", "stars"),
        ("Followers", "followers"),
        ("Contributions / yr", "contributions"),
    ]
    for i, (label, _) in enumerate(labels):
        x = 52 + (i % 2) * 180
        y = 148 + (i // 2) * 66
        rounded(draw, [x, y, x + 168, y + 58], 8, fill="#0D1117", outline="#1C2128", width=1)
        rounded(draw, [x, y + 12, x + 3, y + 46], 1.5, fill=accents[i])
        draw_text(draw, (x + 14, y + 39), label, font(MONO, 9), MUTED)

    for i, lang in enumerate(data["languages"]):
        y = 148 + i * 26
        draw_text(draw, (466, y), lang["name"], font(MONO, 11), TEXT)
        draw_text(
            draw,
            (848, y),
            f"{lang['pct']:.1f}%",
            font(MONO, 11),
            MUTED,
            anchor="ra",
        )
        rounded(draw, [466, y + 14, 848, y + 20], 3, fill="#21262D")

    draw_text(draw, (52, 314), "CONTRIBUTION ACTIVITY", font(MONO_BOLD, 10), DIM)
    draw_text(
        draw,
        (848, 314),
        f"{data['contributions']} contributions  ·  last 12 months",
        font(MONO, 10),
        MUTED,
        anchor="ra",
    )

    # Heatmap scaffold.
    for x, y, w, h in heat_cells(len(data["days"])):
        rounded(draw, [x, y, x + w, y + h], 2, fill="#21262D")

    return img


def _blend(base: str, color: str, alpha: float) -> tuple[int, int, int]:
    b = tuple(int(base[i : i + 2], 16) for i in (1, 3, 5))
    c = tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))
    return tuple(round(b[i] * (1 - alpha) + c[i] * alpha) for i in range(3))


def heat_color(count: int) -> str:
    if count <= 0:
        return "#21262D"
    if count <= 2:
        return "#0E4429"
    if count <= 5:
        return "#006D32"
    if count <= 9:
        return "#26A641"
    return "#39D353"


def render_frame(static: Image.Image, data: dict, frame: int) -> Image.Image:
    img = static.copy()
    draw = ImageDraw.Draw(img)

    count_p = progress(frame, 5, 46)
    bar_p = progress(frame, 8, 48)
    heat_p = progress(frame, 12, 54)

    values = {
        "repos": data["repos"],
        "stars": data["stars"],
        "followers": data["followers"],
        "contributions": data["contributions"],
    }
    for i, (_, key) in enumerate(
        [
            ("Repositories", "repos"),
            ("Total Stars", "stars"),
            ("Followers", "followers"),
            ("Contributions / yr", "contributions"),
        ]
    ):
        x = 52 + (i % 2) * 180
        y = 148 + (i // 2) * 66
        value = round(values[key] * count_p)
        draw_text(draw, (x + 14, y + 8), f"{value:,}", font(BOLD, 24), TEXT)

    for i, lang in enumerate(data["languages"]):
        y = 148 + i * 26
        width = int((848 - 466) * lang["pct"] / 100 * bar_p)
        if width > 1:
            rounded(draw, [466, y + 14, 466 + width, y + 20], 3, fill=lang["color"])

    # Heatmap reveal: columns appear left to right.
    reveal = int(len(data["days"]) * heat_p)
    cells = heat_cells(len(data["days"]))
    for i, count in enumerate(data["days"][:reveal]):
        if count <= 0:
            continue
        x, y, w, h = cells[i]
        rounded(draw, [x, y, x + w, y + h], 2, fill=heat_color(count))

    # Gentle pulsing accent line under the header.
    pulse = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(frame / FRAMES * 2 * math.pi))
    color = _blend(BG, CYAN, pulse)
    draw.rectangle([40 * S, 98 * S, (40 + 120) * S, 99 * S], fill=color)

    return img.resize((W, H), Image.LANCZOS)


def main() -> None:
    if len(sys.argv) > 1:
        payload = json.loads(Path(sys.argv[1]).read_text())
    else:
        payload = fetch_data()

    data = summarize(payload)
    static = build_static_layer(data)

    frames = [render_frame(static, data, f) for f in range(FRAMES)]
    palette_src = frames[-1].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    frames = [
        f.quantize(palette=palette_src, dither=Image.Dither.NONE) for f in frames
    ]

    out = Path(__file__).resolve().parent.parent / "assets" / "github_stats.gif"
    frames[0].save(
        out,
        save_all=True,
        append_images=frames[1:],
        duration=DURATION,
        loop=0,
        optimize=True,
        disposal=1,
    )
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB, {FRAMES} frames)")


if __name__ == "__main__":
    main()
