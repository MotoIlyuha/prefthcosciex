"""Task 27 — one algorithm, two files: a small one and a million-number one (2 points).

The whole point of the task is that a quadratic solution passes on file A and dies
on file B, so the instance ships both. File B is not stored: it is a pure function
of its seed, so the worker can materialise the ~7 MB of text on demand while the
generator streams it to compute the answer.

The 2027 answer layout — both numbers on one line — comes from ``fipi_2027.yaml``.
"""

from __future__ import annotations

from typing import Any

from egegen.core.errors import GenerationFailedError
from egegen.core.fipi import load_fipi_config
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng, bulk_ints
from egegen.core.tables import to_txt
from egegen.core.templates import render
from egegen.core.types import Attachment, Instance, Uniqueness

BRUTE_LIMIT = 2000
A_SIZES = {1: 400, 2: 1000, 3: 2000, 4: 5000, 5: 0}
B_SIZES = {1: 20_000, 2: 50_000, 3: 200_000, 4: 500_000, 5: 0}
VALUE_LO, VALUE_HI = -(10**6), 10**6


class Task27(Generator):
    task_no = 27
    answer_kind = "two_ints"
    checker = "int_pair_ordered"
    requires_code = True
    uniqueness = Uniqueness.FUNCTIONAL
    #: The doc allows 2 s here: the instance is built asynchronously by the worker.
    generation_budget_ms = 2000
    sweep_seeds = 3

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(12):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailedError(f"t27/{subtype}: no valid instance")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        cfg = load_fipi_config().t27
        a_size = A_SIZES[difficulty] or cfg.file_a_size
        b_size = B_SIZES[difficulty] or cfg.file_b_size
        a_values = bulk_ints(rng.fork("A").seed, a_size, VALUE_LO, VALUE_HI)
        b_seed = rng.fork("B").seed

        k = rng.randint(3, 6 + difficulty)
        m = rng.choice([3, 4, 5, 6, 7, 8, 9, 11])
        window = rng.randint(4, 8 + difficulty)

        meta: dict[str, Any] = {
            "subtype": subtype,
            "a_values": a_values,
            "b_seed": b_seed,
            "b_size": b_size,
            "b_lo": VALUE_LO,
            "b_hi": VALUE_HI,
            "mini_b_size": min(cfg.mini_b_size, b_size),
            "k": k,
            "m": m,
            "window": window,
            "answer_layout": cfg.answer_layout,
            "separator": cfg.separator,
        }
        meta["question"] = {
            "27.1_pair_distance_mod": "pair_mod",
            "27.2_pair_one_divisible": "pair_one_div",
            "27.3_count_pairs": "count_pairs",
            "27.4_window_sum": "window_sum",
            "27.5_median_point": "median",
        }.get(subtype)
        if meta["question"] is None:
            return None

        answer_a = self._solve_stream(a_values, meta)
        if answer_a is None:
            return None
        answer_b = self._solve_stream(self._values_b(meta), meta)
        if answer_b is None:
            return None
        meta["answer_a"], meta["answer_b"] = answer_a, answer_b
        answer = self._format(answer_a, answer_b, meta)

        mini_b = bulk_ints(b_seed, meta["mini_b_size"], VALUE_LO, VALUE_HI)
        template = self.templates.pick(rng, subtype)
        statement = render(
            template,
            a_size=a_size,
            b_size=b_size,
            mini_size=meta["mini_b_size"],
            k=k,
            m=m,
            window=window,
            preview="\n".join([str(a_size), *[str(v) for v in a_values[:6]]]),
            layout_hint=(
                "в одну строку через пробел"
                if cfg.answer_layout == "one_line_pair"
                else "в две строки: сначала для файла A, затем для файла B"
            ),
        )
        return Instance(
            task_no=self.task_no,
            subtype=subtype,
            difficulty=difficulty,
            seed=0,
            statement_md=statement,
            answer=answer,
            answer_kind="two_ints" if cfg.answer_layout == "one_line_pair" else "string",
            checker=("int_pair_ordered" if cfg.answer_layout == "one_line_pair" else "two_lines"),
            solution_steps=self._solution(meta, answer_a, answer_b),
            reference_code=self._reference_code(meta),
            template_id=template.id,
            assets=[
                Attachment("27A.txt", "text/plain", "txt", to_txt([a_size, *a_values])),
                Attachment(
                    "27B-mini.txt",
                    "text/plain",
                    "txt",
                    to_txt([len(mini_b), *mini_b]),
                ),
                # The full file is built by the worker from b_seed and gzipped to S3.
                Attachment("27B.txt", "text/plain", "txt", b"", deferred=True),
            ],
            meta=meta,
        )

    def _values_b(self, meta: dict[str, Any]) -> list[int]:
        return bulk_ints(meta["b_seed"], meta["b_size"], meta["b_lo"], meta["b_hi"])

    def _format(self, a: int, b: int, meta: dict[str, Any]) -> str:
        if meta["answer_layout"] == "one_line_pair":
            return f"{a}{meta['separator']}{b}"
        return f"{a}\n{b}"

    # -- solving ------------------------------------------------------------
    def _solve_stream(self, values: list[int], meta: dict[str, Any]) -> int | None:
        """The intended O(n) pass: one sweep, remembering the best candidate so far."""
        k, m = meta["k"], meta["m"]
        n = len(values)
        match meta["question"]:
            case "pair_mod":
                best_by_rest = [None] * m  # type: list[int | None]
                answer: int | None = None
                for i in range(n):
                    if i - k >= 0:
                        far = values[i - k]
                        r = far % m
                        if best_by_rest[r] is None or far > best_by_rest[r]:
                            best_by_rest[r] = far
                    need = (-values[i]) % m
                    partner = best_by_rest[need]
                    if partner is not None:
                        total = values[i] + partner
                        if answer is None or total > answer:
                            answer = total
                return answer
            case "pair_one_div":
                best_any: int | None = None
                best_div: int | None = None
                answer = None
                for i in range(n):
                    if i - k >= 0:
                        far = values[i - k]
                        if best_any is None or far > best_any:
                            best_any = far
                        if far % m == 0 and (best_div is None or far > best_div):
                            best_div = far
                    if best_div is not None:
                        total = values[i] + best_div
                        if answer is None or total > answer:
                            answer = total
                    if values[i] % m == 0 and best_any is not None:
                        total = values[i] + best_any
                        if answer is None or total > answer:
                            answer = total
                return answer
            case "count_pairs":
                counts = [0] * m
                total_pairs = 0
                for i in range(n):
                    if i - k >= 0:
                        counts[values[i - k] % m] += 1
                    total_pairs += counts[(-values[i]) % m]
                return total_pairs
            case "window_sum":
                w = meta["window"]
                if n < w:
                    return None
                running = sum(values[:w])
                best = running if running % m == 0 else None
                for i in range(w, n):
                    running += values[i] - values[i - w]
                    if running % m == 0 and (best is None or running > best):
                        best = running
                return best
            case "median":
                ordered = sorted(values)
                pivot = ordered[len(ordered) // 2]
                return sum(abs(v - pivot) for v in ordered)
        raise ValueError(meta["question"])

    def _solve_backwards(self, values: list[int], meta: dict[str, Any]) -> int | None:
        """The mirror image of the fast pass, so a prefix/suffix slip cannot hide.

        Where the fast solver walks forward remembering the best element *before*
        position ``i - k``, this one walks backward remembering the best element
        *after* ``i + k``. Both stay O(n) time and O(M) memory, which matters: an
        O(n x M) table would be hundreds of megabytes on the million-number file.
        """
        k, m = meta["k"], meta["m"]
        n = len(values)
        match meta["question"]:
            case "pair_mod":
                best_by_rest: list[int | None] = [None] * m
                answer: int | None = None
                for i in range(n - 1, -1, -1):
                    if i + k < n:
                        far = values[i + k]
                        r = far % m
                        if best_by_rest[r] is None or far > best_by_rest[r]:
                            best_by_rest[r] = far
                    partner = best_by_rest[(-values[i]) % m]
                    if partner is not None:
                        total = values[i] + partner
                        if answer is None or total > answer:
                            answer = total
                return answer
            case "pair_one_div":
                best_any: int | None = None
                best_div: int | None = None
                answer = None
                for i in range(n - 1, -1, -1):
                    if i + k < n:
                        far = values[i + k]
                        if best_any is None or far > best_any:
                            best_any = far
                        if far % m == 0 and (best_div is None or far > best_div):
                            best_div = far
                    if best_div is not None:
                        total = values[i] + best_div
                        if answer is None or total > answer:
                            answer = total
                    if values[i] % m == 0 and best_any is not None:
                        total = values[i] + best_any
                        if answer is None or total > answer:
                            answer = total
                return answer
            case "count_pairs":
                trailing = [0] * m
                total_pairs = 0
                for i in range(n - 1, -1, -1):
                    if i + k < n:
                        trailing[values[i + k] % m] += 1
                    total_pairs += trailing[(-values[i]) % m]
                return total_pairs
            case "window_sum":
                w = meta["window"]
                if n < w:
                    return None
                prefix = [0]
                for v in values:
                    prefix.append(prefix[-1] + v)
                best: int | None = None
                for i in range(n - w + 1):
                    total = prefix[i + w] - prefix[i]
                    if total % m == 0 and (best is None or total > best):
                        best = total
                return best
            case "median":
                ordered = sorted(values)
                prefix = [0]
                for v in ordered:
                    prefix.append(prefix[-1] + v)
                best = None
                for idx, pivot in enumerate(ordered):
                    left = pivot * idx - prefix[idx]
                    right = (prefix[-1] - prefix[idx + 1]) - pivot * (len(ordered) - idx - 1)
                    total = left + right
                    if best is None or total < best:
                        best = total
                return best
        return None

    def _solve_quadratic(self, values: list[int], meta: dict[str, Any]) -> int | None:
        """The two-loop solution students write first. Only viable on file A."""
        if len(values) > BRUTE_LIMIT:
            return None
        k, m = meta["k"], meta["m"]
        n = len(values)
        match meta["question"]:
            case "pair_mod":
                best = None
                for i in range(n):
                    for j in range(i + k, n):
                        if (values[i] + values[j]) % m == 0:
                            total = values[i] + values[j]
                            if best is None or total > best:
                                best = total
                return best
            case "pair_one_div":
                best = None
                for i in range(n):
                    for j in range(i + k, n):
                        if values[i] % m == 0 or values[j] % m == 0:
                            total = values[i] + values[j]
                            if best is None or total > best:
                                best = total
                return best
            case "count_pairs":
                return sum(
                    1 for i in range(n) for j in range(i + k, n) if (values[i] + values[j]) % m == 0
                )
        return None

    def solve_fast(self, meta: dict[str, Any]) -> str:
        a = self._solve_stream(meta["a_values"], meta)
        b = self._solve_stream(self._values_b(meta), meta)
        if a is None or b is None:
            raise GenerationFailedError("t27: no qualifying pair")
        return self._format(a, b, meta)

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        a = self._solve_backwards(meta["a_values"], meta)
        b = self._solve_backwards(self._values_b(meta), meta)
        if a is None or b is None:
            return None
        quadratic = self._solve_quadratic(meta["a_values"], meta)
        if quadratic is not None and quadratic != a:
            # The two-loop reading of the statement and the linear one must agree on
            # file A; that is exactly the self-check the method card prescribes.
            return f"quadratic disagrees on A: {quadratic} vs {a}"
        return self._format(a, b, meta)

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        if not answer.strip():
            raise ValueError("t27: empty answer")

    # -- explanation --------------------------------------------------------
    def _reference_code(self, meta: dict[str, Any]) -> str:
        k, m, w = meta["k"], meta["m"], meta["window"]
        head = (
            "for name in ('27A.txt', '27B.txt'):\n"
            "    f = open(name); n = int(f.readline())\n"
            "    a = [int(f.readline()) for _ in range(n)]\n"
        )
        match meta["question"]:
            case "pair_mod":
                body = (
                    f"    K, M = {k}, {m}\n"
                    "    best = None; mx = [None] * M\n"
                    "    for i in range(n):\n"
                    "        if i - K >= 0:\n"
                    "            r = a[i - K] % M\n"
                    "            if mx[r] is None or a[i - K] > mx[r]: mx[r] = a[i - K]\n"
                    "        need = (-a[i]) % M\n"
                    "        if mx[need] is not None:\n"
                    "            s = a[i] + mx[need]\n"
                    "            if best is None or s > best: best = s\n"
                )
            case "pair_one_div":
                body = (
                    f"    K, M = {k}, {m}\n"
                    "    best = None; any_max = None; div_max = None\n"
                    "    for i in range(n):\n"
                    "        if i - K >= 0:\n"
                    "            x = a[i - K]\n"
                    "            any_max = x if any_max is None else max(any_max, x)\n"
                    "            if x % M == 0:\n"
                    "                div_max = x if div_max is None else max(div_max, x)\n"
                    "        if div_max is not None:\n"
                    "            s = a[i] + div_max\n"
                    "            if best is None or s > best: best = s\n"
                    "        if a[i] % M == 0 and any_max is not None:\n"
                    "            s = a[i] + any_max\n"
                    "            if best is None or s > best: best = s\n"
                )
            case "count_pairs":
                body = (
                    f"    K, M = {k}, {m}\n"
                    "    best = 0; cnt = [0] * M\n"
                    "    for i in range(n):\n"
                    "        if i - K >= 0: cnt[a[i - K] % M] += 1\n"
                    "        best += cnt[(-a[i]) % M]\n"
                )
            case "window_sum":
                body = (
                    f"    W, M = {w}, {m}\n"
                    "    cur = sum(a[:W]); best = cur if cur % M == 0 else None\n"
                    "    for i in range(W, n):\n"
                    "        cur += a[i] - a[i - W]\n"
                    "        if cur % M == 0 and (best is None or cur > best): best = cur\n"
                )
            case "median":
                body = (
                    "    b = sorted(a); med = b[len(b) // 2]\n"
                    "    best = sum(abs(x - med) for x in b)\n"
                )
            case _:
                raise ValueError(meta["question"])
        tail = (
            "    print(best, end=' ')\n"
            if meta["answer_layout"] == "one_line_pair"
            else "    print(best)\n"
        )
        return head + body + tail

    def _solution(self, meta: dict[str, Any], answer_a: int, answer_b: int) -> list[str]:
        layout = (
            "оба числа в **одной строке** через пробел"
            if meta["answer_layout"] == "one_line_pair"
            else "числа в две строки"
        )
        return [
            "**Шаг 1.** Сначала решите задачу для файла A «в лоб», двумя циклами. "
            "Это проверка того, что вы правильно поняли условие, а не решение: "
            "на файле B квадратичный перебор — это 10¹² операций, он не успеет "
            "никогда.",
            "**Шаг 2.** Быстрое решение — один проход. Идём по массиву и помним "
            "лучшего кандидата среди элементов, отстоящих не менее чем на K "
            "позиций назад; для текущего элемента нужен остаток "
            "`(-a[i]) % M`.\n\n```python\n" + self._reference_code(meta) + "```",
            "**Шаг 3.** Наивный и быстрый ответы **на файле A обязаны совпасть**. "
            "Если не совпали — ошибка в быстром решении, и файл B считать рано.",
            f"**Ответ:** для A — **{answer_a}**, для B — **{answer_b}**. "
            f"Записываем {layout}. За одно верное число даётся 1 балл из 2.",
        ]


register(Task27())
