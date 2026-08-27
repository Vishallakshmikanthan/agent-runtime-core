"""ARC SDK — ``WrappedAgent`` universal proxy.

``arc.wrap(agent)`` returns a :class:`WrappedAgent` instance that:

* Preserves the **complete original API** via ``__getattr__`` delegation.
* Intercepts every callable entry-point (``__call__``, ``invoke``, ``run``,
  ``kickoff``, ``initiate_chat``, ``run_task``) and routes them through the
  ARC pipeline (middleware → firewall → recorder → verifier → recovery → events).
* Exposes ``arc_session_id`` and ``arc_trace()`` for lightweight introspection
  without importing dashboard code.

No agent code changes are required. No framework SDK is a hard dependency —
all framework detection is duck-typed.
"""

from __future__ import annotations

import logging
from typing import Any, Generic, List, Optional, TypeVar

from ._runtime import ARCRuntime, _run_maybe_coroutine
from .types import StepType, TraceStep

logger = logging.getLogger("arc.agent")

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Framework detection
# ---------------------------------------------------------------------------

_FRAMEWORK_CHECKS: list[tuple[str, list[str]]] = [
    # Order matters — more specific checks come first.
    # AsyncAnthropic must come before Anthropic because both share messages+beta.
    # AsyncAnthropic clients expose __aenter__ / __aexit__ as async context managers.
    ("async_anthropic", ["messages", "beta", "__aenter__", "__aexit__"]),
    ("anthropic", ["messages", "beta"]),           # Anthropic SDK sync client
    ("openai_agents", ["run", "tools", "model"]),  # OpenAI Agents SDK Runner/Agent
    ("langgraph", ["invoke", "stream", "get_graph"]),  # LangGraph CompiledGraph
    ("crewai", ["kickoff", "agents", "tasks"]),    # CrewAI Crew
    ("autogen", ["initiate_chat", "name", "system_message"]),  # AutoGen Agent
    ("openhands", ["run_task", "config", "sandbox"]),  # OpenHands runtime
    ("openai_client", ["chat", "completions"]),    # Raw OpenAI client
]


def _detect_framework(agent: Any) -> str:
    """Return a framework label for *agent* via duck-type inspection.

    Falls back to ``"generic"`` if no known shape is recognised.
    """
    for framework, attrs in _FRAMEWORK_CHECKS:
        if all(hasattr(agent, a) for a in attrs):
            return framework
    if callable(agent):
        return "callable"
    return "generic"


# ---------------------------------------------------------------------------
# Framework-specific interception helpers
# ---------------------------------------------------------------------------

def _make_interceptor(
    runtime: ARCRuntime,
    agent: Any,
    method_name: str,
    step_name: str,
    step_type: StepType = StepType.TOOL_CALL,
):
    """Return a wrapper function that intercepts *method_name* on *agent*."""
    original = getattr(agent, method_name)

    def _intercepted(*args: Any, **kwargs: Any) -> Any:
        return runtime.run_agent_call(
            invoke=lambda: original(*args, **kwargs),
            args=args,
            kwargs=kwargs,
            name=step_name,
            step_type=step_type,
        )

    _intercepted.__name__ = method_name
    _intercepted.__qualname__ = f"WrappedAgent.{method_name}"
    _intercepted.__doc__ = getattr(original, "__doc__", None)
    return _intercepted


# ---------------------------------------------------------------------------
# WrappedAgent proxy
# ---------------------------------------------------------------------------

