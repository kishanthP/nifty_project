import json
import struct

import httpx
import pyotp
import pytest

from app.services.market_data.angelone import AngelOneClient, AngelOneProvider, parse_tick
from app.services.market_data.base import InstrumentRef, ProviderAuthError, ProviderConfigError

NIFTY = InstrumentRef(
    id=1, symbol="NIFTY50", name="NIFTY 50", angelone_exchange_type=1, angelone_token="99926000"
)


def _packet(mode: int, ltp_paise: int, ohlc: tuple[int, int, int, int] | None = None) -> bytes:
    token = b"99926000".ljust(25, b"\x00")
    data = (
        struct.pack("<BB", mode, 1) + token + struct.pack("<qqq", 7, 1_760_000_000_000, ltp_paise)
    )
    if ohlc:
        data += struct.pack("<qqqdd", 0, 0, 0, 0.0, 0.0)  # qty, avg price, volume, buy/sell qty
        data += struct.pack("<qqqq", *ohlc)
    return data


def test_parse_ltp_packet() -> None:
    tick = parse_tick(_packet(1, 2_256_340))
    assert tick.token == "99926000"
    assert tick.exchange_type == 1
    assert tick.ltp == 22563.40
    assert tick.open is None


def test_parse_quote_packet_has_ohlc() -> None:
    tick = parse_tick(_packet(2, 2_256_340, (2_250_000, 2_258_010, 2_249_500, 2_255_000)))
    assert (tick.open, tick.high, tick.low, tick.close) == (22500.0, 22580.1, 22495.0, 22550.0)


def test_parse_rejects_short_packet() -> None:
    with pytest.raises(ValueError):
        parse_tick(b"\x01\x01")


def _client(handler) -> AngelOneClient:  # noqa: ANN001
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AngelOneClient("key", "A123", "1234", pyotp.random_base32(), http=http)


async def test_login_and_quote() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("loginByPassword"):
            body = json.loads(request.content)
            assert body["clientcode"] == "A123" and len(body["totp"]) == 6
            assert request.headers["X-PrivateKey"] == "key"
            return httpx.Response(
                200,
                json={"status": True, "data": {"jwtToken": "Bearer abc", "feedToken": "feed"}},
            )
        assert request.headers["Authorization"] == "Bearer abc"
        return httpx.Response(
            200,
            json={
                "status": True,
                "data": {
                    "fetched": [{"exchange": "NSE", "symbolToken": "99926000", "ltp": 22550.5}]
                },
            },
        )

    client = _client(handler)
    session = await client.login()
    assert session.jwt == "abc" and session.feed_token == "feed"
    rows = await client.quote({"NSE": ["99926000"]})
    assert rows[0]["ltp"] == 22550.5


async def test_expired_token_raises_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"status": False, "errorcode": "AG8002", "message": "Token Expired"}
        )

    with pytest.raises(ProviderAuthError):
        await _client(handler).quote({"NSE": ["99926000"]})


async def test_snapshot_maps_quote_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("loginByPassword"):
            return httpx.Response(
                200, json={"status": True, "data": {"jwtToken": "t", "feedToken": "f"}}
            )
        row = {
            "exchange": "NSE",
            "symbolToken": "99926000",
            "ltp": 22563.4,
            "open": 22500,
            "high": 22580.1,
            "low": 22495,
            "close": 22550,
            "netChange": 13.4,
            "percentChange": 0.06,
            "exchFeedTime": "15-Oct-2026 15:29:59",
        }
        return httpx.Response(200, json={"status": True, "data": {"fetched": [row]}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = AngelOneProvider("key", "A123", "1234", pyotp.random_base32(), http=http)
    [quote] = await provider._snapshot([NIFTY])
    assert quote.symbol == "NIFTY50" and quote.ltp == 22563.4
    assert quote.prev_close == 22550 and quote.change == 13.4
    assert quote.exchange_ts is not None and quote.exchange_ts.hour == 15


def test_missing_credentials_is_config_error() -> None:
    with pytest.raises(ProviderConfigError):
        AngelOneProvider("", "", "", "")
    with pytest.raises(ProviderConfigError):
        AngelOneProvider("key", "A123", "1234", "not a base32 secret!")
