"""SVG builders for statement schemas (graphs, Turtle drawings, grids).

SVG is produced as text and shipped inline so the client renders it without a
network round-trip and it stays crisp on a 360px phone. All geometry is integer
based to keep byte-identical output for a given seed.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from xml.sax.saxutils import escape

# Palette is deliberately theme-neutral: strokes use currentColor so the SVG
# inherits Telegram's light/dark theme from the surrounding element.
_STYLE = (
    "<style>"
    ".n{fill:var(--bayt-svg-node,#ffffff);stroke:currentColor;stroke-width:2}"
    ".e{stroke:currentColor;stroke-width:2;fill:none}"
    ".t{font:600 14px system-ui,sans-serif;fill:currentColor;text-anchor:middle;"
    "dominant-baseline:central}"
    ".w{font:500 12px system-ui,sans-serif;fill:currentColor;text-anchor:middle}"
    ".p{stroke:currentColor;stroke-width:2.5;fill:none;stroke-linecap:round;"
    "stroke-linejoin:round}"
    ".g{stroke:currentColor;stroke-width:1;opacity:.35}"
    "</style>"
)


@dataclass(frozen=True, slots=True)
class Point:
    x: int
    y: int


def _header(width: int, height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" role="img" style="max-width:{width}px;height:auto">{_STYLE}'
    )


def circle_layout(n: int, cx: int, cy: int, r: int) -> list[Point]:
    """Place ``n`` nodes evenly on a circle, first node at the top."""
    pts: list[Point] = []
    for i in range(n):
        angle = -math.pi / 2 + 2 * math.pi * i / n
        pts.append(Point(round(cx + r * math.cos(angle)), round(cy + r * math.sin(angle))))
    return pts


def graph_svg(
    labels: Sequence[str],
    edges: Iterable[tuple[int, int, int | None]],
    *,
    width: int = 340,
    height: int = 300,
    node_radius: int = 20,
    title: str = "Схема дорог",
) -> str:
    """Undirected weighted graph on a circular layout.

    ``edges`` are ``(a, b, weight)`` index pairs; ``weight`` may be ``None`` for an
    unweighted schema.
    """
    pts = circle_layout(len(labels), width // 2, height // 2, min(width, height) // 2 - 34)
    parts = [_header(width, height), f"<title>{escape(title)}</title>"]
    for a, b, w in edges:
        pa, pb = pts[a], pts[b]
        parts.append(f'<line class="e" x1="{pa.x}" y1="{pa.y}" x2="{pb.x}" y2="{pb.y}"/>')
        if w is not None:
            mx, my = (pa.x + pb.x) // 2, (pa.y + pb.y) // 2
            # Nudge the label off the line so it stays readable where edges cross.
            ox = round(8 * math.copysign(1, mx - width / 2 or 1))
            parts.append(
                f'<rect x="{mx + ox - 12}" y="{my - 9}" width="24" height="16" rx="4" '
                f'fill="var(--bayt-svg-node,#ffffff)" opacity=".92"/>'
                f'<text class="w" x="{mx + ox}" y="{my + 3}">{w}</text>'
            )
    for i, label in enumerate(labels):
        p = pts[i]
        parts.append(f'<circle class="n" cx="{p.x}" cy="{p.y}" r="{node_radius}"/>')
        parts.append(f'<text class="t" x="{p.x}" y="{p.y}">{escape(label)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def turtle_svg(
    path: Sequence[tuple[int, int]],
    *,
    marks: Sequence[tuple[int, int]] = (),
    grid_step: int = 1,
    title: str = "Рисунок Черепахи",
) -> str:
    """Render a Turtle path on a unit grid, scaled to fit a phone screen."""
    xs = [p[0] for p in path] + [m[0] for m in marks]
    ys = [p[1] for p in path] + [m[1] for m in marks]
    min_x, max_x = min(xs) - 1, max(xs) + 1
    min_y, max_y = min(ys) - 1, max(ys) + 1
    span_x, span_y = max(max_x - min_x, 1), max(max_y - min_y, 1)
    scale = max(6, min(28, 300 // max(span_x, span_y)))
    pad = 16
    width = span_x * scale + 2 * pad
    height = span_y * scale + 2 * pad

    def sx(x: int) -> int:
        return round((x - min_x) * scale + pad)

    def sy(y: int) -> int:
        return round((max_y - y) * scale + pad)

    parts = [_header(width, height), f"<title>{escape(title)}</title>"]
    for gx in range(min_x, max_x + 1, grid_step):
        parts.append(
            f'<line class="g" x1="{sx(gx)}" y1="{pad}" x2="{sx(gx)}" y2="{height - pad}"/>'
        )
    for gy in range(min_y, max_y + 1, grid_step):
        parts.append(f'<line class="g" x1="{pad}" y1="{sy(gy)}" x2="{width - pad}" y2="{sy(gy)}"/>')
    d = " ".join(("M" if i == 0 else "L") + f"{sx(x)} {sy(y)}" for i, (x, y) in enumerate(path))
    parts.append(f'<path class="p" d="{d}"/>')
    for mx, my in marks:
        parts.append(f'<circle cx="{sx(mx)}" cy="{sy(my)}" r="3" fill="currentColor"/>')
    parts.append("</svg>")
    return "".join(parts)


def grid_svg(
    cells: Sequence[Sequence[str]],
    *,
    walls: Sequence[tuple[int, int, str]] = (),
    start: tuple[int, int] | None = None,
    finish: tuple[int, int] | None = None,
    title: str = "Поле Робота",
) -> str:
    """Grid with per-cell text and thick wall segments (task 18)."""
    rows, cols = len(cells), len(cells[0])
    cell = max(26, min(46, 320 // cols))
    pad = 12
    width, height = cols * cell + 2 * pad, rows * cell + 2 * pad
    parts = [_header(width, height), f"<title>{escape(title)}</title>"]
    for r in range(rows):
        for c in range(cols):
            x, y = pad + c * cell, pad + r * cell
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" class="g" fill="none"/>'
            )
            parts.append(
                f'<text class="w" x="{x + cell // 2}" y="{y + cell // 2 + 4}">'
                f"{escape(cells[r][c])}</text>"
            )
    if start is not None:
        x, y = pad + start[1] * cell, pad + start[0] * cell
        parts.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" fill="currentColor" '
            f'opacity=".12"/>'
        )
    if finish is not None:
        x, y = pad + finish[1] * cell, pad + finish[0] * cell
        parts.append(
            f'<rect x="{x + 3}" y="{y + 3}" width="{cell - 6}" height="{cell - 6}" '
            f'class="e" stroke-dasharray="4 3" fill="none"/>'
        )
    for r, c, side in walls:
        x, y = pad + c * cell, pad + r * cell
        coords = {
            "top": (x, y, x + cell, y),
            "bottom": (x, y + cell, x + cell, y + cell),
            "left": (x, y, x, y + cell),
            "right": (x + cell, y, x + cell, y + cell),
        }[side]
        parts.append(
            f'<line x1="{coords[0]}" y1="{coords[1]}" x2="{coords[2]}" y2="{coords[3]}" '
            f'stroke="currentColor" stroke-width="4" stroke-linecap="square"/>'
        )
    parts.append("</svg>")
    return "".join(parts)


def dag_svg(
    labels: Sequence[str],
    layers: Sequence[Sequence[int]],
    edges: Iterable[tuple[int, int]],
    *,
    width: int = 340,
    title: str = "Ориентированный граф",
) -> str:
    """A layered drawing of a directed acyclic graph, arcs pointing left to right."""
    node_radius = 15
    gap_x = max(60, (width - 2 * node_radius - 20) // max(1, len(layers) - 1))
    gap_y = 56
    height = max(len(layer) for layer in layers) * gap_y + 40
    positions: dict[int, Point] = {}
    for column, layer in enumerate(layers):
        offset = (height - (len(layer) - 1) * gap_y) // 2
        for row, node in enumerate(layer):
            positions[node] = Point(node_radius + 12 + column * gap_x, offset + row * gap_y)

    parts = [
        _header(width, height),
        f"<title>{escape(title)}</title>",
        '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
        'markerHeight="6" orient="auto-start-reverse">'
        '<path d="M0 0 L10 5 L0 10 z" fill="currentColor"/></marker></defs>',
    ]
    for a, b in edges:
        pa, pb = positions[a], positions[b]
        dx, dy = pb.x - pa.x, pb.y - pa.y
        length = max(1.0, math.hypot(dx, dy))
        # Stop the arc at the circle's edge so the arrowhead is not hidden.
        sx = round(pa.x + dx / length * node_radius)
        sy = round(pa.y + dy / length * node_radius)
        ex = round(pb.x - dx / length * (node_radius + 3))
        ey = round(pb.y - dy / length * (node_radius + 3))
        parts.append(
            f'<line class="e" x1="{sx}" y1="{sy}" x2="{ex}" y2="{ey}" marker-end="url(#a)"/>'
        )
    for node, label in enumerate(labels):
        p = positions[node]
        parts.append(f'<circle class="n" cx="{p.x}" cy="{p.y}" r="{node_radius}"/>')
        parts.append(f'<text class="t" x="{p.x}" y="{p.y}">{escape(label)}</text>')
    parts.append("</svg>")
    return "".join(parts)
