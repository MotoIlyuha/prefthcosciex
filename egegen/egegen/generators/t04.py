"""Task 4 — coding with the Fano condition (prefix-free codes).

The whole task is one picture: a binary trie where every assigned code word blocks
its entire subtree. Every subtype is a different question about that trie.
"""

from __future__ import annotations

from itertools import product
from typing import Any

from egegen.core.errors import GenerationFailed
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.templates import render
from egegen.core.types import Instance, Uniqueness
from egegen.generators._common import markdown_table

LETTERS = "АБВГДЕЖЗИК"
MAX_LEN = 6


def _prefix_free(codes: list[str]) -> bool:
    return all(
        not (a.startswith(b) or b.startswith(a))
        for i, a in enumerate(codes)
        for b in codes[i + 1 :]
    )


def _suffix_free(codes: list[str]) -> bool:
    return all(
        not (a.endswith(b) or b.endswith(a))
        for i, a in enumerate(codes)
        for b in codes[i + 1 :]
    )


def _free_words(fixed: list[str], length: int, *, suffix: bool) -> list[str]:
    """All words of exactly ``length`` that keep the code Fano-valid."""
    test = _suffix_free if suffix else _prefix_free
    return [
        "".join(bits)
        for bits in product("01", repeat=length)
        if test([*fixed, "".join(bits)])
    ]


