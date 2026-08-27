"""Transparent interception proxies for a provider SDK client.

``ARC(client)`` exposes ``arc.messages`` and ``arc.beta`` (and any nested
namespace) as proxies that forward calls to the wrapped SDK **unchanged**, running each
``messages.create`` / ``messages.stream`` through the :class:`~._runtime.ARCRuntime` pipeline.  Every other attribute
(``count_tokens``, ``models``, ``batches``, …) passes straight through, so the
proxy is a drop-in for the real client.

Sync and async SDK clients are both supported:

* Sync  — :class:`_MessagesProxy`, :class:`_StreamManagerProxy`,
  :class:`_NamespaceProxy`
* Async — :class:`AsyncMessagesProxy`, :class:`AsyncStreamManagerProxy`,
  :class:`AsyncNamespaceProxy`

The underlying SDK itself is never modified, and request kwargs / response
objects are never mutated — streaming, tool calls, extended thinking, and MCP
all flow through untouched.
"""

from __future__ import annotations

import time
from types import TracebackType
from typing import Any, Dict, List, Optional, Type

from ._runtime import ARCRuntime


def _split_arc_kwargs(kwargs: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pop ARC-only kwargs so they never reach the SDK."""
    return kwargs.pop("arc_context_sources", None) or []


# ---------------------------------------------------------------------------
# Sync transport proxies
# ---------------------------------------------------------------------------

class _StreamManagerProxy:
    """Wraps a provider stream context manager, recording once it completes.

    Delegates the object yielded by ``__enter__`` to the real stream, so
    ``stream.text_stream`` / ``stream.get_final_message()`` behave normally.
    """

    def __init__(
        self,
        manager: Any,
        runtime: ARCRuntime,
        payload: Dict[str, Any],
        context_sources: List[Dict[str, Any]],
    ) -> None:
        self._manager = manager
        self._runtime = runtime
        self._payload = payload
        self._context_sources = context_sources
        self._stream: Any = None
        self._step_number = 0
        self._start = time.perf_counter()

    def __enter__(self) -> Any:
        self._step_number = self._runtime.begin_stream(self._payload, self._context_sources)
        return self._manager.__enter__()

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[Type[BaseException]],
        exc_tb: Optional[TracebackType],
    ) -> Any:
        suppressed = self._manager.__exit__(exc_type, exc_val, exc_tb)
        latency = (time.perf_counter() - self._start) * 1000.0
        final_message, error = None, None
        if exc_val is not None:
            error = str(exc_val)
        else:
            try:
                final_message = self._stream.get_final_message()
            except Exception:  # noqa: BLE001 - stream may be unconsumed
                error = "final message unavailable"
        self._runtime.finish_stream(
            self._step_number, self._payload, latency, final_message, error
        )
        return suppressed

    def __getattr__(self, name: str) -> Any:
        return getattr(self._manager, name)


class _MessagesProxy:
    """Intercepts ``create`` / ``stream``; passes everything else through."""

    def __init__(self, target: Any, runtime: ARCRuntime) -> None:
        self._target = target
        self._runtime = runtime

    def create(self, **kwargs: Any) -> Any:
        context_sources = _split_arc_kwargs(kwargs)
        return self._runtime.run_create(
            kwargs, lambda payload: self._target.create(**payload), context_sources
        )

    def stream(self, **kwargs: Any) -> _StreamManagerProxy:
        context_sources = _split_arc_kwargs(kwargs)
        manager = self._target.stream(**kwargs)
        return _StreamManagerProxy(manager, self._runtime, kwargs, context_sources)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target, name)


# ---------------------------------------------------------------------------
# Async transport proxies
# ---------------------------------------------------------------------------

class AsyncStreamManagerProxy:
    """Wraps a provider *async* stream context manager, recording on exit.

    Usage::

        async with arc.messages.stream(...) as stream:
            async for text in stream.text_stream:
                print(text)
    """

    def __init__(
        self,
        manager: Any,
        runtime: ARCRuntime,
        payload: Dict[str, Any],
        context_sources: List[Dict[str, Any]],
    ) -> None:
        self._manager = manager
        self._runtime = runtime
        self._payload = payload
        self._context_sources = context_sources
        self._stream: Any = None
        self._step_number = 0
        self._start = time.perf_counter()

    async def __aenter__(self) -> Any:
        self._step_number = await self._runtime.async_begin_stream(
            self._payload, self._context_sources
        )
        self._start = time.perf_counter()
        self._stream = await self._manager.__aenter__()
        return self._stream

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[Type[BaseException]],
        exc_tb: Optional[TracebackType],
    ) -> Any:
        suppressed = await self._manager.__aexit__(exc_type, exc_val, exc_tb)
        latency = (time.perf_counter() - self._start) * 1000.0
        final_message, error = None, None
        if exc_val is not None:
            error = str(exc_val)
        else:
            try:
                final_message = await self._stream.get_final_message()
            except Exception:  # noqa: BLE001 - stream may be unconsumed
                error = "final message unavailable"
        await self._runtime.async_finish_stream(
            self._step_number, self._payload, latency, final_message, error
        )
        return suppressed

    def __getattr__(self, name: str) -> Any:
        return getattr(self._manager, name)


class AsyncMessagesProxy:
    """Intercepts async ``create`` / ``stream``; passes everything else through."""

    def __init__(self, target: Any, runtime: ARCRuntime) -> None:
        self._target = target
        self._runtime = runtime

    async def create(self, **kwargs: Any) -> Any:
        context_sources = _split_arc_kwargs(kwargs)
        target = self._target

        async def _invoke(payload: Dict[str, Any]) -> Any:
            return await target.create(**payload)

        return await self._runtime.async_run_create(kwargs, _invoke, context_sources)

    def stream(self, **kwargs: Any) -> AsyncStreamManagerProxy:
        context_sources = _split_arc_kwargs(kwargs)
        manager = self._target.stream(**kwargs)
        return AsyncStreamManagerProxy(manager, self._runtime, kwargs, context_sources)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target, name)


class AsyncNamespaceProxy:
    """Async-aware proxy for resource namespaces (e.g. ``client.beta``).

    Same recursive design as :class:`_NamespaceProxy` but returns
    :class:`AsyncMessagesProxy` for ``messages`` children.
    """

    def __init__(self, target: Any, runtime: ARCRuntime) -> None:
        self._target = target
        self._runtime = runtime

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._target, name)
        if name == "messages":
            return AsyncMessagesProxy(attr, self._runtime)
        # Recursively proxy any sub-namespace that itself has a 'messages' child
        if hasattr(attr, "messages"):
            return AsyncNamespaceProxy(attr, self._runtime)
        return attr


__all__ = [
    # Sync
    "_MessagesProxy",
    "_NamespaceProxy",
    "_StreamManagerProxy",
    # Async
    "AsyncMessagesProxy",
    "AsyncNamespaceProxy",
    "AsyncStreamManagerProxy",
]