"""Angel One SmartAPI: free, real-time NSE prices.

Login uses client code + PIN + TOTP, so the worker logs in by itself every day
(no manual browser login). We only read market data and never place orders, so no
static IP registration is needed.

This is a small async client. Endpoints, headers and the binary tick layout follow
Angel One's official `smartapi-python` SDK (v1.5.5). The SDK itself is not used
because it blocks the event loop, writes log files and calls an IP-lookup service
when it's imported.
"""

import asyncio
import json
import logging
import struct
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Any

import httpx
import pyotp
import websockets
from websockets.exceptions import InvalidStatus, WebSocketException

from app.schemas.market import Candle, Quote
from app.services import market_hours
from app.services.market_data.base import (
    Backoff,
    InstrumentRef,
    MarketDataProvider,
    ProviderAuthError,
    ProviderConfigError,
    ProviderError,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://apiconnect.angelone.in"
WS_URL = "wss://smartapisocket.angelone.in/smart-stream"
LOGIN_PATH = "/rest/auth/angelbroking/user/v1/loginByPassword"
QUOTE_PATH = "/rest/secure/angelbroking/market/v1/quote"
CANDLE_PATH = "/rest/secure/angelbroking/historical/v1/getCandleData"

# WebSocket exchange type → REST exchange name.
EXCHANGE_NAMES = {1: "NSE", 3: "BSE"}
WS_MODE_QUOTE = 2  # LTP + open/high/low/close
# Error codes that mean "log in again".
AUTH_ERROR_CODES = {"AG8001", "AG8002", "AG8003", "AB1010", "AB8050", "AB8051"}
# Login failures on Angel One's side ("something went wrong"): temporary, safe to retry.
TRANSIENT_ERROR_CODES = {"AB1004", "AB2000", "AB2001"}
NO_TICK_TIMEOUT = 30.0

# Any other refused login means wrong details. Repeating a wrong login can get the
# account blocked, so the worker tries once more (with a fresh TOTP code) and then stops.
MAX_LOGIN_REJECTIONS = 2
LOGIN_RETRY_SECONDS = 60.0
LOGIN_PAUSED_LOG_SECONDS = 600.0
LOGIN_HINTS = {
    "AB1050": (
        "The TOTP code was wrong. ANGELONE_TOTP_SECRET must be the secret key text shown "
        "with the QR code, not a 6-digit code, and the computer's clock must be correct."
    ),
    "AB7001": "Put your 4-digit MPIN in ANGELONE_PIN, not your trading password.",
}
DEFAULT_LOGIN_HINT = (
    "Check ANGELONE_API_KEY, ANGELONE_CLIENT_CODE (your client ID), "
    "ANGELONE_PIN (your 4-digit MPIN) and ANGELONE_TOTP_SECRET in .env."
)


class LoginRejected(ProviderAuthError):
    """Angel One refused the login details. Retrying with the same details won't help."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.hint = LOGIN_HINTS.get(code, DEFAULT_LOGIN_HINT)
        super().__init__(
            f"Angel One refused the login ({code or 'no code'}: {message}). {self.hint}"
        )


class LoginPaused(ProviderError):
    """No login attempt is made right now, to protect the account from being blocked."""

    def __init__(self, reason: str, retry_in: float | None = None) -> None:
        self.retry_in = retry_in  # None = paused until the worker restarts
        super().__init__(reason)


# ---------------------------------------------------------------- binary ticks
@dataclass(frozen=True)
class TickPacket:
    mode: int
    exchange_type: int
    token: str
    sequence: int
    exchange_ts_ms: int
    ltp: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None


def _paise(value: int) -> float | None:
    return round(value / 100, 2) if value else None


def parse_tick(data: bytes) -> TickPacket:
    """Decode one little-endian tick packet. Prices arrive in paise."""
    if len(data) < 51:
        raise ValueError(f"Tick packet too short: {len(data)} bytes")
    mode, exchange_type = struct.unpack_from("<BB", data, 0)
    token = data[2:27].split(b"\x00", 1)[0].decode("ascii")
    sequence, exchange_ts_ms, ltp = struct.unpack_from("<qqq", data, 27)
    open_ = high = low = close = None
    if mode in (2, 3) and len(data) >= 123:
        o, h, l, c = struct.unpack_from("<qqqq", data, 91)  # noqa: E741
        open_, high, low, close = _paise(o), _paise(h), _paise(l), _paise(c)
    return TickPacket(
        mode=mode,
        exchange_type=exchange_type,
        token=token,
        sequence=sequence,
        exchange_ts_ms=exchange_ts_ms,
        ltp=round(ltp / 100, 2),
        open=open_,
        high=high,
        low=low,
        close=close,
    )


# ---------------------------------------------------------------- REST client
@dataclass
class Session:
    jwt: str
    feed_token: str
    logged_in_at: datetime


class AngelOneClient:
    def __init__(
        self,
        api_key: str,
        client_code: str,
        pin: str,
        totp_secret: str,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.client_code = client_code
        self._pin = pin
        self._totp = pyotp.TOTP(totp_secret)
        self._http = http or httpx.AsyncClient(timeout=10)
        self._mac = ":".join(f"{(uuid.getnode() >> s) & 0xFF:02x}" for s in range(40, -1, -8))
        self.jwt: str | None = None

    def _headers(self, with_auth: bool) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": self._mac,
            "X-PrivateKey": self.api_key,
        }
        if with_auth and self.jwt:
            headers["Authorization"] = f"Bearer {self.jwt}"
        return headers

    async def _send(self, path: str, payload: dict[str, Any], *, auth: bool) -> dict[str, Any]:
        """POST and return the JSON body. Network and HTTP problems raise ProviderError."""
        try:
            response = await self._http.post(
                BASE_URL + path, json=payload, headers=self._headers(auth)
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Angel One request failed: {exc}") from exc
        if response.status_code in (401, 403):
            raise ProviderAuthError(f"Angel One rejected the session (HTTP {response.status_code})")
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise ProviderError(
                f"Angel One returned HTTP {response.status_code}: {response.text[:200]}"
            )
        return body

    @staticmethod
    def _succeeded(body: dict[str, Any]) -> bool:
        return body.get("status") is True or body.get("success") is True

    @staticmethod
    def _error(body: dict[str, Any]) -> tuple[str, str]:
        code = str(body.get("errorcode") or body.get("errorCode") or "")
        return code, str(body.get("message") or "unknown error")

    async def _post(self, path: str, payload: dict[str, Any]) -> Any:
        body = await self._send(path, payload, auth=True)
        if self._succeeded(body):
            return body.get("data")
        code, message = self._error(body)
        if code in AUTH_ERROR_CODES or "token" in message.lower():
            raise ProviderAuthError(f"{code} {message}".strip())
        raise ProviderError(f"Angel One error {code}: {message}")

    async def login(self) -> Session:
        """One login attempt. Raises LoginRejected when Angel One refuses the details."""
        payload = {"clientcode": self.client_code, "password": self._pin, "totp": self._totp.now()}
        try:
            body = await self._send(LOGIN_PATH, payload, auth=False)
        except ProviderAuthError as exc:
            # The account details were not checked yet, so this is safe to retry.
            raise ProviderError(f"{exc}. If this keeps happening, check ANGELONE_API_KEY.") from exc
        if not self._succeeded(body):
            code, message = self._error(body)
            if code in TRANSIENT_ERROR_CODES:
                raise ProviderError(f"Angel One login failed temporarily: {code} {message}")
            raise LoginRejected(code, message)
        data = body.get("data") or {}
        if not data.get("jwtToken") or not data.get("feedToken"):
            raise ProviderError("Angel One login response did not include tokens")
        self.jwt = str(data["jwtToken"]).removeprefix("Bearer ").strip()
        return Session(
            jwt=self.jwt, feed_token=data["feedToken"], logged_in_at=market_hours.now_ist()
        )

    async def quote(self, exchange_tokens: dict[str, list[str]]) -> list[dict[str, Any]]:
        data = await self._post(QUOTE_PATH, {"mode": "FULL", "exchangeTokens": exchange_tokens})
        return list((data or {}).get("fetched") or [])

    async def candles(
        self, exchange: str, token: str, start: datetime, end: datetime
    ) -> list[list[Any]]:
        payload = {
            "exchange": exchange,
            "symboltoken": token,
            "interval": "ONE_MINUTE",
            "fromdate": start.strftime("%Y-%m-%d %H:%M"),
            "todate": end.strftime("%Y-%m-%d %H:%M"),
        }
        return list(await self._post(CANDLE_PATH, payload) or [])

    async def aclose(self) -> None:
        await self._http.aclose()


# ---------------------------------------------------------------- helpers
def mask(value: str) -> str:
    """'A123456' -> 'A1***56', enough to spot a typo without showing the whole value."""
    if len(value) <= 4:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def ws_headers(api_key: str, client_code: str, session: Session) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {session.jwt}",
        "x-api-key": api_key,
        "x-client-code": client_code,
        "x-feed-token": session.feed_token,
    }


def subscribe_message(tokens_by_type: dict[int, list[str]]) -> str:
    return json.dumps(
        {
            "correlationID": "sharemkt01",
            "action": 1,
            "params": {
                "mode": WS_MODE_QUOTE,
                "tokenList": [{"exchangeType": t, "tokens": v} for t, v in tokens_by_type.items()],
            },
        }
    )


def intraday_window() -> tuple[datetime, datetime]:
    """Start and end of the latest trading session (up to now if it's still running)."""
    day = market_hours.last_session_date()
    start = datetime.combine(day, market_hours.MARKET_OPEN, tzinfo=market_hours.IST)
    end = min(
        market_hours.now_ist(),
        datetime.combine(day, market_hours.MARKET_CLOSE, tzinfo=market_hours.IST),
    )
    return start, end


# ---------------------------------------------------------------- provider
def _parse_feed_time(value: Any) -> datetime | None:
    # REST quotes stamp time like "15-Oct-2026 15:29:59" (IST).
    try:
        return datetime.strptime(str(value), "%d-%b-%Y %H:%M:%S").replace(tzinfo=market_hours.IST)
    except (TypeError, ValueError):
        return None


class AngelOneProvider(MarketDataProvider):
    name = "angelone"

    def __init__(
        self,
        api_key: str,
        client_code: str,
        pin: str,
        totp_secret: str,
        relogin_time: str = "08:30",
        http: httpx.AsyncClient | None = None,
        ws_connect: Callable[..., Any] = websockets.connect,
        login_retry_seconds: float = LOGIN_RETRY_SECONDS,
    ) -> None:
        if not all([api_key, client_code, pin, totp_secret]):
            raise ProviderConfigError(
                "Angel One needs ANGELONE_API_KEY, ANGELONE_CLIENT_CODE, ANGELONE_PIN "
                "and ANGELONE_TOTP_SECRET in .env"
            )
        try:
            pyotp.TOTP(totp_secret).now()
        except Exception as exc:  # pyotp raises binascii/ValueError for bad secrets
            raise ProviderConfigError("ANGELONE_TOTP_SECRET is not a valid TOTP secret") from exc
        self._client = AngelOneClient(api_key, client_code, pin, totp_secret, http=http)
        self._ws_connect = ws_connect
        self._relogin_at = time.fromisoformat(relogin_time)
        self._session: Session | None = None
        self._login_lock = asyncio.Lock()
        self._login_retry_seconds = login_retry_seconds
        self._rejections = 0
        self._next_login_at = 0.0  # event-loop clock
        self._paused_reason: str | None = None
        self._snapshots: dict[str, Quote] = {}

    # --- session handling ---
    def _session_stale(self) -> bool:
        if self._session is None:
            return True
        now = market_hours.now_ist()
        cutoff = datetime.combine(now.date(), self._relogin_at, tzinfo=market_hours.IST)
        return now >= cutoff and self._session.logged_in_at < cutoff

    async def _ensure_session(self) -> Session:
        async with self._login_lock:
            if self._session is not None and not self._session_stale():
                return self._session
            if self._paused_reason:
                raise LoginPaused(self._paused_reason)
            now = asyncio.get_running_loop().time()
            if now < self._next_login_at:
                raise LoginPaused(
                    "Waiting before trying the Angel One login again",
                    retry_in=self._next_login_at - now,
                )
            try:
                self._session = await self._client.login()
            except LoginRejected as exc:
                self._rejections += 1
                if self._rejections >= MAX_LOGIN_REJECTIONS:
                    self._paused_reason = (
                        f"Login stopped after {self._rejections} refused attempts so your "
                        f"account isn't blocked. {exc.hint} Then run: docker compose up -d"
                    )
                else:
                    self._next_login_at = now + self._login_retry_seconds
                raise
            self._rejections = 0
            logger.info("Logged in to Angel One as %s", mask(self._client.client_code))
            return self._session

    def _drop_session(self) -> None:
        self._session = None
        self._client.jwt = None

    async def _call(self, fn: Callable[..., Any], *args: Any) -> Any:
        """Run a REST call, logging in again once if the session has expired."""
        await self._ensure_session()
        try:
            return await fn(*args)
        except ProviderAuthError:
            self._drop_session()
            await self._ensure_session()
            return await fn(*args)

    # --- quotes ---
    async def _snapshot(self, instruments: Sequence[InstrumentRef]) -> list[Quote]:
        by_exchange: dict[str, list[str]] = defaultdict(list)
        lookup: dict[tuple[str, str], InstrumentRef] = {}
        for inst in instruments:
            exchange = EXCHANGE_NAMES[inst.angelone_exchange_type or 0]
            by_exchange[exchange].append(inst.angelone_token or "")
            lookup[(exchange, inst.angelone_token or "")] = inst
        rows = await self._call(self._client.quote, dict(by_exchange))
        status = "open" if market_hours.is_market_open() else "closed"
        quotes = []
        for row in rows:
            inst = lookup.get((str(row.get("exchange")), str(row.get("symbolToken"))))
            if inst is None or row.get("ltp") is None:
                continue
            quote = Quote(
                symbol=inst.symbol,
                name=inst.name,
                ltp=round(float(row["ltp"]), 2),
                open=row.get("open"),
                high=row.get("high"),
                low=row.get("low"),
                prev_close=row.get("close"),
                change=row.get("netChange"),
                change_pct=row.get("percentChange"),
                exchange_ts=_parse_feed_time(row.get("exchFeedTime")),
                received_at=datetime.now(UTC),
                source=self.name,
                market_status=status,
            ).with_derived_change()
            self._snapshots[inst.symbol] = quote
            quotes.append(quote)
        return quotes

    def _merge_tick(self, inst: InstrumentRef, tick: TickPacket) -> Quote:
        previous = self._snapshots.get(inst.symbol)
        prev_close = (previous.prev_close if previous else None) or tick.close
        quote = Quote(
            symbol=inst.symbol,
            name=inst.name,
            ltp=tick.ltp,
            open=tick.open or (previous.open if previous else None),
            high=tick.high or (previous.high if previous else None),
            low=tick.low or (previous.low if previous else None),
            prev_close=prev_close,
            exchange_ts=datetime.fromtimestamp(tick.exchange_ts_ms / 1000, UTC)
            if tick.exchange_ts_ms
            else None,
            received_at=datetime.now(UTC),
            source=self.name,
            market_status="open" if market_hours.is_market_open() else "closed",
        ).with_derived_change()
        self._snapshots[inst.symbol] = quote
        return quote

    @staticmethod
    def _handle_text(message: str) -> None:
        if message.strip().lower() == "pong":
            return
        try:
            payload = json.loads(message)
        except ValueError:
            logger.debug("Ignoring text frame: %s", message[:200])
            return
        error = f"{payload.get('errorCode', '')} {payload.get('errorMessage', '')}".strip()
        if error:
            if "token" in error.lower() or "auth" in error.lower():
                raise ProviderAuthError(f"WebSocket: {error}")
            logger.warning("Angel One WebSocket error: %s", error)

    @staticmethod
    async def _heartbeat(ws: Any) -> None:
        # Angel One expects a text "ping" regularly, besides protocol-level pings.
        while True:
            await asyncio.sleep(25)
            await ws.send("ping")

    async def _ws_stream(self, instruments: Sequence[InstrumentRef]) -> AsyncIterator[Quote]:
        session = await self._ensure_session()
        tokens_by_type: dict[int, list[str]] = defaultdict(list)
        lookup: dict[tuple[int, str], InstrumentRef] = {}
        for inst in instruments:
            exchange_type = inst.angelone_exchange_type or 0
            tokens_by_type[exchange_type].append(inst.angelone_token or "")
            lookup[(exchange_type, inst.angelone_token or "")] = inst
        try:
            connection = self._ws_connect(
                WS_URL,
                additional_headers=ws_headers(
                    self._client.api_key, self._client.client_code, session
                ),
                ping_interval=20,
                ping_timeout=20,
                open_timeout=15,
                close_timeout=5,
            )
            async with connection as ws:
                await ws.send(subscribe_message(tokens_by_type))
                logger.info("Angel One live feed connected (%d instruments)", len(instruments))
                heartbeat = asyncio.create_task(self._heartbeat(ws))
                try:
                    while market_hours.in_stream_window() and not self._session_stale():
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=NO_TICK_TIMEOUT)
                        except TimeoutError:
                            if market_hours.is_market_open():
                                raise ProviderError("No ticks for 30s, reconnecting") from None
                            continue  # quiet before the open / after the close is normal
                        if isinstance(message, str):
                            self._handle_text(message)
                            continue
                        tick = parse_tick(message)
                        inst = lookup.get((tick.exchange_type, tick.token))
                        if inst is not None:
                            yield self._merge_tick(inst, tick)
                finally:
                    heartbeat.cancel()
        except InvalidStatus as exc:
            status_code = exc.response.status_code
            if status_code in (401, 403):
                raise ProviderAuthError(f"WebSocket handshake rejected ({status_code})") from exc
            raise ProviderError(f"WebSocket handshake failed ({status_code})") from exc

    async def stream(self, instruments: Sequence[InstrumentRef]) -> AsyncIterator[Quote]:
        tracked = [
            i
            for i in instruments
            if i.angelone_token and i.angelone_exchange_type in EXCHANGE_NAMES
        ]
        if not tracked:
            raise ProviderConfigError("No active instruments have Angel One tokens")
        backoff = Backoff(initial=2, maximum=300)
        while True:
            try:
                # A REST snapshot first: shows the last price even when the market is closed.
                for quote in await self._snapshot(tracked):
                    yield quote
                if not market_hours.in_stream_window():
                    wait = market_hours.seconds_until_stream_window()
                    await asyncio.sleep(min(300.0, max(5.0, wait)))
                    continue
                async for quote in self._ws_stream(tracked):
                    backoff.reset()
                    yield quote
            except ProviderConfigError:
                raise
            except LoginRejected as exc:
                logger.error("%s", exc)
                self._drop_session()
                await asyncio.sleep(self._login_retry_seconds)
            except LoginPaused as exc:
                if exc.retry_in is None:
                    logger.error("Angel One: %s", exc)
                await asyncio.sleep(
                    LOGIN_PAUSED_LOG_SECONDS if exc.retry_in is None else max(1.0, exc.retry_in)
                )
            except ProviderAuthError as exc:
                logger.warning("Angel One auth problem: %s (will log in again)", exc)
                self._drop_session()
                await backoff.sleep()
            except (ProviderError, WebSocketException, OSError, TimeoutError, ValueError) as exc:
                # ValueError = a malformed tick packet; reconnecting resyncs the stream.
                logger.warning("Angel One feed interrupted: %s", exc)
                await backoff.sleep()

    async def fetch_intraday(self, instrument: InstrumentRef) -> list[Candle]:
        if not instrument.angelone_token or instrument.angelone_exchange_type not in EXCHANGE_NAMES:
            return []
        start, end = intraday_window()
        rows = await self._call(
            self._client.candles,
            EXCHANGE_NAMES[instrument.angelone_exchange_type],
            instrument.angelone_token,
            start,
            end,
        )
        candles = []
        for row in rows:
            try:
                ts = datetime.fromisoformat(str(row[0]))
                candles.append(
                    Candle(
                        time=int(ts.timestamp()),
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                    )
                )
            except (IndexError, TypeError, ValueError):
                continue
        return candles

    async def aclose(self) -> None:
        await self._client.aclose()
