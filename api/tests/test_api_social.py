"""Curators (9), notifications (10), tickets (7.7), privacy (14.3) and the admin panel."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CuratorLink,
    Event,
    Instance,
    Notification,
    Transaction,
    User,
    UserSettings,
    Wallet,
)
from app.services.instances import create
from app.services.notify import render, schedule
from app.services.privacy import purge_due
from tests.conftest import login


async def _uid(client: httpx.AsyncClient, headers: dict[str, str]) -> int:
    return int((await client.get("/me", headers=headers)).json()["id"])


async def _link(
    client: httpx.AsyncClient,
    student: dict[str, str],
    curator: dict[str, str],
    role: str = "parent",
    access: str | None = None,
) -> int:
    invite = (await client.post("/curators/invite", headers=student, json={"role": role})).json()
    assert invite["link"].startswith("https://t.me/bayt_test_bot?start=cur_")
    accepted = await client.post(
        "/curators/accept", headers=curator, json={"token": invite["token"]}
    )
    assert accepted.status_code == 200, accepted.text
    link_id = int(accepted.json()["link_id"])
    assert accepted.json()["status"] == "pending"
    chosen = access or ("progress" if role == "parent" else "full")
    confirm = await client.patch(
        f"/curators/{link_id}/access", headers=student, json={"access": chosen}
    )
    assert confirm.json()["status"] == "active"
    return link_id


async def test_curator_sees_only_what_the_access_level_allows(client: httpx.AsyncClient) -> None:
    student = await login(client, 4001, "Ученик")
    parent = await login(client, 4002, "Мама")
    sid = await _uid(client, student)
    link_id = await _link(client, student, parent, access="fact")
    board = (await client.get("/curator/students", headers=parent)).json()
    assert [s["student_id"] for s in board["students"]] == [sid]
    assert len(board["nudges"]) == 6
    card = (await client.get(f"/curator/students/{sid}", headers=parent)).json()
    assert {"streak", "threshold_today", "rank"} <= set(card)
    assert "confidence" not in card and "attempts" not in card
    await client.patch(f"/curators/{link_id}/access", headers=student, json={"access": "full"})
    full = (await client.get(f"/curator/students/{sid}", headers=parent)).json()
    assert {"confidence", "forecast", "attempts", "reasons", "subtypes"} <= set(full)
    preview = (await client.get(f"/curators/{link_id}/preview", headers=student)).json()
    assert set(preview) == set(full) - {"access", "role", "focus", "league_enabled"}
    stranger = await login(client, 4003, "Чужой")
    assert (await client.get(f"/curator/students/{sid}", headers=stranger)).status_code == 404


async def test_free_text_reasons_never_reach_the_curator(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    student = await login(client, 4011)
    tutor = await login(client, 4012)
    sid = await _uid(client, student)
    await _link(client, student, tutor, role="tutor")
    row = await create(
        db, user_id=sid, task_no=2, subtype=None, difficulty=2, seed=1, context="practice"
    )
    await db.commit()
    await client.post(
        f"/instances/{row.id}/answer", headers=student, json={"answer": "ЯЯЯЯ", "time_spent_s": 100}
    )
    await client.post(
        f"/instances/{row.id}/feedback",
        headers=student,
        json={"reason": "other", "text": "секретная жалоба на учителя"},
    )
    card = (await client.get(f"/curator/students/{sid}", headers=tutor)).text
    assert "секретная" not in card
    assert '"other":1' in card.replace(" ", "")


async def test_invite_limits_and_expiry(client: httpx.AsyncClient, db: AsyncSession) -> None:
    student = await login(client, 4021)
    await _link(client, student, await login(client, 4022))
    await _link(client, student, await login(client, 4023))
    third = await client.post("/curators/invite", headers=student, json={"role": "parent"})
    assert third.status_code == 409
    other = await login(client, 4024)
    invite = (await client.post("/curators/invite", headers=other, json={})).json()
    self_link = await client.post(
        "/curators/accept", headers=other, json={"token": invite["token"]}
    )
    assert self_link.status_code == 409
    from app.db.models import CuratorInvite

    row = await db.get(CuratorInvite, invite["token"])
    assert row is not None
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()
    late = await client.post(
        "/curators/accept", headers=await login(client, 4025), json={"token": invite["token"]}
    )
    assert late.status_code == 410


async def test_nudge_once_a_day_and_focus_for_tutors(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    student = await login(client, 4031)
    parent = await login(client, 4032)
    tutor = await login(client, 4033)
    sid = await _uid(client, student)
    await _link(client, student, parent)
    await _link(client, student, tutor, role="tutor")
    bad = await client.post(
        f"/curator/students/{sid}/nudge", headers=parent, json={"code": "free text is not allowed"}
    )
    assert bad.status_code == 422
    ok = await client.post(
        f"/curator/students/{sid}/nudge", headers=parent, json={"code": "streak"}
    )
    assert ok.status_code == 200
    again = await client.post(
        f"/curator/students/{sid}/nudge", headers=parent, json={"code": "proud"}
    )
    assert again.status_code == 429
    parent_focus = await client.post(
        f"/curator/students/{sid}/focus", headers=parent, json={"task_nos": [15]}
    )
    assert parent_focus.status_code == 403
    focus = await client.post(
        f"/curator/students/{sid}/focus", headers=tutor, json={"task_nos": [15, 23]}
    )
    assert focus.json()["task_nos"] == [15, 23]
    conf = (await client.get("/confidence", headers=student)).json()
    assert conf["focus"] == [15, 23]
    report = await client.get(f"/curator/students/{sid}/report", headers=tutor)
    assert report.status_code == 200 and "<table>" in report.text
    league_parent = await client.patch(
        f"/curator/students/{sid}/link", headers=parent, json={"league_enabled": True}
    )
    assert league_parent.status_code == 403
    await client.patch(
        f"/curator/students/{sid}/link", headers=tutor, json={"league_enabled": True}
    )
    league = (await client.get("/league", headers=student)).json()
    assert league and league[0]["table"][0]["me"] is True


async def test_revoke_tells_the_curator_without_a_reason(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    student = await login(client, 4041)
    curator = await login(client, 4042)
    cid = await _uid(client, curator)
    link_id = await _link(client, student, curator)
    assert (await client.delete(f"/curators/{link_id}", headers=student)).status_code == 204
    link = await db.get(CuratorLink, link_id)
    assert link is not None and link.status == "revoked"
    note = await db.scalar(
        select(Notification).where(Notification.user_id == cid, Notification.kind == "cur_revoked")
    )
    assert note is not None and note.payload == {}
    assert (await client.get("/curator/students", headers=curator)).json()["students"] == []


async def test_at_most_two_notifications_a_day(client: httpx.AsyncClient, db: AsyncSession) -> None:
    headers = await login(client, 4051)
    uid = await _uid(client, headers)
    noon = datetime.now(UTC).replace(hour=9, minute=0, second=0, microsecond=0)
    first = await schedule(db, uid, "floor_unlocked", {"floor": 2, "title": "x"}, now=noon)
    second = await schedule(db, uid, "exam_checked", {"primary": 10}, now=noon)
    third = await schedule(db, uid, "curator_nudge", {"text": "!"}, now=noon)
    assert first is not None and second is not None and third is None
    # A curator's channel has its own budget and does not eat the student's.
    assert (
        await schedule(db, uid, "cur_floor", {"name": "A", "floor": 2, "title": "x"}, now=noon)
        is not None
    )
    settings = await db.get(UserSettings, uid)
    assert settings is not None
    settings.notifications = {**settings.notifications, "weekly_summary": False}
    await db.commit()
    assert await schedule(db, uid, "weekly_summary", {}, now=noon + timedelta(days=1)) is None


async def test_quiet_hours_move_the_message_to_the_morning(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    headers = await login(client, 4061)
    uid = await _uid(client, headers)
    user = await db.get(User, uid)
    assert user is not None
    user.tz = "Asia/Vladivostok"
    await db.commit()
    late = datetime(2026, 10, 5, 14, 30, tzinfo=UTC)  # 00:30 in Vladivostok
    row = await schedule(db, uid, "exam_checked", {"primary": 5}, now=late)
    assert row is not None
    local = row.scheduled_at.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Vladivostok"))
    assert local.hour == 8
    assert render("exam_checked", {"primary": 21, "test": 80}) == (
        "Экзамен проверен: 21 первичных (80 тестовых)."
    )


async def test_confirmed_ticket_refunds_and_compensates(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    admin = await login(client, 4070, "Админ")  # the first account is the admin
    headers = await login(client, 4071)
    uid = await _uid(client, headers)
    wallet = await db.get(Wallet, uid)
    assert wallet is not None
    wallet.balance = 30
    await db.commit()
    row = await create(
        db, user_id=uid, task_no=12, subtype=None, difficulty=3, seed=2, context="practice"
    )
    await db.commit()
    row_id = row.id
    await client.post(f"/instances/{row_id}/hint", headers=headers)
    short = await client.post(
        "/reports/issue", headers=headers, json={"instance_id": row.id, "text": "ой"}
    )
    assert short.status_code == 422
    ticket = await client.post(
        "/reports/issue",
        headers=headers,
        json={"instance_id": row.id, "text": "В условии нет числа"},
    )
    assert ticket.status_code == 200
    dup = await client.post(
        "/reports/issue",
        headers=headers,
        json={"instance_id": row.id, "text": "В условии нет числа"},
    )
    assert dup.status_code == 409
    assert (await client.get("/admin/issues", headers=headers)).status_code == 403
    queue = (await client.get("/admin/issues", headers=admin)).json()
    assert queue[0]["seed"] == 2 and queue[0]["expected"] == row.answer
    resolved = await client.post(
        f"/admin/issues/{ticket.json()['id']}/resolve",
        headers=admin,
        json={"confirmed": True, "resolution": "Исправлено"},
    )
    assert resolved.json()["refund"] == 8 + 20  # the hint back plus the compensation
    db.expire_all()
    wallet = await db.get(Wallet, uid)
    assert wallet is not None and wallet.balance == 30 - 8 + 28
    inst = await db.get(Instance, row_id)
    assert inst is not None and inst.void is True
    assert (await client.get(f"/instances/{row_id}", headers=headers)).status_code == 404
    regressions = (await client.get("/admin/issues/regressions", headers=admin)).json()
    assert regressions[0]["task_no"] == 12 and regressions[0]["seed"] == 2


async def test_export_and_deletion(client: httpx.AsyncClient, db: AsyncSession) -> None:
    headers = await login(client, 4081)
    uid = await _uid(client, headers)
    await client.get("/today", headers=headers)
    export = (await client.get("/me/export", headers=headers)).json()
    assert export["user"]["id"] == uid
    assert export["instances"]
    assert all("hidden_seed" not in i and "reference_code" not in i for i in export["instances"])
    assert all("answer" not in i for i in export["instances"] if i["state"] == "planned")
    deleted = await client.delete("/me", headers=headers)
    assert deleted.status_code == 200
    assert (await client.get("/me", headers=headers)).status_code == 401
    user = await db.get(User, uid)
    assert user is not None
    user.delete_requested_at = datetime.now(UTC) - timedelta(days=8)
    await db.commit()
    assert await purge_due(db) == 1
    db.expire_all()
    assert await db.get(User, uid) is None
    left = await db.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.user_id == uid)
    )
    assert left == 0
    events = await db.scalar(select(func.count()).select_from(Event).where(Event.user_id == uid))
    assert events == 0


async def test_signing_in_cancels_a_pending_deletion(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    headers = await login(client, 4082)
    await client.delete("/me", headers=headers)
    headers = await login(client, 4082)
    me = (await client.get("/me", headers=headers)).json()
    assert me["delete_requested_at"] is None


async def test_admin_dashboards_and_config(client: httpx.AsyncClient, db: AsyncSession) -> None:
    admin = await login(client, 4090, "Админ")
    student = await login(client, 4091)
    assert (await client.get("/admin/economy", headers=student)).status_code == 403
    health = (await client.get("/admin/economy", headers=admin)).json()
    assert health["season_id"] == "2026-2027"
    funnel = (await client.get("/admin/funnel", headers=admin)).json()
    assert funnel["signed_up"] == 2
    assert (await client.get("/admin/generators", headers=admin)).status_code == 200
    assert (await client.get("/admin/anomalies", headers=admin)).status_code == 200
    no_season = await client.put(
        "/admin/config/economy", headers=admin, json={"patch": {"prices": {"freeze": 40}}}
    )
    assert no_season.status_code == 422
    broken = await client.put(
        "/admin/config/economy",
        headers=admin,
        json={"patch": {"season_id": "2027-2028", "day": {"threshold": 500}}},
    )
    assert broken.status_code == 422  # threshold above the cap fails validation
    ok = await client.put(
        "/admin/config/economy",
        headers=admin,
        json={"patch": {"season_id": "2027-2028", "prices": {"freeze": 40}}},
    )
    assert ok.status_code == 200
    assert (await client.get("/shop", headers=student)).json()["freeze"]["price"] == 40
    fipi = await client.put(
        "/admin/config/fipi",
        headers=admin,
        json={"patch": {"t10": {"answer_transform": "address_no_dots"}}},
    )
    assert fipi.status_code == 200
    assert fipi.json()["fipi"]["t10"]["answer_transform"] == "address_no_dots"
    reset = await client.put("/admin/config/economy", headers=admin, json={"patch": None})
    assert reset.json()["economy"]["prices"]["freeze"] == 50
    audit = (await client.get("/admin/audit", headers=admin)).json()
    assert [a["action"] for a in audit][:3] == ["config_set", "config_set", "config_set"]
    found = (await client.get("/admin/users?q=4091", headers=admin)).json()
    assert found[0]["tg_id"] == 4091
    granted = await client.post(
        f"/admin/users/{found[0]['id']}/coins",
        headers=admin,
        json={"delta": 100, "reason": "компенсация сбоя"},
    )
    assert granted.json()["balance"] == 100
    sent = await client.post(
        "/admin/broadcast/demo",
        headers=admin,
        json={"summary": "В задании 10 ответ — сумма октетов"},
    )
    assert sent.json()["scheduled"] == 2


async def test_admin_smoke_runs_every_generator(client: httpx.AsyncClient) -> None:
    admin = await login(client, 4099, "Админ")
    report = (await client.post("/admin/generators/smoke", headers=admin)).json()
    assert len(report) == 27
    assert all(r["ok"] for r in report), [r for r in report if not r["ok"]]


async def test_client_events_are_whitelisted(client: httpx.AsyncClient, db: AsyncSession) -> None:
    headers = await login(client, 4101)
    ok = await client.post(
        "/events", headers=headers, json={"name": "session_end", "props": {"duration": 900}}
    )
    assert ok.status_code == 204
    bad = await client.post("/events", headers=headers, json={"name": "shop_buy"})
    assert bad.status_code == 422
    row = await db.scalar(select(Event).where(Event.name == "session_end"))
    assert row is not None and row.props["band"] == "B" and "tg_id" not in row.props


async def test_internal_start_accepts_a_curator_invite(client: httpx.AsyncClient) -> None:
    student = await login(client, 4111)
    invite = (await client.post("/curators/invite", headers=student, json={})).json()
    resp = await client.post(
        "/internal/bot/start",
        headers={"X-Internal-Token": "test-internal-token"},
        json={"user": {"id": 4112, "first_name": "Папа"}, "payload": f"cur_{invite['token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["curator"]["status"] == "pending"
    mine = (await client.get("/curators", headers=student)).json()
    assert mine[0]["name"] == "Папа" and mine[0]["status"] == "pending"
    me = (await client.get("/me", headers=student)).json()
    assert me["curator_requests"] == 1
