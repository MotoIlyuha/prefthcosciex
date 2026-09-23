"""``walls.json`` for task 18.

Thick cell borders in an ``.ods`` file are invisible on a phone, so the instance also
carries the wall set as JSON. The mini-grid draws them as heavy lines and the
student's Python code can read the very same structure (doc, Appendix A task 18).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field


@dataclass(slots=True)
class Walls:
    """Walls to the right of, and below, the given cells."""

    right: set[tuple[int, int]] = field(default_factory=set)
    down: set[tuple[int, int]] = field(default_factory=set)

    def to_json(self) -> bytes:
        """Compact, stable JSON: one cell pair per entry, sorted for byte-identity."""
        right = ", ".join(f"[{i}, {j}]" for i, j in sorted(self.right))
        down = ", ".join(f"[{i}, {j}]" for i, j in sorted(self.down))
        return f'{{\n  "right": [{right}],\n  "down": [{down}]\n}}\n'.encode()

    def blocks_from_left(self, i: int, j: int) -> bool:
        """True when a wall stops the robot entering (i, j) from (i, j-1)."""
        return (i, j - 1) in self.right

    def blocks_from_above(self, i: int, j: int) -> bool:
        """True when a wall stops the robot entering (i, j) from (i-1, j)."""
        return (i - 1, j) in self.down

    def svg_segments(self) -> list[tuple[int, int, str]]:
        """Wall segments for :func:`egegen.core.svg.grid_svg`.

        The movement model calls the lower wall "down" (the direction it blocks);
        the drawing calls it "bottom" (the side of the cell it sits on).
        """
        return [(i, j, "right") for i, j in sorted(self.right)] + [
            (i, j, "bottom") for i, j in sorted(self.down)
        ]


def reachable(
    rows: int, cols: int, walls: Walls, *, start: tuple[int, int], moves: Sequence[str]
) -> bool:
    """Whether the bottom-right cell stays reachable under the movement rules.

    ``moves`` holds the directions the robot may take, e.g. ``("right", "down")``.
    A wall layout that strands the finish makes the task unanswerable, so the
    generator rejects it.
    """
    seen = {start}
    stack = [start]
    target = (rows - 1, cols - 1) if "down" in moves else (0, cols - 1)
    while stack:
        i, j = stack.pop()
        if (i, j) == target:
            return True
        for move in moves:
            ni, nj = _step(i, j, move)
            if not (0 <= ni < rows and 0 <= nj < cols) or (ni, nj) in seen:
                continue
            if _blocked(i, j, move, walls):
                continue
            seen.add((ni, nj))
            stack.append((ni, nj))
    return target in seen


def _step(i: int, j: int, move: str) -> tuple[int, int]:
    return {
        "right": (i, j + 1),
        "down": (i + 1, j),
        "up": (i - 1, j),
        "left": (i, j - 1),
    }[move]


def _blocked(i: int, j: int, move: str, walls: Walls) -> bool:
    match move:
        case "right":
            return (i, j) in walls.right
        case "left":
            return (i, j - 1) in walls.right
        case "down":
            return (i, j) in walls.down
        case "up":
            return (i - 1, j) in walls.down
    raise ValueError(f"unknown move {move!r}")


def walls_from_pairs(right: Iterable[Sequence[int]], down: Iterable[Sequence[int]]) -> Walls:
    return Walls({(int(a), int(b)) for a, b in right}, {(int(a), int(b)) for a, b in down})
