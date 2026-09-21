"""Turtle geometry and lattice-point counting for task 6."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TypeAlias

Pt: TypeAlias = tuple[float, float]
EPS = 1e-9


def turtle_polygon(commands: Sequence[tuple[float, float]], start: Pt = (0.0, 0.0)) -> list[Pt]:
    """Vertices of the figure drawn by a Turtle program.

    The Turtle starts at ``start`` facing **up** (90 degrees); a positive ``turn`` is a
    left turn, so "Направо 90" is ``-90`` (doc, Appendix A task 6).
    ``commands`` is a list of ``(forward, turn)`` pairs.
    """
    x, y = start
    angle = 90.0
    pts: list[Pt] = [(x, y)]
    for dist, turn in commands:
        x += dist * math.cos(math.radians(angle))
        y += dist * math.sin(math.radians(angle))
        pts.append((round(x, 9), round(y, 9)))
        angle += turn
    # The closing vertex coincides with the start; drop it so edges wrap cleanly.
    if len(pts) > 1 and math.dist(pts[0], pts[-1]) < 1e-6:
        pts.pop()
    return pts


def point_on_edge(px: float, py: float, a: Pt, b: Pt, eps: float = EPS) -> bool:
    (x1, y1), (x2, y2) = a, b
    cross = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
    if abs(cross) > eps:
        return False
    return (
        min(x1, x2) - eps <= px <= max(x1, x2) + eps
        and min(y1, y2) - eps <= py <= max(y1, y2) + eps
    )


def inside(px: float, py: float, poly: Sequence[Pt], *, strict: bool, eps: float = EPS) -> bool:
    """Ray-casting point-in-polygon with an explicit boundary rule.

    ``strict=True`` counts only interior points; ``strict=False`` also counts points
    lying exactly on an edge — the distinction the exam turns on.
    """
    n = len(poly)
    for i in range(n):
        if point_on_edge(px, py, poly[i], poly[(i + 1) % n], eps):
            return not strict
    crossings = False
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > py) != (y2 > py) and px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
            crossings = not crossings
    return crossings


def count_lattice_points(poly: Sequence[Pt], *, strict: bool) -> int:
    """Integer-coordinate points inside the polygon (and on its edges when not strict)."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return sum(
        inside(x, y, poly, strict=strict)
        for x in range(math.floor(min(xs)) - 1, math.ceil(max(xs)) + 2)
        for y in range(math.floor(min(ys)) - 1, math.ceil(max(ys)) + 2)
    )


def count_lattice_points_intersection(
    poly_a: Sequence[Pt], poly_b: Sequence[Pt], *, strict: bool
) -> int:
    xs = [p[0] for p in poly_a] + [p[0] for p in poly_b]
    ys = [p[1] for p in poly_a] + [p[1] for p in poly_b]
    return sum(
        inside(x, y, poly_a, strict=strict) and inside(x, y, poly_b, strict=strict)
        for x in range(math.floor(min(xs)) - 1, math.ceil(max(xs)) + 2)
        for y in range(math.floor(min(ys)) - 1, math.ceil(max(ys)) + 2)
    )


def rectangle_formula(width: int, height: int, *, strict: bool) -> int:
    """Closed form for an axis-aligned w x h rectangle — the naive cross-check."""
    return (width - 1) * (height - 1) if strict else (width + 1) * (height + 1)


def polygon_area(poly: Sequence[Pt]) -> float:
    n = len(poly)
    return (
        abs(
            sum(
                poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1]
                for i in range(n)
            )
        )
        / 2
    )
