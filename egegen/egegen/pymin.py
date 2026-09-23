"""Python-minimum track (design doc, Appendix C): eight micro-lessons.

Each exercise is a short program and the question "what does it print?". The fast
solver computes the output from the parameters; the naive one actually executes the
rendered program, so the text a student reads and the answer can never drift apart.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass
from typing import Any

from egegen.core.rng import Rng
from egegen.core.types import derive_hidden_seed

LESSONS: dict[int, str] = {
    1: "Числа и строки: print, int, str, //, %",
    2: "Цикл for и range, накопление суммы",
    3: "Условия и логика: and/or/not, <= как импликация",
    4: "Строки: срезы, count, in, replace(…, 1)",
    5: "Списки: sorted, set, len, индексы",
    6: "Чтение данных: первая строка — параметры",
    7: "Функции и рекурсия, lru_cache",
    8: "Инструменты ЕГЭ: itertools.product, permutations",
}


@dataclass(slots=True)
class Exercise:
    lesson: int
    seed: int
    hidden_seed: int
    code: str
    answer: str
    explanation: str
    params: dict[str, Any]

    @property
    def statement_md(self) -> str:
        return (
            f"**Python‑минимум · урок {self.lesson}.** {LESSONS[self.lesson]}\n\n"
            "Что напечатает программа?\n\n"
            f"```python\n{self.code}```\n\n"
            "Запишите в ответе ровно то, что появится на экране (целое число)."
        )


def generate(lesson: int, seed: int) -> Exercise:
    if lesson not in LESSONS:
        raise ValueError(f"lesson must be 1..8, got {lesson}")
    rng = Rng(seed).fork(f"pymin:{lesson}")
    builder = {1: _l1, 2: _l2, 3: _l3, 4: _l4, 5: _l5, 6: _l6, 7: _l7, 8: _l8}[lesson]
    code, answer, explanation, params = builder(rng)
    return Exercise(lesson, seed, derive_hidden_seed(seed), code, str(answer), explanation, params)


def execute(code: str) -> str:
    """The naive solver: run the program we generated and capture what it prints."""
    buffer = io.StringIO()
    scope: dict[str, Any] = {"__name__": "__pymin__"}
    with contextlib.redirect_stdout(buffer):
        # Only ever runs programs this module generated itself, never user input.
        exec(compile(code, "<pymin>", "exec"), scope)
    return buffer.getvalue().strip()


def _l1(rng: Rng) -> tuple[str, int, str, dict[str, Any]]:
    a, b = rng.randint(20, 99), rng.randint(3, 9)
    c = rng.randint(2, 9)
    code = f"a = {a}\nb = {b}\nprint(a // b * {c} + a % b)\n"
    answer = a // b * c + a % b
    return (
        code,
        answer,
        (
            f"`//` — целочисленное деление: {a} // {b} = {a // b}; `%` — остаток: "
            f"{a} % {b} = {a % b}. Итого {a // b} · {c} + {a % b} = {answer}."
        ),
        {"a": a, "b": b, "c": c},
    )


def _l2(rng: Rng) -> tuple[str, int, str, dict[str, Any]]:
    start, stop, step = rng.randint(1, 5), rng.randint(12, 30), rng.randint(2, 4)
    code = f"s = 0\nfor i in range({start}, {stop}, {step}):\n    s += i\nprint(s)\n"
    answer = sum(range(start, stop, step))
    return (
        code,
        answer,
        (
            f"`range({start}, {stop}, {step})` даёт числа от {start} с шагом {step}, "
            f"**не включая** {stop}. Их сумма — {answer}."
        ),
        {"start": start, "stop": stop, "step": step},
    )


def _l3(rng: Rng) -> tuple[str, int, str, dict[str, Any]]:
    n, a, b = rng.randint(20, 60), rng.randint(2, 5), rng.randint(2, 7)
    code = (
        f"cnt = 0\nfor x in range(1, {n}):\n"
        f"    if (x % {a} == 0) <= (x % {b} == 0):\n        cnt += 1\nprint(cnt)\n"
    )
    answer = sum(1 for x in range(1, n) if (x % a == 0) <= (x % b == 0))
    return (
        code,
        answer,
        (
            "`<=` между двумя логическими значениями — это импликация: она ложна только "
            f"когда слева истина, а справа ложь. Подходит {answer} чисел."
        ),
        {"n": n, "a": a, "b": b},
    )


def _l4(rng: Rng) -> tuple[str, int, str, dict[str, Any]]:
    base = "".join(rng.choice("ab") for _ in range(rng.randint(8, 14)))
    code = f"s = '{base}'\ns = s.replace('ab', 'b', 1)\nprint(len(s) + s.count('b'))\n"
    changed = base.replace("ab", "b", 1)
    answer = len(changed) + changed.count("b")
    return (
        code,
        answer,
        (
            "`replace('ab', 'b', 1)` заменяет **только первое** вхождение — третий "
            f"аргумент здесь главное. Получается `{changed}`, ответ {answer}."
        ),
        {"base": base},
    )


def _l5(rng: Rng) -> tuple[str, int, str, dict[str, Any]]:
    items = [rng.randint(1, 9) for _ in range(rng.randint(6, 9))]
    k = rng.randint(0, 2)
    code = f"a = {items}\nb = sorted(set(a))\nprint(len(b) * 10 + b[{k}])\n"
    uniq = sorted(set(items))
    answer = len(uniq) * 10 + uniq[k]
    return (
        code,
        answer,
        (
            f"`set` убирает повторы, `sorted` упорядочивает: {uniq}. Элементов {len(uniq)}, "
            f"`b[{k}]` = {uniq[k]} (индексы с нуля). Ответ {answer}."
        ),
        {"items": items, "k": k},
    )


def _l6(rng: Rng) -> tuple[str, int, str, dict[str, Any]]:
    n = rng.randint(4, 7)
    limit = rng.randint(20, 60)
    values = [rng.randint(1, 40) for _ in range(n)]
    lines = [f"{n} {limit}", *[str(v) for v in values]]
    code = (
        f"data = {lines}\n"
        "n, limit = map(int, data[0].split())   # первая строка — параметры\n"
        "nums = [int(x) for x in data[1:n + 1]]\n"
        "print(sum(x for x in nums if x <= limit))\n"
    )
    answer = sum(v for v in values if v <= limit)
    return (
        code,
        answer,
        (
            "Первая строка файла — это параметры, а не данные: её читают отдельно. "
            f"Числа не больше {limit}: их сумма {answer}."
        ),
        {"values": values, "limit": limit},
    )


def _l7(rng: Rng) -> tuple[str, int, str, dict[str, Any]]:
    n = rng.randint(8, 18)
    add = rng.randint(1, 3)
    code = (
        "from functools import lru_cache\n\n@lru_cache(None)\ndef f(n):\n"
        f"    if n <= 2: return 1\n    return f(n - 1) + f(n - 2) + {add}\n\nprint(f({n}))\n"
    )
    memo = {1: 1, 2: 1, 0: 1}
    for k in range(3, n + 1):
        memo[k] = memo[k - 1] + memo[k - 2] + add
    answer = memo[n]
    return (
        code,
        answer,
        (
            "`@lru_cache` запоминает уже посчитанные значения, поэтому ветвящаяся "
            f"рекурсия считается мгновенно. f({n}) = {answer}."
        ),
        {"n": n, "add": add},
    )


def _l8(rng: Rng) -> tuple[str, int, str, dict[str, Any]]:
    alphabet = "".join(sorted(rng.sample("АБВГДЕ", rng.randint(3, 4))))
    length = rng.randint(3, 4)
    letter = alphabet[0]
    code = (
        "from itertools import product\n"
        f"cnt = 0\nfor w in product('{alphabet}', repeat={length}):\n"
        f"    if w.count('{letter}') == 1:\n        cnt += 1\nprint(cnt)\n"
    )
    k = len(alphabet)
    answer = length * (k - 1) ** (length - 1)
    return (
        code,
        answer,
        (
            f"`product` перебирает все {k}^{length} слов. Ровно одна буква {letter}: "
            f"выбрать её место {length} способами, остальные — по {k - 1}. Ответ {answer}."
        ),
        {"alphabet": alphabet, "length": length},
    )
