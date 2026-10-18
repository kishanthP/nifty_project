"""Check your Angel One details before switching the app to live prices.

Run it (it reads the current .env every time):
    docker compose run --rm --no-deps api python -m app.tools.check_angelone

It makes exactly ONE login attempt, then fetches the NIFTY 50 price, chart candles and
the live feed, and says what to fix if something is wrong. Secrets are never printed.
"""

import asyncio
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
import pyotp
import websockets
from websockets.exceptions import InvalidStatus, WebSocketException

from app.core.config import Settings, get_settings
from app.services import market_hours
from app.services.formatting import format_inr
from app.services.market_data.angelone import (
    BASE_URL,
    WS_URL,
    AngelOneClient,
    LoginRejected,
    Session,
    intraday_window,
    mask,
    parse_tick,
    subscribe_message,
    ws_headers,
)
from app.services.market_data.base import ProviderError

CLOCK_URL = "https://smartapi.angelone.in/"
NIFTY_TOKEN = "99926000"
NSE = 1
MAX_CLOCK_DRIFT_SECONDS = 15
LIVE_FEED_WAIT_SECONDS = 10

Printer = Callable[[str], None]


def check_settings(settings: Settings) -> list[str]:
    """Problems with the four Angel One values. Mentions names only, never the values."""
    values = {
        "ANGELONE_API_KEY": settings.angelone_api_key,
        "ANGELONE_CLIENT_CODE": settings.angelone_client_code,
        "ANGELONE_PIN": settings.angelone_pin.get_secret_value(),
        "ANGELONE_TOTP_SECRET": settings.angelone_totp_secret.get_secret_value(),
    }
    problems = []
    for name, value in values.items():
        if not value.strip():
            problems.append(f"{name} is empty in .env")
        elif value != value.strip():
            problems.append(f"{name} has a space at the start or end")

    pin = values["ANGELONE_PIN"].strip()
    if pin and not pin.isdigit():
        problems.append(
            "ANGELONE_PIN must be your MPIN (the 4-digit PIN that opens the Angel One app), "
            "not your password"
        )
    secret = values["ANGELONE_TOTP_SECRET"].strip()
    if secret.isdigit() and len(secret) <= 8:
        problems.append(
            "ANGELONE_TOTP_SECRET looks like a 6-digit code. Use the secret key text shown "
            "with the QR code instead (the code changes every 30 seconds, the key never does)"
        )
    elif secret:
        try:
            pyotp.TOTP(secret).now()
        except Exception:  # pyotp raises binascii/ValueError for bad secrets
            problems.append(
                "ANGELONE_TOTP_SECRET is not a valid secret key "
                "(it should only have letters A-Z and digits 2-7)"
            )
    return problems


class Unreachable(Exception):
    pass


async def clock_drift(http: httpx.AsyncClient) -> float | None:
    """Seconds this computer's clock is ahead (+) or behind (-) Angel One's servers.

    None when the servers don't say what time it is. Raises Unreachable when
    Angel One can't be reached at all.
    """
    reached = False
    # The API host sends no Date header, the developer portal does.
    for url in (CLOCK_URL, BASE_URL):
        try:
            response = await http.head(url)
        except httpx.HTTPError:
            continue
        reached = True
        try:
            server_time = parsedate_to_datetime(response.headers.get("date", ""))
        except (TypeError, ValueError):
            continue
        return (datetime.now(UTC) - server_time).total_seconds()
    if not reached:
        raise Unreachable
    return None


