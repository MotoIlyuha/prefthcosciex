"""Creating, projecting and regenerating task instances.

The instance row carries everything needed to check an answer without calling the
generator again. The assets are written to the asset store; a missing asset is
regenerated from the seed, since the generator is a pure function of it.
"""

from __future__ import annotations

import base64
from datetime import UTC, date, datetime, timedelta
from typing import Any

from egegen.core.registry import get_generator
from egegen.core.types import Instance as GenInstance
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.errors import not_found
from app.db.models import Instance
from app.logic.timeutil import day_bounds
from app.services.assets import store

INLINE_LIMIT = 64 * 1024
EXPIRY = timedelta(hours=24)


def _generate(task_no: int, seed: int, difficulty: int, subtype: str | None) -> GenInstance:
    return get_generator(task_no).generate(seed, difficulty, subtype)


async def generate(task_no: int, seed: int, difficulty: int, subtype: str | None) -> GenInstance:
    # Generation is CPU-bound (up to a few hundred ms for 27): keep it off the loop.
    return await run_in_threadpool(_generate, task_no, seed, difficulty, subtype)


async def create(
    session: AsyncSession,
    *,
    user_id: int,
    task_no: int,
    subtype: str | None,
    difficulty: int,
    seed: int,
    context: str,
    slot: str = "practice",
    mandatory: bool = False,
    planned_for: date | None = None,
    tz: str | None = None,
    flags: list[str] | None = None,
    exam_id: int | None = None,
    expires_at: datetime | None = None,
) -> Instance:
    gen = await generate(task_no, seed, difficulty, subtype)
    now = datetime.now(UTC)
    if expires_at is None:
        if context == "daily" and planned_for is not None:
            _, expires_at = day_bounds(tz, planned_for)
        else:
            expires_at = now + EXPIRY
    row = Instance(
        user_id=user_id,
        task_no=task_no,
        subtype_id=gen.subtype,
        difficulty=difficulty,
        seed=seed,
        hidden_seed=gen.hidden_seed,
        gen_version=gen.version,
        context=context,
        slot=slot,
        mandatory=mandatory,
        statement_md=gen.statement_md,
        assets=[_asset_meta(a) for a in gen.assets],
        answer=gen.answer,
        answer_hash=gen.answer_hash(),
        answer_kind=gen.answer_kind,
        checker=gen.checker,
        checker_options=dict(gen.checker_options),
        solution_steps=list(gen.solution_steps),
        reference_code=gen.reference_code,
        method_card_id=gen.method_card_id,
        target_seconds=gen.target_seconds,
        exam_like=gen.exam_like,
        requires_code=gen.requires_code,
        flags=list(flags or []),
        state="planned",
        planned_for=planned_for,
        expires_at=expires_at,
        exam_id=exam_id,
        meta={"template_id": gen.template_id, "uniqueness": str(gen.uniqueness)},
    )
    session.add(row)
    await session.flush()
    for asset in gen.assets:
        if not asset.deferred:
            await store().put(asset_key(row.id, asset.name), asset.content)
    return row


def _asset_meta(asset: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "name": asset.name,
        "mime": asset.mime,
        "kind": asset.kind,
        "size": asset.size,
        "sha256": asset.sha256,
        "inline": asset.inline,
        "deferred": asset.deferred,
    }
    if asset.inline and asset.size <= INLINE_LIMIT:
        meta["content"] = asset.content.decode("utf-8")
    return meta


def asset_key(instance_id: int, name: str) -> str:
    return f"instances/{instance_id}/{name}"


async def read_asset(row: Instance, name: str) -> bytes:
    meta = next((a for a in row.assets if a["name"] == name), None)
    if meta is None:
        raise not_found("файл задания")
    key = asset_key(row.id, name)
    data = await store().get(key)
    if data is not None:
        return data
    if meta.get("deferred"):
        # File B of task 27: the worker materialises it; do it inline as a fallback.
        from app.services.bigfiles import build_deferred

        data = await build_deferred(row, name)
    else:
        gen = await generate(row.task_no, row.seed, row.difficulty, row.subtype_id)
        match = next((a for a in gen.assets if a.name == name), None)
        if match is None:
            raise not_found("файл задания")
        data = match.content
    await store().put(key, data)
    return data


def public(row: Instance) -> dict[str, Any]:
    """Client projection. No answer, no hidden seed, no solution, no reference code."""
    return {
        "id": row.id,
        "task_no": row.task_no,
        "subtype": row.subtype_id,
        "difficulty": row.difficulty,
        "context": row.context,
        "slot": row.slot,
        "mandatory": row.mandatory,
        "statement_md": row.statement_md,
        "assets": [
            {k: v for k, v in a.items() if k != "sha256" or not a.get("deferred")}
            for a in row.assets
        ],
        "answer_kind": row.answer_kind,
        "checker_options": row.checker_options,
        "method_card_id": row.method_card_id,
        "target_seconds": row.target_seconds,
        "requires_code": row.requires_code,
        "flags": row.flags,
        "state": row.state,
        "attempts_count": row.attempts_count,
        "hints_used": row.hints_used,
        "revealed": row.revealed,
        "expires_at": row.expires_at,
        "draft": row.draft,
        "exam_id": row.exam_id,
    }


async def owned(session: AsyncSession, instance_id: int, user_id: int) -> Instance:
    row = await session.get(Instance, instance_id)
    if row is None or row.user_id != user_id or row.void:
        raise not_found("задание")
    return row


def encode_files(files: dict[str, bytes]) -> dict[str, str]:
    return {name: base64.b64encode(data).decode() for name, data in files.items()}
