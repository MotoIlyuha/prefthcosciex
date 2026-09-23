"""Sign-in (12.3, 14.1): initData HMAC, freshness, refresh rotation, web links."""

from __future__ import annotations

import time
from urllib.parse import parse_qsl, urlencode

import httpx

from tests.conftest import init_data, login


async def test_valid_init_data_signs_in_and_creates_the_account(client: httpx.AsyncClient) -> None:
    resp = await client.post("/auth/telegram", json={"init_data": init_data(1001)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is True
    assert body["user"]["first_name"] == "Аня"
    # The first account ever becomes the admin when no admin ids are configured.
    assert body["user"]["is_admin"] is True
    me = await client.get("/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["wallet"]["balance"] == 0

    again = await client.post("/auth/telegram", json={"init_data": init_data(1001)})
    assert again.json()["created"] is False


async def test_forged_signature_is_rejected(client: httpx.AsyncClient) -> None:
    fields = dict(parse_qsl(init_data(1002)))
    fields["user"] = fields["user"].replace("1002", "1003")  # impersonation attempt
    resp = await client.post("/auth/telegram", json={"init_data": urlencode(fields)})
    assert resp.status_code == 401
    assert resp.json()["detail"]["reason"] == "bad signature"


async def test_hash_from_another_bot_is_rejected(client: httpx.AsyncClient) -> None:
    from app.core.initdata import sign_init_data

    fields = dict(parse_qsl(init_data(1004)))
    fields.pop("hash")
    fields["hash"] = sign_init_data(fields, "999:OTHER-BOT")
    resp = await client.post("/auth/telegram", json={"init_data": urlencode(fields)})
    assert resp.status_code == 401


async def test_expired_auth_date_is_rejected(client: httpx.AsyncClient) -> None:
    stale = init_data(1005, auth_date=int(time.time()) - 11 * 60)
    resp = await client.post("/auth/telegram", json={"init_data": stale})
    assert resp.status_code == 401
    assert resp.json()["detail"]["reason"] == "stale auth_date"
    fresh_enough = init_data(1005, auth_date=int(time.time()) - 9 * 60)
    assert (
        await client.post("/auth/telegram", json={"init_data": fresh_enough})
    ).status_code == 200


async def test_requests_without_or_with_a_bad_token_are_refused(client: httpx.AsyncClient) -> None:
    assert (await client.get("/today")).status_code == 401
    bad = await client.get("/today", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401


async def test_refresh_rotates_and_reuse_ends_every_session(client: httpx.AsyncClient) -> None:
    first = (await client.post("/auth/telegram", json={"init_data": init_data(1006)})).json()
    rotated = await client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert rotated.status_code == 200
    second = rotated.json()
    assert second["refresh_token"] != first["refresh_token"]
    # Presenting the old one again looks like theft: everything is revoked.
    reused = await client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert reused.status_code == 401
    assert reused.json()["detail"]["code"] == "refresh_reused"
    dead = await client.post("/auth/refresh", json={"refresh_token": second["refresh_token"]})
    assert dead.status_code == 401


async def test_access_token_cannot_be_used_as_refresh(client: httpx.AsyncClient) -> None:
    body = (await client.post("/auth/telegram", json={"init_data": init_data(1007)})).json()
    resp = await client.post("/auth/refresh", json={"refresh_token": body["access_token"]})
    assert resp.status_code == 401


async def test_bot_web_link_is_single_use(client: httpx.AsyncClient) -> None:
    headers = {"X-Internal-Token": "test-internal-token"}
    user = {"id": 1008, "first_name": "Бот"}
    assert (await client.post("/internal/bot/web-link", json=user)).status_code == 403
    url = (await client.post("/internal/bot/web-link", json=user, headers=headers)).json()["url"]
    token = url.split("token=")[1]
    ok = await client.post("/auth/web-link", json={"token": token})
    assert ok.status_code == 200
    assert "bayt_refresh" in ok.cookies
    again = await client.post("/auth/web-link", json={"token": token})
    assert again.status_code == 401


async def test_login_widget(client: httpx.AsyncClient) -> None:
    from app.core.initdata import sign_login_widget

    fields = {"id": "1009", "first_name": "Веб", "auth_date": str(int(time.time()))}
    fields["hash"] = sign_login_widget(fields, "123456:TEST-TOKEN-for-bayt-tests")
    resp = await client.post(
        "/auth/widget", json={**fields, "id": 1009, "auth_date": int(fields["auth_date"])}
    )
    assert resp.status_code == 200, resp.text
    forged = {**fields, "first_name": "Хакер"}
    bad = await client.post(
        "/auth/widget", json={**forged, "id": 1009, "auth_date": int(fields["auth_date"])}
    )
    assert bad.status_code == 401


async def test_dev_login_is_off_unless_enabled(client: httpx.AsyncClient) -> None:
    resp = await client.post("/auth/dev", json={"tg_id": 5})
    assert resp.status_code == 404


async def test_logout_revokes_refresh(client: httpx.AsyncClient) -> None:
    body = (await client.post("/auth/telegram", json={"init_data": init_data(1010)})).json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    assert (await client.post("/auth/logout", headers=headers)).status_code == 204
    resp = await client.post("/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert resp.status_code == 401


async def test_health(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["generators"] == 27
    headers = await login(client, 1011)
    assert (await client.get("/me", headers=headers)).status_code == 200
