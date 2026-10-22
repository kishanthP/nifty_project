from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select, update

from app.core.config import Settings, get_settings
from app.models import Alert, DeviceToken
from app.schemas.market import Candle
from tests.conftest import auth, make_quote


# ---------------------------------------------------------------- auth & users
async def test_requires_login(client) -> None:
    assert (await client.get("/api/v1/alerts")).status_code == 401
    bad = await client.get("/api/v1/alerts", headers={"Authorization": "Bearer dev:not-an-email"})
    assert bad.status_code == 401


async def test_me_creates_user_once(client) -> None:
    first = await client.get("/api/v1/me", headers=auth())
    second = await client.get("/api/v1/me", headers=auth())
    assert first.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["email"] == "alice@example.com"


# ---------------------------------------------------------------- market
async def test_quote_and_candles_come_from_cache(client, cache) -> None:
    assert (await client.get("/api/v1/market/quote/NIFTY50")).status_code == 404
    await cache.set_quote(make_quote(22550.35))
    await cache.set_candles("NIFTY50", [Candle(time=1, open=1, high=2, low=0.5, close=1.5)], 60)

    quote = (await client.get("/api/v1/market/quote/nifty50")).json()
    assert quote["ltp"] == 22550.35 and quote["change"] == 50.35
    candles = (await client.get("/api/v1/market/candles/NIFTY50")).json()
    assert candles == [{"time": 1, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}]


async def test_market_status_and_instruments(client) -> None:
    status = (await client.get("/api/v1/market/status")).json()
    assert {"is_open", "reason", "next_open"} <= status.keys()
    instruments = (await client.get("/api/v1/market/instruments")).json()
    assert instruments[0]["symbol"] == "NIFTY50"


async def test_health(client) -> None:
    body = (await client.get("/api/v1/health")).json()
    assert body["database"] == "ok" and body["redis"] == "ok"
    assert body["feed"]["status"] == "down"  # no worker in tests


# ---------------------------------------------------------------- alerts
async def test_direction_is_inferred_from_current_price(client, cache) -> None:
    """The user's example: NIFTY at 22,550 → 22,560 means 'above', 22,540 means 'below'."""
    await cache.set_quote(make_quote(22550))
    above = await client.post("/api/v1/alerts", json={"target_price": 22560}, headers=auth())
    below = await client.post("/api/v1/alerts", json={"target_price": "22540"}, headers=auth())
    assert above.status_code == 201, above.text
    assert above.json()["condition"] == "above" and above.json()["base_price"] == 22550.0
    assert below.json()["condition"] == "below"


async def test_rejects_condition_already_met(client, cache) -> None:
    await cache.set_quote(make_quote(22550))
    response = await client.post(
        "/api/v1/alerts", json={"target_price": 22540, "condition": "above"}, headers=auth()
    )
    assert response.status_code == 422
    assert "already at or above" in response.json()["detail"]

    same = await client.post("/api/v1/alerts", json={"target_price": 22550}, headers=auth())
    assert same.status_code == 422


async def test_validation_errors(client, cache) -> None:
    no_price = await client.post("/api/v1/alerts", json={"target_price": 22560}, headers=auth())
    assert no_price.status_code == 422 and "not available" in no_price.json()["detail"]

    await cache.set_quote(make_quote(22550))
    for body in (
        {"target_price": 22560.123},
        {"target_price": -1},
        {"target_price": 22560, "symbol": "XYZ"},
    ):
        response = await client.post("/api/v1/alerts", json=body, headers=auth())
        assert response.status_code in (404, 422), body


