"""Task 23 — graphs: optimal path and path counting (new in the 2027 exam).

How the graph reaches the student — a weight matrix in an ``.ods``, an edge list in
a ``.txt``, or a drawing — is read from ``fipi_2027.yaml``, because the approved demo
version in November may settle on any of the three. The solvers never see the
difference: they work on the graph, not on its presentation.
"""

from __future__ import annotations

from typing import Any

from egegen.core.errors import GenerationFailedError
from egegen.core.fipi import load_fipi_config
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.svg import dag_svg, graph_svg
from egegen.core.tables import to_csv, to_ods, to_txt
from egegen.core.templates import render
from egegen.core.types import Attachment, Instance, Uniqueness
from egegen.generators._common import LATIN_VERTEX_LETTERS, markdown_table
from egegen.solvers.graphs import (
    all_simple_paths,
    count_paths_dag,
    count_paths_dag_avoiding,
    count_paths_dag_through,
    count_shortest_paths,
    floyd_warshall,
    longest_path_dag,
    shortest_path_weight,
)

WEIGHTED_SUBTYPES = {"23.1_shortest_path", "23.4_shortest_via", "23.5_count_shortest"}


class Task23(Generator):
    task_no = 23
    answer_kind = "int"
    checker = "exact"
    requires_code = True
    uniqueness = Uniqueness.FUNCTIONAL
    generation_budget_ms = 400

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(40):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailedError(f"t23/{subtype}: no well-posed graph")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        cfg = load_fipi_config().t23
        weighted = subtype in WEIGHTED_SUBTYPES
        if weighted:
            built = self._weighted_graph(rng, difficulty, cfg)
        else:
            built = self._dag(rng, difficulty, cfg)
        if built is None:
            return None
        meta, fields = built
        meta["subtype"] = subtype
        meta["graph_input_format"] = cfg.graph_input_format
        meta["weighted"] = weighted

        question = self._question(rng, meta, subtype)
        if question is None:
            return None
        meta.update(question["meta"])
        fields.update(question["fields"])

        try:
            answer = self.solve_fast(meta)
        except (KeyError, ValueError):
            return None
        if not answer or not self._plausible(answer, meta, cfg):
            return None

        assets, presentation = self._present(meta)
        fields["presentation"] = presentation
        template = self.templates.pick(rng, subtype)
        statement = render(template, **fields)
        if any(a.kind == "svg" for a in assets):
            statement += "\n\n![Граф](asset:23.svg)"
        return Instance(
            task_no=self.task_no,
            subtype=subtype,
            difficulty=difficulty,
            seed=0,
            statement_md=statement,
            answer=answer,
            solution_steps=self._solution(meta, answer),
            reference_code=self._reference_code(meta),
            template_id=template.id,
            assets=assets,
            meta=meta,
        )

    # -- graph construction --------------------------------------------------
    def _weighted_graph(
        self, rng: Rng, difficulty: int, cfg: Any
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        size = rng.randint(
            cfg.weighted_min_nodes,
            min(cfg.weighted_max_nodes, 8 + difficulty, len(LATIN_VERTEX_LETTERS)),
        )
        labels = list(LATIN_VERTEX_LETTERS[:size])
        matrix = [[0] * size for _ in range(size)]
        order = rng.permutation(size)
        for k in range(1, size):
            a, b = order[k], order[rng.randint(0, k - 1)]
            matrix[a][b] = matrix[b][a] = rng.randint(1, cfg.max_weight)
        pairs = [(i, j) for i in range(size) for j in range(i + 1, size) if not matrix[i][j]]
        rng.shuffle(pairs)
        for i, j in pairs[: size + difficulty]:
            matrix[i][j] = matrix[j][i] = rng.randint(1, cfg.max_weight)
        meta = {"labels": labels, "matrix": matrix, "size": size}
        return meta, {"size": size}

    def _dag(
        self, rng: Rng, difficulty: int, cfg: Any
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        size = rng.randint(
            cfg.dag_min_nodes,
            min(cfg.dag_max_nodes, 9 + difficulty * 2, len(LATIN_VERTEX_LETTERS)),
        )
        labels = list(LATIN_VERTEX_LETTERS[:size])
        layer_count = max(3, min(size // 2, 3 + difficulty))
        layers: list[list[int]] = [[] for _ in range(layer_count)]
        layers[0].append(0)
        layers[-1].append(size - 1)
        for node in range(1, size - 1):
            layers[rng.randint(1, layer_count - 2)].append(node)
        if any(not layer for layer in layers):
            return None
        edges: list[list[int]] = []
        for index in range(layer_count - 1):
            for node in layers[index]:
                targets = rng.sample(layers[index + 1], rng.randint(1, len(layers[index + 1])))
                edges.extend([node, t] for t in targets)
            for node in layers[index + 1]:
                if not any(e[1] == node for e in edges):
                    edges.append([rng.choice(layers[index]), node])
        # A few skip-level arcs make the counting non-trivial while keeping acyclicity.
        for _ in range(difficulty):
            src_layer = rng.randint(0, layer_count - 3)
            dst_layer = rng.randint(src_layer + 2, layer_count - 1)
            pair = [rng.choice(layers[src_layer]), rng.choice(layers[dst_layer])]
            if pair not in edges:
                edges.append(pair)
        meta = {
            "labels": labels,
            "layers": [list(layer) for layer in layers],
            "edges": sorted(edges),
            "size": size,
        }
        return meta, {"size": size}

    def _question(self, rng: Rng, meta: dict[str, Any], subtype: str) -> dict[str, Any] | None:
        labels: list[str] = meta["labels"]
        source, target = 0, meta["size"] - 1
        match subtype:
            case "23.1_shortest_path":
                return {
                    "meta": {"question": "shortest", "source": source, "target": target},
                    "fields": {"source": labels[source], "target": labels[target]},
                }
            case "23.4_shortest_via":
                via = rng.randint(1, meta["size"] - 2)
                return {
                    "meta": {
                        "question": "shortest_via",
                        "source": source,
                        "target": target,
                        "via": via,
                    },
                    "fields": {
                        "source": labels[source],
                        "target": labels[target],
                        "via": labels[via],
                    },
                }
            case "23.5_count_shortest":
                return {
                    "meta": {
                        "question": "count_shortest",
                        "source": source,
                        "target": target,
                    },
                    "fields": {"source": labels[source], "target": labels[target]},
                }
            case "23.2_dag_paths":
                return {
                    "meta": {"question": "paths", "source": source, "target": target},
                    "fields": {"source": labels[source], "target": labels[target]},
                }
            case "23.3_paths_through":
                via = rng.randint(1, meta["size"] - 2)
                question = rng.choice(["paths_through", "paths_avoiding"])
                return {
                    "meta": {
                        "question": question,
                        "source": source,
                        "target": target,
                        "via": via,
                    },
                    "fields": {
                        "source": labels[source],
                        "target": labels[target],
                        "via": labels[via],
                        "condition": (
                            f"проходящих через вершину **{labels[via]}**"
                            if question == "paths_through"
                            else f"**не** проходящих через вершину **{labels[via]}**"
                        ),
                    },
                }
            case "23.6_longest_dag":
                return {
                    "meta": {"question": "longest", "source": source, "target": target},
                    "fields": {"source": labels[source], "target": labels[target]},
                }
        return None

    def _plausible(self, answer: str, meta: dict[str, Any], cfg: Any) -> bool:
        value = int(answer)
        if meta["question"] in ("paths", "paths_through", "paths_avoiding"):
            return int(cfg.dag_answer_min) <= value <= int(cfg.dag_answer_max)
        if meta["question"] == "count_shortest":
            return 1 <= value <= 12
        return 2 <= value <= 10_000

    # -- presentation --------------------------------------------------------
    def _present(self, meta: dict[str, Any]) -> tuple[list[Attachment], str]:
        labels: list[str] = meta["labels"]
        fmt = meta["graph_input_format"]
        if meta["weighted"]:
            matrix = meta["matrix"]
            rows = [["", *labels], *[[labels[i], *matrix[i]] for i in range(len(labels))]]
            match fmt:
                case "matrix_ods":
                    return (
                        [
                            Attachment(
                                "23.ods",
                                "application/vnd.oasis.opendocument.spreadsheet",
                                "ods",
                                to_ods(rows, sheet_name="Матрица"),
                            ),
                            Attachment("23.csv", "text/csv", "csv", to_csv(rows)),
                        ],
                        "Граф задан весовой матрицей в файле `23.ods` (та же таблица "
                        "есть в `23.csv`). Пустая ячейка означает, что ребра нет.\n\n"
                        + markdown_table(
                            ["", *labels],
                            [[labels[i], *matrix[i]] for i in range(len(labels))],
                            blank_zero=True,
                        ),
                    )
                case "edges_txt":
                    lines = [
                        f"{labels[i]} {labels[j]} {matrix[i][j]}"
                        for i in range(len(labels))
                        for j in range(i + 1, len(labels))
                        if matrix[i][j]
                    ]
                    return (
                        [Attachment("23.txt", "text/plain", "txt", to_txt(lines))],
                        "Граф задан списком рёбер в файле `23.txt`: в каждой строке "
                        "две вершины и вес ребра между ними.",
                    )
                case "figure":
                    svg = graph_svg(
                        labels,
                        [
                            (i, j, matrix[i][j])
                            for i in range(len(labels))
                            for j in range(i + 1, len(labels))
                            if matrix[i][j]
                        ],
                        title="Взвешенный граф",
                    )
                    return (
                        [
                            Attachment(
                                "23.svg",
                                "image/svg+xml",
                                "svg",
                                svg.encode("utf-8"),
                                inline=True,
                            )
                        ],
                        "Граф изображён на схеме; числа у рёбер — их веса.",
                    )
        edges = meta["edges"]
        match fmt:
            case "matrix_ods":
                size = len(labels)
                grid = [[0] * size for _ in range(size)]
                for a, b in edges:
                    grid[a][b] = 1
                rows = [["", *labels], *[[labels[i], *grid[i]] for i in range(size)]]
                return (
                    [
                        Attachment(
                            "23.ods",
                            "application/vnd.oasis.opendocument.spreadsheet",
                            "ods",
                            to_ods(rows, sheet_name="Матрица"),
                        ),
                        Attachment("23.csv", "text/csv", "csv", to_csv(rows)),
                    ],
                    "Граф задан матрицей смежности в файле `23.ods` (та же таблица "
                    "есть в `23.csv`). Единица в строке u и столбце v означает дугу "
                    "u → v.\n\n"
                    + markdown_table(
                        ["", *labels],
                        [[labels[i], *grid[i]] for i in range(size)],
                        blank_zero=True,
                    ),
                )
            case "edges_txt":
                lines = [f"{labels[a]} {labels[b]}" for a, b in edges]
                return (
                    [Attachment("23.txt", "text/plain", "txt", to_txt(lines))],
                    "Граф задан списком дуг в файле `23.txt`: в каждой строке начало и конец дуги.",
                )
            case "figure":
                svg = dag_svg(labels, meta["layers"], [(a, b) for a, b in edges])
                return (
                    [
                        Attachment(
                            "23.svg",
                            "image/svg+xml",
                            "svg",
                            svg.encode("utf-8"),
                            inline=True,
                        )
                    ],
                    "Граф изображён на схеме; стрелки показывают направление дуг.",
                )
        raise ValueError(fmt)

    # -- solving -------------------------------------------------------------
    def _weighted(self, meta: dict[str, Any]) -> dict[str, dict[str, int]]:
        labels, matrix = meta["labels"], meta["matrix"]
        return {
            labels[i]: {labels[j]: matrix[i][j] for j in range(len(labels)) if matrix[i][j]}
            for i in range(len(labels))
        }

    def _adjacency(self, meta: dict[str, Any]) -> dict[str, list[str]]:
        labels = meta["labels"]
        adj: dict[str, list[str]] = {label: [] for label in labels}
        for a, b in meta["edges"]:
            adj[labels[a]].append(labels[b])
        return adj

    def solve_fast(self, meta: dict[str, Any]) -> str:
        labels = meta["labels"]
        source, target = labels[meta["source"]], labels[meta["target"]]
        match meta["question"]:
            case "shortest":
                return str(int(shortest_path_weight(self._weighted(meta), source, target)))
            case "shortest_via":
                graph = self._weighted(meta)
                via = labels[meta["via"]]
                first = shortest_path_weight(graph, source, via)
                second = shortest_path_weight(graph, via, target)
                return (
                    ""
                    if first == float("inf") or second == float("inf")
                    else str(int(first + second))
                )
            case "count_shortest":
                return str(count_shortest_paths(self._weighted(meta), source, target))
            case "paths":
                return str(count_paths_dag(self._adjacency(meta), source, target))
            case "paths_through":
                return str(
                    count_paths_dag_through(
                        self._adjacency(meta), source, labels[meta["via"]], target
                    )
                )
            case "paths_avoiding":
                return str(
                    count_paths_dag_avoiding(
                        self._adjacency(meta), source, target, labels[meta["via"]]
                    )
                )
            case "longest":
                adj = self._adjacency(meta)
                weights = {u: dict.fromkeys(vs, 1) for u, vs in adj.items()}
                value = longest_path_dag(adj, weights, source, target)
                return "" if value == float("-inf") else str(int(value))
        raise ValueError(meta["question"])

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        """Floyd-Warshall for the weighted questions; full path enumeration for DAGs."""
        labels = meta["labels"]
        source, target = labels[meta["source"]], labels[meta["target"]]
        match meta["question"]:
            case "shortest":
                return str(int(floyd_warshall(self._weighted(meta))[source][target]))
            case "shortest_via":
                table = floyd_warshall(self._weighted(meta))
                via = labels[meta["via"]]
                return str(int(table[source][via] + table[via][target]))
            case "count_shortest":
                graph = self._weighted(meta)
                best = floyd_warshall(graph)[source][target]
                adj = {u: list(vs) for u, vs in graph.items()}
                try:
                    paths = all_simple_paths(adj, source, target, limit=60_000)
                except ValueError:
                    return None
                return str(
                    sum(
                        1
                        for path in paths
                        if sum(graph[path[i]][path[i + 1]] for i in range(len(path) - 1)) == best
                    )
                )
            case "paths" | "paths_through" | "paths_avoiding":
                adj = self._adjacency(meta)
                try:
                    paths = all_simple_paths(adj, source, target, limit=60_000)
                except ValueError:
                    return None
                via = labels[meta["via"]] if "via" in meta else None
                if meta["question"] == "paths":
                    return str(len(paths))
                if meta["question"] == "paths_through":
                    return str(sum(1 for p in paths if via in p))
                return str(sum(1 for p in paths if via not in p))
            case "longest":
                adj = self._adjacency(meta)
                try:
                    paths = all_simple_paths(adj, source, target, limit=60_000)
                except ValueError:
                    return None
                return str(max((len(p) - 1 for p in paths), default=0))
        return None

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        if not answer:
            raise ValueError("t23: target unreachable")

    # -- explanation ---------------------------------------------------------
    def _reference_code(self, meta: dict[str, Any]) -> str:
        labels = meta["labels"]
        source, target = labels[meta["source"]], labels[meta["target"]]
        reader = {
            "matrix_ods": (
                "import csv\n"
                "rows = list(csv.reader(open('23.csv')))\n"
                "names = rows[0][1:]\n"
                "g = {u: {} for u in names}\n"
                "for r in rows[1:]:\n"
                "    for v, w in zip(names, r[1:]):\n"
                "        if w.strip() and int(w): g[r[0]][v] = int(w)\n"
            ),
            "edges_txt": (
                "g = {}\n"
                "for line in open('23.txt'):\n"
                "    parts = line.split()\n"
                "    u, v = parts[0], parts[1]\n"
                "    w = int(parts[2]) if len(parts) > 2 else 1\n"
                "    g.setdefault(u, {})[v] = w\n"
                "    g.setdefault(v, {})\n"
            ),
            "figure": (
                "# граф со схемы выписывается руками\n"
                "g = {'A': {'B': 3, 'C': 1}, 'B': {'D': 1}, 'C': {'D': 5}, 'D': {}}\n"
            ),
        }[meta["graph_input_format"]]
        if meta["weighted"]:
            body = (
                "import heapq\n"
                "def dijkstra(g, s):\n"
                "    d = {s: 0}; pq = [(0, s)]\n"
                "    while pq:\n"
                "        du, u = heapq.heappop(pq)\n"
                "        if du > d[u]: continue\n"
                "        for v, w in g[u].items():\n"
                "            if du + w < d.get(v, float('inf')):\n"
                "                d[v] = du + w; heapq.heappush(pq, (d[v], v))\n"
                "    return d\n"
            )
            if meta["question"] == "shortest_via":
                tail = (
                    f"print(dijkstra(g, '{source}')['{labels[meta['via']]}']"
                    f" + dijkstra(g, '{labels[meta['via']]}')['{target}'])\n"
                )
            else:
                tail = f"print(dijkstra(g, '{source}')['{target}'])\n"
            return reader + "\n" + body + "\n" + tail
        body = (
            "from functools import lru_cache\n"
            "@lru_cache(None)\n"
            "def paths(u, t):\n"
            "    return 1 if u == t else sum(paths(v, t) for v in g.get(u, {}))\n"
        )
        match meta["question"]:
            case "paths":
                tail = f"print(paths('{source}', '{target}'))\n"
            case "paths_through":
                via = labels[meta["via"]]
                tail = f"print(paths('{source}', '{via}') * paths('{via}', '{target}'))\n"
            case "paths_avoiding":
                via = labels[meta["via"]]
                tail = (
                    f"print(paths('{source}', '{target}')"
                    f" - paths('{source}', '{via}') * paths('{via}', '{target}'))\n"
                )
            case _:
                body = (
                    "from functools import lru_cache\n"
                    "@lru_cache(None)\n"
                    "def longest(u, t):\n"
                    "    if u == t: return 0\n"
                    "    best = -10**9\n"
                    "    for v in g.get(u, {}):\n"
                    "        best = max(best, 1 + longest(v, t))\n"
                    "    return best\n"
                )
                tail = f"print(longest('{source}', '{target}'))\n"
        return reader + "\n" + body + "\n" + tail

    def _solution(self, meta: dict[str, Any], answer: str) -> list[str]:
        labels = meta["labels"]
        source, target = labels[meta["source"]], labels[meta["target"]]
        if meta["weighted"]:
            head = (
                "**Шаг 1.** Кратчайший путь считается **по весам**, а не по числу "
                "рёбер. Граф неориентированный, поэтому каждое ребро идёт в обе "
                "стороны — не забудьте про это при чтении матрицы."
            )
            if meta["question"] == "shortest_via":
                mid = (
                    f"**Шаг 2.** «Через {labels[meta['via']]}» — это сумма двух "
                    f"кратчайших путей: {source} → {labels[meta['via']]} и "
                    f"{labels[meta['via']]} → {target}."
                )
            elif meta["question"] == "count_shortest":
                mid = (
                    "**Шаг 2.** Считаем не длину, а **количество** кратчайших путей: "
                    "при релаксации, если найден путь той же длины, складываем "
                    "количества."
                )
            else:
                mid = (
                    "**Шаг 2.** Для графа из десятка вершин подойдёт и Дейкстра, "
                    "и Флойд–Уоршелл (три вложенных цикла) — второй проще запомнить."
                )
            return [
                head,
                mid,
                "**Шаг 3.** Шаблон:\n\n```python\n" + self._reference_code(meta) + "```",
                f"**Ответ:** **{answer}**.",
            ]
        return [
            "**Шаг 1.** Граф ориентированный и ацикличный, поэтому число путей "
            "конечно и считается рекурсией с кэшем: "
            "`paths(u) = 1, если u — конец, иначе сумма paths(v) по всем дугам u → v`.",
            (
                "**Шаг 2.** «Через X» — это произведение `paths(A→X) · paths(X→B)`; "
                "«минуя X» — разность `paths(A→B) − paths(A→X) · paths(X→B)`. "
                "Вычитание корректно **только** потому, что граф ацикличен: пройти "
                "через X дважды нельзя."
                if meta["question"] in ("paths_through", "paths_avoiding")
                else "**Шаг 2.** На схеме то же самое делается в уме: подпишите "
                "у каждой вершины число путей, ведущих в неё из начальной, слева "
                "направо — число в вершине равно сумме чисел предшественников."
            ),
            "**Шаг 3.** Шаблон:\n\n```python\n" + self._reference_code(meta) + "```",
            f"**Ответ:** **{answer}**.",
        ]


register(Task23())
