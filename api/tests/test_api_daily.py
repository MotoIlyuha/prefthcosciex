"""«Сегодня» and the answer flow: rewards, attempts, idempotency, anti-cheat (4–7)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from egegen.core.registry import get_generator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Attempt, DailyStats, Instance, Streak, Transaction, Wallet
from app.services.instances import create
from tests.conftest import JobRecorder, login

SECRET_FIELDS = {"answer", "hidden_seed", "answer_hash", "solution_steps", "reference_code"}


def _walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            keys.add(k)
            keys |= _walk_keys(v)
    elif isinstance(value, list):
        for v in value:
            keys |= _walk_keys(v)
    return keys


async def _instance(db: AsyncSession, instance_id: int) -> Instance:
    db.expire_all()
    row = await db.get(Instance, instance_id)
    assert row is not None
    return row


async def _answer(
    client: httpx.AsyncClient, headers: dict[str, str], instance_id: int, answer: str, **extra: Any
) -> httpx.Response:
    body = {"answer": answer, "time_spent_s": extra.pop("time_spent_s", 200), **extra}
    return await client.post(f"/instances/{instance_id}/answer", json=body, headers=headers)


async def _user_id(client: httpx.AsyncClient, headers: dict[str, str]) -> int:
    return int((await client.get("/me", headers=headers)).json()["id"])


async def test_today_builds_a_plan_that_follows_the_rules(client: httpx.AsyncClient) -> None:
    headers = await login(client, 2001)
    resp = await client.get("/today", headers=headers)
    assert resp.status_code == 200
    today = resp.json()
    mandatory = [i for i in today["items"] if i["mandatory"]]
    assert len(mandatory) >= 3
    assert sum(i["target_seconds"] for i in mandatory) <= 20 * 60
    assert sum(i["reward"] for i in mandatory) >= 40
    assert today["progress"]["threshold"] == 30
    assert today["progress"]["cap"] == 120
    # A second call returns the same plan instead of generating another.
    again = (await client.get("/today", headers=headers)).json()
    assert [i["instance_id"] for i in again["items"]] == [i["instance_id"] for i in today["items"]]
    assert not SECRET_FIELDS & _walk_keys(today)


async def test_instance_never_leaks_the_answer(client: httpx.AsyncClient) -> None:
    headers = await login(client, 2002)
    item = (await client.get("/today", headers=headers)).json()["items"][0]
    resp = await client.get(f"/instances/{item['instance_id']}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "issued"
    assert not SECRET_FIELDS & _walk_keys(body)
    other = await login(client, 2003, "Боря")
    stolen = await client.get(f"/instances/{item['instance_id']}", headers=other)
    assert stolen.status_code == 404


async def test_correct_first_attempt_pays_once_even_when_replayed(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    headers = await login(client, 2004)
    uid = await _user_id(client, headers)
    row = await create(
        db, user_id=uid, task_no=1, subtype=None, difficulty=1, seed=11, context="practice"
    )
    await db.commit()
    key = {"Idempotency-Key": "answer-1"}
    first = await _answer(client, headers | key, row.id, row.answer, time_spent_s=40)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["status"] == "correct"
    assert body["coins"] == 12 + 2  # 8 × 1.5, plus the speed bonus
    replay = await _answer(client, headers | key, row.id, row.answer, time_spent_s=40)
    assert replay.json() == body
    closed = await _answer(client, headers, row.id, row.answer)
    assert closed.status_code == 409
    wallet = await db.get(Wallet, uid)
    assert wallet is not None and wallet.balance == 14
    txs = list(await db.scalars(select(Transaction).where(Transaction.user_id == uid)))
    assert len(txs) == 1 and txs[0].reason == "task_reward"


async def test_three_wrong_answers_close_the_task(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    headers = await login(client, 2005)
    uid = await _user_id(client, headers)
    row = await create(
        db, user_id=uid, task_no=8, subtype=None, difficulty=3, seed=5, context="practice"
    )
    await db.commit()
    wrong = str(int(row.answer) + 1)
    first = (await _answer(client, headers, row.id, wrong)).json()
    assert first["status"] == "wrong" and first["attempts_left"] == 2
    assert first["ask_reason"] is True
    await _answer(client, headers, row.id, wrong)
    third = (await _answer(client, headers, row.id, wrong)).json()
    assert third["attempts_left"] == 0
    assert third["verdict_text"] == "Задача закрыта с ошибкой"
    assert (await _instance(db, row.id)).state == "failed"
    # A closed task: the answer is no longer accepted, the reveal of the day is free.
    reveal = await client.post(f"/instances/{row.id}/reveal", headers=headers)
    assert reveal.status_code == 200
    assert reveal.json()["free"] is True
    assert reveal.json()["solution"]["answer"] == row.answer


async def test_format_error_is_not_an_attempt(client: httpx.AsyncClient, db: AsyncSession) -> None:
    headers = await login(client, 2006)
    uid = await _user_id(client, headers)
    row = await create(
        db, user_id=uid, task_no=8, subtype=None, difficulty=2, seed=6, context="practice"
    )
    await db.commit()
    resp = (await _answer(client, headers, row.id, "двенадцать")).json()
    assert resp["status"] == "format_error" and resp["counted"] is False
    assert (await _instance(db, row.id)).attempts_count == 0


async def test_second_attempt_pays_the_base_rate(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    headers = await login(client, 2007)
    uid = await _user_id(client, headers)
    row = await create(
        db, user_id=uid, task_no=11, subtype=None, difficulty=3, seed=7, context="practice"
    )
    await db.commit()
    await _answer(client, headers, row.id, str(int(row.answer) + 1), time_spent_s=900)
    second = (await _answer(client, headers, row.id, row.answer, time_spent_s=900)).json()
    assert second["status"] == "correct"
    assert second["coins"] == 15  # П, difficulty 3, second attempt ×1.0, no speed bonus


async def test_hints_cost_coins_and_reduce_the_reward(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    headers = await login(client, 2008)
    uid = await _user_id(client, headers)
    row = await create(
        db, user_id=uid, task_no=5, subtype=None, difficulty=3, seed=8, context="practice"
    )
    await db.commit()
    broke = await client.post(f"/instances/{row.id}/hint", headers=headers)
    assert broke.status_code == 402
    wallet = await db.get(Wallet, uid)
    assert wallet is not None
    wallet.balance = 20
    await db.commit()
    hint = await client.post(f"/instances/{row.id}/hint", headers=headers)
    assert hint.status_code == 200 and hint.json()["price"] == 5
    result = (await _answer(client, headers, row.id, row.answer, time_spent_s=900)).json()
    assert result["coins"] == 11  # ceil(10 × 1.5 × 0.7)


async def test_too_fast_answer_asks_for_the_method(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    headers = await login(client, 2009)
    uid = await _user_id(client, headers)
    row = await create(
        db, user_id=uid, task_no=15, subtype=None, difficulty=3, seed=9, context="practice"
    )
    await db.commit()
    ask = (await _answer(client, headers, row.id, row.answer, time_spent_s=5)).json()
    assert ask["status"] == "method_check" and ask["counted"] is False
    options = ask["options"]
    wrong_method = (
        await _answer(client, headers, row.id, row.answer, time_spent_s=5, method_choice=options[1])
    ).json()
    assert wrong_method["status"] == "correct"
    assert "method_note" in wrong_method
    assert wrong_method["coins"] == 23  # 15 × 1.5, no speed bonus


@pytest.mark.parametrize("task_no", [17, 24, 26, 27])
async def test_correct_answer_without_code_is_not_verified(
    task_no: int, client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """7.5.2: on 16, 17, 23–27 a bare answer is «верный, метод не подтверждён»: half pay."""
    headers = await login(client, 2100 + task_no)
    uid = await _user_id(client, headers)
    row = await create(
        db,
        user_id=uid,
        task_no=task_no,
        subtype=None,
        difficulty=3,
        seed=40 + task_no,
        context="practice",
    )
    await db.commit()
    resp = (await _answer(client, headers, row.id, row.answer, time_spent_s=3000)).json()
    assert resp["status"] == "correct"
    assert resp["verify_status"] == "no_code"
    assert resp["verdict_text"] == "Ответ верный, метод не подтверждён"
    from app.logic.rewards import RewardInput, reward

    full = reward(RewardInput(task_no, 3, 1, code_verified=True))
    assert resp["coins"] == reward(RewardInput(task_no, 3, 1, code_verified=False))
    assert resp["coins"] < full
    attempt = await db.scalar(select(Attempt).where(Attempt.instance_id == row.id))
    assert attempt is not None and attempt.verify_status == "no_code"


async def test_reference_code_passes_the_hidden_variant(
    client: httpx.AsyncClient, db: AsyncSession, jobs_recorder: JobRecorder
) -> None:
    headers = await login(client, 2201)
    uid = await _user_id(client, headers)
    row = await create(
        db, user_id=uid, task_no=17, subtype=None, difficulty=3, seed=77, context="practice"
    )
    await db.commit()
    assert row.reference_code
    resp = (
        await _answer(
            client, headers, row.id, row.answer, time_spent_s=3000, code=row.reference_code
        )
    ).json()
    assert resp["verify_status"] == "ok", resp
    assert resp["verdict_text"] == "Решено надёжно"
    assert not jobs_recorder.calls


async def test_hardcoded_answer_fails_the_hidden_variant(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    headers = await login(client, 2202)
    uid = await _user_id(client, headers)
    row = await create(
        db, user_id=uid, task_no=24, subtype=None, difficulty=3, seed=78, context="practice"
    )
    await db.commit()
    cheat = f"print({row.answer!r})"
    resp = (
        await _answer(client, headers, row.id, row.answer, time_spent_s=3000, code=cheat)
    ).json()
    assert resp["verify_status"] == "mismatch"
    assert resp["verdict_text"] == "Ответ верный, метод не подтверждён"


async def test_big_file_of_27_defers_the_check_to_the_worker(
    client: httpx.AsyncClient, db: AsyncSession, jobs_recorder: JobRecorder
) -> None:
    headers = await login(client, 2203)
    uid = await _user_id(client, headers)
    row = await create(
        db, user_id=uid, task_no=27, subtype=None, difficulty=3, seed=79, context="practice"
    )
    await db.commit()
    gen = get_generator(27)
    assert any(a.deferred for a in gen.generate(row.hidden_seed, 3, row.subtype_id).assets)
    resp = (
        await _answer(client, headers, row.id, row.answer, time_spent_s=3000, code="print(1)")
    ).json()
    assert resp["verify_status"] == "pending"
    assert jobs_recorder.calls and jobs_recorder.calls[0][0] == "recheck_code"


async def test_threshold_moves_the_streak_and_the_cap_stops_coins(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    headers = await login(client, 2301)
    uid = await _user_id(client, headers)
    await client.get("/today", headers=headers)
    earned = 0
    threshold_seen = False
    seed = 100
    while earned < 130:
        row = await create(
            db, user_id=uid, task_no=15, subtype=None, difficulty=5, seed=seed, context="practice"
        )
        await db.commit()
        seed += 1
        resp = (await _answer(client, headers, row.id, row.answer, time_spent_s=900)).json()
        earned += resp["coins"] + resp["capped"]
        threshold_seen = threshold_seen or bool(resp.get("threshold_met"))
    assert threshold_seen
    db.expire_all()
    streak = await db.get(Streak, uid)
    assert streak is not None and streak.current == 1
    stats = await db.scalar(select(DailyStats).where(DailyStats.user_id == uid))
    assert stats is not None
    assert stats.coins_earned == 120
    assert stats.coins_capped > 0
    today = (await client.get("/today", headers=headers)).json()
    assert today["free_practice"] is True
    assert today["progress"]["cap_reached"] is True


async def test_feedback_reason_pays_a_small_bonus_once(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    headers = await login(client, 2401)
    uid = await _user_id(client, headers)
    row = await create(
        db, user_id=uid, task_no=6, subtype=None, difficulty=3, seed=12, context="practice"
    )
    await db.commit()
    await _answer(client, headers, row.id, str(int(row.answer) + 1))
    fb = await client.post(
        f"/instances/{row.id}/feedback", headers=headers, json={"reason": "no_method"}
    )
    assert fb.status_code == 200
    assert fb.json()["bonus"] == 2
    assert fb.json()["reaction"]["card_id"].startswith("t06:")
    dup = await client.post(
        f"/instances/{row.id}/feedback", headers=headers, json={"reason": "careless"}
    )
    assert dup.json()["duplicate"] is True
    detail = (await client.get("/confidence/6", headers=headers)).json()
    assert detail["reasons"][0]["code"] == "no_method"


async def test_similar_task_and_draft(client: httpx.AsyncClient, db: AsyncSession) -> None:
    headers = await login(client, 2501)
    uid = await _user_id(client, headers)
    row = await create(
        db, user_id=uid, task_no=4, subtype=None, difficulty=2, seed=13, context="practice"
    )
    await db.commit()
    similar = await client.post("/instances/similar", headers=headers, json={"instance_id": row.id})
    assert similar.status_code == 200, similar.text
    body = similar.json()
    assert body["task_no"] == 4 and body["subtype"] == row.subtype_id
    assert body["id"] != row.id
    closed_floor = await client.post("/instances/similar", headers=headers, json={"task_no": 27})
    assert closed_floor.status_code == 403
    draft = await client.patch(
        f"/instances/{row.id}/draft", headers=headers, json={"answer": "12", "code": "print(1)"}
    )
    assert draft.json()["draft"] == {"answer": "12", "code": "print(1)"}


async def test_asset_download_regenerates_missing_files(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    headers = await login(client, 2601)
    uid = await _user_id(client, headers)
    row = await create(
        db, user_id=uid, task_no=17, subtype=None, difficulty=2, seed=14, context="practice"
    )
    await db.commit()
    name = row.assets[0]["name"]
    resp = await client.get(f"/instances/{row.id}/assets/{name}", headers=headers)
    assert resp.status_code == 200
    assert len(resp.content) == row.assets[0]["size"]


async def test_server_run(client: httpx.AsyncClient, db: AsyncSession) -> None:
    headers = await login(client, 2701)
    uid = await _user_id(client, headers)
    row = await create(
        db, user_id=uid, task_no=17, subtype=None, difficulty=2, seed=15, context="practice"
    )
    await db.commit()
    name = row.assets[0]["name"]
    code = f"print(len(open({name!r}).read().split()))"
    resp = await client.post(f"/instances/{row.id}/run", headers=headers, json={"code": code})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert int(resp.json()["stdout"]) > 0
    assert (await _instance(db, row.id)).code_run_seen is True
