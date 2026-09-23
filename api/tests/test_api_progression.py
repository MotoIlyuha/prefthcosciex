"""Floors, extern, boss, shop, exams, onboarding and placement (3.3, 5.3, 5.5, 6.5, 8, 11.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Exam, ExamAnswer, Instance, Streak, UserFloor, UserSettings, Wallet
from app.services.answers import verify_code
from app.services.instances import create
from tests.conftest import login


async def _uid(client: httpx.AsyncClient, headers: dict[str, str]) -> int:
    return int((await client.get("/me", headers=headers)).json()["id"])


async def _fund(db: AsyncSession, uid: int, coins: int) -> None:
    wallet = await db.get(Wallet, uid)
    assert wallet is not None
    wallet.balance = coins
    await db.commit()


async def _answer_instance(
    client: httpx.AsyncClient,
    db: AsyncSession,
    headers: dict[str, str],
    instance_id: int,
    correct: bool = True,
) -> dict[str, object]:
    db.expire_all()
    row = await db.get(Instance, instance_id)
    assert row is not None
    answer = row.answer if correct else "0 0" if row.answer_kind == "two_ints" else "999999999"
    if not correct and answer == row.answer:
        answer = "1"
    resp = await client.post(
        f"/instances/{instance_id}/answer",
        headers=headers,
        json={
            "answer": answer,
            "time_spent_s": 600,
            "code": row.reference_code if correct else None,
        },
    )
    assert resp.status_code == 200, resp.text
    body: dict[str, object] = resp.json()
    return body


async def test_path_and_unlocking_a_floor_with_coins(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    headers = await login(client, 3001)
    uid = await _uid(client, headers)
    path = (await client.get("/path", headers=headers)).json()
    assert [f["number"] for f in path["floors"]] == list(range(1, 14))
    assert path["floors"][0]["state"] == "unlocked"
    assert path["floors"][1]["price"] == 200
    assert path["floors"][11]["price"] == 450
    poor = await client.post("/path/2/unlock", headers=headers)
    assert poor.status_code == 402
    skip = await client.post("/path/3/unlock", headers=headers)
    assert skip.status_code == 409
    await _fund(db, uid, 250)
    ok = await client.post("/path/2/unlock", headers=headers | {"Idempotency-Key": "f2"})
    assert ok.status_code == 200
    replay = await client.post("/path/2/unlock", headers=headers | {"Idempotency-Key": "f2"})
    assert replay.json() == ok.json()
    db.expire_all()
    wallet = await db.get(Wallet, uid)
    assert wallet is not None and wallet.balance == 50
    assert (await client.post("/path/2/unlock", headers=headers)).status_code == 409


async def test_extern_three_of_three_opens_the_floor(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    headers = await login(client, 3002)
    uid = await _uid(client, headers)
    resp = await client.post("/path/5/extern", headers=headers)
    assert resp.status_code == 200, resp.text
    trial = resp.json()
    assert len(trial["instances"]) == 3
    assert all(i["difficulty"] == 4 for i in trial["instances"])
    last: dict[str, object] = {}
    for inst in trial["instances"]:
        last = await _answer_instance(client, db, headers, inst["id"])
        assert last["coins"] == 0  # a level test pays nothing
    assert last["context_result"] == {
        "trial_id": trial["trial_id"],
        "kind": "extern",
        "correct": 3,
        "total": 3,
        "finished": True,
        "passed": True,
    }
    floor = await db.get(UserFloor, (uid, 5))
    assert floor is not None and floor.unlocked_by == "extern"
    again = await client.post("/path/6/extern", headers=headers)
    assert again.status_code == 429  # one extern a day


async def test_failed_extern_keeps_the_floor_closed(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    headers = await login(client, 3003)
    uid = await _uid(client, headers)
    trial = (await client.post("/path/4/extern", headers=headers)).json()
    await _answer_instance(client, db, headers, trial["instances"][0]["id"], correct=False)
    for inst in trial["instances"][1:]:
        await _answer_instance(client, db, headers, inst["id"])
    assert await db.get(UserFloor, (uid, 4)) is None


async def test_boss_marks_the_floor(client: httpx.AsyncClient, db: AsyncSession) -> None:
    headers = await login(client, 3004)
    uid = await _uid(client, headers)
    locked = await client.post("/path/2/boss", headers=headers)
    assert locked.status_code == 403
    trial = (await client.post("/path/1/boss", headers=headers)).json()
    for inst in trial["instances"]:
        await _answer_instance(client, db, headers, inst["id"])
    db.expire_all()
    floor = await db.get(UserFloor, (uid, 1))
    assert floor is not None and floor.state == "boss_passed"


async def test_shop_freeze_ticket_cosmetic(client: httpx.AsyncClient, db: AsyncSession) -> None:
    headers = await login(client, 3005)
    uid = await _uid(client, headers)
    await _fund(db, uid, 1000)
    shop = (await client.get("/shop", headers=headers)).json()
    assert shop["freeze"]["price"] == 50
    for _ in range(2):
        assert (
            await client.post("/shop/buy", headers=headers, json={"item": "freeze"})
        ).status_code == 200
    third = await client.post("/shop/buy", headers=headers, json={"item": "freeze"})
    assert third.status_code == 409
    ticket = await client.post("/shop/buy", headers=headers, json={"item": "exam_ticket"})
    assert ticket.json()["tickets"] == 1
    cosmetic = await client.post(
        "/shop/buy", headers=headers, json={"item": "cosmetic:frame_bronze"}
    )
    assert cosmetic.json()["price"] == 100
    twice = await client.post("/shop/buy", headers=headers, json={"item": "cosmetic:frame_bronze"})
    assert twice.status_code == 409
    assert cosmetic.json()["balance"] == 1000 - 100 - 150 - 100
    unknown = await client.post("/shop/buy", headers=headers, json={"item": "floor-99"})
    assert unknown.status_code == 422


async def test_streak_restore_within_48_hours(client: httpx.AsyncClient, db: AsyncSession) -> None:
    headers = await login(client, 3006)
    uid = await _uid(client, headers)
    await _fund(db, uid, 200)
    streak = await db.get(Streak, uid)
    assert streak is not None
    today = datetime.now(UTC).date()
    streak.current, streak.best = 0, 12
    streak.lost_on, streak.lost_value = today - timedelta(days=1), 12
    streak.accounted_until = today - timedelta(days=1)
    await db.commit()
    shop = (await client.get("/shop", headers=headers)).json()
    assert shop["restore"]["price"] == 80
    resp = await client.post("/shop/buy", headers=headers, json={"item": "restore"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["streak"] == 12


async def test_half_exam_is_scored_and_opens_free_reveals(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    headers = await login(client, 3007)
    uid = await _uid(client, headers)
    poor = await client.post("/exams", headers=headers, json={"kind": "half"})
    assert poor.status_code == 402
    await _fund(db, uid, 100)
    exam = (await client.post("/exams", headers=headers, json={"kind": "half"})).json()
    assert len(exam["sheet"]) == 15
    assert exam["seconds_left"] > 59 * 60
    busy = await client.post("/exams", headers=headers, json={"kind": "block", "task_no": 5})
    assert busy.status_code == 409
    first = exam["sheet"][0]
    # No hints and no reveals during the exam; the instance never reveals the answer.
    assert (
        await client.post(f"/instances/{first['instance']['id']}/hint", headers=headers)
    ).status_code == 403
    rows = {
        r.id: r for r in await db.scalars(select(Instance).where(Instance.exam_id == exam["id"]))
    }
    for item in exam["sheet"][:10]:
        row = rows[item["instance"]["id"]]
        resp = await client.post(
            f"/exams/{exam['id']}/answers",
            headers=headers,
            json={"position": item["position"], "answer": row.answer, "time_spent_s": 120},
        )
        assert resp.status_code == 200
    direct = await client.post(
        f"/instances/{first['instance']['id']}/answer",
        headers=headers,
        json={"answer": "1", "time_spent_s": 5},
    )
    assert direct.status_code == 409
    result = (await client.post(f"/exams/{exam['id']}/finish", headers=headers)).json()
    assert result["primary"] == 10
    assert result["test"] == 0  # a half variant has no test-score scale
    view = (await client.get(f"/exams/{exam['id']}", headers=headers)).json()
    assert view["finished"] is True
    assert sum(1 for s in view["sheet"] if s["correct"]) == 10
    reveal = await client.post(
        f"/instances/{exam['sheet'][14]['instance']['id']}/reveal", headers=headers
    )
    assert reveal.status_code == 200 and reveal.json()["free"] is True
    wallet = await db.get(Wallet, uid)
    assert wallet is not None and wallet.balance == 40


async def test_first_full_exam_of_the_month_is_free_and_27_scores_per_number(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    headers = await login(client, 3008)
    exam = (await client.post("/exams", headers=headers, json={"kind": "full"})).json()
    assert len(exam["sheet"]) == 27
    row = await db.get(Exam, exam["id"])
    assert row is not None and row.paid_with == "free"
    inst = await db.get(Instance, exam["sheet"][26]["instance"]["id"])
    assert inst is not None and inst.task_no == 27
    first_number = inst.answer.split()[0]
    await client.post(
        f"/exams/{exam['id']}/answers",
        headers=headers,
        json={"position": 27, "answer": f"{first_number} 0"},
    )
    result = (await client.post(f"/exams/{exam['id']}/finish", headers=headers)).json()
    assert result["per_position"][26]["points"] == 1  # one of two numbers right
    assert result["primary"] == 1
    assert result["test"] > 0
    answer = await db.get(ExamAnswer, (exam["id"], 27))
    assert answer is not None and answer.is_correct is False
    second = await client.post("/exams", headers=headers, json={"kind": "full"})
    assert second.status_code == 402  # the free one is used, no coins, no ticket


async def test_training_exam_pauses_and_costs_nothing(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    headers = await login(client, 3009)
    exam = (
        await client.post(
            "/exams", headers=headers, json={"kind": "block", "task_no": 8, "training": True}
        )
    ).json()
    assert len(exam["sheet"]) == 5
    assert {s["task_no"] for s in exam["sheet"]} == {8}
    paused = (await client.post(f"/exams/{exam['id']}/pause", headers=headers)).json()
    assert paused["paused"] is True
    blocked = await client.post(
        f"/exams/{exam['id']}/answers", headers=headers, json={"position": 1, "answer": "1"}
    )
    assert blocked.status_code == 409
    resumed = (await client.post(f"/exams/{exam['id']}/resume", headers=headers)).json()
    assert resumed["paused"] is False
    result = (await client.post(f"/exams/{exam['id']}/finish", headers=headers)).json()
    assert result["primary"] == 0


async def test_onboarding_first_win_pays_twelve(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    headers = await login(client, 3010)
    uid = await _uid(client, headers)
    steps = [
        {"step": 1, "privacy_consent": True},
        {"step": 2, "band": "unknown"},
        {"step": 3, "python_level": "none"},
        {
            "step": 4,
            "tz": "Asia/Yekaterinburg",
            "daily_time": "17:30",
            "notifications_consent": True,
        },
    ]
    for body in steps:
        resp = await client.patch("/me/onboarding", headers=headers, json=body)
        assert resp.status_code == 200, resp.text
    bad_tz = await client.patch("/me/onboarding", headers=headers, json={"tz": "Mars/Base"})
    assert bad_tz.status_code == 422
    task = (await client.post("/onboarding/first-task", headers=headers)).json()
    assert task["task_no"] in (1, 4) and task["difficulty"] == 1
    row = await db.get(Instance, task["id"])
    assert row is not None
    result = (
        await client.post(
            f"/instances/{task['id']}/answer",
            headers=headers,
            json={"answer": row.answer, "time_spent_s": 3},
        )
    ).json()
    assert result["status"] == "correct"  # no method check during onboarding
    assert result["coins"] >= 12
    done = await client.patch("/me/onboarding", headers=headers, json={"step": 5, "done": True})
    assert done.json()["done"] is True
    me = (await client.get("/me", headers=headers)).json()
    assert me["tz"] == "Asia/Yekaterinburg"
    assert me["settings"]["band_pending"] is True
    assert me["settings"]["python_level"] == "none"
    settings = await db.get(UserSettings, uid)
    assert settings is not None and settings.consent_at is not None


async def test_onboarding_requires_consent(client: httpx.AsyncClient) -> None:
    headers = await login(client, 3011)
    resp = await client.patch("/me/onboarding", headers=headers, json={"done": True})
    assert resp.status_code == 409


async def test_placement_eight_steps_open_floors(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    headers = await login(client, 3012)
    uid = await _uid(client, headers)
    inst = (await client.post("/placement/start", headers=headers)).json()
    assert inst["task_no"] == 8 and inst["difficulty"] == 3
    result: dict[str, object] = {}
    for _ in range(8):
        result = await _answer_instance(client, db, headers, inst["id"])
        placement = result["context_result"]["placement"]  # type: ignore[index]
        if placement.get("finished"):
            break
        inst = {"id": placement["next_instance_id"]}
    final = result["context_result"]["placement"]  # type: ignore[index]
    assert final["finished"] is True and final["correct"] == 8
    assert len(final["floors"]) > 5
    assert final["challenge"] is True
    opened = list(await db.scalars(select(UserFloor.floor_id).where(UserFloor.user_id == uid)))
    assert set(final["floors"]) <= set(opened)
    again = await client.post("/placement/start", headers=headers)
    assert again.status_code == 409


async def test_vacation_and_easy_day(client: httpx.AsyncClient) -> None:
    headers = await login(client, 3013)
    today = datetime.now(UTC).date()
    same_day = await client.post(
        "/me/vacation", headers=headers, json={"days": [today.isoformat()]}
    )
    assert same_day.status_code == 409
    base = today + timedelta(days=2)
    if base.month != (base + timedelta(days=2)).month:
        base = base + timedelta(days=5)
    ok = await client.post(
        "/me/vacation",
        headers=headers,
        json={"days": [(base + timedelta(days=i)).isoformat() for i in range(3)]},
    )
    assert ok.status_code == 200, ok.text
    easy = await client.post("/me/easy-day", headers=headers, json={})
    assert easy.status_code == 200
    today_view = (await client.get("/today", headers=headers)).json()
    assert today_view["progress"]["threshold"] == 10


async def test_progress_and_confidence(client: httpx.AsyncClient, db: AsyncSession) -> None:
    headers = await login(client, 3014)
    uid = await _uid(client, headers)
    row = await create(
        db, user_id=uid, task_no=7, subtype=None, difficulty=3, seed=3, context="practice"
    )
    await db.commit()
    await client.post(
        f"/instances/{row.id}/answer",
        headers=headers,
        json={"answer": row.answer, "time_spent_s": 200},
    )
    progress = (await client.get("/progress?range=7d", headers=headers)).json()
    assert len(progress["days"]) == 7 and progress["days"][-1]["today"] is True
    assert progress["totals"]["solved"] == 1
    conf = (await client.get("/confidence", headers=headers)).json()
    assert len(conf["tasks"]) == 27
    assert conf["tasks"][6]["attempts"] == 1 and conf["tasks"][6]["value"] > 0
    assert conf["forecast"]["margin"] == 2
    detail = (await client.get("/confidence/7", headers=headers)).json()
    assert detail["subtypes"] and detail["method_card_id"].startswith("t07:")
    theory = (await client.get("/theory/7", headers=headers)).json()
    assert theory["cards"]
    assert (await client.get("/progress?range=5y", headers=headers)).status_code == 422


async def test_every_code_task_reference_passes_its_own_recheck(db: AsyncSession) -> None:
    """The anti-cheat must never reject an honest program (7.5.2)."""
    from app.core.initdata import TelegramUser
    from app.services.users import ensure_user

    user, _ = await ensure_user(db, TelegramUser(3999, "Проверка", None, "ru"))
    await db.commit()
    for task_no in (16, 17, 23, 24, 25, 26, 27):
        for seed in (1, 2):
            row = await create(
                db,
                user_id=user.id,
                task_no=task_no,
                subtype=None,
                difficulty=3,
                seed=seed,
                context="practice",
            )
            assert row.reference_code, task_no
            status = await verify_code(row, row.reference_code, build_deferred=True)
            assert status == "ok", (task_no, seed, row.subtype_id)
            cheat = await verify_code(row, f"print({row.answer!r})", build_deferred=True)
            assert cheat != "ok", (task_no, seed, row.subtype_id)


async def test_trial_view_and_public_config(client: httpx.AsyncClient) -> None:
    headers = await login(client, 3020)
    trial = (await client.post("/path/3/extern", headers=headers)).json()
    view = (await client.get(f"/path/trials/{trial['trial_id']}", headers=headers)).json()
    assert [i["id"] for i in view["instances"]] == [i["id"] for i in trial["instances"]]
    assert view["finished"] is False
    other = await login(client, 3021)
    assert (await client.get(f"/path/trials/{trial['trial_id']}", headers=other)).status_code == 404
    config = (await client.get("/config/public")).json()
    assert config == {"bot_username": "bayt_test_bot", "bot_id": 123456,
                      "fipi_banner": config["fipi_banner"]}
    assert config["fipi_banner"]
