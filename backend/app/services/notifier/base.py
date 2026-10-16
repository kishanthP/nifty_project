from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class PushMessage:
    title: str
    body: str
    data: dict[str, str] = field(default_factory=dict)
    tag: str | None = None  # same tag = the browser replaces instead of stacking


@dataclass
class SendResult:
    success_count: int = 0
    failure_count: int = 0
    invalid_tokens: list[str] = field(default_factory=list)  # remove these from the database
    error: str | None = None
    retryable: bool = False


class Notifier(Protocol):
    channel: str

    async def send(self, tokens: list[str], message: PushMessage) -> SendResult: ...
