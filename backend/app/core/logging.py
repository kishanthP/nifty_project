import logging


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Third-party libraries are noisy at INFO.
    for noisy in ("httpx", "httpcore", "websockets", "urllib3", "google"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
