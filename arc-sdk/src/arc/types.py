"""ARC — public typed contracts.

Contains the Pydantic v2 data models exchanged with the ARC control plane and
the structural (``Protocol``) interfaces that middleware, plugins, and event
handlers implement. These are *contracts only* — no behaviour is defined here.

All models follow the project standard::

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
"""

from __future__ import annotations

from enum import Enum
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Union,
    runtime_checkable,
)

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SessionStatus(str, Enum):
    """Lifecycle status of a protected agent session."""

    ACTIVE = "active"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERED = "recovered"


class StepType(str, Enum):
    """Category of a recorded execution step."""

    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    CHECKPOINT = "checkpoint"
    VERIFICATION = "verification"
    RECOVERY_ROLLBACK = "recovery_rollback"


class EventType(str, Enum):
    """Well-known runtime events emitted on the event bus."""

    PLAN_CREATED = "plan_created"
    GRAPH_BUILT = "graph_built"
    STEP_RECORDED = "step_recorded"
    CHECKPOINT_CREATED = "checkpoint_created"
    VERIFICATION_FAILED = "verification_failed"
    RECOVERY_TRIGGERED = "recovery_triggered"
    SESSION_COMPLETED = "session_completed"


class ReasoningStrategy(str, Enum):
    """How much deliberate reasoning the request warrants."""

    DIRECT = "direct"          # answer immediately, no scratch reasoning
    STEP_BY_STEP = "step_by_step"  # moderate, structured reasoning
    EXTENDED = "extended"      # deep, long-horizon reasoning


class RetrievalStrategy(str, Enum):
    """How aggressively context should be retrieved/augmented."""

    NONE = "none"
    LIGHT = "light"
    AGGRESSIVE = "aggressive"


class ToolStrategy(str, Enum):
    """How tools should be offered to the model."""

    NONE = "none"
    AUTO = "auto"          # model decides
    PARALLEL = "parallel"  # encourage concurrent tool calls


class VerificationStrategy(str, Enum):
    """How strictly the recorded response is verified."""

    SKIP = "skip"
    STANDARD = "standard"
    STRICT = "strict"


class RecoveryPolicy(str, Enum):
    """What to do when a step fails verification."""

    NONE = "none"                    # record only
    CHECKPOINT = "checkpoint"        # checkpoint + surface a recovery plan
    RETRY_ONCE = "retry_once"        # re-invoke the provider once


# ---------------------------------------------------------------------------
# Data models (wire contracts)
# ---------------------------------------------------------------------------


class _Model(BaseModel):
    """Shared base applying the project-wide Pydantic configuration."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain ``dict`` representation of the model."""
        return self.model_dump()


class TraceStep(_Model):
    """A single execution step captured by the Flight Recorder."""

    step_id: str = Field(..., description="Unique step identifier")
    session_id: str = Field(..., description="Parent session identifier")
    step_type: StepType = Field(default=StepType.LLM_CALL, description="Step category")
    step_number: int = Field(default=1, description="Sequential index within the session")
    name: Optional[str] = Field(default=None, description="Human-readable step name")
    input_data: Dict[str, Any] = Field(default_factory=dict, description="Step input payload")
    output_data: Optional[Dict[str, Any]] = Field(default=None, description="Step output payload")
    latency_ms: float = Field(default=0.0, description="Execution latency in milliseconds")
    token_usage: Dict[str, int] = Field(default_factory=dict, description="Token accounting")
    confidence_score: float = Field(default=1.0, description="Heuristic confidence (0.0-1.0)")
    error: Optional[str] = Field(default=None, description="Error message if the step failed")


class Checkpoint(_Model):
    """A restorable state snapshot created by the Recovery Engine."""

    checkpoint_id: str = Field(..., description="Unique checkpoint identifier")
    session_id: str = Field(..., description="Parent session identifier")
    step_number: int = Field(..., description="Step index the checkpoint was taken at")
    state_hash: Optional[str] = Field(default=None, description="State checksum")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Checkpoint metadata")


