"""ARC Runtime — the graph-driven interception orchestrator.

Every model request is compiled by the Adaptive Planner into an
:class:`~._runtime.graph.ExecutionGraph`, which is the **source of truth** for
runtime behaviour. A :class:`~._runtime.graph.executor.EventDrivenGraphExecutor`
walks that graph and publishes events on an internal
:class:`~._runtime.graph.bus.InProcessGraphBus`; the runtime services
(firewall, recorder, verifier, recovery, replay) **subscribe** to those events
and coordinate only through a shared ``ExecutionContext`` — they never call one
another directly. The end-to-end shape remains::

    Middleware -> [graph: firewall -> dispatch -> record -> verify -> recover
                   -> replay] -> Dashboard

The provider's response object is returned to the caller **unchanged** — the
runtime only observes it for recording. Both sync and async Anthropic client
shapes are supported, including streaming, tool use, and MCP.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from .config import ARCConfig
from .integrations.adapter import make_provider_adapter
from .runtime.events.default import DefaultEventBus
from .runtime.firewall.default import ContextFirewall
from .runtime.graph import ExecutionContext, ExecutionGraph
from .runtime.graph.builder import build_execution_graph
from .runtime.graph.bus import InProcessGraphBus
from .runtime.graph.executor import EventDrivenGraphExecutor
from .runtime.graph.services import RuntimeServices
from .runtime.middleware.default import MiddlewarePipeline
from .runtime.planner import Planner
from .runtime.planner.default import AdaptivePlanner, make_planner_middleware
from .runtime.recorder.default import FlightRecorder
from .runtime.recovery.default import RecoveryEngine
from .runtime.replay import DefaultReplayStore
from .runtime.verification import Verifier
from .runtime.verification.engine import DefaultVerificationEngine
from .runtime.verification.plugins import ResponseIntegrityVerifier
from .runtime.verifier.default import ConfidenceVerifier
from .types import (
    Event,
    EventHandler,
    EventType,
    ExecutionPlan,
    Middleware,
    RequestContext,
    ResponseContext,
    StepType,
    TraceStep,
)

_STRICT_MIN_CONFIDENCE = 0.7

Invoke = Callable[[Dict[str, Any]], Any]


def extract_response(
    raw: Any,
) -> Tuple[str, Dict[str, int], List[str], Optional[str], bool]:
    """Observe a provider response without mutating it.

    Returns ``(text, token_usage, tool_names, stop_reason, has_thinking)``.

    Handles:
    * Anthropic ``Message`` — typed content blocks (text, thinking, tool_use)
    * Plain ``dict`` with a ``content`` key
    * Bare ``str``
    """
    text_parts: List[str] = []
    tool_names: List[str] = []
    has_thinking = False

    content = getattr(raw, "content", None)
    if content is None and isinstance(raw, dict):
        content = raw.get("content")

    if isinstance(content, list):
        for block in content:
            # Resolve block type from attribute or dict key
            btype: Optional[str] = getattr(block, "type", None)
            if btype is None and isinstance(block, dict):
                btype = block.get("type")

            if btype == "text":
                txt = (
                    block.get("text", "") if isinstance(block, dict)
                    else getattr(block, "text", "") or ""
                )
                text_parts.append(txt)
            elif btype == "thinking":
                # Extended thinking block — record presence but not content
                has_thinking = True
            elif btype == "tool_use":
                name = (
                    block.get("name") if isinstance(block, dict)
                    else getattr(block, "name", None)
                ) or "tool"
                tool_names.append(name)
            elif btype is None and hasattr(block, "text"):
                # Fallback: un-typed block that carries .text
                text_parts.append(getattr(block, "text", "") or "")
    elif isinstance(content, str):
        text_parts.append(content)
    elif isinstance(raw, str):
        text_parts.append(raw)

    usage_obj = (
        getattr(raw, "usage", None)
        or (raw.get("usage") if isinstance(raw, dict) else None)
    )
    usage: Dict[str, int] = {}
    if usage_obj is not None:
        usage = {
            "input_tokens": int(
                usage_obj.get("input_tokens", 0)
                if isinstance(usage_obj, dict)
                else getattr(usage_obj, "input_tokens", 0) or 0
            ),
            "output_tokens": int(
                usage_obj.get("output_tokens", 0)
                if isinstance(usage_obj, dict)
                else getattr(usage_obj, "output_tokens", 0) or 0
            ),
        }

    stop_reason: Optional[str] = getattr(raw, "stop_reason", None)
    if stop_reason is None and isinstance(raw, dict):
        stop_reason = raw.get("stop_reason")

    return "".join(text_parts).strip(), usage, tool_names, stop_reason, has_thinking


class ARCRuntime:
    """Composes the runtime engines and drives the interception pipeline."""

    def __init__(
        self,
        config: ARCConfig,
        *,
        get_middleware: Callable[[], List[Middleware]],
        get_handlers: Callable[[str], List[EventHandler]],
        planner: Optional[Planner] = None,
        verifiers: Optional[List[Verifier]] = None,
    ) -> None:
        self.config = config
        self.session_id = str(uuid.uuid4())
        self.recorder = FlightRecorder()
        self.firewall = ContextFirewall()
        self.recovery = RecoveryEngine()
        # Verification Engine: confidence is derived from these checks. The
        # structural integrity verifier always runs; developers register more.
        self.verification = DefaultVerificationEngine(
            [ResponseIntegrityVerifier(), *(verifiers or [])]
        )
        # Retained for the read-side `arc.verify()` API over recorded steps.
        self.verifier = ConfidenceVerifier(config.confidence_threshold)
        self.events = DefaultEventBus(get_handlers)
        self.planner: Planner = planner or AdaptivePlanner(config)
        # The Adaptive Planner is the first (outermost) middleware; user
        # middleware runs inside it, so everything follows the plan.
        planner_mw = make_planner_middleware(lambda: self.planner, self.events.emit)
        self.pipeline = MiddlewarePipeline(lambda: [planner_mw, *get_middleware()])
        self.replay = DefaultReplayStore(self.recorder, self.recovery, config.confidence_threshold)

        # Graph subsystem: the executor walks planner-generated graphs and the
        # services subscribe to its events (no direct engine-to-engine calls).
        self._graph_bus = InProcessGraphBus()
        self._services = RuntimeServices(
            recorder=self.recorder,
            firewall=self.firewall,
            engine=self.verification,
            recovery=self.recovery,
            replay=self.replay,
            emit_user=self.events.emit,
            dashboard_url=lambda: self.dashboard_url,
            extract_response=extract_response,
            confidence_threshold=config.confidence_threshold,
            strict_min_confidence=_STRICT_MIN_CONFIDENCE,
        )
        self._services.register(self._graph_bus)
        # Provider adapter: translates abstract graph decisions into provider
        # SDK kwargs (e.g. thinking budget → Anthropic `thinking` param).
        _adapter = make_provider_adapter(config.provider)
        self.executor = EventDrivenGraphExecutor(
            self._graph_bus, self.recorder.next_step_number, adapter=_adapter
        )
        self._stream_contexts: Dict[int, ExecutionContext] = {}

    @property
    def dashboard_url(self) -> str:
        """Live dashboard URL for the current session."""
        return f"{self.config.dashboard_url}/sessions/{self.session_id}"

    # -- non-streaming create --------------------------------------------

    def run_create(
        self,
        payload: Dict[str, Any],
        invoke: Invoke,
        context_sources: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        """Run one ``messages.create`` through the graph; return the raw response.

        The middleware onion (planner first) wraps graph compilation; the graph
        is then executed by the event-driven executor.
        """
        request = RequestContext(
            session_id=self.session_id,
            provider=self.config.provider,
            payload=payload,
            context_sources=list(context_sources or []),
        )
        observable = payload.get("stream") is not True
        response_ctx = self.pipeline.execute(
            request, lambda req: self._graph_core(req, invoke, observable)
        )
        return response_ctx.metadata["raw_response"]

    def _graph_core(
        self, req: RequestContext, invoke: Invoke, observable: bool
    ) -> ResponseContext:
        ctx = self._new_context(req, streaming=False, observable=observable, is_async=False)
        self.executor.execute(ctx, invoke)
        return ResponseContext(
            session_id=req.session_id,
            output={"observable": observable},
            step=ctx.step,
            metadata={"raw_response": ctx.response},
        )

    # -- streaming (context-manager) -------------------------------------

    def begin_stream(
        self, payload: Dict[str, Any], context_sources: Optional[List[Dict[str, Any]]]
    ) -> int:
        """Compile the stream graph and run its pre-dispatch nodes.

        Streams bypass the middleware onion, so the planner is invoked directly
        (via :meth:`_new_context`) to honour "plan before the request reaches
        the model". Returns the step number, used to correlate finish_stream.
        """
        request = self._stream_request(payload, context_sources)
        ctx = self._new_context(request, streaming=True, observable=True, is_async=False)
        self.executor.begin_stream(ctx)
        self._stream_contexts[ctx.step_number] = ctx
        return ctx.step_number

    def finish_stream(
        self,
        step_number: int,
        payload: Dict[str, Any],
        latency_ms: float,
        final_message: Any,
        error: Optional[str],
    ) -> Optional[TraceStep]:
        """Run the post-dispatch nodes for a stream once it has completed."""
        ctx = self._stream_contexts.pop(step_number, None)
        if ctx is None:  # unknown stream (defensive) — nothing to record
            return None
        ctx.final_message = final_message
        ctx.error = error
        ctx.latency_ms = latency_ms
        self.executor.finish_stream(ctx)
        return ctx.step

    # -- graph compilation -----------------------------------------------

    def _new_context(
        self,
        request: RequestContext,
        *,
        streaming: bool,
        observable: bool,
        is_async: bool,
    ) -> ExecutionContext:
        """Plan (if needed), build the graph, and assemble the execution context."""
        plan, graph = self._compile(request, streaming=streaming, observable=observable)
        return ExecutionContext(
            request=request,
            plan=plan,
            graph=graph,
            session_id=request.session_id,
            input_summary=self._input_summary(request.payload),
            observable=observable,
            streaming=streaming,
            is_async=is_async,
        )

    def _compile(
        self, request: RequestContext, *, streaming: bool, observable: bool
    ) -> Tuple[ExecutionPlan, ExecutionGraph]:
        # The planner middleware (sync create) pre-plans into request.metadata;
        # every other entrypoint plans here and emits plan_created itself.
        plan: Optional[ExecutionPlan] = request.metadata.get("execution_plan")
        if plan is None:
            plan = self.planner.plan(request)
            self.events.emit(
                Event(
                    type=EventType.PLAN_CREATED.value,
                    session_id=request.session_id,
                    payload=plan.to_dict(),
                )
            )
        graph = build_execution_graph(plan, observable=observable, streaming=streaming)
        request.metadata["execution_graph"] = graph
        self.events.emit(
            Event(
                type=EventType.GRAPH_BUILT.value,
                session_id=request.session_id,
                payload={"nodes": [k.value for k in graph.kinds()]},
            )
        )
        return plan, graph

    def _stream_request(
        self, payload: Dict[str, Any], context_sources: Optional[List[Dict[str, Any]]]
    ) -> RequestContext:
        return RequestContext(
            session_id=self.session_id,
            provider=self.config.provider,
            payload=payload,
            context_sources=list(context_sources or []),
        )

    # -- helpers ----------------------------------------------------------

    def _record_failure(
        self,
        session_id: str,
        step_number: int,
        input_summary: Dict[str, Any],
        error: str,
        latency: float,
    ) -> TraceStep:
        step = self.recorder.record(
            self.recorder.build_step(
                session_id,
                step_number,
                step_type=StepType.LLM_CALL,
                name="provider call (failed)",
                input_data=input_summary,
                error=error,
                latency_ms=latency,
            )
        )
        self.events.emit(
            Event(
                type=EventType.VERIFICATION_FAILED.value,
                session_id=session_id,
                payload={"step_number": step_number, "error": error},
            )
        )
        self._emit_recovery(session_id, step_number)
        return step

    def _emit_recovery(self, session_id: str, step_number: int) -> None:
        plan = self.recovery.plan(session_id, failed_at_step=step_number)
        self.events.emit(
            Event(
                type=EventType.RECOVERY_TRIGGERED.value,
                session_id=session_id,
                payload={"status": plan.status},
            )
        )

    def _emit_recorded(self, session_id: str, step: TraceStep) -> None:
        self.events.emit(
            Event(
                type=EventType.STEP_RECORDED.value,
                session_id=session_id,
                payload={
                    "step_number": step.step_number,
                    "confidence": step.confidence_score,
                    "dashboard_url": self.dashboard_url,
                },
            )
        )

    @staticmethod
    def _input_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
        # Capture request metadata without copying large/opaque message content.
        thinking_val = payload.get("thinking")
        has_thinking = bool(thinking_val) and (
            (isinstance(thinking_val, dict) and thinking_val.get("type") == "enabled")
            or not isinstance(thinking_val, dict)
        )
        return {
            "model": payload.get("model"),
            "message_count": len(payload.get("messages") or []),
            "max_tokens": payload.get("max_tokens"),
            "streaming": bool(payload.get("stream")),
            "has_tools": bool(payload.get("tools")),
            "has_thinking": has_thinking,
            "has_mcp": bool(payload.get("mcp_servers")),
            "betas": list(payload.get("betas") or []),
            "request_metadata": payload.get("metadata") or {},
        }


    # -- agent wrapping ---------------------------------------------------

    def run_agent_call(
        self,
        invoke: "Invoke",
        args: tuple,
        kwargs: dict,
        *,
        session_id: Optional[str] = None,
        name: str = "agent.call",
        step_type: "StepType" = StepType.TOOL_CALL,
    ) -> Any:
        """Run one wrapped agent call through the full pipeline.

        The agent's return value is returned **unchanged**. ARC only observes
        the call: it checkpoints before, records after, verifies confidence,
        triggers recovery when needed, and emits lifecycle events.

        :param invoke: Zero-argument callable that performs the actual agent call.
        :param args: Positional args forwarded to the agent (for metadata only).
        :param kwargs: Keyword args forwarded to the agent (for metadata only).
        :param session_id: Override the runtime session (defaults to self.session_id).
        :param name: Human-readable step label recorded in the Flight Recorder.
        :param step_type: Step category (defaults to ``TOOL_CALL``).
        :returns: The raw return value of ``invoke()``.
        """
        sid = session_id or self.session_id
        step_number = self.recorder.next_step_number(sid)
        _, conflicts = self.firewall.filter([])
        self.events.emit(
            Event(
                type="request_started",
                session_id=sid,
                payload={"step_number": step_number, "agent_call": name, "conflicts": len(conflicts)},
            )
        )
        self.recovery.checkpoint(sid, step_number, {"step": step_number, "name": name})
        input_summary: Dict[str, Any] = {
            "callable": name,
            "arg_count": len(args),
            "kwarg_keys": sorted(kwargs.keys()),
        }
        start = time.perf_counter()
        try:
            raw = invoke()
            raw = _run_maybe_coroutine(raw)
        except Exception as exc:  # noqa: BLE001 - record then re-raise unchanged
            latency = (time.perf_counter() - start) * 1000.0
            self._record_failure(sid, step_number, input_summary, str(exc), latency)
            raise

        latency = (time.perf_counter() - start) * 1000.0
        output_text = str(raw) if raw is not None else None
        step = self.recorder.record(
            self.recorder.build_step(
                sid,
                step_number,
                step_type=step_type,
                name=name,
                input_data=input_summary,
                output_text=output_text,
                latency_ms=latency,
            )
        )
        self.verifier.verify([step])
        self._emit_recorded(sid, step)
        return raw

    # -- async pipeline ------------------------------------------------------

    async def async_run_create(
        self,
        payload: Dict[str, Any],
        invoke: "AsyncInvoke",
        context_sources: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        """Async equivalent of :meth:`run_create` for ``AsyncAnthropic`` clients.

        Async requests bypass the sync middleware onion; the planner is invoked
        directly during graph compilation. The graph and services are identical
        to the sync path — only the dispatch node is awaited.
        """
        request = RequestContext(
            session_id=self.session_id,
            provider=self.config.provider,
            payload=payload,
            context_sources=list(context_sources or []),
        )
        observable = payload.get("stream") is not True
        ctx = self._new_context(
            request, streaming=False, observable=observable, is_async=True
        )
        await self.executor.execute_async(ctx, invoke)
        return ctx.response

    async def async_begin_stream(
        self,
        payload: Dict[str, Any],
        context_sources: Optional[List[Dict[str, Any]]],
    ) -> int:
        """Async equivalent of :meth:`begin_stream`."""
        request = self._stream_request(payload, context_sources)
        ctx = self._new_context(request, streaming=True, observable=True, is_async=True)
        self.executor.begin_stream(ctx)
        self._stream_contexts[ctx.step_number] = ctx
        return ctx.step_number

    async def async_finish_stream(
        self,
        step_number: int,
        payload: Dict[str, Any],
        latency_ms: float,
        final_message: Any,
        error: Optional[str],
    ) -> Optional[TraceStep]:
        """Async equivalent of :meth:`finish_stream`."""
        return self.finish_stream(step_number, payload, latency_ms, final_message, error)


AsyncInvoke = Callable[[Dict[str, Any]], Any]  # returns a coroutine at call-time


def _run_maybe_coroutine(value: Any) -> Any:
    """If *value* is a coroutine or awaitable, drive it to completion synchronously."""
    import asyncio
    import inspect as _inspect

    if not _inspect.isawaitable(value):
        return value
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        # Best-effort: schedule on the running loop via concurrent.futures
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, value)
            return future.result()
    return asyncio.run(value)


__all__ = [
    "ARCRuntime",
    "AsyncInvoke",
    "extract_response",
    "_run_maybe_coroutine",
]