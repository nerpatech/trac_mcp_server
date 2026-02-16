"""Async utilities for bridging sync XML-RPC calls to async MCP handlers."""

import asyncio
import logging
from typing import Any, Callable, Coroutine, Sequence, TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)

# Module-level semaphore, initialized at server startup
_semaphore: asyncio.Semaphore | None = None


def init_semaphore(max_parallel: int = 2) -> None:
    """Initialize the concurrency semaphore. Call once at server startup."""
    global _semaphore
    _semaphore = asyncio.Semaphore(max_parallel)
    logger.info(
        "Trac request semaphore initialized: max_parallel=%d",
        max_parallel,
    )


async def run_sync(
    func: Callable[..., T], *args: Any, **kwargs: Any
) -> T:
    """Run a synchronous function in a thread pool without blocking the event loop.

    This is used to wrap synchronous XML-RPC calls in async MCP tool handlers.
    Does NOT acquire the semaphore (backward-compatible, unchanged behavior).

    Args:
        func: Synchronous function to call
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        Result of func(*args, **kwargs)

    Example:
        # In MCP tool handler:
        client = TracClient(config)
        ticket = await run_sync(client.get_ticket, ticket_id)
    """
    return await asyncio.to_thread(func, *args, **kwargs)


async def run_sync_limited(
    func: Callable[..., T], *args: Any, **kwargs: Any
) -> T:
    """Run a synchronous function in a thread pool, bounded by the concurrency semaphore.

    Falls back to unbounded if semaphore not initialized.

    Args:
        func: Synchronous function to call
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        Result of func(*args, **kwargs)
    """
    if _semaphore is None:
        return await asyncio.to_thread(func, *args, **kwargs)
    async with _semaphore:
        return await asyncio.to_thread(func, *args, **kwargs)


async def gather_limited(
    coros: Sequence[Coroutine[Any, Any, T]],
) -> list[T]:
    """Run coroutines concurrently, bounded by the semaphore.

    Each coroutine should use run_sync_limited internally.
    Returns results in order. Exceptions propagate from the first failure.

    Args:
        coros: Sequence of coroutines to run concurrently.

    Returns:
        List of results in the same order as input coroutines.
    """
    return list(await asyncio.gather(*coros))
