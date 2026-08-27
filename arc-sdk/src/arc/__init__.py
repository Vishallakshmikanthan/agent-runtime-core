"""ARC — Agent Runtime Core SDK.

A provider-agnostic reliability runtime for AI agents: a Context Firewall, a
Flight Recorder, and a self-healing Recovery Engine behind one facade.

Quickstart
----------
>>> from arc import ARC
>>> arc = ARC(api_key="...", provider_api_key="...")   # doctest: +SKIP
>>> protected = arc.wrap(my_client)                    # doctest: +SKIP

The public surface is intentionally small: construct :class:`ARC`, then use
``wrap``, ``run``, ``trace``, ``recover``, ``verify``, ``replay``, ``inspect``
and the extension points ``middleware``, ``plugin``, ``event``.
"""

from __future__ import annotations

from ._facade import ARC
from .config import ARCConfig
from .exceptions import (
    APIConnectionError,
    APIError,
    ARCError,
    AuthenticationError,
    ConfigurationError,
    MiddlewareError,
    NotFoundError,
    PluginError,
    RecoveryError,
    ServerError,
    VerificationError,
)
from .runtime.graph import ExecutionGraph, ExecutionNode, GraphEventType, NodeKind
from .runtime.planner import Planner
from .runtime.verification import (
    UNVERIFIED_CONFIDENCE,
    VerificationCheck,
    VerificationContext,
    VerificationEngine,
    VerificationReport,
    Verifier,
)
from .runtime.verification.plugins import (
    AssertionVerifier,
    ExecutionResult,
    ExecutionVerifier,
    ExternalAPIVerifier,
    JSONSchemaVerifier,
    JudgeVerdict,
    LLMJudgeVerifier,
    PydanticVerifier,
    ResponseIntegrityVerifier,
    ToolOutputVerifier,
)
from .types import (
    Checkpoint,
    ConflictItem,
    Event,
    EventHandler,
    EventType,
    ExecutionPlan,
    Middleware,
    Plugin,
    ReasoningStrategy,
    RecoveryPlan,
    RecoveryPolicy,
    ReplayTimeline,
    RequestContext,
    ResponseContext,
    RetrievalStrategy,
    Runnable,
    Session,
    SessionStatus,
    StepType,
    ToolStrategy,
    TraceStep,
    VerificationResult,
    VerificationStrategy,
)
from .version import __version__

__all__ = [
    # Facade + configuration
    "ARC",
    "ARCConfig",
    "__version__",
    # Data contracts
    "Session",
    "TraceStep",
    "Checkpoint",
    "ConflictItem",
    "VerificationResult",
    "ReplayTimeline",
    "RecoveryPlan",
    "Event",
    "ExecutionPlan",
    "ExecutionGraph",
    "ExecutionNode",
    "NodeKind",
    "GraphEventType",
    "RequestContext",
    "ResponseContext",
    "SessionStatus",
    "StepType",
    "EventType",
    "ReasoningStrategy",
    "RetrievalStrategy",
    "ToolStrategy",
    "VerificationStrategy",
    "RecoveryPolicy",
    # Extension-point interfaces
    "Middleware",
    "Plugin",
    "Planner",
    "EventHandler",
    "Runnable",
    # Verification Engine
    "VerificationEngine",
    "Verifier",
    "VerificationContext",
    "VerificationCheck",
    "VerificationReport",
    "UNVERIFIED_CONFIDENCE",
    "ResponseIntegrityVerifier",
    "JSONSchemaVerifier",
    "PydanticVerifier",
    "ToolOutputVerifier",
    "ExternalAPIVerifier",
    "LLMJudgeVerifier",
    "JudgeVerdict",
    "AssertionVerifier",
    "ExecutionVerifier",
    "ExecutionResult",
    # Exceptions
    "ARCError",
    "ConfigurationError",
    "APIError",
    "APIConnectionError",
    "AuthenticationError",
    "NotFoundError",
    "ServerError",
    "VerificationError",
    "RecoveryError",
    "MiddlewareError",
    "PluginError",
]