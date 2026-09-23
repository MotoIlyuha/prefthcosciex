"""Task 13 — counting an executor's programs (this slot held task 23 before 2027).

The command set and the value ranges come from ``fipi_2027.yaml`` (section t13), so
a change in the approved demo version is a config edit. The counting itself is a
dynamic program; the naive cross-check enumerates programs breadth-first.
"""

from __future__ import annotations

from typing import Any

from egegen.core.errors import GenerationFailedError
from egegen.core.fipi import load_fipi_config
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.templates import render
from egegen.core.types import Instance, Uniqueness
from egegen.solvers.executor import (
    command_label,
    count_avoiding,
    count_programs,
    count_programs_bounded,
    count_programs_naive,
    count_through,
    count_through_not_through,
    is_monotone,
)


class Task13(Generator):
    task_no = 13
    answer_kind = "int"
    checker = "exact"
    uniqueness = Uniqueness.FUNCTIONAL

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(120):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailedError(f"t13/{subtype}: no instance in the configured answer range")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        cfg = load_fipi_config().t13
        commands = list(cfg.commands)
        if subtype == "13.5_non_monotone":
            commands = [*commands, "sub1"]
        a = rng.randint(cfg.min_a, cfg.min_a + 12)
        # How fast the program count grows depends entirely on the command set, which
        # comes from the config: two commands need a wide A..B gap to reach a few
        # hundred programs, three commands blow past the cap almost immediately. So B
        # is searched for rather than drawn at random.
        b = self._pick_target(rng, a, commands, cfg, difficulty)
        if b is None:
            return None

        meta: dict[str, Any] = {
            "subtype": subtype,
            "commands": commands,
            "a": a,
            "b": b,
            "answer_min": cfg.answer_min,
            "answer_max": cfg.answer_max,
        }
        fields: dict[str, Any] = {
            "a": a,
            "b": b,
            "commands": self._describe_commands(commands),
        }

        match subtype:
            case "13.1_direct":
                meta["question"] = "direct"
            case "13.2_through":
                c = self._waypoint(rng, a, b)
                if c is None:
                    return None
                meta["question"], meta["c"] = "through", c
                fields["c"] = c
            case "13.3_avoiding":
                c = self._waypoint(rng, a, b)
                if c is None:
                    return None
                meta["question"], meta["c"] = "avoiding", c
                fields["c"] = c
            case "13.4_through_not_through":
                pair = self._two_waypoints(rng, a, b)
                if pair is None:
                    return None
                meta["question"], (meta["c"], meta["d"]) = "through_not", pair
                fields["c"], fields["d"] = pair
            case "13.5_non_monotone":
                meta["question"] = "bounded"
                meta["lo"], meta["hi"] = 1, b + 10
                # With a subtract command the count grows steeply with the length
                # bound, so the bound is searched for instead of fixed by difficulty.
                length = self._pick_length(meta, cfg, difficulty)
                if length is None:
                    return None
                meta["max_len"] = length
                fields["lo"], fields["hi"] = meta["lo"], meta["hi"]
                fields["max_len"] = length
            case "13.6_trajectory":
                c = self._waypoint(rng, a, b)
                if c is None:
                    return None
                meta["question"], meta["c"] = "through", c
                fields["c"] = c
            case _:
                return None

        answer = self.solve_fast(meta)
        if not cfg.answer_min <= int(answer) <= cfg.answer_max:
            return None

        template = self.templates.pick(rng, subtype)
        return Instance(
            task_no=self.task_no,
            subtype=subtype,
            difficulty=difficulty,
            seed=0,
            statement_md=render(template, **fields),
            answer=answer,
            solution_steps=self._solution(meta, answer),
            reference_code=self._reference_code(meta),
            template_id=template.id,
            meta=meta,
        )

    def _pick_target(
        self, rng: Rng, a: int, commands: list[str], cfg: Any, difficulty: int
    ) -> int | None:
        """Smallest-to-largest sweep for a B whose program count sits in the band."""
        if not is_monotone(commands):
            return int(min(cfg.max_b, a + 10 + difficulty * 4))
        band_lo = max(cfg.answer_min * 4, 12)
        band_hi = cfg.answer_max
        usable = [
            b
            for b in range(a + 6, min(cfg.max_b, a + 120) + 1)
            if band_lo <= count_programs(a, b, commands) <= band_hi
        ]
        if not usable:
            return None
        # Harder instances take a larger B, which means a bigger search tree.
        span = max(1, len(usable) // 5)
        window = usable[min((difficulty - 1) * span, len(usable) - 1) :][:span]
        return rng.choice(window or usable)

    def _pick_length(self, meta: dict[str, Any], cfg: Any, difficulty: int) -> int | None:
        """Shortest length bound whose program count is inside the configured band."""
        usable: list[int] = []
        for length in range(3, 20):
            total = count_programs_bounded(
                meta["a"],
                meta["b"],
                meta["commands"],
                lo=meta["lo"],
                hi=meta["hi"],
                max_len=length,
            )
            if total > cfg.answer_max:
                break
            if total >= cfg.answer_min:
                usable.append(length)
        if not usable:
            return None
        return usable[min(difficulty - 1, len(usable) - 1)]

    def _waypoint(self, rng: Rng, a: int, b: int) -> int | None:
        if b - a < 6:
            return None
        return rng.randint(a + 2, b - 2)

    def _two_waypoints(self, rng: Rng, a: int, b: int) -> tuple[int, int] | None:
        if b - a < 10:
            return None
        c = rng.randint(a + 2, b - 5)
        d = rng.randint(c + 2, b - 2)
        return (c, d) if c < d else None

    def _describe_commands(self, commands: list[str]) -> str:
        return "; ".join(f"{i + 1}. {command_label(cmd)}" for i, cmd in enumerate(commands))

    # -- solving ------------------------------------------------------------
    def solve_fast(self, meta: dict[str, Any]) -> str:
        commands = meta["commands"]
        a, b = meta["a"], meta["b"]
        match meta["question"]:
            case "direct":
                return str(count_programs(a, b, commands))
            case "through":
                return str(count_through(a, meta["c"], b, commands))
            case "avoiding":
                return str(count_avoiding(a, b, meta["c"], commands))
            case "through_not":
                return str(count_through_not_through(a, meta["c"], meta["d"], b, commands))
            case "bounded":
                return str(
                    count_programs_bounded(
                        a, b, commands, lo=meta["lo"], hi=meta["hi"], max_len=meta["max_len"]
                    )
                )
        raise ValueError(meta["question"])

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        """Enumerate programs breadth-first instead of folding them into a DP."""
        commands = meta["commands"]
        a, b = meta["a"], meta["b"]
        if not is_monotone(commands):
            return None  # the bounded variant is cross-checked by enumerate_answers
        match meta["question"]:
            case "direct":
                return str(count_programs_naive(a, b, commands))
            case "through":
                return str(
                    count_programs_naive(a, meta["c"], commands)
                    * count_programs_naive(meta["c"], b, commands)
                )
            case "avoiding":
                return str(
                    count_programs_naive(a, b, commands)
                    - count_programs_naive(a, meta["c"], commands)
                    * count_programs_naive(meta["c"], b, commands)
                )
            case "through_not":
                c, d = meta["c"], meta["d"]
                tail = count_programs_naive(c, b, commands) - count_programs_naive(
                    c, d, commands
                ) * count_programs_naive(d, b, commands)
                return str(count_programs_naive(a, c, commands) * tail)
        return None

    def enumerate_answers(self, meta: dict[str, Any]) -> list[str] | None:
        """For the bounded variant, count programs by explicit depth-first walk."""
        if meta["question"] != "bounded":
            return None
        from egegen.solvers.executor import COMMAND_LIBRARY

        fns = [COMMAND_LIBRARY[c][1] for c in meta["commands"]]
        lo, hi, target = meta["lo"], meta["hi"], meta["b"]
        total = 0
        stack: list[tuple[int, int]] = [(meta["a"], meta["max_len"])]
        while stack:
            value, budget = stack.pop()
            if value == target:
                total += 1
            if budget == 0:
                continue
            for fn in fns:
                nxt = fn(value)
                if lo <= nxt <= hi:
                    stack.append((nxt, budget - 1))
        return [str(total)]

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        if not meta["answer_min"] <= int(answer) <= meta["answer_max"]:
            raise ValueError(f"t13: answer {answer} outside the configured range")

    # -- explanation --------------------------------------------------------
    def _reference_code(self, meta: dict[str, Any]) -> str:
        from egegen.solvers.executor import COMMAND_LIBRARY

        exprs = []
        for cmd in meta["commands"]:
            match cmd:
                case "add1" | "add2" | "add3":
                    exprs.append(f"f(a + {cmd[3:]}, b)")
                case "mul2" | "mul3":
                    exprs.append(f"f(a * {cmd[3:]}, b)")
                case "sub1" | "sub2":
                    exprs.append(f"f(a - {cmd[3:]}, b)")
            assert cmd in COMMAND_LIBRARY
        head = (
            "from functools import lru_cache\n\n@lru_cache(None)\ndef f(a, b):\n"
            "    if a > b: return 0\n"
            "    if a == b: return 1\n"
            f"    return {' + '.join(exprs)}\n\n"
        )
        a, b = meta["a"], meta["b"]
        match meta["question"]:
            case "direct":
                return head + f"print(f({a}, {b}))\n"
            case "through":
                c = meta["c"]
                return head + f"print(f({a}, {c}) * f({c}, {b}))\n"
            case "avoiding":
                c = meta["c"]
                return head + f"print(f({a}, {b}) - f({a}, {c}) * f({c}, {b}))\n"
            case "through_not":
                c, d = meta["c"], meta["d"]
                return head + (f"print(f({a}, {c}) * (f({c}, {b}) - f({c}, {d}) * f({d}, {b})))\n")
            case "bounded":
                return (
                    "from functools import lru_cache\n\n@lru_cache(None)\n"
                    "def f(a, steps):\n"
                    f"    here = 1 if a == {b} else 0\n"
                    "    if steps == 0: return here\n"
                    "    total = here\n"
                    "    for nxt in ("
                    + ", ".join(e.replace("f(", "").replace(", b)", "") for e in exprs)
                    + "):\n"
                    f"        if {meta['lo']} <= nxt <= {meta['hi']}:\n"
                    "            total += f(nxt, steps - 1)\n"
                    "    return total\n\n"
                    f"print(f({a}, {meta['max_len']}))\n"
                )
        raise ValueError(meta["question"])

    def _solution(self, meta: dict[str, Any], answer: str) -> list[str]:
        a, b = meta["a"], meta["b"]
        steps = [
            "**Шаг 1.** Обозначим через f(a, b) число программ, переводящих число a "
            "в число b. Пустая программа считается, поэтому **f(b, b) = 1**; если "
            "a > b, ни одна программа не подходит, поэтому f(a, b) = 0.",
            "**Шаг 2.** Каждая программа начинается с одной из команд, поэтому "
            "f(a, b) — это сумма по всем командам:\n\n```python\n"
            + self._reference_code(meta)
            + "```",
        ]
        match meta["question"]:
            case "through":
                steps.append(
                    f"**Шаг 3.** «Через {meta['c']}» — это произведение: сначала "
                    f"дойти из {a} в {meta['c']}, затем из {meta['c']} в {b}. "
                    f"Ответ — **{answer}**."
                )
            case "avoiding":
                steps.append(
                    f"**Шаг 3.** «Минуя {meta['c']}» — из всех программ вычитаем те, "
                    "что проходят через это число. Вычитание корректно именно потому, "
                    "что команды только увеличивают значение, и через точку можно пройти "
                    f"не более одного раза. Ответ — **{answer}**."
                )
            case "through_not":
                steps.append(
                    f"**Шаг 3.** «Через {meta['c']}, но не через {meta['d']}»: "
                    f"f({a}, {meta['c']}) × (f({meta['c']}, {b}) − "
                    f"f({meta['c']}, {meta['d']}) × f({meta['d']}, {b})). "
                    f"Ответ — **{answer}**."
                )
            case "bounded":
                steps.append(
                    "**Шаг 3.** Здесь есть команда, уменьшающая число, поэтому "
                    "значение может вернуться назад, и без ограничений программ "
                    f"бесконечно много. Условие задаёт диапазон [{meta['lo']}; "
                    f"{meta['hi']}] и длину не более {meta['max_len']} команд — "
                    f"считаем в этих рамках. Ответ — **{answer}**."
                )
            case _:
                steps.append(f"**Шаг 3.** Ответ — **{answer}**.")
        return steps


register(Task13())