class Session(_Model):
    """A protected agent session."""

    session_id: str = Field(..., description="Unique session identifier")
    agent_name: str = Field(..., description="Name of the protected agent")
    task: str = Field(..., description="Task or goal description")
    status: SessionStatus = Field(default=SessionStatus.ACTIVE, description="Lifecycle status")
    total_steps: int = Field(default=0, description="Number of recorded steps")
    total_tokens: int = Field(default=0, description="Total tokens consumed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class ConflictItem(_Model):
    """A conflict surfaced by the Context Firewall during verification."""

    source_id: str = Field(..., description="Identifier of the conflicting source")
    conflict_type: str = Field(..., description="Category of conflict")
    description: str = Field(..., description="Human-readable conflict description")
    confidence_score: float = Field(default=1.0, description="Confidence of the conflict")
    mitigation: Optional[str] = Field(default=None, description="Suggested mitigation")


class VerificationResult(_Model):
    """Outcome of a policy/compliance verification run."""

    is_valid: bool = Field(..., description="True when no blocking conflicts were found")
    conflicts: List[ConflictItem] = Field(default_factory=list, description="Detected conflicts")
    firewall_status: str = Field(default="pass", description="'pass', 'warn', or 'block'")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Verification metadata")


class SanitizationAction(str, Enum):
    """Action taken by a Prompt Firewall detector."""

    NONE = "none"
    REDACT = "redact"
    DROP = "drop"
    BLOCK = "block"
    TRUNCATE = "truncate"
    DEDUPLICATE = "deduplicate"


class FirewallFinding(_Model):
    """A threat, violation, or sanitization event detected by a firewall detector."""

    detector_name: str = Field(..., description="Name of the detector")
    category: str = Field(..., description="Detector category (e.g. prompt_injection, pii, secrets)")
    severity: str = Field(default="medium", description="'low', 'medium', 'high', or 'critical'")
    message: str = Field(..., description="Human-readable finding description")
    location: str = Field(default="content", description="Input location (e.g. system, messages[0], tool_output)")
    action_taken: SanitizationAction = Field(default=SanitizationAction.NONE, description="Action applied")
    matched_text: Optional[str] = Field(default=None, description="Text segment that triggered the detector")


class PromptFirewallResult(_Model):
    """Complete result of inspecting and sanitizing prompt inputs before model dispatch."""

    is_safe: bool = Field(..., description="True if no blocking threats were detected")
    sanitized_payload: Dict[str, Any] = Field(default_factory=dict, description="Sanitized request payload")
    sanitized_sources: List[Dict[str, Any]] = Field(default_factory=list, description="Sanitized context sources")
    findings: List[FirewallFinding] = Field(default_factory=list, description="All detector findings")
    conflicts: List[ConflictItem] = Field(default_factory=list, description="Detected context conflicts")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Execution metadata")


class ReplayTimeline(_Model):
    """Ordered, replayable view of a recorded session."""

    session_id: str = Field(..., description="Session identifier")
    status: SessionStatus = Field(default=SessionStatus.ACTIVE, description="Session status")
    timeline_steps: List[TraceStep] = Field(default_factory=list, description="Ordered steps")
    failure_points: List[TraceStep] = Field(default_factory=list, description="Failed steps")
    recovery_checkpoints: List[Checkpoint] = Field(default_factory=list, description="Checkpoints")


class RecoveryPlan(_Model):
    """Recovery strategy computed by the Recovery Engine."""

    session_id: str = Field(..., description="Session identifier")
    status: str = Field(default="ready", description="Recovery readiness status")
    recommended_checkpoint: Optional[Checkpoint] = Field(
        default=None, description="Best checkpoint to roll back to"
    )
    available_checkpoints: List[Checkpoint] = Field(
        default_factory=list, description="All available checkpoints"
    )
    recovery_actions: List[Dict[str, Any]] = Field(
        default_factory=list, description="Ordered recovery actions"
    )


class ExecutionPlan(_Model):
    """A provider-independent plan for a single request.

    Produced by the Adaptive Planner (the first middleware) before the request
    reaches the model. Downstream stages follow it: ARC enforces
    ``verification_strategy`` and ``recovery_policy`` directly, and exposes the
    remaining strategies (reasoning/thinking/context/retrieval/tool) on the
    request and via the ``plan_created`` event for provider adapters and
    downstream middleware to apply. The plan never contains provider-specific
    request keys.
    """

    reasoning_strategy: ReasoningStrategy = Field(
        default=ReasoningStrategy.DIRECT, description="Depth of deliberate reasoning"
    )
    thinking_budget: int = Field(
        default=0, description="Abstract token budget for reasoning (0 = none)"
    )
    context_budget: int = Field(
        default=0, description="Abstract token budget for injected context"
    )
    retrieval_strategy: RetrievalStrategy = Field(
        default=RetrievalStrategy.NONE, description="Context retrieval aggressiveness"
    )
    tool_strategy: ToolStrategy = Field(
        default=ToolStrategy.NONE, description="How tools are offered to the model"
    )
    verification_strategy: VerificationStrategy = Field(
        default=VerificationStrategy.STANDARD, description="Response verification strictness"
    )
    recovery_policy: RecoveryPolicy = Field(
        default=RecoveryPolicy.CHECKPOINT, description="Action on verification failure"
    )
    rationale: str = Field(default="", description="Why the planner chose this plan")
    signals: Dict[str, Any] = Field(
        default_factory=dict, description="Provider-independent signals the plan derived from"
    )


class Event(_Model):
    """An event dispatched on the ARC runtime event bus."""

    type: str = Field(..., description="Event type (see :class:`EventType`)")
    session_id: Optional[str] = Field(default=None, description="Associated session, if any")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event payload")


class CircuitState(str, Enum):
    """Lifecycle state of a per-subscriber circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class DLQItem(_Model):
    """An item retained in the Event Bus Dead Letter Queue after processing failure."""

    dlq_id: str = Field(..., description="Unique DLQ entry identifier")
    event: Event = Field(..., description="The original event that failed dispatch")
    handler_name: str = Field(..., description="Name of the failed subscriber handler")
    error: str = Field(..., description="Error message or exception description")
    attempts: int = Field(default=1, description="Number of failure attempts")
    failed_at: float = Field(..., description="Unix timestamp of permanent failure")


class EventBusStats(_Model):
    """Live performance metrics and health stats of the hardened event bus."""

    events_emitted: int = Field(default=0, description="Total events emitted")
    events_processed: int = Field(default=0, description="Total subscriber invocations completed")
    failures: int = Field(default=0, description="Total subscriber invocation failures")
    timeouts: int = Field(default=0, description="Total subscriber timeouts")
    retries: int = Field(default=0, description="Total subscriber retry attempts")
    dlq_size: int = Field(default=0, description="Current Dead Letter Queue size")
    circuit_breakers: Dict[str, str] = Field(
        default_factory=dict, description="Per-handler circuit breaker states ('closed', 'open', 'half_open')"
    )


# ---------------------------------------------------------------------------
# Structural interfaces (contracts for extension points)
# ---------------------------------------------------------------------------

#: A callable that continues the middleware chain for a given step request.
NextCall = Callable[["RequestContext"], "ResponseContext"]


class RequestContext(_Model):
    """Mutable request passed through the middleware pipeline before dispatch."""

    session_id: Optional[str] = Field(default=None, description="Session identifier")
    provider: Optional[str] = Field(default=None, description="Target provider adapter")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Provider request payload")
    context_sources: List[Dict[str, Any]] = Field(
        default_factory=list, description="Candidate context sources for the firewall"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Cross-cutting metadata")


class ResponseContext(_Model):
    """Result flowing back up the middleware pipeline after dispatch."""

    session_id: Optional[str] = Field(default=None, description="Session identifier")
    output: Dict[str, Any] = Field(default_factory=dict, description="Provider response payload")
    step: Optional[TraceStep] = Field(default=None, description="Recorded step, if any")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Cross-cutting metadata")


@runtime_checkable
class Middleware(Protocol):
    """Interceptor invoked around every protected runtime step.

    Implementations wrap the ``next`` callable to observe or mutate the request
    on the way in and the response on the way out (onion model).
    """

    def __call__(self, request: RequestContext, call_next: NextCall) -> ResponseContext:
        ...


@runtime_checkable
class Plugin(Protocol):
    """A lifecycle-aware extension attached to an :class:`~arc.ARC` instance."""

    name: str

    def setup(self, arc: Any) -> None:
        """Called once when the plugin is registered."""

    def teardown(self, arc: Any) -> None:
        """Called when the owning ARC instance is closed."""


#: An event handler; may be synchronous or asynchronous.
EventHandler = Union[Callable[[Event], None], Callable[[Event], Awaitable[None]]]

#: Anything that can be executed under ARC protection via :meth:`ARC.run`.
Runnable = Union[Callable[..., Any], "SupportsInvoke"]


@runtime_checkable
class SupportsInvoke(Protocol):
    """Structural type for objects exposing an ``invoke`` entrypoint."""

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        ...


__all__ = [
    "SessionStatus",
    "StepType",
    "EventType",
    "ReasoningStrategy",
    "RetrievalStrategy",
    "ToolStrategy",
    "VerificationStrategy",
    "RecoveryPolicy",
    "TraceStep",
    "Checkpoint",
    "Session",
    "ConflictItem",
    "VerificationResult",
    "SanitizationAction",
    "FirewallFinding",
    "PromptFirewallResult",
    "ReplayTimeline",
    "RecoveryPlan",
    "ExecutionPlan",
    "Event",
    "CircuitState",
    "DLQItem",
    "EventBusStats",
    "RequestContext",
    "ResponseContext",
    "NextCall",
    "Middleware",
    "Plugin",
    "EventHandler",
    "Runnable",
    "SupportsInvoke",
]