"""Task 8 — combinatorics: counting words, codes and numbers under constraints.

Constraints are declarative, and the two solvers consume them in opposite ways: the
fast path folds each constraint into a step of a digit-by-digit dynamic program,
while the naive path applies the very same constraints to finished words produced by
``itertools.product``. A mistake in the incremental logic therefore shows up as a
mismatch rather than as a wrong answer shipped to a student.
"""

from __future__ import annotations

from functools import lru_cache
from itertools import product
from typing import Any

from egegen.core.errors import GenerationFailed
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.templates import render
from egegen.core.types import Instance, Uniqueness

ALPHABETS = ["АЕИОУ", "АБВГД", "КЛМНО", "ЛМНОП", "АЕИОУЫ", "БВГДЖЗ"]
VOWELS = "АЕИОУЫ"
BRUTE_LIMIT = 400_000


class Task08(Generator):
    task_no = 8
    answer_kind = "int"
    checker = "exact"
    uniqueness = Uniqueness.FUNCTIONAL

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(60):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailed(f"t08/{subtype}: no valid instance")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        if subtype == "8.4_digits_base":
            base = rng.choice([4, 5, 6, 7, 8])
            alphabet = "0123456789"[:base]
        else:
            alphabet = "".join(sorted(set(rng.choice(ALPHABETS))))
        length = self._length_for(rng, subtype, difficulty, len(alphabet))
        constraints = self._constraints(rng, subtype, difficulty, alphabet, length)
        if constraints is None:
            return None

        meta: dict[str, Any] = {
            "subtype": subtype,
            "alphabet": alphabet,
            "length": length,
            "constraints": constraints,
            "closed_form": subtype == "8.5_large",
        }
        fields: dict[str, Any] = {
            "alphabet": ", ".join(alphabet),
            "alphabet_plain": alphabet,
            "length": length,
            "conditions": self._describe(constraints, alphabet),
            "count": len(alphabet),
        }

        if subtype == "8.2_word_number":
            word = self._pick_word(rng, meta)
            if word is None:
                return None
            meta["word"] = word
            fields["word"] = word

        answer = self.solve_fast(meta)
        if not self._plausible(answer, subtype):
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
            template_id=template.id,
            meta=meta,
        )

    def _length_for(self, rng: Rng, subtype: str, difficulty: int, size: int) -> int:
        if subtype == "8.5_large":
            return rng.randint(7, 10)
        if subtype == "8.3_distinct_letters":
            return rng.randint(3, min(size, 3 + difficulty // 2))
        base = {1: 3, 2: 4, 3: 4, 4: 5, 5: 5}[difficulty]
        while size**base > BRUTE_LIMIT and base > 2:
            base -= 1
        return base

    def _constraints(
        self, rng: Rng, subtype: str, difficulty: int, alphabet: str, length: int
    ) -> list[dict[str, Any]] | None:
        if subtype == "8.3_distinct_letters":
            return [{"kind": "all_distinct"}]
        if subtype == "8.5_large":
            # Only constraints with a closed form, so the intended method is a formula.
            choice = rng.choice(["no_repeat_adjacent", "starts_in"])
            if choice == "no_repeat_adjacent":
                return [{"kind": "no_repeat_adjacent"}]
            first = "".join(sorted(rng.sample(alphabet, max(1, len(alphabet) // 2))))
            return [{"kind": "starts_in", "set": first}]
        if subtype == "8.2_word_number":
            return []

        pool: list[dict[str, Any]] = [
            {"kind": "max_count", "letter": rng.choice(alphabet), "k": rng.randint(1, 2)},
            {"kind": "exact_count", "letter": rng.choice(alphabet), "k": 1},
            {"kind": "no_repeat_adjacent"},
            {
                "kind": "forbid_pair",
                "a": rng.choice(alphabet),
                "b": rng.choice(alphabet),
            },
            {"kind": "starts_in", "set": "".join(sorted(rng.sample(alphabet, 2)))},
            {"kind": "ends_in", "set": "".join(sorted(rng.sample(alphabet, 2)))},
        ]
        vowels = "".join(ch for ch in alphabet if ch in VOWELS)
        if len(vowels) >= 2:
            pool.append({"kind": "no_adjacent_in", "set": vowels})
        count = 1 if difficulty <= 2 else (2 if difficulty <= 4 else 3)
        rng.shuffle(pool)
        picked = pool[:count]
        kinds = [c["kind"] for c in picked]
        if len(set(kinds)) != len(kinds):
            return None
        return picked

    def _pick_word(self, rng: Rng, meta: dict[str, Any]) -> str | None:
        alphabet: str = meta["alphabet"]
        word = "".join(rng.choices(alphabet, k=meta["length"]))
        return word

    def _describe(self, constraints: list[dict[str, Any]], alphabet: str) -> str:
        if not constraints:
            return ""
        lines: list[str] = []
        for c in constraints:
            match c["kind"]:
                case "max_count":
                    lines.append(
                        f"буква {c['letter']} встречается не более {c['k']} раз"
                    )
                case "min_count":
                    lines.append(f"буква {c['letter']} встречается не менее {c['k']} раз")
                case "exact_count":
                    lines.append(f"буква {c['letter']} встречается ровно {c['k']} раз")
                case "no_repeat_adjacent":
                    lines.append("никакие две одинаковые буквы не стоят рядом")
                case "forbid_pair":
                    lines.append(f"сочетание «{c['a']}{c['b']}» не встречается")
                case "starts_in":
                    lines.append(
                        "слово начинается с одной из букв " + ", ".join(c["set"])
                    )
                case "ends_in":
                    lines.append(
                        "слово заканчивается одной из букв " + ", ".join(c["set"])
                    )
                case "no_adjacent_in":
                    lines.append(
                        "никакие две буквы из набора "
                        + ", ".join(c["set"])
                        + " не стоят рядом"
                    )
                case "all_distinct":
                    lines.append("все буквы в слове различны")
        return "; ".join(lines)

    def _plausible(self, answer: str, subtype: str) -> bool:
        value = int(answer)
        if subtype == "8.2_word_number":
            return value >= 2
        return 2 <= value <= 10**12

    # -- constraint semantics ----------------------------------------------
    def _word_ok(self, word: str, constraints: list[dict[str, Any]]) -> bool:
        """Whole-word predicate: the naive path's only notion of a constraint."""
        for c in constraints:
            match c["kind"]:
                case "max_count":
                    if word.count(c["letter"]) > c["k"]:
                        return False
                case "min_count":
                    if word.count(c["letter"]) < c["k"]:
                        return False
                case "exact_count":
                    if word.count(c["letter"]) != c["k"]:
                        return False
                case "no_repeat_adjacent":
                    if any(a == b for a, b in zip(word, word[1:], strict=False)):
                        return False
                case "forbid_pair":
                    if c["a"] + c["b"] in word:
                        return False
                case "starts_in":
                    if word[0] not in c["set"]:
                        return False
                case "ends_in":
                    if word[-1] not in c["set"]:
                        return False
                case "no_adjacent_in":
                    if any(
                        a in c["set"] and b in c["set"]
                        for a, b in zip(word, word[1:], strict=False)
                    ):
                        return False
                case "all_distinct":
                    if len(set(word)) != len(word):
                        return False
        return True

    # -- solving ------------------------------------------------------------
    def solve_fast(self, meta: dict[str, Any]) -> str:
        if meta["subtype"] == "8.2_word_number":
            return str(self._word_index_positional(meta))
        if meta["closed_form"]:
            value = self._closed_form(meta)
            if value is not None:
                return str(value)
        return str(self._count_dp(meta))

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        alphabet: str = meta["alphabet"]
        length: int = meta["length"]
        if meta["subtype"] == "8.2_word_number":
            return str(self._word_index_by_listing(meta))
        if len(alphabet) ** length > BRUTE_LIMIT:
            # Too many words to enumerate: fall back to the digit-by-digit DP, which
            # is still independent of the closed-form formula used above.
            return str(self._count_dp(meta)) if meta["closed_form"] else None
        constraints = meta["constraints"]
        return str(
            sum(
                1
                for combo in product(alphabet, repeat=length)
                if self._word_ok("".join(combo), constraints)
            )
        )

    def _count_dp(self, meta: dict[str, Any]) -> int:
        """Digit-by-digit dynamic program over (position, last letter, counts, used)."""
        alphabet: str = meta["alphabet"]
        length: int = meta["length"]
        constraints: list[dict[str, Any]] = meta["constraints"]
        tracked = [c for c in constraints if c["kind"].endswith("_count")]
        distinct = any(c["kind"] == "all_distinct" for c in constraints)

        @lru_cache(maxsize=None)
        def walk(pos: int, last: int, counts: tuple[int, ...], used: int) -> int:
            if pos == length:
                for c, seen in zip(tracked, counts, strict=True):
                    if c["kind"] == "exact_count" and seen != c["k"]:
                        return 0
                    if c["kind"] == "min_count" and seen < c["k"]:
                        return 0
                for c in constraints:
                    if c["kind"] == "ends_in" and alphabet[last] not in c["set"]:
                        return 0
                return 1
            total = 0
            for i, ch in enumerate(alphabet):
                if not self._step_ok(pos, last, i, ch, used, constraints, alphabet):
                    continue
                new_counts = list(counts)
                blocked = False
                for idx, c in enumerate(tracked):
                    if c["letter"] == ch:
                        new_counts[idx] += 1
                        if c["kind"] in ("max_count", "exact_count") and new_counts[
                            idx
                        ] > c["k"]:
                            blocked = True
                if blocked:
                    continue
                next_used = (used | (1 << i)) if distinct else 0
                total += walk(pos + 1, i, tuple(new_counts), next_used)
            return total

        return walk(0, -1, tuple(0 for _ in tracked), 0)

    def _step_ok(
        self,
        pos: int,
        last: int,
        index: int,
        ch: str,
        used: int,
        constraints: list[dict[str, Any]],
        alphabet: str,
    ) -> bool:
        for c in constraints:
            match c["kind"]:
                case "starts_in":
                    if pos == 0 and ch not in c["set"]:
                        return False
                case "no_repeat_adjacent":
                    if last >= 0 and index == last:
                        return False
                case "forbid_pair":
                    if last >= 0 and alphabet[last] == c["a"] and ch == c["b"]:
                        return False
                case "no_adjacent_in":
                    if last >= 0 and alphabet[last] in c["set"] and ch in c["set"]:
                        return False
                case "all_distinct":
                    if used >> index & 1:
                        return False
        return True

    def _closed_form(self, meta: dict[str, Any]) -> int | None:
        """Product formula for the restricted constraint set used by 8.5."""
        alphabet: str = meta["alphabet"]
        k, length = len(alphabet), meta["length"]
        constraints = meta["constraints"]
        if len(constraints) != 1:
            return None
        c = constraints[0]
        if c["kind"] == "no_repeat_adjacent":
            return k * (k - 1) ** (length - 1)
        if c["kind"] == "starts_in":
            return len(c["set"]) * k ** (length - 1)
        return None

    def _word_index_positional(self, meta: dict[str, Any]) -> int:
        """Rank of the word by positional arithmetic: no list is ever built."""
        alphabet: str = meta["alphabet"]
        base = len(alphabet)
        index = 0
        for ch in meta["word"]:
            index = index * base + alphabet.index(ch)
        return index + 1

    def _word_index_by_listing(self, meta: dict[str, Any]) -> int:
        """Rank found by actually sorting the whole list, as a student would."""
        alphabet: str = meta["alphabet"]
        words = sorted("".join(c) for c in product(alphabet, repeat=meta["length"]))
        return words.index(meta["word"]) + 1

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        if int(answer) < 1:
            raise ValueError("t08: count must be positive")

    # -- explanation --------------------------------------------------------
    def _solution(self, meta: dict[str, Any], answer: str) -> list[str]:
        alphabet: str = meta["alphabet"]
        length = meta["length"]
        if meta["subtype"] == "8.2_word_number":
            word = meta["word"]
            positions = ", ".join(
                f"{ch} — {alphabet.index(ch)}" for ch in dict.fromkeys(word)
            )
            return [
                f"**Шаг 1.** Порядок букв берём **из условия**: {', '.join(alphabet)} — "
                "а не из настоящего алфавита.",
                "**Шаг 2.** Список всех слов упорядочен как числа в системе счисления "
                f"с основанием {len(alphabet)}, где цифра буквы — её номер в алфавите "
                f"условия ({positions}).",
                f"**Шаг 3.** Переводим слово {word} в число и прибавляем 1 "
                f"(нумерация с единицы): получаем **{answer}**.\n\n"
                "```python\nfrom itertools import product\n"
                f"words = sorted(''.join(w) for w in product('{alphabet}', repeat={length}))\n"
                f"print(words.index('{word}') + 1)\n```",
            ]
        conditions = self._describe(meta["constraints"], alphabet) or "без дополнительных условий"
        total = len(alphabet) ** length
        if meta["closed_form"]:
            c = meta["constraints"][0]
            if c["kind"] == "no_repeat_adjacent":
                formula = (
                    f"{len(alphabet)} × {len(alphabet) - 1}^{length - 1}: первую букву "
                    f"выбираем {len(alphabet)} способами, каждую следующую — "
                    f"{len(alphabet) - 1} способами (нельзя повторить предыдущую)"
                )
            else:
                formula = (
                    f"{len(c['set'])} × {len(alphabet)}^{length - 1}: первая буква — "
                    f"{len(c['set'])} вариантов, остальные — по {len(alphabet)}"
                )
            return [
                f"**Шаг 1.** Условие: {conditions}.",
                f"**Шаг 2.** Перебор здесь уже не нужен ({len(alphabet)}^{length} = "
                f"{total} слов) — считаем по формуле умножения: {formula}.",
                f"**Шаг 3.** Получаем **{answer}**.",
            ]
        return [
            f"**Шаг 1.** Всего слов длины {length} из {len(alphabet)} букв — "
            f"{len(alphabet)}^{length} = {total}. Перебор такого размера Python "
            "выполняет мгновенно.",
            f"**Шаг 2.** Условие оформляем отдельной функцией и проверяем на двух-трёх "
            f"примерах: {conditions}.",
            "**Шаг 3.** Считаем подходящие слова:\n\n```python\n"
            "from itertools import product\n"
            f"alphabet = '{alphabet}'\ncnt = 0\n"
            f"for w in product(alphabet, repeat={length}):\n"
            "    s = ''.join(w)\n"
            "    if ...:   # ← условие из шага 2\n"
            "        cnt += 1\n"
            f"print(cnt)\n```\n\nОтвет — **{answer}**.",
        ]


register(Task08())
