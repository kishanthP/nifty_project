"""Settings and helpers used when hosting on Render + Supabase (deploy/FREE-CLOUD.md)."""

import asyncio
import base64
import logging

import pytest

from app.core.config import Settings
from app.core.firebase import _credentials_from_json
from app.workers import market_worker


@pytest.mark.parametrize(
    "given",
    [
        "postgresql://user:pw@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres",
        "postgres://user:pw@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres",
        "postgresql+asyncpg://user:pw@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres",
    ],
)
def test_hosted_database_urls_use_the_async_driver(given: str) -> None:
    url = Settings(database_url=given).database_url
    assert (
        url == "postgresql+asyncpg://user:pw@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"
    )


@pytest.mark.parametrize("raw", ['{"type": "service_account"}', "not json", "bm90IGpzb24="])
def test_bad_firebase_json_is_rejected_without_logging_it(
    raw: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        assert _credentials_from_json(raw) is None
    assert "FIREBASE_CREDENTIALS_JSON" in caplog.text
    assert raw not in caplog.text
    assert base64.b64decode("bm90IGpzb24=").decode() not in caplog.text


async def test_embedded_worker_restarts_after_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    runs: list[int] = []
    second_run_started = asyncio.Event()

    class FlakyWorker:
        def __init__(self, settings: Settings) -> None:
            pass

        async def run(self) -> None:
            runs.append(1)
            if len(runs) == 1:
                raise RuntimeError("feed broke")
            second_run_started.set()
            await asyncio.Event().wait()  # runs until cancelled

    monkeypatch.setattr(market_worker, "MarketWorker", FlakyWorker)
    monkeypatch.setattr(market_worker, "EMBEDDED_RESTART_SECONDS", 0)
    task = asyncio.create_task(market_worker.run_embedded(Settings()))
    await asyncio.wait_for(second_run_started.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(runs) == 2
