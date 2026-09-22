"""Task 24 — processing a long character string from a file.

Every subtype is a single linear pass with a counter and a running maximum. The fast
solver writes that pass by hand; the naive one re-derives the same answer from
``split``/``groupby``/``re`` so that an off-by-one at the end of the string — the
classic way to lose this task — shows up as a mismatch.
"""

from __future__ import annotations

import re
from itertools import groupby
from typing import Any

from egegen.core.errors import GenerationFailed
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.templates import render
from egegen.core.types import Attachment, Instance, Uniqueness

MINI_SIZE = 2000


class Task24(Generator):
    task_no = 24
    answer_kind = "int"
    checker = "exact"
    requires_code = True
    uniqueness = Uniqueness.FUNCTIONAL
    generation_budget_ms = 500

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(20):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailed(f"t24/{subtype}: no valid instance")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        alphabet = "".join(sorted(set(rng.choice(["ABC", "ABCD", "ABCDE", "ABCDEF"]))))
        size = 100_000
        text = self._random_text(rng, alphabet, size, difficulty, subtype)
        meta: dict[str, Any] = {
            "subtype": subtype,
            "alphabet": alphabet,
            "text": text,
            "size": len(text),
        }
        fields: dict[str, Any] = {
            "alphabet": ", ".join(alphabet),
            "size": len(text),
            "preview": text[:60],
        }

        match subtype:
            case "24.1_without_char":
                banned = rng.choice(alphabet)
                meta["question"], meta["char"] = "without_char", banned
                fields["char"] = banned
            case "24.2_alternating":
                meta["question"] = "no_equal_adjacent"
            case "24.3_window_k":
                target = rng.choice(alphabet)
                k = rng.randint(2, 4)
                meta["question"], meta["char"], meta["k"] = "window", target, k
                fields["char"], fields["k"] = target, k
            case "24.4_exact_pattern":
                a, b = rng.sample(alphabet, 2)
                meta["question"], meta["pattern"] = "pattern", a + b
                fields["pattern"] = a + b
            case "24.5_multiline":
                lines = [
                    "".join(rng.choices(alphabet, k=rng.randint(200, 600)))
                    for _ in range(rng.randint(40, 80))
                ]
                meta["text"] = "\n".join(lines)
                meta["question"] = "best_line"
                meta["char"] = rng.choice(alphabet)
                fields["char"] = meta["char"]
                fields["size"] = len(lines)
                fields["preview"] = lines[0][:60]
            case "24.6_no_three_repeat":
                meta["question"] = "at_most_two"
            case _:
                return None

        answer = self.solve_fast(meta)
        if not 3 <= int(answer) <= len(meta["text"]):
            return None

        body = meta["text"]
        mini = body.split("\n")[0][:MINI_SIZE] if "\n" in body else body[:MINI_SIZE]
        meta["mini_answer"] = self.solve_fast({**meta, "text": mini})
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
            assets=[
                Attachment("24.txt", "text/plain", "txt", (body + "\n").encode("utf-8")),
                Attachment(
                    "24-mini.txt", "text/plain", "txt", (mini + "\n").encode("utf-8")
                ),
            ],
            checker_options={"mini_file": "24-mini.txt"},
            meta=meta,
        )

    def _random_text(
        self, rng: Rng, alphabet: str, size: int, difficulty: int, subtype: str
    ) -> str:
        """Random text with a planted long stretch, so the answer is not pure luck."""
        body = rng.choices(alphabet, k=size)
        planted = rng.randint(20, 40 + difficulty * 12)
        at = rng.randint(0, size - planted - 1)
        if subtype == "24.2_alternating":
            for i in range(planted):
                body[at + i] = alphabet[(i + at) % len(alphabet)]
        elif subtype == "24.4_exact_pattern":
            a, b = alphabet[0], alphabet[1]
            for i in range(planted):
                body[at + i] = a if i % 2 == 0 else b
        return "".join(body)

    # -- solving ------------------------------------------------------------
    def solve_fast(self, meta: dict[str, Any]) -> str:
        """One explicit pass with a counter and a running maximum."""
        text: str = meta["text"]
        match meta["question"]:
            case "without_char":
                best = current = 0
                banned = meta["char"]
                for ch in text:
                    current = 0 if ch == banned else current + 1
                    best = max(best, current)
                return str(best)
            case "no_equal_adjacent":
                best = current = 1
                for i in range(1, len(text)):
                    current = current + 1 if text[i] != text[i - 1] else 1
                    best = max(best, current)
                return str(best)
            case "at_most_two":
                best = current = 1
                run = 1
                for i in range(1, len(text)):
                    if text[i] == text[i - 1]:
                        run += 1
                    else:
                        run = 1
                    current = current + 1 if run <= 2 else 2
                    best = max(best, current)
                return str(best)
            case "window":
                target, k = meta["char"], meta["k"]
                lo = seen = best = 0
                for hi, ch in enumerate(text):
                    seen += ch == target
                    while seen > k:
                        seen -= text[lo] == target
                        lo += 1
                    best = max(best, hi - lo + 1)
                return str(best)
            case "pattern":
                a, b = meta["pattern"]
                best = current = 0
                i = 0
                while i + 1 < len(text):
                    if text[i] == a and text[i + 1] == b:
                        current += 2
                        best = max(best, current)
                        i += 2
                    else:
                        current = 0
                        i += 1
                return str(best)
            case "best_line":
                target = meta["char"]
                return str(max(line.count(target) for line in text.split("\n")))
        raise ValueError(meta["question"])

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        """Re-derive the same answer with library tools instead of a hand-written pass."""
        text: str = meta["text"]
        match meta["question"]:
            case "without_char":
                return str(max(len(part) for part in text.split(meta["char"])))
            case "no_equal_adjacent":
                best = 1
                length = 1
                for a, b in zip(text, text[1:], strict=False):
                    length = length + 1 if a != b else 1
                    best = max(best, length)
                return str(best)
            case "at_most_two":
                # Runs longer than two break the substring; a run of length L
                # contributes its last two characters to the next candidate.
                runs = [(ch, len(list(group))) for ch, group in groupby(text)]
                best = 0
                current = 0
                for _, length in runs:
                    if length <= 2:
                        current += length
                    else:
                        best = max(best, current + 2)
                        current = 2
                    best = max(best, current)
                return str(best)
            case "window":
                target, k = meta["char"], meta["k"]
                positions = [-1] + [i for i, ch in enumerate(text) if ch == target]
                positions.append(len(text))
                if len(positions) - 2 <= k:
                    return str(len(text))
                best = 0
                for i in range(len(positions) - k - 1):
                    best = max(best, positions[i + k + 1] - positions[i] - 1)
                return str(best)
            case "pattern":
                a, b = meta["pattern"]
                found = re.findall(f"(?:{re.escape(a)}{re.escape(b)})+", text)
                return str(max((len(m) for m in found), default=0))
            case "best_line":
                return str(
                    max(sum(1 for ch in line if ch == meta["char"]) for line in text.split("\n"))
                )
        return None

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        if int(answer) < 1:
            raise ValueError("t24: answer must be positive")

    # -- explanation --------------------------------------------------------
    def _reference_code(self, meta: dict[str, Any]) -> str:
        head = "s = open('24.txt').read().strip()\n"
        match meta["question"]:
            case "without_char":
                return head + f"print(max(len(p) for p in s.split('{meta['char']}')))\n"
            case "no_equal_adjacent":
                return head + (
                    "best = cur = 1\n"
                    "for i in range(1, len(s)):\n"
                    "    cur = cur + 1 if s[i] != s[i-1] else 1\n"
                    "    best = max(best, cur)\n"
                    "print(best)\n"
                )
            case "at_most_two":
                return head + (
                    "best = cur = 1\nrun = 1\n"
                    "for i in range(1, len(s)):\n"
                    "    run = run + 1 if s[i] == s[i-1] else 1\n"
                    "    cur = cur + 1 if run <= 2 else 2\n"
                    "    best = max(best, cur)\n"
                    "print(best)\n"
                )
            case "window":
                return head + (
                    f"lo = k = best = 0\n"
                    "for hi in range(len(s)):\n"
                    f"    k += s[hi] == '{meta['char']}'\n"
                    f"    while k > {meta['k']}:\n"
                    f"        k -= s[lo] == '{meta['char']}'; lo += 1\n"
                    "    best = max(best, hi - lo + 1)\n"
                    "print(best)\n"
                )
            case "pattern":
                return (
                    "import re\n"
                    + head
                    + f"print(max((len(m) for m in re.findall(r'(?:{meta['pattern']})+', s)),"
                    " default=0))\n"
                )
            case "best_line":
                return (
                    "print(max(line.count('"
                    + meta["char"]
                    + "') for line in open('24.txt')))\n"
                )
        raise ValueError(meta["question"])

    def _solution(self, meta: dict[str, Any], answer: str) -> list[str]:
        return [
            "**Шаг 1.** Проверьте метод на короткой строке, написанной руками "
            "(20–30 символов), где ответ виден глазами. Это занимает минуту "
            "и ловит почти все ошибки.",
            "**Шаг 2.** Файл читается одной строкой: `s = open('24.txt').read().strip()`. "
            "`strip()` обязателен — иначе в конце окажется символ перевода строки.",
            "**Шаг 3.** Один линейный проход:\n\n```python\n"
            + self._reference_code(meta)
            + "```",
            f"**Ответ:** **{answer}**. Не забывайте про последний отрезок: если "
            "максимум обновляется только при «сбросе» счётчика, конец строки "
            "теряется — здесь максимум обновляется на каждом шаге.",
        ]


register(Task24())