async def test_list_filter_and_ownership(client, cache) -> None:
    await cache.set_quote(make_quote(22550))
    created = (
        await client.post(
            "/api/v1/alerts", json={"target_price": 22600, "note": "breakout"}, headers=auth()
        )
    ).json()
    await client.post("/api/v1/alerts", json={"target_price": 22500}, headers=auth())

    mine = (await client.get("/api/v1/alerts?status=active", headers=auth())).json()
    assert len(mine) == 2 and {a["note"] for a in mine} == {"breakout", None}

    other = auth("mallory@example.com")
    assert (await client.get("/api/v1/alerts", headers=other)).json() == []
    assert (
        await client.delete(f"/api/v1/alerts/{created['id']}", headers=other)
    ).status_code == 404

    assert (
        await client.delete(f"/api/v1/alerts/{created['id']}", headers=auth())
    ).status_code == 204
    assert len((await client.get("/api/v1/alerts", headers=auth())).json()) == 1


async def test_rearm_triggered_alert(client, cache, session_factory) -> None:
    await cache.set_quote(make_quote(22550))
    alert = (
        await client.post("/api/v1/alerts", json={"target_price": 22560}, headers=auth())
    ).json()
    async with session_factory() as session:
        await session.execute(
            update(Alert)
            .where(Alert.id == alert["id"])
            .values(
                status="triggered", triggered_at=datetime.now(UTC), triggered_price=Decimal("22561")
            )
        )
        await session.commit()

    # Price is now above the target, so re-arming as-is would fire instantly → refused.
    await cache.set_quote(make_quote(22570))
    refused = await client.patch(
        f"/api/v1/alerts/{alert['id']}", json={"status": "active"}, headers=auth()
    )
    assert refused.status_code == 422

    rearmed = await client.patch(
        f"/api/v1/alerts/{alert['id']}",
        json={"status": "active", "target_price": 22600},
        headers=auth(),
    )
    body = rearmed.json()
    assert rearmed.status_code == 200
    assert (body["status"], body["target_price"], body["triggered_at"]) == ("active", 22600.0, None)


async def test_active_alert_limit(client, cache) -> None:
    client.app.dependency_overrides[get_settings] = lambda: Settings(max_active_alerts_per_user=2)
    await cache.set_quote(make_quote(22550))
    for target in (22600, 22650):
        assert (
            await client.post("/api/v1/alerts", json={"target_price": target}, headers=auth())
        ).status_code == 201
    third = await client.post("/api/v1/alerts", json={"target_price": 22700}, headers=auth())
    assert third.status_code == 422 and "at most 2" in third.json()["detail"]
    client.app.dependency_overrides.clear()


# ---------------------------------------------------------------- devices & notifications
async def test_device_registration_and_test_push(client, notifier, session_factory) -> None:
    token = "fcm-token-" + "a" * 40
    assert (
        await client.post("/api/v1/devices", json={"token": token}, headers=auth())
    ).status_code == 204
    # Same browser, different account: the token moves.
    await client.post("/api/v1/devices", json={"token": token}, headers=auth("bob@example.com"))
    async with session_factory() as session:
        assert len((await session.scalars(select(DeviceToken))).all()) == 1

    result = (await client.post("/api/v1/devices/test", headers=auth("bob@example.com"))).json()
    assert result == {"channel": "fcm", "devices": 1, "delivered": 1, "error": None}
    assert notifier.sent[-1][0] == [token]

    alice = (await client.post("/api/v1/devices/test", headers=auth())).json()
    assert alice["devices"] == 0 and alice["delivered"] == 0

    await client.post(
        "/api/v1/devices/unregister", json={"token": token}, headers=auth("bob@example.com")
    )
    async with session_factory() as session:
        assert (await session.scalars(select(DeviceToken))).all() == []


async def test_notifications_list_is_per_user(client) -> None:
    response = await client.get("/api/v1/notifications", headers=auth())
    assert response.status_code == 200 and response.json() == []


