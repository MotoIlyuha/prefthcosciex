"""Deferred assets: file B of task 27 (10^6 numbers), built from its seed and gzipped."""

from __future__ import annotations

from egegen.core.rng import bulk_ints
from egegen.core.tables import to_txt
from starlette.concurrency import run_in_threadpool

from app.core.errors import not_found
from app.db.models import Instance


def _build(meta: dict[str, int], name: str) -> bytes:
    if name != "27B.txt":
        raise KeyError(name)
    values = bulk_ints(meta["b_seed"], meta["b_size"], meta["b_lo"], meta["b_hi"])
    return to_txt([len(values), *values])


async def build_deferred(row: Instance, name: str) -> bytes:
    return await build_deferred_for_seed(row, row.seed, name)


async def build_deferred_for_seed(row: Instance, seed: int, name: str) -> bytes:
    """File B of another variant of the same subtype (the code re-check, 7.5.2)."""
    from app.services.instances import generate

    gen = await generate(row.task_no, seed, row.difficulty, row.subtype_id)
    try:
        return await run_in_threadpool(_build, gen.meta, name)
    except KeyError as exc:
        raise not_found("файл задания") from exc
