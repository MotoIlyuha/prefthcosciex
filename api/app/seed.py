"""Reference data: task types, subtypes, floors and method cards.

Idempotent — safe to run on every deploy (``python -m app.seed``).
"""

from __future__ import annotations

import asyncio

from egegen.core.cards import all_cards
from egegen.core.registry import list_generators
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.loader import curriculum, economy, floors
from app.db.models import Floor, GeneratorVersion, Subtype, TaskType, TheoryCard
from app.db.session import dispose, session_factory


async def seed(session: AsyncSession) -> None:
    cur = curriculum()
    for no, info in cur.tasks.items():
        await session.execute(
            insert(TaskType)
            .values(
                no=no,
                title=info.title,
                level=info.level,
                points=info.points,
                target_seconds=info.minutes * 60,
                requires_software=info.software,
            )
            .on_conflict_do_update(
                index_elements=[TaskType.no],
                set_={
                    "title": info.title,
                    "level": info.level,
                    "points": info.points,
                    "target_seconds": info.minutes * 60,
                },
            )
        )
    for gen in list_generators():
        for sid, spec in gen.templates.subtypes.items():
            values = {
                "id": sid,
                "task_no": gen.task_no,
                "code": sid,
                "title": spec.title,
                "default_difficulty": 3,
                "target_seconds": spec.target_seconds,
                "requires_code": gen.requires_code,
            }
            await session.execute(
                insert(Subtype)
                .values(**values, beta=False)
                .on_conflict_do_update(
                    index_elements=[Subtype.id],
                    set_={k: v for k, v in values.items() if k != "id"},
                )
            )
        await session.execute(
            insert(GeneratorVersion)
            .values(task_no=gen.task_no, version=gen.version, changelog="initial release")
            .on_conflict_do_nothing(index_elements=["task_no", "version"])
        )
    prices = economy().prices
    cfg = floors()
    for floor in cfg.floors:
        values = {
            "order_no": floor.number,
            "title": floor.title,
            "task_nos": floor.tasks,
            "unlock_cost": prices.floor(floor.number),
            "season_id": cfg.season_id,
        }
        await session.execute(
            insert(Floor)
            .values(id=floor.number, **values)
            .on_conflict_do_update(index_elements=[Floor.id], set_=values)
        )
    for card in all_cards():
        await session.execute(
            insert(TheoryCard)
            .values(
                id=card.id,
                task_no=card.task_no,
                subtype_id=card.subtype,
                body_md=card.body_md,
                code_templates=[],
            )
            .on_conflict_do_update(index_elements=[TheoryCard.id], set_={"body_md": card.body_md})
        )
    await session.commit()


async def main() -> None:
    async with session_factory()() as session:
        await seed(session)
    await dispose()
    print("seed: ok")


if __name__ == "__main__":
    asyncio.run(main())