async def check_live_feed(
    client: AngelOneClient, session: Session, ws_connect: Callable[..., Any], say: Printer
) -> bool:
    headers = ws_headers(client.api_key, client.client_code, session)
    try:
        async with ws_connect(
            WS_URL, additional_headers=headers, open_timeout=15, close_timeout=5
        ) as ws:
            await ws.send(subscribe_message({NSE: [NIFTY_TOKEN]}))
            loop = asyncio.get_running_loop()
            deadline = loop.time() + LIVE_FEED_WAIT_SECONDS
            while (remaining := deadline - loop.time()) > 0:
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except TimeoutError:
                    break
                if isinstance(message, bytes):
                    tick = parse_tick(message)
                    if tick.token == NIFTY_TOKEN:
                        price = format_inr(tick.ltp)
                        say(f"  OK  Live feed works: tick received, NIFTY 50 at {price}")
                        return True
    except InvalidStatus as exc:
        say(f"  X   Live feed refused the connection (HTTP {exc.response.status_code})")
        return False
    except (WebSocketException, OSError, TimeoutError, ValueError) as exc:
        say(f"  X   Could not connect to the live feed: {exc}")
        return False

    if market_hours.is_market_open():
        say("  !   Connected to the live feed, but no tick arrived in 10 seconds. Try again.")
        return False
    say("  OK  Connected to the live feed (no ticks right now because the market is closed)")
    return True


async def run(
    settings: Settings,
    http: httpx.AsyncClient,
    ws_connect: Callable[..., Any] = websockets.connect,
    say: Printer = print,
) -> bool:
    say("Checking your Angel One settings...")
    problems = check_settings(settings)
    if problems:
        for problem in problems:
            say(f"  X   {problem}")
        say("Fix these in .env and run the check again. (No login was attempted.)")
        return False
    say(f"  OK  All 4 values are filled in (client code {mask(settings.angelone_client_code)})")

    try:
        drift = await clock_drift(http)
    except Unreachable:
        say("  X   Could not reach Angel One (apiconnect.angelone.in). Is the internet working?")
        return False
    if drift is None:
        say("  !   Could not check the clock (Angel One didn't send the time). Continuing.")
    elif abs(drift) > MAX_CLOCK_DRIFT_SECONDS:
        say(
            f"  X   Docker's clock is off by {abs(drift):.0f} seconds, so the TOTP code would be "
            "wrong. Quit and restart Docker Desktop (this often happens after the PC sleeps), "
            "then run the check again. (No login was attempted.)"
        )
        return False
    else:
        say(f"  OK  Clock is correct (within {abs(drift):.0f} s of Angel One)")

    client = AngelOneClient(
        settings.angelone_api_key,
        settings.angelone_client_code,
        settings.angelone_pin.get_secret_value(),
        settings.angelone_totp_secret.get_secret_value(),
        http=http,
    )
    try:
        session = await client.login()
    except LoginRejected as exc:
        say(f"  X   {exc}")
        say("Fix .env, then wait at least a minute before trying again.")
        say("Many wrong logins in a row can get your Angel One account blocked.")
        return False
    except ProviderError as exc:
        say(f"  X   Login did not go through: {exc}")
        say("This is usually temporary on Angel One's side. Try again in a few minutes.")
        return False
    say("  OK  Logged in to Angel One")

    try:
        rows = await client.quote({"NSE": [NIFTY_TOKEN]})
    except ProviderError as exc:
        say(f"  X   Could not get the NIFTY 50 price: {exc}")
        return False
    row = next((r for r in rows if str(r.get("symbolToken")) == NIFTY_TOKEN), None)
    if row is None or row.get("ltp") is None:
        say(f"  X   Angel One did not return NIFTY 50 (token {NIFTY_TOKEN})")
        return False
    say(
        f"  OK  {row.get('tradingSymbol') or 'NIFTY 50'} price: {format_inr(row['ltp'])} "
        f"(as of {row.get('exchFeedTime') or 'unknown time'} IST)"
    )

    start, end = intraday_window()
    try:
        candles = await client.candles("NSE", NIFTY_TOKEN, start, end)
        say(f"  OK  Chart data: {len(candles)} one-minute candles for {start:%d %b %Y}")
    except ProviderError as exc:
        # Not fatal: the live price and alerts work without the chart.
        say(f"  !   Chart data not available: {exc}")

    if not await check_live_feed(client, session, ws_connect, say):
        return False

    say("")
    say("All good! To use live Angel One prices, set these in .env:")
    say("    MARKET_DATA_PROVIDER=angelone")
    say("    FALLBACK_PROVIDER=yahoo")
    say("then run:  docker compose up -d")
    return True


async def main() -> int:
    async with httpx.AsyncClient(timeout=15) as http:
        ok = await run(get_settings(), http)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
