"""A small Redis lock so only ONE market worker talks to the broker at a time.

Start two workers and the second waits on standby. If the active one dies, its lock
expires after `ttl` seconds and the standby takes over automatically.
"""

import asyncio
import logging

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Renew or release only if we still own the lock (compare-and-set in one atomic step).
_RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('pexpire', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


class LockLostError(RuntimeError):
    pass


class RedisLock:
    def __init__(self, redis: Redis, key: str, owner: str, ttl_seconds: int = 15) -> None:
        self.redis = redis
        self.key = key
        self.owner = owner
        self.ttl_ms = ttl_seconds * 1000

    async def try_acquire(self) -> bool:
        return bool(await self.redis.set(self.key, self.owner, nx=True, px=self.ttl_ms))

    async def acquire(self, poll_seconds: float = 5.0) -> None:
        announced = False
        while not await self.try_acquire():
            if not announced:
                logger.info("Another worker holds the market feed; waiting on standby")
                announced = True
            await asyncio.sleep(poll_seconds)
        logger.info("Acquired market feed lock (%s)", self.owner)

    async def keep_alive(self) -> None:
        """Renew forever; raises LockLostError if someone else now owns the lock."""
        interval = self.ttl_ms / 1000 / 3
        while True:
            await asyncio.sleep(interval)
            renewed = await self.redis.eval(_RENEW_SCRIPT, 1, self.key, self.owner, self.ttl_ms)
            if not renewed:
                raise LockLostError("Market feed lock was lost")

    async def release(self) -> None:
        await self.redis.eval(_RELEASE_SCRIPT, 1, self.key, self.owner)
