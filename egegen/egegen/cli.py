"""``egegen`` command line: generate, inspect and stress the task generators."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Annotated

import typer

from egegen.core.registry import get_generator, list_generators
from egegen.testing import check_instance, sweep

app = typer.Typer(add_completion=False, help="Generators for the 27 EGE-2027 tasks.")


@app.command("list")
def list_cmd() -> None:
    """List every registered generator with its subtypes."""
    for gen in list_generators():
        typer.echo(f"t{gen.task_no:02d}  {gen.title}")
        for sid in gen.subtypes:
            spec = gen.templates.subtypes[sid]
            typer.echo(
                f"      {sid:<28} {spec.title}  "
                f"(сложность {spec.difficulty_range[0]}–{spec.difficulty_range[1]}, "
                f"{spec.target_seconds} с)"
            )


@app.command()
def gen(
    task: Annotated[int, typer.Argument(help="Task number 1..27")],
    seed: Annotated[int, typer.Option(help="Base seed")] = 1,
    n: Annotated[int, typer.Option(help="How many instances to generate")] = 1,
    difficulty: Annotated[int, typer.Option(min=1, max=5)] = 3,
    subtype: Annotated[str | None, typer.Option(help="Restrict to one subtype")] = None,
    check: Annotated[bool, typer.Option(help="Run the full property checks too")] = True,
) -> None:
    """Generate N instances, timing them and running the invariants."""
    generator = get_generator(task)
    times: list[float] = []
    failures: list[str] = []
    started = time.perf_counter()
    for i in range(n):
        if check:
            report = check_instance(generator, seed + i, difficulty, subtype or _pick(generator, i))
            times.append(report.gen_ms)
            if not report.ok:
                failures.append(str(report))
        else:
            _, ms = generator.timed_generate(seed + i, difficulty, subtype)
            times.append(ms)
    total = time.perf_counter() - started
    typer.echo(
        f"t{task:02d}: {n} экземпляров за {total:.2f} с — "
        f"медиана {statistics.median(times):.1f} мс, максимум {max(times):.1f} мс"
    )
    for line in failures[:20]:
        typer.secho(line, fg=typer.colors.RED)
    if failures:
        typer.secho(f"{len(failures)} экземпляров не прошли проверки", fg=typer.colors.RED)
        raise typer.Exit(1)


def _pick(generator: object, i: int) -> str:
    subtypes = generator.subtypes  # type: ignore[attr-defined]
    return subtypes[i % len(subtypes)]


@app.command()
def show(
    task: Annotated[int, typer.Argument(help="Task number 1..27")],
    seed: Annotated[int, typer.Option()] = 1,
    difficulty: Annotated[int, typer.Option(min=1, max=5)] = 3,
    subtype: Annotated[str | None, typer.Option()] = None,
    assets_dir: Annotated[Path | None, typer.Option(help="Write assets here")] = None,
) -> None:
    """Print one instance: statement, answer, solution, reference code."""
    generator = get_generator(task)
    inst = generator.generate(seed, difficulty, subtype)
    typer.echo(f"=== t{task:02d} · {inst.subtype} · сложность {inst.difficulty} ===")
    typer.echo(inst.statement_md)
    typer.echo(f"\n--- ОТВЕТ ({inst.answer_kind}) ---\n{inst.answer}")
    typer.echo(f"\n--- РАЗБОР ---\n{inst.solution_md}")
    if inst.reference_code:
        typer.echo(f"\n--- ЭТАЛОННЫЙ КОД ---\n{inst.reference_code}")
    for asset in inst.assets:
        typer.echo(f"\n[asset] {asset.name} {asset.mime} {asset.size} B sha={asset.sha256[:12]}")
        if assets_dir:
            assets_dir.mkdir(parents=True, exist_ok=True)
            (assets_dir / asset.name).write_bytes(asset.content)


@app.command()
def property_check(
    task: Annotated[int | None, typer.Option(help="One task, or all when omitted")] = None,
    seeds: Annotated[int, typer.Option(help="Seeds per subtype and difficulty")] = 25,
) -> None:
    """Run the property sweep over one generator or all of them."""
    generators = [get_generator(task)] if task else list_generators()
    bad = 0
    for generator in generators:
        reports = sweep(generator, range(1000, 1000 + seeds))
        failed = [r for r in reports if not r.ok]
        worst = max((r.gen_ms for r in reports), default=0.0)
        status = "OK " if not failed else "FAIL"
        typer.echo(
            f"[{status}] t{generator.task_no:02d} {len(reports)} экземпляров, "
            f"максимум {worst:.0f} мс"
        )
        for report in failed[:5]:
            typer.secho(f"       {report}", fg=typer.colors.RED)
        bad += len(failed)
    if bad:
        typer.secho(f"{bad} проверок не прошло", fg=typer.colors.RED)
        raise typer.Exit(1)


@app.command()
def selfcheck() -> None:
    """Golden values quoted in the design doc, as an executable assertion."""
    from egegen.solvers.games import GameAnalyzer, one_pile_moves

    n = 129
    game = GameAnalyzer(one_pile_moves([1], [2]), lambda s: s >= n)
    got = {
        "19": [s for s in range(1, n) if game.L1(s)],
        "20": [s for s in range(1, n) if game.W2(s)],
        "21": [s for s in range(1, n) if game.L2(s)],
    }
    want = {"19": [64], "20": [32, 63], "21": [62]}
    typer.echo(json.dumps(got, ensure_ascii=False))
    if got != want:
        typer.secho(f"расхождение с дизайн-доком: ожидалось {want}", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.secho("Игры N=129 (+1, x2): 19 → 64; 20 → 32, 63; 21 → 62 — совпадает", fg=typer.colors.GREEN)


def main() -> None:
    sys.exit(app())


if __name__ == "__main__":
    main()