class Task04(Generator):
    task_no = 4
    answer_kind = "int"
    checker = "exact"
    uniqueness = Uniqueness.FUNCTIONAL

    # -- generation ---------------------------------------------------------
    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(80):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailed(f"t04/{subtype}: no valid instance")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        suffix = subtype == "4.2_reverse_fano"
        count = 3 + difficulty // 2 if difficulty <= 4 else 5
        fixed_letters = list(LETTERS[:count])
        codes = self._random_code(rng, count, difficulty, suffix=suffix)
        if codes is None:
            return None

        meta: dict[str, Any] = {
            "letters": fixed_letters,
            "codes": codes,
            "suffix": suffix,
            "subtype": subtype,
        }
        fields: dict[str, Any] = {}

        match subtype:
            case "4.1_shortest_code" | "4.2_reverse_fano":
                new_letter = LETTERS[count]
                meta["new_letter"] = new_letter
                fields = {"letter": new_letter, "table": self._table(fixed_letters, codes)}
                answer_kind, checker = "letters", "binary_word"
            case "4.3_min_total_length":
                extra = 2 if difficulty <= 3 else 3
                meta["extra"] = extra
                meta["extra_letters"] = list(LETTERS[count : count + extra])
                fields = {
                    "table": self._table(fixed_letters, codes),
                    "extra": extra,
                    "extra_letters": ", ".join(LETTERS[count : count + extra]),
                }
                answer_kind, checker = "int", "exact"
            case "4.4_decode":
                word_len = 4 + difficulty
                word = "".join(rng.choices(fixed_letters, k=word_len))
                encoded = "".join(codes[fixed_letters.index(ch)] for ch in word)
                meta["encoded"] = encoded
                fields = {"table": self._table(fixed_letters, codes), "encoded": encoded}
                answer_kind, checker = "letters", "letters"
            case "4.5_count_words":
                k = max(3, min(MAX_LEN, 3 + difficulty // 2))
                meta["k"] = k
                fields = {"table": self._table(fixed_letters, codes), "k": k}
                answer_kind, checker = "int", "exact"
            case _:
                return None

        try:
            answer = self.solve_fast(meta)
        except GenerationFailed:
            # The random code saturated the trie: no room for another word. Retry.
            return None
        if not self._plausible(subtype, answer):
            return None

        template = self.templates.pick(rng, subtype)
        return Instance(
            task_no=self.task_no,
            subtype=subtype,
            difficulty=difficulty,
            seed=0,
            statement_md=render(template, **fields),
            answer=answer,
            answer_kind=answer_kind,
            checker=checker,
            checker_options=self._checker_options(checker, fixed_letters),
            solution_steps=self._solution(meta, answer),
            template_id=template.id,
            meta=meta,
        )

    def _checker_options(self, checker: str, letters: list[str]) -> dict[str, Any]:
        """The alphabet the answer field accepts, so a typo is caught before scoring."""
        if checker == "binary_word":
            return {"alphabet": "01"}
        if checker == "letters":
            return {"alphabet": "".join(letters)}
        return {}

    def _random_code(
        self, rng: Rng, count: int, difficulty: int, *, suffix: bool
    ) -> list[str] | None:
        """Random Fano-valid code, built by claiming trie nodes one at a time."""
        max_len = 3 if difficulty <= 2 else (4 if difficulty <= 4 else 5)
        codes: list[str] = []
        test = _suffix_free if suffix else _prefix_free
        for _ in range(count):
            options = [
                w
                for length in range(1, max_len + 1)
                for w in ("".join(b) for b in product("01", repeat=length))
                if test([*codes, w])
            ]
            if not options:
                return None
            codes.append(rng.choice(options))
        # Leave the trie with room to grow, otherwise every subtype is unanswerable.
        if not any(test([*codes, w]) for w in ("0", "1", "00", "01", "10", "11")):
            return None
        return codes

    def _table(self, letters: list[str], codes: list[str]) -> str:
        return markdown_table(["Буква", "Кодовое слово"], list(zip(letters, codes, strict=True)))

    def _plausible(self, subtype: str, answer: str) -> bool:
        match subtype:
            case "4.5_count_words":
                return 1 <= int(answer) <= 60
            case "4.3_min_total_length":
                return 3 <= int(answer) <= 40
            case "4.4_decode":
                return len(answer) >= 4
        return 1 <= len(answer) <= MAX_LEN

    # -- solving ------------------------------------------------------------
    def solve_fast(self, meta: dict[str, Any]) -> str:
        codes: list[str] = list(meta["codes"])
        suffix = bool(meta["suffix"])
        match meta["subtype"]:
            case "4.1_shortest_code" | "4.2_reverse_fano":
                return self._shortest_by_trie(codes, suffix=suffix)
            case "4.3_min_total_length":
                return str(self._min_total_lengths(codes, int(meta["extra"]), suffix=suffix))
            case "4.4_decode":
                return self._decode_trie(codes, meta["letters"], str(meta["encoded"]))
            case "4.5_count_words":
                return str(self._count_free_formula(codes, int(meta["k"]), suffix=suffix))
        raise ValueError(meta["subtype"])

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        codes: list[str] = list(meta["codes"])
        suffix = bool(meta["suffix"])
        match meta["subtype"]:
            case "4.1_shortest_code" | "4.2_reverse_fano":
                for length in range(1, MAX_LEN + 1):
                    free = _free_words(codes, length, suffix=suffix)
                    if free:
                        return min(free, key=lambda w: (len(w), int(w, 2)))
                return None
            case "4.3_min_total_length":
                return self._min_total_bruteforce(codes, int(meta["extra"]), suffix=suffix)
            case "4.4_decode":
                return self._decode_backtrack(codes, meta["letters"], str(meta["encoded"]))
            case "4.5_count_words":
                return str(len(_free_words(codes, int(meta["k"]), suffix=suffix)))
        return None

    # fast implementations --------------------------------------------------
    def _free_roots(self, codes: list[str]) -> list[str]:
        """Maximal usable nodes of the trie.

        A node is usable when no code word equals it, lies above it, or lies below
        it. The maximal such nodes describe the whole free space compactly, which is
        what makes the length questions answerable without enumerating words.
        """
        roots: list[str] = []
        stack = [""]
        while stack:
            node = stack.pop()
            if any(node.startswith(c) for c in codes):
                continue  # the node sits inside an assigned subtree
            if any(c.startswith(node) for c in codes):
                # A code word lies below: the node itself is unusable, children may not be.
                stack.extend([node + "1", node + "0"])
                continue
            roots.append(node)
        return sorted(roots, key=lambda w: (len(w), w))

    def _free_nodes_at(self, codes: list[str], length: int) -> list[str]:
        """Every usable word of exactly ``length``, expanded from the free roots."""
        out: list[str] = []
        for root in self._free_roots(codes):
            if len(root) > length:
                continue
            out.extend(root + "".join(t) for t in product("01", repeat=length - len(root)))
        return out

    def _shortest_by_trie(self, codes: list[str], *, suffix: bool) -> str:
        """Shortest usable word, then smallest numeric value — via the free roots.

        Under the reverse condition the trie is built on reversed words, but the
        ordering is still by the numeric value of the *actual* word, so the winner is
        chosen after mapping back.
        """
        view = [c[::-1] for c in codes] if suffix else codes
        roots = self._free_roots(view)
        if not roots:
            raise GenerationFailed("t04: trie is full")
        length = min(len(r) for r in roots) or 1
        for candidate_len in range(length, MAX_LEN + 1):
            nodes = self._free_nodes_at(view, candidate_len)
            if nodes:
                words = [n[::-1] for n in nodes] if suffix else nodes
                return min(words, key=lambda w: int(w, 2))
        raise GenerationFailed("t04: trie is full")

    def _min_total_lengths(self, codes: list[str], extra: int, *, suffix: bool) -> int:
        """Smallest total length of ``extra`` new code words.

        Greedy "always take the shortest free node" is wrong: claiming a shallow node
        destroys the subtree the remaining words need. Instead every multiset of
        lengths is tested against the free forest with a best-fit packing — placing a
        word of length L inside a free root of depth d frees siblings at depths
        d+1 … L — and the cheapest feasible multiset wins.
        """
        view = [c[::-1] for c in codes] if suffix else codes
        roots = [len(r) for r in self._free_roots(view)]
        if not roots:
            raise GenerationFailed("t04: trie is full")
        best: int | None = None
        for lengths in self._length_multisets(extra, MAX_LEN):
            total = sum(lengths)
            if best is not None and total >= best:
                continue
            if self._packs(sorted(lengths), list(roots)):
                best = total
        if best is None:
            raise GenerationFailed("t04: cannot place the requested code words")
        return best

    def _length_multisets(self, count: int, max_len: int) -> list[tuple[int, ...]]:
        from itertools import combinations_with_replacement

        return sorted(
            combinations_with_replacement(range(1, max_len + 1), count), key=sum
        )

    def _packs(self, lengths: list[int], roots: list[int]) -> bool:
        """Best-fit packing of ``lengths`` into free subtrees of the given depths."""
        available = sorted(roots)
        for length in lengths:
            fits = [d for d in available if d <= length]
            if not fits:
                return False
            chosen = fits[-1]  # deepest root that still fits: wastes the least space
            available.remove(chosen)
            # Descending from depth `chosen` to `length` frees one sibling per level.
            available.extend(range(chosen + 1, length + 1))
            available.sort()
        return True

    def _decode_trie(self, codes: list[str], letters: list[str], encoded: str) -> str:
        """Single left-to-right pass: a prefix code has exactly one parse."""
        lookup = dict(zip(codes, letters, strict=True))
        out: list[str] = []
        buffer = ""
        for bit in encoded:
            buffer += bit
            if buffer in lookup:
                out.append(lookup[buffer])
                buffer = ""
        if buffer:
            raise GenerationFailed("t04: encoded string does not decode cleanly")
        return "".join(out)

    def _count_free_formula(self, codes: list[str], k: int, *, suffix: bool) -> int:
        """Count usable words of length k from the free roots: sum of 2^(k-d)."""
        view = [c[::-1] for c in codes] if suffix else codes
        return sum(2 ** (k - len(r)) for r in self._free_roots(view) if len(r) <= k)

    # naive implementations -------------------------------------------------
    def _min_total_bruteforce(self, codes: list[str], extra: int, *, suffix: bool) -> str | None:
        """Search over actual sets of code words, with no trie reasoning at all.

        Branch and bound over the candidate words sorted by length: this knows
        nothing about free subtrees or Kraft's inequality, so it is a genuine
        independent check of the packing solver.
        """
        test = _suffix_free if suffix else _prefix_free
        candidates = sorted(
            (
                "".join(bits)
                for length in range(1, MAX_LEN + 1)
                for bits in product("01", repeat=length)
                if test([*codes, "".join(bits)])
            ),
            key=len,
        )
        if not candidates:
            return None
        shortest = len(candidates[0])
        best: int | None = None

        def search(start: int, chosen: list[str], total: int) -> None:
            nonlocal best
            if len(chosen) == extra:
                best = total if best is None else min(best, total)
                return
            remaining = extra - len(chosen)
            if best is not None and total + remaining * shortest >= best:
                return
            for i in range(start, len(candidates)):
                word = candidates[i]
                if best is not None and total + len(word) * remaining >= best:
                    break  # candidates are sorted by length: nothing shorter follows
                if test([*codes, *chosen, word]):
                    search(i + 1, [*chosen, word], total + len(word))

        search(0, [], 0)
        return None if best is None else str(best)

    def _decode_backtrack(self, codes: list[str], letters: list[str], encoded: str) -> str | None:
        """Try every split; asserts the parse is unique, which Fano guarantees."""
        lookup = dict(zip(codes, letters, strict=True))
        results: list[str] = []

        def walk(pos: int, acc: list[str]) -> None:
            if len(results) > 1:
                return
            if pos == len(encoded):
                results.append("".join(acc))
                return
            for code, letter in lookup.items():
                if encoded.startswith(code, pos):
                    walk(pos + len(code), [*acc, letter])

        walk(0, [])
        return results[0] if len(results) == 1 else None

    def enumerate_answers(self, meta: dict[str, Any]) -> list[str] | None:
        if meta["subtype"] in ("4.1_shortest_code", "4.2_reverse_fano"):
            suffix = bool(meta["suffix"])
            for length in range(1, MAX_LEN + 1):
                free = _free_words(list(meta["codes"]), length, suffix=suffix)
                if free:
                    # Minimal length first, then minimal numeric value — one winner.
                    return [min(free, key=lambda w: int(w, 2))]
        return None

    # -- explanation --------------------------------------------------------
    def _solution(self, meta: dict[str, Any], answer: str) -> list[str]:
        codes = ", ".join(f"{a} — `{b}`" for a, b in zip(meta["letters"], meta["codes"], strict=True))
        head = (
            "**Шаг 1.** Нарисуйте двоичное дерево и отметьте занятые вершины. "
            "Каждое кодовое слово занимает не только свою вершину, но и всё "
            f"поддерево под ней. Заданные коды: {codes}."
        )
        match meta["subtype"]:
            case "4.1_shortest_code":
                return [
                    head,
                    "**Шаг 2.** Перебираем слова по возрастанию длины (1, 2, 3, …), "
                    "внутри длины — по возрастанию числового значения. Условие Фано "
                    "проверяем **в обе стороны**: новое слово не должно быть началом "
                    "старого, а старое — началом нового.",
                    f"**Шаг 3.** Первое подходящее слово — `{answer}`. "
                    "Ведущие нули значимы: `01` и `1` — разные слова.",
                ]
            case "4.2_reverse_fano":
                return [
                    head,
                    "**Шаг 2.** Это обратное условие Фано: ни один код не должен быть "
                    "**окончанием** другого. Удобно перевернуть все слова и решать "
                    "обычную задачу на префиксы.",
                    f"**Шаг 3.** Кратчайшее подходящее слово с наименьшим числовым "
                    f"значением — `{answer}`.",
                ]
            case "4.3_min_total_length":
                return [
                    head,
                    "**Шаг 2.** Нельзя просто брать самое короткое свободное слово: "
                    "заняв высокую вершину, вы закроете поддерево, которое нужно "
                    "остальным буквам. Смотрите на свободные поддеревья целиком — "
                    "спуск на один уровень внутри свободного поддерева освобождает "
                    "соседнюю вершину того же уровня.",
                    f"**Шаг 3.** Суммарная длина новых кодовых слов — **{answer}**.",
                ]
            case "4.4_decode":
                return [
                    head,
                    "**Шаг 2.** Код префиксный, поэтому читаем биты слева направо и "
                    "как только накопленный кусок совпал с кодовым словом — "
                    "записываем букву и начинаем заново. Возврата назад не требуется.",
                    f"**Шаг 3.** Получается слово **{answer}**.",
                ]
            case "4.5_count_words":
                k = meta["k"]
                return [
                    head,
                    f"**Шаг 2.** Всего слов длины {k} ровно 2^{k} = {2 ** int(k)}. "
                    "Вычёркиваем те, что конфликтуют с уже занятыми вершинами: слово "
                    "длины L ≤ k закрывает 2^(k−L) слов, слово длиннее k закрывает "
                    "одно (своё собственное начало).",
                    f"**Шаг 3.** Остаётся **{answer}** подходящих слов.",
                ]
        return [head]


register(Task04())
