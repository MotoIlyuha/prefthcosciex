"""Task 22 — parallel processes described by a dependency table.

A process starts only once **all** of its dependencies have finished, and the number
of processors is unlimited unless the statement says otherwise. The fast solver
memoises finish times; the naive one relaxes them repeatedly until nothing changes,
which needs no notion of topological order at all.
"""

from __future__ import annotations

from typing import Any

from egegen.core.errors import GenerationFailedError
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.tables import preview, to_csv, to_ods
from egegen.core.templates import render
from egegen.core.types import Attachment, Instance, Uniqueness

HEADER = ["ID процесса", "Время выполнения", "ID процессов, от которых зависит"]


class Task22(Generator):
    task_no = 22
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
        raise GenerationFailedError(f"t22/{subtype}: no valid instance")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        count = 8 + difficulty + rng.randint(0, 3)
        processes = self._random_dag(rng, count, difficulty)
        meta: dict[str, Any] = {
            "subtype": subtype,
            "processes": processes,
        }
        fields: dict[str, Any] = {}

        finishes = self._finish_times(processes)
        total = max(finishes.values())

        match subtype:
            case "22.1_total_time":
                meta["question"] = "total"
            case "22.2_max_parallel":
                meta["question"] = "max_parallel"
            case "22.3_finished_by":
                moment = rng.randint(total // 3, max(total // 3 + 1, total - 2))
                meta["question"], meta["moment"] = "finished_by", moment
                fields["moment"] = moment
            case "22.4_earliest_start":
                target = rng.choice(sorted(p["id"] for p in processes if p["deps"]))
                meta["question"], meta["target"] = "earliest_start", target
                fields["target"] = target
            case "22.5_limited_cpus":
                cpus = rng.randint(2, 3)
                meta["question"], meta["cpus"] = "limited", cpus
                fields["cpus"] = cpus
            case _:
                return None

        answer = self.solve_fast(meta)
        if not 2 <= int(answer) <= 10_000:
            return None

        rows = [HEADER, *[[p["id"], p["time"], self._deps_text(p)] for p in processes]]
        csv_bytes = to_csv(rows, delimiter=";")
        fields["preview"] = preview(rows, limit=6)
        fields["count"] = len(processes)
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
                Attachment("22.csv", "text/csv", "csv", csv_bytes),
                Attachment(
                    "22.ods",
                    "application/vnd.oasis.opendocument.spreadsheet",
                    "ods",
                    to_ods(rows, sheet_name="Процессы"),
                ),
            ],
            meta=meta,
        )

    def _random_dag(self, rng: Rng, count: int, difficulty: int) -> list[dict[str, Any]]:
        """Dependencies always point at smaller ids, so the graph cannot have a cycle."""
        processes: list[dict[str, Any]] = []
        for i in range(1, count + 1):
            max_deps = 0 if i == 1 else min(3, i - 1, 1 + difficulty // 2)
            n_deps = rng.randint(0, max_deps) if i > 1 else 0
            deps = sorted(rng.sample(range(1, i), n_deps)) if n_deps else []
            processes.append({"id": i, "time": rng.randint(1, 20), "deps": deps})
        return processes

    def _deps_text(self, process: dict[str, Any]) -> str:
        return ";".join(str(d) for d in process["deps"]) if process["deps"] else "0"

    # -- solving ------------------------------------------------------------
    def _finish_times(self, processes: list[dict[str, Any]]) -> dict[int, int]:
        """Memoised recursion: finish = duration + max(finish of dependencies)."""
        by_id = {p["id"]: p for p in processes}
        cache: dict[int, int] = {}

        def finish(pid: int) -> int:
            if pid not in cache:
                process = by_id[pid]
                cache[pid] = process["time"] + max((finish(d) for d in process["deps"]), default=0)
            return cache[pid]

        return {p["id"]: finish(p["id"]) for p in processes}

    def _finish_times_relaxed(self, processes: list[dict[str, Any]]) -> dict[int, int]:
        """Repeat relaxation until nothing changes — no recursion, no ordering."""
        by_id = {p["id"]: p for p in processes}
        finish = {p["id"]: p["time"] for p in processes}
        for _ in range(len(processes) + 1):
            changed = False
            for pid, process in by_id.items():
                ready = max((finish[d] for d in process["deps"]), default=0)
                candidate = ready + process["time"]
                if candidate > finish[pid]:
                    finish[pid] = candidate
                    changed = True
            if not changed:
                break
        return finish

    def _answer_from(self, meta: dict[str, Any], finish: dict[int, int]) -> str:
        processes: list[dict[str, Any]] = meta["processes"]
        by_id = {p["id"]: p for p in processes}
        match meta["question"]:
            case "total":
                return str(max(finish.values()))
            case "max_parallel":
                events: list[tuple[int, int]] = []
                for pid, end in finish.items():
                    events.append((end - by_id[pid]["time"], 1))
                    events.append((end, -1))
                events.sort()
                best = current = 0
                for _, delta in events:
                    current += delta
                    best = max(best, current)
                return str(best)
            case "finished_by":
                return str(sum(1 for end in finish.values() if end <= meta["moment"]))
            case "earliest_start":
                target = meta["target"]
                return str(max((finish[d] for d in by_id[target]["deps"]), default=0))
            case "limited":
                return str(self._schedule_limited(processes, meta["cpus"]))
        raise ValueError(meta["question"])

    def _schedule_limited(self, processes: list[dict[str, Any]], cpus: int) -> int:
        """List scheduling, event driven.

        The tie-break — the ready process with the smallest id starts first — is
        stated in the statement, so the answer is well defined. The tick-by-tick
        replay in :meth:`enumerate_answers` is the independent check on this.
        """
        by_id = {p["id"]: p for p in processes}
        finish: dict[int, int] = {}
        running: list[tuple[int, int]] = []  # (end time, pid)
        pending = sorted(by_id)
        now = 0
        while pending or running:
            while len(running) < cpus:
                ready = next(
                    (
                        pid
                        for pid in pending
                        if all(d in finish and finish[d] <= now for d in by_id[pid]["deps"])
                    ),
                    None,
                )
                if ready is None:
                    break
                pending.remove(ready)
                running.append((now + by_id[ready]["time"], ready))
            if not running:
                break  # only reachable if the graph had a cycle, which it cannot
            running.sort()
            now = running[0][0]
            while running and running[0][0] == now:
                end, pid = running.pop(0)
                finish[pid] = end
        return max(finish.values())

    def solve_fast(self, meta: dict[str, Any]) -> str:
        return self._answer_from(meta, self._finish_times(meta["processes"]))

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        if meta["question"] == "limited":
            return None  # the schedule has no second formulation; see enumerate_answers
        return self._answer_from(meta, self._finish_times_relaxed(meta["processes"]))

    def enumerate_answers(self, meta: dict[str, Any]) -> list[str] | None:
        """For the limited-processor variant, replay the schedule tick by tick."""
        if meta["question"] != "limited":
            return None
        processes: list[dict[str, Any]] = meta["processes"]
        by_id = {p["id"]: p for p in processes}
        cpus: int = meta["cpus"]
        remaining = {p["id"]: p["time"] for p in processes}
        finish: dict[int, int] = {}
        busy: set[int] = set()
        clock = 0
        limit = sum(p["time"] for p in processes) + 1
        while len(finish) < len(processes) and clock <= limit:
            # Fill free processors at the current moment, smallest id first.
            for pid in sorted(by_id):
                if len(busy) >= cpus:
                    break
                if pid in finish or pid in busy:
                    continue
                if all(d in finish and finish[d] <= clock for d in by_id[pid]["deps"]):
                    busy.add(pid)
            # Then let one millisecond pass.
            clock += 1
            for pid in sorted(busy):
                remaining[pid] -= 1
                if remaining[pid] == 0:
                    finish[pid] = clock
                    busy.discard(pid)
        return [str(max(finish.values()))] if len(finish) == len(processes) else []

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        if int(answer) < 1:
            raise ValueError("t22: answer must be positive")

    # -- explanation --------------------------------------------------------
    def _reference_code(self, meta: dict[str, Any]) -> str:
        head = (
            "import csv\nfrom functools import lru_cache\n\n"
            "rows = list(csv.reader(open('22.csv'), delimiter=';'))[1:]\n"
            "proc = {int(r[0]): (int(r[1]),\n"
            "        [int(x) for x in r[2].split(';') if x.strip() not in ('', '0')])\n"
            "        for r in rows}\n\n"
            "@lru_cache(None)\ndef fin(p):\n"
            "    t, deps = proc[p]\n"
            "    return t + max((fin(d) for d in deps), default=0)\n\n"
        )
        match meta["question"]:
            case "total":
                return head + "print(max(fin(p) for p in proc))\n"
            case "max_parallel":
                return head + (
                    "events = []\n"
                    "for p, (t, _) in proc.items():\n"
                    "    events.append((fin(p) - t, 1)); events.append((fin(p), -1))\n"
                    "events.sort()\n"
                    "best = cur = 0\n"
                    "for _, d in events:\n"
                    "    cur += d; best = max(best, cur)\n"
                    "print(best)\n"
                )
            case "finished_by":
                return head + f"print(sum(fin(p) <= {meta['moment']} for p in proc))\n"
            case "earliest_start":
                return head + (
                    f"print(max((fin(d) for d in proc[{meta['target']}][1]), default=0))\n"
                )
            case "limited":
                return head + (
                    "# процессоров мало: запускаем готовый процесс с наименьшим ID\n"
                    f"CPUS = {meta['cpus']}\n"
                    "done, busy, clock = {}, {}, 0\n"
                    "left = {p: proc[p][0] for p in proc}\n"
                    "while len(done) < len(proc):\n"
                    "    for p in sorted(busy):\n"
                    "        left[p] -= 1\n"
                    "        if left[p] == 0: done[p] = clock + 1; del busy[p]\n"
                    "    clock += 1\n"
                    "    for p in sorted(proc):\n"
                    "        if len(busy) >= CPUS: break\n"
                    "        if p in done or p in busy: continue\n"
                    "        if all(d in done and done[d] <= clock for d in proc[p][1]):\n"
                    "            busy[p] = clock\n"
                    "print(max(done.values()))\n"
                )
        raise ValueError(meta["question"])

    def _solution(self, meta: dict[str, Any], answer: str) -> list[str]:
        finish = self._finish_times(meta["processes"])
        slowest = max(finish, key=lambda pid: finish[pid])
        base = [
            "**Шаг 1.** Момент окончания процесса = его длительность + **максимум** "
            "моментов окончания всех процессов, от которых он зависит. Зависимость "
            "«0» означает, что зависимостей нет.",
            "**Шаг 2.** Считаем рекурсией с кэшем — порядок строк в файле значения "
            "не имеет:\n\n```python\n" + self._reference_code(meta) + "```",
        ]
        match meta["question"]:
            case "total":
                base.append(
                    f"**Шаг 3.** Самым поздним заканчивается процесс {slowest} "
                    f"в момент {finish[slowest]}. Это и есть минимальное время "
                    f"выполнения всей совокупности: **{answer}**. Обратите внимание: "
                    "спрашивают **момент**, а не длительность последнего процесса."
                )
            case "max_parallel":
                base.append(
                    "**Шаг 3.** Каждый процесс занимает отрезок [конец − длительность; "
                    "конец]. Проходим по событиям «начался / закончился» и находим "
                    f"максимальное число одновременно активных: **{answer}**."
                )
            case "finished_by":
                base.append(
                    f"**Шаг 3.** Считаем процессы с моментом окончания не позже "
                    f"{meta['moment']}: их **{answer}**."
                )
            case "earliest_start":
                base.append(
                    f"**Шаг 3.** Процесс {meta['target']} стартует, когда завершатся "
                    "**все** его зависимости, то есть в момент максимума их окончаний: "
                    f"**{answer}**."
                )
            case "limited":
                base.append(
                    f"**Шаг 3.** Процессоров всего {meta['cpus']}, поэтому готовые "
                    "процессы ждут очереди; по условию первым запускается готовый "
                    f"процесс с наименьшим номером. Все процессы завершаются "
                    f"к моменту **{answer}**."
                )
        return base


register(Task22())
