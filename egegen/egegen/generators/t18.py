"""Task 18 — the collecting robot on a spreadsheet grid.

Walls in an ``.ods`` file are cell borders, which are invisible on a phone. The
instance therefore ships three views of the same field: the numbers as CSV/ODS, the
walls as ``walls.json``, and an SVG where the walls are drawn as heavy lines.

The fast solver fills the table forward; the naive one recurses backwards from the
finish, so a wall applied in the wrong direction shows up as a mismatch.
"""

from __future__ import annotations

from typing import Any

from egegen.core.errors import GenerationFailedError
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.svg import grid_svg
from egegen.core.tables import to_csv, to_ods
from egegen.core.templates import render
from egegen.core.types import Attachment, Instance, Uniqueness
from egegen.core.walls import Walls


class Task18(Generator):
    task_no = 18
    answer_kind = "two_ints"
    checker = "int_pair_ordered"
    requires_code = True
    uniqueness = Uniqueness.FUNCTIONAL
    generation_budget_ms = 300

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(40):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailedError(f"t18/{subtype}: no field with a reachable finish")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        size = 6 + difficulty + rng.randint(0, 2)
        grid = [[rng.randint(1, 99) for _ in range(size)] for _ in range(size)]
        upward = subtype == "18.3_up_right"
        wall_share = 0.0 if subtype == "18.1_no_walls" else 0.10 + 0.04 * difficulty
        walls = self._random_walls(rng, size, wall_share)

        meta: dict[str, Any] = {
            "subtype": subtype,
            "grid": grid,
            "size": size,
            "upward": upward,
            "walls_right": sorted(walls.right),
            "walls_down": sorted(walls.down),
        }
        best = self._fill_forward(meta)
        if best is None:
            return None
        maximum, minimum = best
        if maximum == minimum:
            return None  # a field with a single possible path teaches nothing
        answer = f"{maximum} {minimum}"

        rows = [[str(v) for v in row] for row in grid]
        svg = grid_svg(
            rows,
            walls=walls.svg_segments(),
            start=(size - 1, 0) if upward else (0, 0),
            finish=(0, size - 1) if upward else (size - 1, size - 1),
            title="Поле робота",
        )
        template = self.templates.pick(rng, subtype)
        statement = render(
            template,
            size=size,
            start="левой нижней" if upward else "левой верхней",
            finish="правой верхней" if upward else "правой нижней",
            moves="вверх или вправо" if upward else "вправо или вниз",
            walls_note=(
                ""
                if subtype == "18.1_no_walls"
                else "Жирные линии на схеме — стены: через них робот пройти не может. "
                "Те же стены перечислены в файле `walls.json`."
            ),
        )
        return Instance(
            task_no=self.task_no,
            subtype=subtype,
            difficulty=difficulty,
            seed=0,
            statement_md=statement + "\n\n![Поле робота](asset:18.svg)",
            answer=answer,
            solution_steps=self._solution(meta, maximum, minimum),
            reference_code=self._reference_code(meta),
            template_id=template.id,
            assets=[
                Attachment("18.svg", "image/svg+xml", "svg", svg.encode("utf-8"), inline=True),
                Attachment("18.csv", "text/csv", "csv", to_csv(grid)),
                Attachment(
                    "18.ods",
                    "application/vnd.oasis.opendocument.spreadsheet",
                    "ods",
                    to_ods(grid, sheet_name="Поле"),
                ),
                Attachment("walls.json", "application/json", "json", walls.to_json()),
            ],
            meta=meta,
        )

    def _random_walls(self, rng: Rng, size: int, share: float) -> Walls:
        right: set[tuple[int, int]] = set()
        down: set[tuple[int, int]] = set()
        for i in range(size):
            for j in range(size):
                if j + 1 < size and rng.chance(share):
                    right.add((i, j))
                if i + 1 < size and rng.chance(share):
                    down.add((i, j))
        return Walls(right, down)

    # -- solving ------------------------------------------------------------
    def _walls(self, meta: dict[str, Any]) -> Walls:
        return Walls(
            {(int(a), int(b)) for a, b in meta["walls_right"]},
            {(int(a), int(b)) for a, b in meta["walls_down"]},
        )

    def _fill_forward(self, meta: dict[str, Any]) -> tuple[int, int] | None:
        """Table filling, exactly as it is done in a spreadsheet."""
        grid, size, walls = meta["grid"], meta["size"], self._walls(meta)
        upward = meta["upward"]
        best_max: list[list[int | None]] = [[None] * size for _ in range(size)]
        best_min: list[list[int | None]] = [[None] * size for _ in range(size)]

        rows = range(size - 1, -1, -1) if upward else range(size)
        start = (size - 1, 0) if upward else (0, 0)
        for i in rows:
            for j in range(size):
                if (i, j) == start:
                    best_max[i][j] = best_min[i][j] = grid[i][j]
                    continue
                options_max: list[int] = []
                options_min: list[int] = []
                # From the left, in both movement schemes.
                if j > 0 and not walls.blocks_from_left(i, j) and best_max[i][j - 1] is not None:
                    options_max.append(best_max[i][j - 1])  # type: ignore[arg-type]
                    options_min.append(best_min[i][j - 1])  # type: ignore[arg-type]
                if upward:
                    # From below: the wall between (i, j) and (i+1, j) is "down" at (i, j).
                    if i + 1 < size and (i, j) not in walls.down and best_max[i + 1][j] is not None:
                        options_max.append(best_max[i + 1][j])  # type: ignore[arg-type]
                        options_min.append(best_min[i + 1][j])  # type: ignore[arg-type]
                elif i > 0 and not walls.blocks_from_above(i, j) and best_max[i - 1][j] is not None:
                    options_max.append(best_max[i - 1][j])  # type: ignore[arg-type]
                    options_min.append(best_min[i - 1][j])  # type: ignore[arg-type]
                if options_max:
                    best_max[i][j] = grid[i][j] + max(options_max)
                    best_min[i][j] = grid[i][j] + min(options_min)

        fi, fj = (0, size - 1) if upward else (size - 1, size - 1)
        if best_max[fi][fj] is None:
            return None
        high, low = best_max[fi][fj], best_min[fi][fj]
        assert high is not None and low is not None
        return high, low

    def _fill_backward(self, meta: dict[str, Any]) -> tuple[int, int] | None:
        """Memoised recursion from the finish towards the start.

        The forward fill visits cells in table order and the recursion visits them
        on demand, so a wrong fill order or a mis-aggregated pair of options shows up
        as a mismatch between the two.
        """
        grid, size, walls = meta["grid"], meta["size"], self._walls(meta)
        upward = meta["upward"]
        start = (size - 1, 0) if upward else (0, 0)
        cache: dict[tuple[int, int], tuple[int, int] | None] = {}

        def best(i: int, j: int) -> tuple[int, int] | None:
            if (i, j) == start:
                return grid[i][j], grid[i][j]
            if (i, j) in cache:
                return cache[(i, j)]
            cache[(i, j)] = None  # guards against revisiting while recursing
            candidates: list[tuple[int, int]] = []
            if j > 0 and (i, j - 1) not in walls.right:
                left = best(i, j - 1)
                if left is not None:
                    candidates.append(left)
            if upward:
                if i + 1 < size and (i, j) not in walls.down:
                    below = best(i + 1, j)
                    if below is not None:
                        candidates.append(below)
            elif i > 0 and (i - 1, j) not in walls.down:
                above = best(i - 1, j)
                if above is not None:
                    candidates.append(above)
            result = (
                (
                    grid[i][j] + max(c[0] for c in candidates),
                    grid[i][j] + min(c[1] for c in candidates),
                )
                if candidates
                else None
            )
            cache[(i, j)] = result
            return result

        fi, fj = (0, size - 1) if upward else (size - 1, size - 1)
        return best(fi, fj)

    def solve_fast(self, meta: dict[str, Any]) -> str:
        result = self._fill_forward(meta)
        if result is None:
            raise GenerationFailedError("t18: finish unreachable")
        return f"{result[0]} {result[1]}"

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        result = self._fill_backward(meta)
        return None if result is None else f"{result[0]} {result[1]}"

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        high, low = (int(x) for x in answer.split())
        if high < low:
            raise ValueError("t18: maximum must not be below the minimum")

    # -- explanation --------------------------------------------------------
    def _reference_code(self, meta: dict[str, Any]) -> str:
        if meta["upward"]:
            move_note = (
                "    # робот идёт вверх или вправо, старт в левой нижней клетке\n"
                "    for i in range(n - 1, -1, -1):\n"
                "        for j in range(m):\n"
                "            c = []\n"
                "            if j > 0 and (i, j - 1) not in R: c.append((mx[i][j-1], mn[i][j-1]))\n"
                "            if i + 1 < n and (i, j) not in D: c.append((mx[i+1][j], mn[i+1][j]))\n"
            )
            finish = "print(mx[0][-1], mn[0][-1])"
        else:
            move_note = (
                "    # робот идёт вправо или вниз, старт в левой верхней клетке\n"
                "    for i in range(n):\n"
                "        for j in range(m):\n"
                "            c = []\n"
                "            if i > 0 and (i - 1, j) not in D: c.append((mx[i-1][j], mn[i-1][j]))\n"
                "            if j > 0 and (i, j - 1) not in R: c.append((mx[i][j-1], mn[i][j-1]))\n"
            )
            finish = "print(mx[-1][-1], mn[-1][-1])"
        return (
            "import csv, json\n"
            "g = [[int(c) for c in row] for row in csv.reader(open('18.csv'))]\n"
            "walls = json.load(open('walls.json'))   # стена справа / снизу от клетки\n"
            "R = {tuple(w) for w in walls['right']}; D = {tuple(w) for w in walls['down']}\n"
            "n, m = len(g), len(g[0])\n"
            "mx = [[None] * m for _ in range(n)]; mn = [[None] * m for _ in range(n)]\n"
            "if True:\n" + move_note + "            c = [t for t in c if t[0] is not None]\n"
            "            mx[i][j] = g[i][j] + (max(t[0] for t in c) if c else 0)\n"
            "            mn[i][j] = g[i][j] + (min(t[1] for t in c) if c else 0)\n" + finish + "\n"
        )

    def _solution(self, meta: dict[str, Any], maximum: int, minimum: int) -> list[str]:
        direction = "вверх или вправо" if meta["upward"] else "вправо или вниз"
        return [
            "**Шаг 1.** Это динамическое программирование по таблице. Значение "
            "клетки = монеты в ней **плюс** лучшее из значений тех клеток, откуда "
            f"в неё можно прийти. Робот ходит только {direction}, поэтому вариантов "
            "прихода не больше двух.",
            "**Шаг 2.** Сначала посчитайте **без стен** — так проще убедиться, что "
            "файл прочитан правильно. Затем добавьте проверку стен: стена "
            "запрещает соответствующее направление прихода.",
            "**Шаг 3.** Максимум и минимум считаются в двух параллельных таблицах "
            "одним проходом:\n\n```python\n" + self._reference_code(meta) + "```",
            f"**Ответ:** **{maximum} {minimum}** — сначала максимальная сумма, "
            "затем минимальная. Стартовая клетка считается.",
        ]


register(Task18())