# ---------------------------------------------------------------- high & low (range) alerts
async def test_range_alert_creates_linked_pair(client, cache) -> None:
    """The user's example: NIFTY at 22,550 → one request for 'above 22,560' and 'below 22,540'."""
    await cache.set_quote(make_quote(22550))
    response = await client.post(
        "/api/v1/alerts/range",
        json={"high_price": 22560, "low_price": 22540, "note": "range"},
        headers=auth(),
    )
    assert response.status_code == 201, response.text
    pair = response.json()
    assert [(a["condition"], a["target_price"]) for a in pair] == [
        ("above", 22560.0),
        ("below", 22540.0),
    ]
    assert pair[0]["group_id"] is not None and pair[0]["group_id"] == pair[1]["group_id"]
    assert pair[0]["one_cancels_other"] is False and pair[0]["note"] == "range"
    listed = (await client.get("/api/v1/alerts?status=active", headers=auth())).json()
    assert len(listed) == 2


async def test_range_alert_validation(client, cache) -> None:
    await cache.set_quote(make_quote(22550))
    cases = [
        ({"high_price": 22540, "low_price": 22560}, "high price must be above"),
        ({"high_price": 22550, "low_price": 22500}, "already at or above"),
        ({"high_price": 22600, "low_price": 22550}, "already at or below"),
    ]
    for body, message in cases:
        response = await client.post("/api/v1/alerts/range", json=body, headers=auth())
        assert response.status_code == 422, body
        assert message in response.json()["detail"]
    assert (await client.get("/api/v1/alerts", headers=auth())).json() == []


async def test_range_alert_counts_two_toward_limit(client, cache) -> None:
    client.app.dependency_overrides[get_settings] = lambda: Settings(max_active_alerts_per_user=3)
    await cache.set_quote(make_quote(22550))
    await client.post("/api/v1/alerts", json={"target_price": 22600}, headers=auth())
    await client.post("/api/v1/alerts", json={"target_price": 22650}, headers=auth())
    response = await client.post(
        "/api/v1/alerts/range", json={"high_price": 22560, "low_price": 22540}, headers=auth()
    )
    assert response.status_code == 422 and "at most 3" in response.json()["detail"]
    client.app.dependency_overrides.clear()


# ---------------------------------------------------------------- multiple (batch) alerts
async def test_batch_alerts_are_independent(client, cache) -> None:
    """The user's example: NIFTY at 22,300 → 'above 22,310' and 'above 22,320' together."""
    await cache.set_quote(make_quote(22300))
    response = await client.post(
        "/api/v1/alerts/batch",
        json={"items": [{"target_price": 22310}, {"target_price": 22320}, {"target_price": 22290}]},
        headers=auth(),
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert [(a["condition"], a["target_price"]) for a in created] == [
        ("above", 22310.0),
        ("above", 22320.0),
        ("below", 22290.0),
    ]
    assert all(a["group_id"] is None and a["status"] == "active" for a in created)
    listed = (await client.get("/api/v1/alerts?status=active", headers=auth())).json()
    assert len(listed) == 3


async def test_batch_alerts_validation_is_all_or_nothing(client, cache) -> None:
    await cache.set_quote(make_quote(22300))
    cases = [
        ([{"target_price": 22310}, {"target_price": 22310}], "listed twice"),
        ([{"target_price": 22310}, {"target_price": 22290, "condition": "above"}], "already at"),
        ([{"target_price": 22310}, {"target_price": 22300}], "current price"),
    ]
    for items, message in cases:
        response = await client.post("/api/v1/alerts/batch", json={"items": items}, headers=auth())
        assert response.status_code == 422, items
        assert message in response.json()["detail"]
    too_many = [{"target_price": 22310 + i} for i in range(11)]
    response = await client.post("/api/v1/alerts/batch", json={"items": too_many}, headers=auth())
    assert response.status_code == 422
    assert (await client.get("/api/v1/alerts", headers=auth())).json() == []


async def test_batch_alerts_respect_limit(client, cache) -> None:
    client.app.dependency_overrides[get_settings] = lambda: Settings(max_active_alerts_per_user=2)
    await cache.set_quote(make_quote(22300))
    items = [{"target_price": p} for p in (22310, 22320, 22330)]
    response = await client.post("/api/v1/alerts/batch", json={"items": items}, headers=auth())
    assert response.status_code == 422 and "at most 2" in response.json()["detail"]
    client.app.dependency_overrides.clear()