class WrappedAgent(Generic[T]):
    """Universal ARC proxy wrapping any agent type.

    Preserves the original API by forwarding every attribute access to the
    underlying agent via ``__getattr__``. Known entry-point methods
    (``__call__``, ``invoke``, ``run``, ``kickoff``, ``initiate_chat``,
    ``run_task``) are intercepted and routed through the ARC pipeline.

    Extra ARC-specific attributes:

    * ``arc_session_id`` — the runtime session that records this agent's steps.
    * ``arc_trace()``    — return the ordered :class:`~arc.TraceStep` list.
    * ``arc_framework``  — detected framework string (e.g. ``"langgraph"``).
    """

    # ARC-private slots so __getattr__ never accidentally delegates them.
    __slots__ = (
        "_arc_agent",
        "_arc_runtime",
        "_arc_name",
        "_arc_task",
        "_arc_framework",
        "_arc_interceptors",
    )

    def __init__(
        self,
        agent: T,
        runtime: ARCRuntime,
        *,
        name: str = "ARC Wrapped Agent",
        task: str = "Protected task",
    ) -> None:
        object.__setattr__(self, "_arc_agent", agent)
        object.__setattr__(self, "_arc_runtime", runtime)
        object.__setattr__(self, "_arc_name", name)
        object.__setattr__(self, "_arc_task", task)

        framework = _detect_framework(agent)
        object.__setattr__(self, "_arc_framework", framework)

        interceptors: dict[str, Any] = {}
        self._build_interceptors(agent, runtime, name, framework, interceptors)
        object.__setattr__(self, "_arc_interceptors", interceptors)

        logger.debug(
            "ARC wrapping agent framework=%r name=%r session=%s",
            framework, name, runtime.session_id,
        )

    # -- interceptor building -------------------------------------------------

    @staticmethod
    def _build_interceptors(
        agent: Any,
        runtime: ARCRuntime,
        name: str,
        framework: str,
        out: dict[str, Any],
    ) -> None:
        """Populate *out* with intercepted callables for known entry-points."""
        _step = f"{name}"

        # __call__ — generic callable / function
        if callable(agent):
            out["__call__"] = lambda *a, **kw: runtime.run_agent_call(
                invoke=lambda: agent(*a, **kw),
                args=a,
                kwargs=kw,
                name=f"{_step}.__call__",
            )

        # Framework-specific entry-points
        _methods: list[tuple[str, str]] = []
        if framework == "langgraph":
            _methods = [("invoke", f"{_step}.invoke"), ("stream", f"{_step}.stream")]
        elif framework == "crewai":
            _methods = [("kickoff", f"{_step}.kickoff")]
        elif framework == "autogen":
            _methods = [
                ("initiate_chat", f"{_step}.initiate_chat"),
                ("receive", f"{_step}.receive"),
                ("generate_reply", f"{_step}.generate_reply"),
            ]
        elif framework == "openhands":
            for m in ("run_task", "run"):
                if hasattr(agent, m):
                    _methods.append((m, f"{_step}.{m}"))
        elif framework in ("anthropic", "async_anthropic", "openai_client", "openai_agents"):
            # Provider-level interception — wrap the callable entry points
            for m in ("run", "invoke", "complete", "generate"):
                if hasattr(agent, m) and callable(getattr(agent, m)):
                    _methods.append((m, f"{_step}.{m}"))
        else:
            # Generic: intercept common patterns if present
            for m in ("run", "invoke", "execute", "call", "generate"):
                if hasattr(agent, m) and callable(getattr(agent, m)):
                    _methods.append((m, f"{_step}.{m}"))

        for method_name, step_label in _methods:
            if hasattr(agent, method_name):
                out[method_name] = _make_interceptor(
                    runtime, agent, method_name, step_label
                )

    # -- proxy attribute access -----------------------------------------------

    def __getattr__(self, name: str) -> Any:
        """Forward unknown attributes to the wrapped agent.

        ARC-intercepted methods are returned from ``_arc_interceptors`` first,
        so the original implementation is replaced transparently.
        """
        interceptors: dict[str, Any] = object.__getattribute__(self, "_arc_interceptors")
        if name in interceptors:
            return interceptors[name]
        agent: Any = object.__getattribute__(self, "_arc_agent")
        return getattr(agent, name)

    def __setattr__(self, name: str, value: Any) -> None:
        # Only our private slots live on self; everything else delegates.
        if name in self.__slots__:
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, "_arc_agent"), name, value)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Intercept direct calls — e.g. ``wrapped(input)``."""
        interceptors: dict[str, Any] = object.__getattribute__(self, "_arc_interceptors")
        if "__call__" in interceptors:
            return interceptors["__call__"](*args, **kwargs)
        # Not originally callable — mimic the TypeError the original would raise.
        agent: Any = object.__getattribute__(self, "_arc_agent")
        return agent(*args, **kwargs)  # type: ignore[operator]

    # -- ARC introspection ----------------------------------------------------

    @property
    def arc_session_id(self) -> str:
        """Identifier of the ARC session recording this agent's steps."""
        runtime: ARCRuntime = object.__getattribute__(self, "_arc_runtime")
        return runtime.session_id

    @property
    def arc_framework(self) -> str:
        """Detected framework label (e.g. ``"langgraph"`` or ``"generic"``)."""
        return object.__getattribute__(self, "_arc_framework")  # type: ignore[return-value]

    def arc_trace(self) -> List[TraceStep]:
        """Return the ordered Flight Recorder steps for this agent's session."""
        runtime: ARCRuntime = object.__getattribute__(self, "_arc_runtime")
        return runtime.recorder.trace(runtime.session_id)

    # -- dunder helpers -------------------------------------------------------

    def __repr__(self) -> str:
        name: str = object.__getattribute__(self, "_arc_name")
        framework: str = object.__getattribute__(self, "_arc_framework")
        runtime: ARCRuntime = object.__getattribute__(self, "_arc_runtime")
        return (
            f"WrappedAgent(name={name!r}, framework={framework!r}, "
            f"session_id={runtime.session_id!r})"
        )

    def __dir__(self) -> list[str]:
        """Merge wrapped-agent dir with ARC introspection attributes."""
        agent: Any = object.__getattribute__(self, "_arc_agent")
        arc_attrs = ["arc_session_id", "arc_framework", "arc_trace"]
        return sorted(set(dir(agent)) | set(arc_attrs))


__all__ = ["WrappedAgent", "_detect_framework", "_run_maybe_coroutine"]