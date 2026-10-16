import logging

from app.core.config import ProviderName, Settings
from app.services.market_data.angelone import AngelOneProvider
from app.services.market_data.base import MarketDataProvider, ProviderConfigError
from app.services.market_data.failover import FailoverProvider
from app.services.market_data.mock import MockProvider
from app.services.market_data.yahoo import YahooProvider

logger = logging.getLogger(__name__)


def _build_single(name: ProviderName, settings: Settings) -> MarketDataProvider:
    if name == "mock":
        return MockProvider(
            start_price=settings.mock_start_price,
            volatility=settings.mock_volatility,
            tick_seconds=settings.mock_tick_seconds,
        )
    if name == "yahoo":
        return YahooProvider(poll_seconds=settings.yahoo_poll_seconds)
    if name == "angelone":
        return AngelOneProvider(
            api_key=settings.angelone_api_key,
            client_code=settings.angelone_client_code,
            pin=settings.angelone_pin.get_secret_value(),
            totp_secret=settings.angelone_totp_secret.get_secret_value(),
            relogin_time=settings.angelone_relogin_time,
        )
    raise ProviderConfigError(f"Unknown market data provider: {name}")


def build_provider(settings: Settings) -> MarketDataProvider:
    """Create the provider chosen by MARKET_DATA_PROVIDER (+ optional FALLBACK_PROVIDER)."""
    fallback_name = settings.fallback_provider
    if fallback_name == settings.market_data_provider:
        fallback_name = None
    try:
        primary = _build_single(settings.market_data_provider, settings)
    except ProviderConfigError as exc:
        if not fallback_name:
            raise
        logger.error("%s — using fallback provider %s only", exc, fallback_name)
        return _build_single(fallback_name, settings)
    if fallback_name:
        backup = _build_single(fallback_name, settings)
        return FailoverProvider(primary, backup, settings.fallback_after_seconds)
    return primary
