import json
import struct
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pyotp

from app.core.config import Settings
from app.tools import check_angelone

GOOD = {
    "angelone_api_key": "apikey-x9q",
    "angelone_client_code": "A123456",
    "angelone_pin": "4321",
    "angelone_totp_secret": pyotp.random_base32(),
}


def _settings(**overrides: str) -> Settings:
    return Settings(**{**GOOD, **overrides})


class FakeAngelOne:
    """Plays Angel One's REST API and records which endpoints were called."""

    def __init__(
        self, login_error: str | None = None, clock_offset_s: float = 0, sends_date: bool = True
    ) -> None:
        self.login_error = login_error
        self.clock_offset_s = clock_offset_s
        self.sends_date = sends_date
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(path)
        server_now = datetime.now(UTC) + timedelta(seconds=self.clock_offset_s)
        headers = {"date": format_datetime(server_now, usegmt=True)} if self.sends_date else {}
        if request.method == "HEAD":
            return httpx.Response(200, headers=headers)
        if path.endswith("loginByPassword"):
            if self.login_error:
                body = {"status": False, "errorcode": self.login_error, "message": "Invalid"}
            else:
                body = {"status": True, "data": {"jwtToken": "jwt", "feedToken": "feed"}}
        elif path.endswith("quote"):
            row = {
                "exchange": "NSE",
                "symbolToken": "99926000",
                "tradingSymbol": "Nifty 50",
                "ltp": 22563.4,
                "exchFeedTime": "16-Oct-2026 15:30:00",
            }
            body = {"status": True, "data": {"fetched": [row]}}
        else:  # candles
            body = {"status": True, "data": [["2026-10-16T09:15:00+05:30", 1, 2, 0.5, 1.5, 0]]}
        return httpx.Response(200, json=body, headers=headers)

    def logins(self) -> int:
        return sum(path.endswith("loginByPassword") for path in self.calls)


class FakeWebSocket:
    def __init__(self, ltp_paise: int) -> None:
        token = b"99926000".ljust(25, b"\x00")
        self.messages = [struct.pack("<BB", 1, 1) + token + struct.pack("<qqq", 1, 0, ltp_paise)]
        self.sent: list[str] = []

    async def __aenter__(self) -> "FakeWebSocket":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def recv(self) -> bytes:
        return self.messages.pop(0)


async def _run(fake: FakeAngelOne, settings: Settings) -> tuple[bool, str, FakeWebSocket]:
    lines: list[str] = []
    ws = FakeWebSocket(2_256_340)
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as http:
        ok = await check_angelone.run(settings, http, lambda *a, **kw: ws, lines.append)
    return ok, "\n".join(lines), ws


def test_settings_problems_name_the_setting_but_not_the_value() -> None:
    problems = check_angelone.check_settings(
        _settings(angelone_api_key="", angelone_pin="MyPass@1", angelone_totp_secret="123456")
    )
    text = " ".join(problems)
    assert "ANGELONE_API_KEY is empty" in text
    assert "MPIN" in text and "MyPass@1" not in text
    assert "6-digit code" in text
    assert check_angelone.check_settings(_settings()) == []


def test_mask_hides_most_of_the_value() -> None:
    assert check_angelone.mask("A123456") == "A1***56"
    assert check_angelone.mask("abc") == "***"


async def test_bad_settings_never_try_to_log_in() -> None:
    fake = FakeAngelOne()
    ok, output, _ = await _run(fake, _settings(angelone_totp_secret="not a secret!"))
    assert not ok and "No login was attempted" in output
    assert fake.calls == []


async def test_wrong_clock_stops_before_login() -> None:
    fake = FakeAngelOne(clock_offset_s=-120)
    ok, output, _ = await _run(fake, _settings())
    assert not ok and "clock is off by 12" in output  # the Date header has 1 s precision
    assert fake.logins() == 0


async def test_missing_server_time_skips_the_clock_check() -> None:
    fake = FakeAngelOne(sends_date=False)
    ok, output, _ = await _run(fake, _settings())
    assert ok and "Could not check the clock" in output
    assert fake.logins() == 1


async def test_unreachable_angel_one_stops_before_login() -> None:
    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no internet", request=request)

    lines: list[str] = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(offline)) as http:
        ok = await check_angelone.run(_settings(), http, say=lines.append)
    assert not ok and "Could not reach Angel One" in "\n".join(lines)


async def test_refused_login_is_tried_only_once() -> None:
    fake = FakeAngelOne(login_error="AB7001")
    ok, output, _ = await _run(fake, _settings())
    assert not ok and "MPIN" in output
    assert fake.logins() == 1


async def test_everything_working() -> None:
    fake = FakeAngelOne()
    ok, output, ws = await _run(fake, _settings())
    assert ok, output
    assert "Logged in" in output
    assert "Nifty 50 price: 22,563.40" in output
    assert "1 one-minute candles" in output
    assert "Live feed works" in output
    assert json.loads(ws.sent[0])["params"]["tokenList"] == [
        {"exchangeType": 1, "tokens": ["99926000"]}
    ]
    for name in (
        "angelone_api_key",
        "angelone_client_code",
        "angelone_pin",
        "angelone_totp_secret",
    ):
        assert GOOD[name] not in output  # secrets are never printed
