"""Task 12 — the Editor executor: repeated single-occurrence replacements.

Two details decide the answer, and both are easy to get wrong:
``заменить`` rewrites only the **first** occurrence, and the ``ЕСЛИ`` commands run
**sequentially**, not as an if/elif chain. The naive solver re-implements the loop
with explicit ``find`` and slicing, so a shortcut in the fast one cannot pass.
"""

from __future__ import annotations

import functools
from typing import Any

from egegen.core.errors import GenerationFailedError
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.templates import render
from egegen.core.types import Instance, Uniqueness

STEP_LIMIT = 60_000
MAX_LENGTH = 600


class Task12(Generator):
    task_no = 12
    answer_kind = "int"
    checker = "exact"
    uniqueness = Uniqueness.FUNCTIONAL

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(60):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailedError(f"t12/{subtype}: no terminating rule set")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        symbols = "123" if difficulty <= 3 and subtype != "12.3_three_rules" else "1234"
        rules = self._random_rules(rng, symbols, difficulty, subtype)
        if rules is None:
            return None
        meta: dict[str, Any] = {"subtype": subtype, "symbols": symbols, "rules": rules}
        if subtype == "12.4_reverse":
            # The reverse question needs a start string parameterised by one number,
            # so that "find N by the result" has something to search over.
            head, tail = rng.sample(symbols, 2)
            meta["start_head"], meta["start_tail"] = head, tail
            meta["start_n"] = rng.randint(6, 30)
            start = head * meta["start_n"] + tail * meta["start_n"]
        else:
            start = self._random_start(rng, symbols, difficulty, subtype)
        meta["start"] = start
        result = self._run_replace(start, rules)
        if result is None:
            return None  # the rule set loops forever on this string
        meta["result_len"] = len(result)

        uniqueness = Uniqueness.FUNCTIONAL
        match subtype:
            case "12.1_digit_sum":
                meta["question"] = "digit_sum"
            case "12.2_length_count":
                meta["question"] = rng.choice(["length", "count"])
                meta["target_symbol"] = rng.choice(symbols)
            case "12.3_three_rules":
                meta["question"] = "digit_sum"
            case "12.4_reverse":
                meta["question"] = "reverse"
                meta["target_metric"] = len(result)
                if self._reverse_candidates(meta) != [meta["start_n"]]:
                    return None  # several N give this length: the question is ambiguous
                uniqueness = Uniqueness.ENUMERATED
            case "12.5_long_string":
                meta["question"] = rng.choice(["digit_sum", "length"])
                meta["target_symbol"] = rng.choice(symbols)
            case _:
                return None

        answer = self.solve_fast(meta)
        if not 2 <= int(answer) <= 10**7:
            return None

        fields = {
            "start": self._format_start(meta),
            "rules": self._describe_rules(rules),
            "condition": self._describe_condition(rules),
            "question": self._describe_question(meta),
            "symbol": meta.get("target_symbol", symbols[0]),
            "target_metric": meta.get("target_metric", 0),
        }
        template = self.templates.pick(rng, subtype)
        return Instance(
            task_no=self.task_no,
            subtype=subtype,
            difficulty=difficulty,
            seed=0,
            statement_md=render(template, **fields),
            answer=answer,
            solution_steps=self._solution(meta, answer),
            template_id=template.id,
            uniqueness=uniqueness,
            meta=meta,
        )

    def _random_rules(
        self, rng: Rng, symbols: str, difficulty: int, subtype: str
    ) -> list[tuple[str, str]] | None:
        wants_three = subtype == "12.3_three_rules" or difficulty >= 4
        count = 3 if (difficulty > 2 and wants_three) else 2
        rules: list[tuple[str, str]] = []
        for _ in range(count):
            a, b = rng.choice(symbols), rng.choice(symbols)
            if a == b:
                return None
            pattern = a + b
            # Replacements that keep the length steady (a swap or a single symbol)
            # are what the exam uses; growth would never terminate.
            replacement = rng.choice([b + a, a, b, b + b])
            if replacement == pattern:
                return None
            rules.append((pattern, replacement))
        if len({p for p, _ in rules}) != len(rules):
            return None
        return rules

    def _random_start(self, rng: Rng, symbols: str, difficulty: int, subtype: str) -> str:
        # Simulation cost grows roughly with the square of the length, and the whole
        # instance has to be produced (and cross-checked) inside 200 ms.
        if subtype == "12.5_long_string":
            span = (34, 62)
        elif difficulty <= 2:
            span = (5, 14)
        else:
            span = (12, 30)
        blocks = [(rng.choice(symbols), rng.randint(*span)) for _ in range(len(symbols))]
        return "".join(ch * n for ch, n in blocks)[:MAX_LENGTH]

    def _format_start(self, meta: dict[str, Any]) -> str:
        """Render the starting string the way the exam writes it: as repeated blocks."""
        text = meta["start"]
        blocks: list[str] = []
        run_char, run_len = text[0], 0
        for ch in text:
            if ch == run_char:
                run_len += 1
            else:
                blocks.append(self._block(run_char, run_len))
                run_char, run_len = ch, 1
        blocks.append(self._block(run_char, run_len))
        return " ".join(blocks)

    def _block(self, ch: str, count: int) -> str:
        return ch if count == 1 else f"{ch}…{ch} ({count} шт.)"

    def _describe_rules(self, rules: list[tuple[str, str]]) -> str:
        return "\n".join(
            f"    ЕСЛИ нашлось ({a}) ТО заменить ({a}, {b}) КОНЕЦ ЕСЛИ" for a, b in rules
        )

    def _describe_condition(self, rules: list[tuple[str, str]]) -> str:
        return " ИЛИ ".join(f"нашлось ({a})" for a, _ in rules)

    def _describe_question(self, meta: dict[str, Any]) -> str:
        match meta["question"]:
            case "digit_sum":
                return "сумму цифр полученной строки"
            case "length":
                return "длину полученной строки"
            case "count":
                return f"количество символов {meta['target_symbol']} в полученной строке"
            case "reverse":
                return "исходное количество символов"
        return ""

    # -- execution ----------------------------------------------------------
    def _run_replace(self, text: str, rules: list[tuple[str, str]]) -> str | None:
        """Reference execution with ``str.replace(..., 1)`` — the exam's semantics."""
        steps = 0
        patterns = [p for p, _ in rules]
        while any(p in text for p in patterns):
            for pattern, replacement in rules:
                if pattern in text:
                    text = text.replace(pattern, replacement, 1)
            steps += 1
            if steps > STEP_LIMIT or len(text) > MAX_LENGTH * 4:
                return None
        return text

    def _run_manual(self, text: str, rules: list[tuple[str, str]]) -> str | None:
        """Same loop written with ``find`` and slicing, sharing no library call."""
        steps = 0
        while True:
            positions = [text.find(p) for p, _ in rules]
            if all(pos < 0 for pos in positions):
                return text
            for (pattern, replacement), _ in zip(rules, positions, strict=True):
                at = text.find(pattern)
                if at >= 0:
                    text = text[:at] + replacement + text[at + len(pattern) :]
            steps += 1
            if steps > STEP_LIMIT or len(text) > MAX_LENGTH * 4:
                return None

    def _metric(self, text: str, question: str, meta: dict[str, Any]) -> int:
        match question:
            case "digit_sum":
                return sum(int(ch) for ch in text)
            case "length":
                return len(text)
            case "count":
                return text.count(meta["target_symbol"])
        raise ValueError(question)

    def _reverse_candidates(self, meta: dict[str, Any]) -> list[int]:
        """Which starting block sizes give a result of the asked length."""
        rules = tuple((str(a), str(b)) for a, b in meta["rules"])
        return list(
            self._reverse_scan(meta["start_head"], meta["start_tail"], rules, meta["target_metric"])
        )

    @functools.lru_cache(maxsize=256)  # noqa: B019 - generators are module-level singletons
    def _reverse_scan(
        self, head: str, tail: str, rules: tuple[tuple[str, str], ...], target: int
    ) -> tuple[int, ...]:
        # Generation checks the candidates and then computes the answer from the same
        # scan: remembering it halves the time of the slowest subtype of task 12.
        out: list[int] = []
        for n in range(3, 61):
            result = self._run_replace(head * n + tail * n, list(rules))
            if result is not None and len(result) == target:
                out.append(n)
        return tuple(out)

    # -- solving ------------------------------------------------------------
    def solve_fast(self, meta: dict[str, Any]) -> str:
        rules = [tuple(r) for r in meta["rules"]]
        if meta["question"] == "reverse":
            hits = self._reverse_candidates(meta)
            return str(hits[0]) if len(hits) == 1 else ""
        result = self._run_replace(meta["start"], rules)
        if result is None:
            return ""
        return str(self._metric(result, meta["question"], meta))

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        rules = [tuple(r) for r in meta["rules"]]
        if meta["question"] == "reverse":
            return None
        result = self._run_manual(meta["start"], rules)
        if result is None:
            return None
        return str(self._metric(result, meta["question"], meta))

    def enumerate_answers(self, meta: dict[str, Any]) -> list[str] | None:
        if meta["question"] == "reverse":
            return [str(n) for n in self._reverse_candidates(meta)]
        return None

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        if not answer:
            raise ValueError("t12: the rule set does not terminate")

    # -- explanation --------------------------------------------------------
    def _solution(self, meta: dict[str, Any], answer: str) -> list[str]:
        rules = meta["rules"]
        body = "\n".join(f"    if '{a}' in s: s = s.replace('{a}', '{b}', 1)" for a, b in rules)
        condition = " or ".join(f"'{a}' in s" for a, _ in rules)
        metric_line = {
            "digit_sum": "print(sum(map(int, s)))",
            "length": "print(len(s))",
            "count": f"print(s.count('{meta.get('target_symbol', '1')}'))",
            "reverse": "print(len(s))",
        }[meta["question"]]
        start_literal = self._start_literal(meta["start"])
        return [
            "**Шаг 1.** Смоделируйте выполнение точно, без «оптимизаций». Два "
            "принципиальных момента: `replace` без третьего аргумента заменит **все** "
            "вхождения — это грубая ошибка; команды `ЕСЛИ` идут **подряд**, а не "
            "через `elif`.",
            "**Шаг 2.** Программа:\n\n```python\n"
            f"s = {start_literal}\n"
            f"while {condition}:\n{body}\n{metric_line}\n```",
            f"**Шаг 3.** Результат — **{answer}**. Если программа зависла, поставьте "
            "счётчик итераций с лимитом: значит, набор правил не завершается, "
            "и условие прочитано неверно.",
        ]

    def _start_literal(self, text: str) -> str:
        parts: list[str] = []
        run_char, run_len = text[0], 0
        for ch in text:
            if ch == run_char:
                run_len += 1
            else:
                parts.append(f"'{run_char}' * {run_len}" if run_len > 1 else f"'{run_char}'")
                run_char, run_len = ch, 1
        parts.append(f"'{run_char}' * {run_len}" if run_len > 1 else f"'{run_char}'")
        return " + ".join(parts)


register(Task12())
