"""ARC SDK — the unified :class:`ARC` facade.

``ARC`` is the single entrypoint developers import. It composes the runtime
engines (recorder, firewall, recovery, verifier), the middleware pipeline, the
plugin registry, and the event bus behind one small, stable surface.

This module defines the **public API only**. Extension-point registration
(``middleware``/``plugin``/``event``) records handlers into in-memory
registries — pure wiring with no dispatch behaviour — while the execution
methods (``wrap``/``run``/``trace``/``recover``/``verify``/``replay``/
``inspect``) declare their typed contracts and raise
:class:`~arc.exceptions.NotImplementedError` until the runtime engines are wired in.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Dict, List, Optional, Type, Union

from ._agent import WrappedAgent, _detect_framework
from ._runtime import ARCRuntime
from .config import ARCConfig
from .exceptions import ConfigurationError
from .types import (
    EventHandler,
    ExecutionPlan,
    Middleware,
    Plugin,
    RecoveryPlan,
    ReplayTimeline,
    RequestContext,
    Runnable,
    Session,
    SessionStatus,
    TraceStep,
    VerificationResult,
)

_SCAFFOLD = (
    "arc-sdk ships the public API and package structure only; the runtime "
    "engine behind ARC.{method}() is not yet wired in."
)

_NO_CLIENT = (
    "No provider client attached. Construct ARC with one — e.g. "
    "ARC(anthropic.Anthropic()) — then call arc.messages.create(...)."
)


class ARC:
    """Unified reliability runtime facade for AI agents.

    Example
    -------
    >>> from anthropic import Anthropic          # doctest: +SKIP
    >>> from arc import ARC                       # doctest: +SKIP
    >>> arc = ARC(Anthropic())                    # doctest: +SKIP
    >>> arc.messages.create(...)                  # doctest: +SKIP
    """

    def __init__(
        self,
        client: Optional[Any] = None,
        *,
        api_key: Optional[str] = None,
        provider_api_key: Optional[str] = None,
        server_url: Optional[str] = None,
        dashboard_url: Optional[str] = None,
        config: Optional[ARCConfig] = None,
        planner: Optional[Any] = None,
        verifiers: Optional[List[Any]] = None,
        **options: Any,
    ) -> None:
        self._provider_client = client
        self._config: ARCConfig = config or ARCConfig.from_env(
            api_key=api_key,
            provider_api_key=provider_api_key,
            server_url=server_url,
            dashboard_url=dashboard_url,
            **options,
        )
        self._middleware: List[Any] = []
        self._plugins: List[Any] = []
        self._event_handlers: Dict[str, List[Any]] = {}
        self._runtime = ARCRuntime(
            self._config,
            get_middleware=lambda: list(self._middleware),
            get_handlers=lambda name: list(self._event_handlers.get(name, [])),
            planner=planner,
            verifiers=verifiers,
        )

    # -- transport interception ------------------------------------------

    @property
    def messages(self) -> Any:
        """Intercepting proxy over ``client.messages`` (``create`` / ``stream``).

        For async clients use :attr:`async_messages` or wrap the client with
        :meth:`wrap` which returns an :class:`~arc.integrations.anthropic.wrapper.AsyncAnthropicClientWrapper`.
        """
        if self._provider_client is None:
            raise ConfigurationError(_NO_CLIENT)
        return self._provider_client.messages

    @property
    def async_messages(self) -> Any:
        """Async intercepting proxy for ``AsyncAnthropic`` clients."""
        if self._provider_client is None:
            raise ConfigurationError(_NO_CLIENT)
        return self._provider_client.async_messages

    @property
    def beta(self) -> Any:
        """Intercepting proxy over ``client.beta`` (e.g. MCP via ``beta.messages``)."""
        if self._provider_client is None:
            raise ConfigurationError(_NO_CLIENT)
        return self._provider_client.beta

    @property
    def async_beta(self) -> Any:
        """Async intercepting proxy over ``client.beta`` for ``AsyncAnthropic`` clients."""
        if self._provider_client is None:
            raise ConfigurationError(_NO_CLIENT)
        return self._provider_client.async_beta

    @property
    def session_id(self) -> str:
        """Identifier of the current interception session."""
        return self._runtime.session_id

    @property
    def dashboard_url(self) -> str:
        """Live dashboard URL for the current session."""
        return self._runtime.dashboard_url

    def _require_client(self) -> Any:
        if self._provider_client is None:
            raise ConfigurationError(_NO_CLIENT)
        return self._provider_client

    # -- introspection ----------------------------------------------------

    @property
    def config(self) -> ARCConfig:
        """The resolved, immutable configuration for this instance."""
        return self._config

    @property
    def planner(self) -> Any:
        """The Adaptive Planner — the first middleware. Assignable to swap it."""
        return self._runtime.planner

    @planner.setter
    def planner(self, planner: Any) -> None:
        self._runtime.planner = planner

    @property
    def verification(self) -> Any:
        """The Verification Engine that derives confidence from evidence."""
        return self._runtime.verification

    def verifier(self, verifier: Any) -> Any:
        """Register a verification plugin; usable directly or as a decorator.

        >>> arc.verifier(JSONSchemaVerifier(schema))              # doctest: +SKIP
        >>> arc.verifier(AssertionVerifier({"has_price": ...}))   # doctest: +SKIP
        """
        self._runtime.verification.register(verifier)
        return verifier

    def plan(self, **request: Any) -> Any:
        """Preview the execution plan for a request without calling the model.

        Accepts the same generic request kwargs as ``messages.create`` (plus an
        optional ``arc_context_sources``); no provider-specific keys are required.
        """
        context_sources = request.pop("arc_context_sources", None) or []
        ctx = RequestContext(
            session_id=self.session_id,
            provider=self._config.provider,
            payload=request,
            context_sources=list(context_sources),
        )
        return self._runtime.planner.plan(ctx)

    def graph(self, **request: Any) -> Any:
        """Preview the execution graph a request would run through.

        The graph — not this facade — is the source of truth for runtime
        behaviour: which nodes exist (firewall, dispatch, record, verify,
        recover, replay) is derived entirely from the plan. No model call is made.
        """
        streaming = request.pop("stream", None) is True
        plan = self.plan(**request)
        return build_execution_graph(plan, observable=not streaming, streaming=streaming)

    @property
    def middlewares(self) -> List[Any]:
        """Registered middleware, in registration (outermost-first) order."""
        return list(self._middleware)

    @property
    def plugins(self) -> List[Any]:
        """Registered plugins."""
        return list(self._plugins)

    # -- execution surface (contracts only) -------------------------------

    def wrap(
        self,
        client: Any,
        *,
        name: str = "ARC Wrapped Agent",
        task: str = "Protected task",
        provider: Optional[str] = None,
    ) -> Any:
        """Wrap a provider/agent client so every call runs through ARC.

        ARC automatically:

        * intercepts execution (calls routed through the ARC pipeline)
        * records runtime (Flight Recorder step per call)
        * injects middleware (registered middleware chain runs around each step)
        * manages context (Context Firewall screens inputs)
        * verifies outputs (ConfidenceVerifier scores every response)
        * recovers failures (RecoveryEngine checkpoints before each step)
        * emits events (``step_recorded``, ``recovery_triggered``, etc.)

        The wrapped object **preserves the original API exactly** via
        ``__getattr__`` delegation — developers never rewrite agent code.

        Supported agent types (detected by duck-typing):

        * **Anthropic SDK** client — ``messages.create``/``stream`` intercepted
          via the full transport proxy.
        * **LangGraph** ``CompiledGraph`` — ``invoke``/``stream`` intercepted.
        * **CrewAI** ``Crew`` — ``kickoff``/``kickoff_async`` intercepted.
        * **AutoGen** ``ConversableAgent`` — ``initiate_chat``/``receive``/
          ``generate_reply`` intercepted.
        * **OpenHands** runtime — ``run_task``/``run`` intercepted.
        * **OpenAI Agents SDK** ``Agent``/``Runner`` — ``run``/``run_sync``
          intercepted.
        * **Generic Python callable** — ``__call__`` intercepted.

        :param client: An agent client or callable to protect.
        :param name: Human-readable agent name recorded on the session.
        :param task: Task/goal description recorded on the session.
        :param provider: Reserved for future provider-adapter override.
        :returns: A drop-in replacement with identical call signatures.

        Example::

            wrapped = arc.wrap(my_agent)
            result  = wrapped.invoke(input)   # exactly the original API
            print(wrapped.arc_trace())        # introspect recorded steps
        """
        framework = _detect_framework(client)

        # Async Anthropic client — full async transport proxy.
        if framework == "async_anthropic":
            from ._transport import AsyncAnthropicClientWrapper
            return AsyncAnthropicClientWrapper(client, self._runtime)

        # Sync Anthropic SDK gets the full sync transport proxy.
        if framework == "anthropic":
            from ._transport import AnthropicClientWrapper
            return AnthropicClientWrapper(client, self._runtime)

        # All other frameworks and generic callables go through WrappedAgent.
        return WrappedAgent(client, self._runtime, name=name, task=task)

    def run(
        self,
        target: Any,
        *args: Any,
        name: str = "ARC Managed Run",
        task: str = "Execute task",
        **kwargs: Any,
    ) -> Any:
        """Execute a callable/agent once under full ARC protection.

        Convenience one-shot equivalent of::

            wrapped = arc.wrap(target, name=name, task=task)
            result  = wrapped(*args, **kwargs)

        :param target: Callable or object exposing ``invoke``.
        :param name: Step label recorded in the Flight Recorder.
        :param task: Task description (informational).
        :returns: The target's return value, after recording and verification.
        """
        if callable(target):
            return self._runtime.run_agent_call(
                invoke=lambda: target(*args, **kwargs),
                args=args,
                kwargs=kwargs,
                name=name,
            )
        # SupportsInvoke path
        invoke_fn = getattr(target, "invoke", None)
        if invoke_fn is not None and callable(invoke_fn):
            return self._runtime.run_agent_call(
                invoke=lambda: invoke_fn(*args, **kwargs),
                args=args,
                kwargs=kwargs,
                name=name,
            )
        raise TypeError(
            f"arc.run() requires a callable or an object with an 'invoke' method; "
            f"got {type(target).__name__!r}"
        )

    def trace(self, session_id: Optional[str] = None) -> List[Any]:
        """Return the ordered Flight Recorder steps for a session.

        Defaults to the current interception session.
        """
        return self._runtime.recorder.trace(session_id or self.session_id)

    def recover(self, session_id: Optional[str] = None) -> Any:
        """Return the recovery plan for a session (current session by default)."""
        return self._runtime.recovery.plan(session_id or self.session_id)

    def verify(
        self,
        session_or_trace: Any = None,
        rules: Optional[List[Any]] = None,
    ) -> Any:
        """Verify a session id, an explicit trace, or the current session."""
        if session_or_trace is None:
            trace = self.trace()
        elif isinstance(session_or_trace, str):
            trace = self.trace(session_or_trace)
        else:
            trace = [
                s if isinstance(s, TraceStep) else TraceStep.model_validate(s)
                for s in session_or_trace
            ]
        return self._runtime.verifier.verify(trace, rules)

    def replay(self, session_id: Optional[str] = None) -> Any:
        """Return a deterministic, replayable timeline for a session."""
        return self._runtime.replay.timeline(session_id or self.session_id)

    def inspect(self, session_id: Optional[str] = None) -> Any:
        """Return the session record and aggregate telemetry."""
        sid = session_id or self.session_id
        steps = self.trace(sid)
        total_tokens = sum(
            (s.token_usage.get("input_tokens", 0) + s.token_usage.get("output_tokens", 0))
            for s in steps
        )
        failed = any(s.error or s.confidence_score < self._config.confidence_threshold for s in steps)
        if not steps:
            status = SessionStatus.ACTIVE
        else:
            status = SessionStatus.FAILED if failed else SessionStatus.COMPLETED
        return Session(
            session_id=sid,
            agent_name=self._config.provider,
            task="Intercepted provider session",
            status=status,
            total_steps=len(steps),
            total_tokens=total_tokens,
            metadata={"dashboard_url": self._runtime.dashboard_url},
        )

    # -- extension points (registration wiring) ---------------------------

    def middleware(self, mw: Optional[Any] = None) -> Any:
        """Register a middleware; usable directly or as a decorator.

        >>> @arc.middleware                              # doctest: +SKIP
        ... def logging_mw(request, call_next):
        ...     return call_next(request)
        """

        def _register(candidate: Any) -> Any:
            if not callable(candidate):
                from .exceptions import MiddlewareError

                raise MiddlewareError("Middleware must be callable.")
            self._middleware.append(candidate)
            return candidate

        return _register if mw is None else _register(mw)  # type: ignore[return-value]

    def plugin(
        self, plugin: Optional[Union[Any, type[Any]]] = None
    ) -> Union[Any, type[Any]]:
        """Register a plugin instance or class; usable as a decorator.

        Registration only records the plugin; ``Plugin.setup`` is invoked by the
        runtime, which this scaffold does not implement.
        """

        def _register(
            candidate: Union[Any, type[Any]]
        ) -> Union[Any, type[Any]]:
            instance = candidate() if isinstance(candidate, type) else candidate
            self._plugins.append(instance)
            return candidate

        return _register if plugin is None else _register(plugin)

    def event(self, name: str) -> Any:
        """Return a decorator registering a handler for an event ``name``.

        >>> @arc.event("step_recorded")                 # doctest: +SKIP
        ... def on_step(evt):
        ...     ...
        """

        def _register(handler: Any) -> Any:
            self._event_handlers.setdefault(name, []).append(handler)
            return handler

        return _register

    def handlers(self, name: str) -> List[Any]:
        """Return the handlers registered for event ``name`` (empty if none)."""
        return list(self._event_handlers.get(name, []))

    # -- lifecycle --------------------------------------------------------

    def close(self) -> None:
        """Tear down registered plugins. The in-memory runtime holds no OS resources."""
        for plugin in self._plugins:
            teardown = getattr(plugin, "teardown", None)
            if callable(teardown):
                try:
                    teardown(self)
                except Exception:  # noqa: BLE001 - teardown must not raise on close
                    pass

    def __enter__(self) -> "ARC":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[Type[BaseException]],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self.close()
        return None

    def __repr__(self) -> str:
        return (
            f"ARC(server_url={self._config.server_url!r}, "
            f"provider={self._config.provider!r}, "
            f"middleware={len(self._middleware)}, plugins={len(self._plugins)})"
        )


__all__ = ["ARC"]