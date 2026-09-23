"""Task 1 — information models: a road schema against an unlabelled distance table.

The figure shows which settlements are connected; the table shows the distances but
its rows and columns are named П1..Пn. The student matches the two by vertex degree
and neighbour degrees. An instance is only released when the asked quantity is the
same under *every* consistent matching (design doc 7.1.2 and Appendix A task 1).
"""

from __future__ import annotations

from typing import Any

from egegen.core.errors import GenerationFailedError
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.svg import graph_svg
from egegen.core.templates import render
from egegen.core.types import Attachment, Instance, Uniqueness
from egegen.generators._common import VERTEX_LETTERS, markdown_table
from egegen.solvers.graphs import dijkstra, matchings

MAX_ATTEMPTS = 60


class Task01(Generator):
    task_no = 1
    answer_kind = "int"
    checker = "exact"
    uniqueness = Uniqueness.ENUMERATED

    # -- generation ---------------------------------------------------------
    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(MAX_ATTEMPTS):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailedError(
            f"t01/{subtype}: no well-posed instance after {MAX_ATTEMPTS} tries"
        )

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        n = 6 if difficulty <= 2 else (7 if difficulty <= 4 else 8)
        adjacency = self._random_connected(rng, n)
        weights = self._weigh(rng, adjacency, n)
        labels = list(VERTEX_LETTERS[:n])

        # Table rows are a shuffled, anonymised view of the same graph.
        order = rng.permutation(n)
        table = [[weights[order[i]][order[j]] for j in range(n)] for i in range(n)]

        question = self._question(rng, labels, weights, n, subtype)
        if question is None:
            return None

        meta: dict[str, Any] = {
            "n": n,
            "figure": [[1 if weights[i][j] else 0 for j in range(n)] for i in range(n)],
            "table": table,
            "labels": labels,
            "subtype": subtype,
            **question["meta"],
        }
        # Every consistent matching must give the same answer, or the task is broken.
        answers = self._all_answers(meta)
        if len(set(answers)) != 1 or not answers:
            return None
        answer = answers[0]
        if not 2 <= int(answer) <= 400:
            return None

        template = self.templates.pick(rng, subtype)
        statement = render(template, **question["fields"])
        svg = graph_svg(
            labels,
            [(i, j, None) for i in range(n) for j in range(i + 1, n) if weights[i][j]],
            title="Схема дорог",
        )
        table_md = markdown_table(
            ["", *[f"П{i + 1}" for i in range(n)]],
            [[f"П{i + 1}", *table[i]] for i in range(n)],
            blank_zero=True,  # an empty cell means "no road", not "length 0"
        )
        body = f"{statement}\n\n{{{{FIGURE}}}}\n\n**Таблица длин дорог**\n\n{table_md}"

        return Instance(
            task_no=self.task_no,
            subtype=subtype,
            difficulty=difficulty,
            seed=0,
            statement_md=body.replace("{{FIGURE}}", "![Схема дорог](asset:schema.svg)"),
            answer=answer,
            solution_steps=self._solution(meta, answer, labels),
            method_card_id="",
            target_seconds=0,
            template_id=template.id,
            assets=[
                Attachment("schema.svg", "image/svg+xml", "svg", svg.encode("utf-8"), inline=True)
            ],
            meta=meta,
        )

    def _random_connected(self, rng: Rng, n: int) -> list[list[int]]:
        """A connected graph built from a random spanning tree plus extra chords."""
        adj = [[0] * n for _ in range(n)]
        order = rng.permutation(n)
        for k in range(1, n):
            a, b = order[k], order[rng.randint(0, k - 1)]
            adj[a][b] = adj[b][a] = 1
        extra = rng.randint(n // 2, n)
        pairs = [(i, j) for i in range(n) for j in range(i + 1, n) if not adj[i][j]]
        rng.shuffle(pairs)
        for i, j in pairs[:extra]:
            adj[i][j] = adj[j][i] = 1
        return adj

    def _weigh(self, rng: Rng, adj: list[list[int]], n: int) -> list[list[int]]:
        w = [[0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                if adj[i][j]:
                    w[i][j] = w[j][i] = rng.randint(2, 60)
        return w

    def _question(
        self, rng: Rng, labels: list[str], weights: list[list[int]], n: int, subtype: str
    ) -> dict[str, Any] | None:
        edges = [(i, j) for i in range(n) for j in range(i + 1, n) if weights[i][j]]
        non_edges = [(i, j) for i in range(n) for j in range(i + 1, n) if not weights[i][j]]
        match subtype:
            case "1.1_edge_length" | "1.5_symmetric":
                if not edges:
                    return None
                a, b = rng.choice(edges)
                return {
                    "meta": {"question": "edge", "pair": [a, b]},
                    "fields": {"a": labels[a], "b": labels[b]},
                }
            case "1.2_two_edges":
                if len(edges) < 2:
                    return None
                (a, b), (c, d) = rng.sample(edges, 2)
                return {
                    "meta": {"question": "two_edges", "pair": [a, b], "pair2": [c, d]},
                    "fields": {"a": labels[a], "b": labels[b], "c": labels[c], "d": labels[d]},
                }
            case "1.3_shortest_path":
                if not non_edges:
                    return None
                a, b = rng.choice(non_edges)
                return {
                    "meta": {"question": "shortest", "pair": [a, b]},
                    "fields": {"a": labels[a], "b": labels[b]},
                }
            case "1.4_vertex_number":
                v = rng.randint(0, n - 1)
                return {
                    "meta": {"question": "row", "vertex": v},
                    "fields": {"a": labels[v], "b": labels[v]},
                }
        return None

    # -- solving ------------------------------------------------------------
    def _all_answers(self, meta: dict[str, Any]) -> list[str]:
        """Answer under every consistent figure/table matching (the uniqueness proof)."""
        figure, table = meta["figure"], meta["table"]
        out: list[str] = []
        for sigma in matchings(figure, table):
            out.append(self._answer_for(meta, sigma))
        return out

    def _answer_for(self, meta: dict[str, Any], sigma: tuple[int, ...]) -> str:
        table = meta["table"]
        match meta["question"]:
            case "edge":
                a, b = meta["pair"]
                return str(table[sigma[a]][sigma[b]])
            case "two_edges":
                a, b = meta["pair"]
                c, d = meta["pair2"]
                return str(table[sigma[a]][sigma[b]] + table[sigma[c]][sigma[d]])
            case "shortest":
                a, b = meta["pair"]
                n = meta["n"]
                graph = {
                    str(i): {str(j): table[i][j] for j in range(n) if table[i][j]} for i in range(n)
                }
                return str(int(dijkstra(graph, str(sigma[a]))[str(sigma[b])]))
            case "row":
                return str(sigma[meta["vertex"]] + 1)
        raise ValueError(f"unknown question {meta['question']!r}")

    def solve_fast(self, meta: dict[str, Any]) -> str:
        """Match via degree-signature-pruned backtracking, then read the table."""
        for sigma in matchings(meta["figure"], meta["table"]):
            return self._answer_for(meta, sigma)
        raise GenerationFailedError("t01: no matching between figure and table")

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        """Sweep all n! relabelings and keep the consistent ones — no pruning at all."""
        from itertools import permutations

        n = meta["n"]
        figure, table = meta["figure"], meta["table"]
        for sigma in permutations(range(n)):
            if all(
                bool(figure[i][j]) == bool(table[sigma[i]][sigma[j]])
                for i in range(n)
                for j in range(n)
            ):
                return self._answer_for(meta, sigma)
        return None

    def enumerate_answers(self, meta: dict[str, Any]) -> list[str] | None:
        return sorted(set(self._all_answers(meta)))

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        if not 1 <= int(answer) <= 400:
            raise ValueError(f"t01: implausible answer {answer}")

    # -- explanation --------------------------------------------------------
    def _solution(self, meta: dict[str, Any], answer: str, labels: list[str]) -> list[str]:
        n = meta["n"]
        figure = meta["figure"]
        sigma = next(iter(matchings(figure, meta["table"])))
        degrees = [sum(figure[i]) for i in range(n)]
        degree_lines = [
            f"- **{labels[i]}** — степень {degrees[i]}, "
            f"степени соседей: {sorted(degrees[j] for j in range(n) if figure[i][j])}"
            for i in range(n)
        ]
        mapping = ", ".join(f"{labels[i]} = П{sigma[i] + 1}" for i in range(n))
        steps = [
            "**Шаг 1.** Степень вершины — это число заполненных ячеек в её строке "
            "таблицы и число выходящих из неё линий на схеме. Выпишем степени и "
            "отсортированные степени соседей для каждой вершины схемы:",
            "\n".join(degree_lines),
            "**Шаг 2.** То же самое считаем по строкам таблицы и сопоставляем записи. "
            "Начинаем с вершин, у которых степень уникальна, затем уточняем по "
            f"соседям. Получаем: {mapping}.",
        ]
        match meta["question"]:
            case "edge":
                a, b = meta["pair"]
                steps.append(
                    f"**Шаг 3.** Дорога {labels[a]}–{labels[b]} — это ячейка на "
                    f"пересечении строки П{sigma[a] + 1} и столбца П{sigma[b] + 1}. "
                    f"Её длина **{answer}**."
                )
            case "two_edges":
                a, b = meta["pair"]
                c, d = meta["pair2"]
                t = meta["table"]
                steps.append(
                    f"**Шаг 3.** {labels[a]}–{labels[b]} = {t[sigma[a]][sigma[b]]}, "
                    f"{labels[c]}–{labels[d]} = {t[sigma[c]][sigma[d]]}. "
                    f"Сумма — **{answer}**."
                )
            case "shortest":
                a, b = meta["pair"]
                steps.append(
                    f"**Шаг 3.** Прямой дороги {labels[a]}–{labels[b]} нет, поэтому "
                    "перебираем все маршруты (а не первый попавшийся) и берём "
                    f"минимальную суммарную длину: **{answer}**."
                )
            case "row":
                v = meta["vertex"]
                steps.append(
                    f"**Шаг 3.** Вершине {labels[v]} соответствует строка "
                    f"**П{answer}** — это и есть ответ."
                )
        return steps


register(Task01())
