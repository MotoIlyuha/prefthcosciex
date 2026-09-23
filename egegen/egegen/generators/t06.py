"""Task 6 — the Turtle executor: count lattice points inside the figure it draws.

The Turtle starts at the origin facing **up**, and "Направо 90" turns clockwise.
Three independent methods back the answer: ray casting, winding number, and — for
figures whose vertices are integral — Pick's theorem, which involves no scan at all.
"""

from __future__ import annotations

from typing import Any

from egegen.core.errors import GenerationFailedError
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.svg import turtle_svg
from egegen.core.templates import render
from egegen.core.types import Attachment, Instance, Uniqueness
from egegen.solvers.polygon import (
    count_lattice_points,
    count_lattice_points_intersection,
    count_lattice_points_winding,
    pick_interior,
    rectangle_formula,
    turtle_polygon,
)


class Task06(Generator):
    task_no = 6
    answer_kind = "int"
    checker = "exact"
    uniqueness = Uniqueness.FUNCTIONAL
    generation_budget_ms = 300

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(40):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailedError(f"t06/{subtype}: no valid instance")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        figure = self._figure(rng, difficulty, subtype)
        if figure is None:
            return None
        meta: dict[str, Any] = {"subtype": subtype, **figure}
        answer = self.solve_fast(meta)
        if not 6 <= int(answer) <= 4000:
            return None

        path = turtle_polygon([tuple(c) for c in meta["commands"]])
        svg = turtle_svg(
            [(round(x), round(y)) for x, y in [*path, path[0]]],
            grid_step=max(1, max(abs(round(p[0])) for p in path) // 12 or 1),
            title="Рисунок Черепахи",
        )
        template = self.templates.pick(rng, subtype)
        return Instance(
            task_no=self.task_no,
            subtype=subtype,
            difficulty=difficulty,
            seed=0,
            statement_md=render(
                template,
                program=meta["program"],
                boundary="строго внутри" if meta["strict"] else "внутри или на границе",
            )
            + "\n\n![Рисунок Черепахи](asset:6.svg)",
            answer=answer,
            solution_steps=self._solution(meta, answer),
            reference_code=self._reference_code(meta),
            template_id=template.id,
            assets=[Attachment("6.svg", "image/svg+xml", "svg", svg.encode("utf-8"), inline=True)],
            meta=meta,
        )

    def _figure(self, rng: Rng, difficulty: int, subtype: str) -> dict[str, Any] | None:
        match subtype:
            case "6.1_rectangle_strict" | "6.2_rectangle_border":
                width = rng.randint(5, 14 + difficulty * 4)
                height = rng.randint(5, 14 + difficulty * 4)
                commands = [[width, -90], [height, -90], [width, -90], [height, -90]]
                program = f"Повтори 2 [Вперёд {width} Направо 90 Вперёд {height} Направо 90]"
                return {
                    "commands": commands,
                    "program": program,
                    "strict": subtype == "6.1_rectangle_strict",
                    "shape": "rectangle",
                    "width": width,
                    "height": height,
                }
            case "6.3_intersection":
                w1 = rng.randint(8, 12 + difficulty * 3)
                h1 = rng.randint(8, 12 + difficulty * 3)
                shift = rng.randint(3, max(4, w1 - 3))
                w2 = rng.randint(6, w1 + 4)
                h2 = rng.randint(6, h1 + 4)
                first = [[w1, -90], [h1, -90], [w1, -90], [h1, -90]]
                second = [[w2, -90], [h2, -90], [w2, -90], [h2, -90]]
                program = (
                    f"Повтори 2 [Вперёд {w1} Направо 90 Вперёд {h1} Направо 90]\n"
                    "Поднять хвост\n"
                    f"Направо 90 Вперёд {shift} Налево 90\n"
                    "Опустить хвост\n"
                    f"Повтори 2 [Вперёд {w2} Направо 90 Вперёд {h2} Направо 90]"
                )
                return {
                    "commands": first,
                    "commands_b": second,
                    "offset": [shift, 0],
                    "program": program,
                    "strict": True,
                    "shape": "intersection",
                }
            case "6.4_slanted":
                side = rng.randint(6, 10 + difficulty * 2)
                base = rng.randint(8, 14 + difficulty * 3)
                commands = [[base, -135], [side, -45], [base, -135], [side, -45]]
                program = f"Повтори 2 [Вперёд {base} Направо 135 Вперёд {side} Направо 45]"
                return {
                    "commands": commands,
                    "program": program,
                    "strict": rng.chance(0.5),
                    "shape": "slanted",
                }
            case "6.5_lshape":
                # Up a, right b, down c, right d, down (a - c), left (b + d) closes
                # the outline, so c must stay below a.
                a = rng.randint(8, 12 + difficulty * 2)
                b = rng.randint(4, 8 + difficulty)
                c = rng.randint(3, a - 3)
                d = rng.randint(4, 8 + difficulty)
                commands = [
                    [a, -90],
                    [b, -90],
                    [c, 90],
                    [d, -90],
                    [a - c, -90],
                    [b + d, -90],
                ]
                program = (
                    f"Вперёд {a} Направо 90 Вперёд {b} Направо 90 Вперёд {c} "
                    f"Налево 90 Вперёд {d} Направо 90 Вперёд {a - c} Направо 90 "
                    f"Вперёд {b + d} Направо 90"
                )
                return {
                    "commands": commands,
                    "program": program,
                    "strict": True,
                    "shape": "lshape",
                }
        return None

    # -- solving ------------------------------------------------------------
    def solve_fast(self, meta: dict[str, Any]) -> str:
        """Ray casting over the bounding box, as the method card teaches."""
        strict = bool(meta["strict"])
        if meta["shape"] == "intersection":
            poly_a = turtle_polygon([tuple(c) for c in meta["commands"]])
            poly_b = turtle_polygon(
                [tuple(c) for c in meta["commands_b"]], start=tuple(meta["offset"])
            )
            return str(count_lattice_points_intersection(poly_a, poly_b, strict=strict))
        poly = turtle_polygon([tuple(c) for c in meta["commands"]])
        return str(count_lattice_points(poly, strict=strict))

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        """Winding number instead of ray casting; Pick's theorem where it applies."""
        strict = bool(meta["strict"])
        if meta["shape"] == "intersection":
            poly_a = turtle_polygon([tuple(c) for c in meta["commands"]])
            poly_b = turtle_polygon(
                [tuple(c) for c in meta["commands_b"]], start=tuple(meta["offset"])
            )
            xs = [p[0] for p in poly_a] + [p[0] for p in poly_b]
            ys = [p[1] for p in poly_a] + [p[1] for p in poly_b]
            from egegen.solvers.polygon import winding_inside

            return str(
                sum(
                    winding_inside(x, y, poly_a, strict=strict)
                    and winding_inside(x, y, poly_b, strict=strict)
                    for x in range(int(min(xs)) - 1, int(max(xs)) + 2)
                    for y in range(int(min(ys)) - 1, int(max(ys)) + 2)
                )
            )
        poly = turtle_polygon([tuple(c) for c in meta["commands"]])
        return str(count_lattice_points_winding(poly, strict=strict))

    def enumerate_answers(self, meta: dict[str, Any]) -> list[str] | None:
        """Pick's theorem — an exact third opinion, with no scanning at all."""
        if meta["shape"] in ("intersection", "slanted"):
            return None
        poly = turtle_polygon([tuple(c) for c in meta["commands"]])
        interior = pick_interior(poly)
        if interior is None:
            return None
        if meta["strict"]:
            return [str(interior)]
        from egegen.solvers.polygon import boundary_lattice_points

        boundary = boundary_lattice_points(poly)
        return None if boundary is None else [str(interior + boundary)]

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        if meta["shape"] == "rectangle":
            expected = rectangle_formula(meta["width"], meta["height"], strict=meta["strict"])
            if int(answer) != expected:
                raise ValueError(f"t06: rectangle formula says {expected}, scan says {answer}")

    # -- explanation --------------------------------------------------------
    def _reference_code(self, meta: dict[str, Any]) -> str:
        commands = ", ".join(f"({d}, {t})" for d, t in meta["commands"])
        return (
            "from math import cos, sin, radians\n\n"
            "def polygon(cmds, start=(0.0, 0.0)):\n"
            "    x, y = start; ang = 90.0; pts = [start]      # старт: вверх\n"
            "    for d, turn in cmds:                          # направо — минус\n"
            "        x += d * cos(radians(ang)); y += d * sin(radians(ang))\n"
            "        pts.append((round(x, 9), round(y, 9))); ang += turn\n"
            "    return pts[:-1]\n\n"
            "def inside(px, py, poly, strict, eps=1e-9):\n"
            "    ins = False; n = len(poly)\n"
            "    for i in range(n):\n"
            "        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]\n"
            "        on = (abs((x2-x1)*(py-y1) - (y2-y1)*(px-x1)) < eps\n"
            "              and min(x1,x2)-eps <= px <= max(x1,x2)+eps\n"
            "              and min(y1,y2)-eps <= py <= max(y1,y2)+eps)\n"
            "        if on: return not strict\n"
            "        if (y1 > py) != (y2 > py) and px < x1 + (py-y1)*(x2-x1)/(y2-y1):\n"
            "            ins = not ins\n"
            "    return ins\n\n"
            f"poly = polygon([{commands}])\n"
            "xs = [p[0] for p in poly]; ys = [p[1] for p in poly]\n"
            f"print(sum(inside(x, y, poly, strict={meta['strict']})\n"
            "          for x in range(int(min(xs))-1, int(max(xs))+2)\n"
            "          for y in range(int(min(ys))-1, int(max(ys))+2)))\n"
        )

    def _solution(self, meta: dict[str, Any], answer: str) -> list[str]:
        head = (
            "**Шаг 1.** Черепаха стартует в начале координат и смотрит **вверх**. "
            "«Направо 90» — поворот по часовой стрелке. Пройдите программу по шагам "
            "и выпишите координаты вершин."
        )
        if meta["shape"] == "rectangle":
            w, h = meta["width"], meta["height"]
            formula = f"({w} − 1)·({h} − 1)" if meta["strict"] else f"({w} + 1)·({h} + 1)"
            return [
                head,
                f"**Шаг 2.** Получается прямоугольник {w} × {h}. Для прямоугольника "
                "считать перебором не нужно — есть формула: строго внутри "
                "(w − 1)(h − 1) точек, вместе с границей (w + 1)(h + 1).",
                f"**Шаг 3.** {formula} = **{answer}**.",
            ]
        return [
            head,
            "**Шаг 2.** Фигура не прямоугольная, поэтому перебираем все целые точки "
            "в описанном прямоугольнике и для каждой проверяем, лежит ли она внутри "
            "многоугольника. Граница учитывается по условию: здесь — "
            + ("строго внутри" if meta["strict"] else "внутри или на границе")
            + ".",
            "**Шаг 3.** Шаблон:\n\n```python\n" + self._reference_code(meta) + "```",
            f"**Ответ:** **{answer}**.",
        ]


register(Task06())
