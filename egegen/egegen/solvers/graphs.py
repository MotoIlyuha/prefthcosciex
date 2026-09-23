"""Graph kernels for tasks 1 and 23."""

from __future__ import annotations

import heapq
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence

Weighted = Mapping[str, Mapping[str, int]]
Adjacency = Mapping[str, Sequence[str]]

INF = float("inf")


def dijkstra(graph: Weighted, source: str) -> dict[str, float]:
    """Shortest distances from ``source`` over non-negative weights."""
    dist: dict[str, float] = {source: 0}
    pq: list[tuple[float, str]] = [(0, source)]
    while pq:
        du, u = heapq.heappop(pq)
        if du > dist.get(u, INF):
            continue
        for v, w in graph[u].items():
            nd = du + w
            if nd < dist.get(v, INF):
                dist[v] = nd
                heapq.heappush(pq, (nd, v))
    return dist


def floyd_warshall(graph: Weighted) -> dict[str, dict[str, float]]:
    """All-pairs shortest paths — the independent cross-check of :func:`dijkstra`."""
    nodes = list(graph)
    dist: dict[str, dict[str, float]] = {
        u: {v: (0.0 if u == v else float(graph[u].get(v, INF))) for v in nodes} for u in nodes
    }
    for k in nodes:
        dk = dist[k]
        for i in nodes:
            dik = dist[i][k]
            if dik == INF:
                continue
            di = dist[i]
            for j in nodes:
                nd = dik + dk[j]
                if nd < di[j]:
                    di[j] = nd
    return dist


def all_simple_paths(
    adj: Adjacency, source: str, target: str, limit: int = 200_000
) -> list[list[str]]:
    """Every simple path source -> target. Naive cross-check; capped to stay bounded."""
    out: list[list[str]] = []
    stack: list[tuple[str, list[str], set[str]]] = [(source, [source], {source})]
    while stack:
        node, path, seen = stack.pop()
        if node == target:
            out.append(path)
            if len(out) > limit:
                raise ValueError("path explosion: raise the limit or shrink the graph")
            continue
        for nxt in adj[node]:
            if nxt not in seen:
                stack.append((nxt, [*path, nxt], seen | {nxt}))
    return out


def shortest_path_weight(graph: Weighted, source: str, target: str) -> float:
    return dijkstra(graph, source).get(target, INF)


def count_shortest_paths(graph: Weighted, source: str, target: str) -> int:
    """Number of distinct minimum-weight paths from ``source`` to ``target``."""
    dist: dict[str, float] = {source: 0}
    ways: dict[str, int] = defaultdict(int, {source: 1})
    pq: list[tuple[float, str]] = [(0, source)]
    done: set[str] = set()
    while pq:
        du, u = heapq.heappop(pq)
        if u in done:
            continue
        done.add(u)
        for v, w in graph[u].items():
            nd = du + w
            if nd < dist.get(v, INF):
                dist[v] = nd
                ways[v] = ways[u]
                heapq.heappush(pq, (nd, v))
            elif nd == dist.get(v, INF):
                ways[v] += ways[u]
    return ways.get(target, 0)


def topological_order(adj: Adjacency) -> list[str]:
    """Kahn's algorithm. Raises when the graph has a cycle (a DAG task would be ill-posed)."""
    indeg: dict[str, int] = dict.fromkeys(adj, 0)
    for u in adj:
        for v in adj[u]:
            indeg[v] += 1
    queue = deque(sorted(u for u, d in indeg.items() if d == 0))
    order: list[str] = []
    while queue:
        u = queue.popleft()
        order.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)
    if len(order) != len(adj):
        raise ValueError("graph is not acyclic")
    return order


def count_paths_dag(adj: Adjacency, source: str, target: str) -> int:
    """Number of directed paths source -> target in a DAG (DP over a topological order)."""
    order = topological_order(adj)
    ways = dict.fromkeys(adj, 0)
    ways[source] = 1
    for u in order:
        if ways[u] == 0:
            continue
        for v in adj[u]:
            ways[v] += ways[u]
    return ways[target]


def count_paths_dag_through(adj: Adjacency, source: str, via: str, target: str) -> int:
    return count_paths_dag(adj, source, via) * count_paths_dag(adj, via, target)


def count_paths_dag_avoiding(adj: Adjacency, source: str, target: str, avoid: str) -> int:
    """Paths that never touch ``avoid``.

    Subtracting ``through`` is valid only because the graph is acyclic: a path can
    visit ``avoid`` at most once (doc, Appendix A, task 23 traps).
    """
    return count_paths_dag(adj, source, target) - count_paths_dag_through(
        adj, source, avoid, target
    )


def longest_path_dag(adj: Adjacency, weights: Weighted, source: str, target: str) -> float:
    order = topological_order(adj)
    best: dict[str, float] = dict.fromkeys(adj, -INF)
    best[source] = 0
    for u in order:
        if best[u] == -INF:
            continue
        for v in adj[u]:
            cand = best[u] + weights[u][v]
            if cand > best[v]:
                best[v] = cand
    return best[target]


def degree_signature(matrix: Sequence[Sequence[int]]) -> list[tuple[int, tuple[int, ...]]]:
    """(degree, sorted neighbour degrees) per row — the manual method for task 1."""
    n = len(matrix)
    deg = [sum(1 for j in range(n) if matrix[i][j]) for i in range(n)]
    return [(deg[i], tuple(sorted(deg[j] for j in range(n) if matrix[i][j]))) for i in range(n)]


def matchings(
    figure: Sequence[Sequence[int]], table: Sequence[Sequence[int]]
) -> Iterable[tuple[int, ...]]:
    """Every bijection figure-vertex -> table-row consistent with both adjacencies.

    Both matrices are read as adjacency (non-zero means "there is an edge"): the
    figure in task 1 carries no weights, so only the shape can be matched. Task 1 is
    well-posed only when the asked quantity is the same under *all* of these
    bijections, which is what the generator checks before releasing an instance.
    """
    n = len(figure)
    sig_f = degree_signature(figure)
    sig_t = degree_signature(table)
    assignment: list[int] = []
    used = [False] * n

    def backtrack() -> Iterable[tuple[int, ...]]:
        i = len(assignment)
        if i == n:
            yield tuple(assignment)
            return
        for j in range(n):
            if used[j] or sig_f[i] != sig_t[j]:
                continue
            if all(bool(figure[i][k]) == bool(table[j][assignment[k]]) for k in range(i)):
                used[j] = True
                assignment.append(j)
                yield from backtrack()
                assignment.pop()
                used[j] = False

    return backtrack()
