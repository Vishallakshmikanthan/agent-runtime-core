# ARC Master Implementation Roadmap & Milestones

This document details the granular, ordered development milestones for converting ARC into an enterprise open-source AI runtime. Each milestone takes under 1 hour, modifies minimal files, is independently testable, and has clear success criteria.

---

## Phase 1: Core Consolidation & Storage Abstraction

### M1.1: Remove Legacy SDK Copies [COMPLETED]
- **Files**: Delete duplicate `arc/sdk/` directory.
- **Goal**: Consolidate SDK source of truth exclusively to `sdk/arc/`.
- **Test**: `pytest sdk/tests/` succeeds.
- **Success Criteria**: Clean SDK directory layout.

### M1.2: Strict Async-Safe Event Loops in SDK
- **Files**: `sdk/arc/agent.py`
- **Goal**: Replace blocking `asyncio.run()` in sync wrappers with loop-aware async dispatchers.
- **Test**: `pytest sdk/tests/test_client_and_agent.py`.
- **Success Criteria**: No event loop collision when wrapping agents in active async contexts.

### M1.3: Standardize Pydantic v2 Models Across API and SDK [COMPLETED]
- **Files**: `sdk/arc/types.py`, `arc/backend/api/schemas.py`, `sdk/tests/test_types.py`
- **Goal**: Align Pydantic schemas between SDK and backend (`Session`, `Step`, `FirewallRule`, `RecoveryDiff`).
- **Test**: `pytest sdk/tests/test_types.py`.
- **Success Criteria**: 100% field type and serialization parity.

### M1.4: Define Abstract `StorageRepository` Interface
- **Files**: `arc/backend/core/storage_interface.py`
- **Goal**: Create abstract base class defining storage contracts (`save_session`, `record_step`, `log_diff`).
- **Test**: Type-check interface with `mypy --strict`.
- **Success Criteria**: Clean storage abstraction without raw ORM coupling.

### M1.5: Integrate Alembic DB Migration System
- **Files**: `arc/backend/alembic.ini`, `arc/backend/migrations/`
- **Goal**: Setup Alembic migrations for database schema evolution.
- **Test**: Run `alembic upgrade head` on fresh database.
- **Success Criteria**: Database tables initialized via migration scripts.

---

## Phase 2: Provider-Agnostic Abstraction Layer

### M2.1: Implement `BaseProviderAdapter` Interface
- **Files**: `sdk/arc/providers/base.py`
- **Goal**: Create provider-agnostic base adapter contract for LLM invocation.
- **Test**: Type-check interface definitions.
- **Success Criteria**: Abstract base class defined with `generate_response` contract.

### M2.2: Implement `AnthropicAdapter`
- **Files**: `sdk/arc/providers/anthropic.py`
- **Goal**: Build Anthropic provider adapter supporting Claude models (`claude-3-7-sonnet`, `claude-3-5-haiku`).
- **Test**: `pytest sdk/tests/test_anthropic_adapter.py`.
- **Success Criteria**: Native prompt, tool, and system message mapping for Claude.

### M2.3: Implement `OpenAIAdapter`
- **Files**: `sdk/arc/providers/openai.py`
- **Goal**: Build OpenAI provider adapter supporting GPT models (`gpt-4o`, `gpt-4o-mini`, `o3-mini`).
- **Test**: `pytest sdk/tests/test_openai_adapter.py`.
- **Success Criteria**: Native function calling and completions mapping.

### M2.4: Implement `GeminiAdapter`
- **Files**: `sdk/arc/providers/gemini.py`
- **Goal**: Build Google Gemini provider adapter supporting `gemini-1.5-pro` and `gemini-2.0-flash`.
- **Test**: `pytest sdk/tests/test_gemini_adapter.py`.
- **Success Criteria**: Clean Vertex AI / Google AI SDK request mapping.

---

## Phase 3: Multi-Framework Integration Layer

### M3.1: Implement `LangGraphAdapter`
- **Files**: `sdk/arc/integrations/langgraph.py`
- **Goal**: Build state graph middleware adapter for LangGraph nodes.
- **Test**: `pytest sdk/tests/test_langgraph_adapter.py`.
- **Success Criteria**: Automatic step tracing and checkpointing during graph execution.

### M3.2: Implement `CrewAIAdapter`
- **Files**: `sdk/arc/integrations/crewai.py`
- **Goal**: Build task delegation middleware adapter for CrewAI multi-agent teams.
- **Test**: `pytest sdk/tests/test_crewai_adapter.py`.
- **Success Criteria**: Delegation step tracing and context firewall filtering in crew tasks.

### M3.3: Implement `AutoGenAdapter`
- **Files**: `sdk/arc/integrations/autogen.py`
- **Goal**: Build conversational turn middleware adapter for AutoGen agents.
- **Test**: `pytest sdk/tests/test_autogen_adapter.py`.
- **Success Criteria**: Conversational message filtering and step recording.

### M3.4: Implement `OpenHandsAdapter`
- **Files**: `sdk/arc/integrations/openhands.py`
- **Goal**: Build event stream execution adapter for OpenHands runtime.
- **Test**: `pytest sdk/tests/test_openhands_adapter.py`.
- **Success Criteria**: Action step tracing and terminal output verification.

---

## Phase 4: Model Context Protocol (MCP) Server Support

### M4.1: Implement MCP Tool Discovery Router
- **Files**: `sdk/arc/mcp/router.py`
- **Goal**: Build discovery and schema parser for connected Model Context Protocol (MCP) servers.
- **Test**: `pytest sdk/tests/test_mcp_router.py`.
- **Success Criteria**: MCP tools parsed and registered dynamically in ARC runtime.

### M4.2: Implement MCP Context Firewall & Trace Filter
- **Files**: `sdk/arc/mcp/firewall.py`
- **Goal**: Integrate Context Firewall verification and Flight Recorder tracing into MCP tool executions.
- **Test**: `pytest sdk/tests/test_mcp_firewall.py`.
- **Success Criteria**: Unsafe MCP tool calls blocked before execution.

---

## Phase 5: Enterprise Governance & Control Plane

### M5.1: Implement In-Memory & Redis Event Broker
- **Files**: `arc/backend/core/event_broker.py`, `arc/backend/api/websocket_router.py`
- **Goal**: Decouple engine events from WebSocket route handlers via pub-sub broker.
- **Test**: `pytest arc/backend/tests/test_event_broker.py`.
- **Success Criteria**: Real-time event streaming across multi-instance control plane.

### M5.2: Implement Interactive State Diff Viewer in Dashboard
- **Files**: `arc/frontend/src/components/RecoveryDiffViewer.jsx`
- **Goal**: Render visual JSON side-by-side state diffs for failure recoveries.
- **Test**: Browser UI verification.
- **Success Criteria**: Interactive diff highlights added, modified, and removed state keys.

---

## Phase 0: Public SDK Facade Scaffold

### M0.1: Scaffold `arc-sdk` Package Structure [COMPLETED]
- **Files**: `arc-sdk/` (new): `pyproject.toml`, `arc/__init__.py`, `arc/_facade.py`, `arc/config.py`, `arc/types.py`, `arc/exceptions.py`, `arc/version.py`, `arc/py.typed`, `arc/runtime/*`, `arc/integrations/*`, `arc/mcp/`, `arc/cli/`, `examples/`, `tests/`, `docs/`.
- **Goal**: Ship the production public API surface (structure only, no runtime internals): the `ARC()` facade exposing `wrap`, `run`, `trace`, `recover`, `verify`, `replay`, `inspect`, `middleware`, `plugin`, `event`; typed data contracts; modular engine interfaces; PEP 561 typing; packaging + entry point; examples + docs.
- **Test**: `cd arc-sdk && pytest` (10 passing contract tests over exports, method presence, registration wiring, and scaffolded `NotImplementedError` behaviour).
- **Success Criteria**: `import arc` exposes the full facade; extension-point registration works; execution methods declare typed contracts and raise `NotImplementedError`.
- **DECISION [RESOLVED]**: `arc-sdk/` (per PROJECT.md §4) is the **canonical** SDK going forward. Runtime internals will be ported from the legacy `sdk/arc` into `arc-sdk/arc`, and `sdk/` will be retired. Migration tracked in M0.2–M0.6 below.

### M0.2: Real ARC Runtime Transport (Anthropic interception) [COMPLETED]
- **Files**: `arc-sdk/arc/_transport.py` (new), `arc-sdk/arc/_runtime.py` (new), `arc-sdk/arc/runtime/{recorder,firewall,verifier,recovery,events,middleware}/default.py` (new), `arc-sdk/arc/runtime/replay/__init__.py` (new), `arc-sdk/arc/_facade.py`, `arc-sdk/arc/config.py`, `arc-sdk/tests/{conftest,test_transport}.py`.
- **Goal**: `ARC(client)` transparently intercepts every Anthropic request. `arc.messages.create(...)` / `arc.messages.stream(...)` (and `arc.beta.messages.*` for MCP) run through the real pipeline — Middleware → Context Firewall → Event Bus → Flight Recorder → Verification → Recovery → Anthropic SDK → Replay Store → Dashboard — and return the SDK response object **unchanged**. Streaming, tool calls, extended thinking, MCP, request metadata, and SDK-owned retries all pass through untouched; non-intercepted resource methods (`count_tokens`, etc.) pass straight through.
- **Non-goals (deferred)**: `wrap()`/`run()` (M0.3); async client interception; remote control-plane persistence (M0.5). No mock transport — the transport is real and duck-typed (no hard `anthropic` dependency).
- **Test**: `cd arc-sdk && pytest` (25 passing: kwargs-untouched forwarding, response passthrough, recording/trace, tool/stream/beta-MCP handling, middleware + event dispatch, failure recording + recovery plan, rule-based verification).
- **Success Criteria**: `from arc import ARC; arc = ARC(Anthropic()); arc.messages.create(...)` works with everything else automatic; provider payloads and responses are never mutated.

### M0.3: Port Agent Protection into `wrap`/`run` [COMPLETED]
- **Files**: `arc-sdk/arc/_agent.py` (new), `arc-sdk/arc/_runtime.py` (extended),
  `arc-sdk/arc/_facade.py` (wrap/run implemented), `arc-sdk/arc/integrations/anthropic/wrapper.py` (new),
  `arc-sdk/arc/integrations/langgraph/wrapper.py` (new), `arc-sdk/arc/integrations/crewai/wrapper.py` (new),
  `arc-sdk/arc/integrations/autogen/wrapper.py` (new), `arc-sdk/arc/integrations/openhands/wrapper.py` (new),
  `arc-sdk/arc/integrations/openai/wrapper.py` (new), `arc-sdk/tests/test_wrap_run.py` (new).
- **Goal**: `ARC.wrap(agent)` returns a `WrappedAgent` proxy preserving the original API.
  ARC automatically intercepts execution, records runtime, injects middleware, manages context,
  verifies outputs, recovers failures, and emits events.
  Supported: Anthropic SDK, LangGraph, CrewAI, AutoGen, OpenHands, OpenAI Agents SDK, Generic Python.
- **Test**: `cd arc-sdk && pytest tests/test_wrap_run.py` — 44 passing.
  Full suite: `cd arc-sdk && pytest` — 69 passing, 0 failed.
- **Success Criteria**: Wrapping any agent records steps; `wrapped.arc_trace()` returns
  flight-recorder history; failures are recorded and recovery plans generated; async agents work.

### M0.4: Wire Middleware Pipeline & Event Bus Dispatch [COMPLETED]
- **Files**: `arc-sdk/arc/runtime/middleware/default.py`, `arc-sdk/arc/runtime/events/default.py`, `arc-sdk/arc/_runtime.py`.
- **Goal**: Implement `MiddlewarePipeline.execute` (onion chain) and `EventBus.emit` so registered middleware/handlers actually run around each step.
- **Test**: covered by `tests/test_transport.py::test_middleware_runs_in_pipeline` / `::test_events_dispatched` (delivered with M0.2).
- **Success Criteria**: Registered middleware observes requests/responses; emitted events reach subscribers.

### M0.5: Point Distribution `arc-sdk` at Canonical Package
- **Files**: `sdk/` (retire), root packaging / editable install.
- **Goal**: Re-install `arc-sdk` editable from `arc-sdk/`, remove the legacy `sdk/arc` editable install so `import arc` resolves to the canonical package.
- **Test**: `python -c "import arc, inspect, os; assert 'arc-sdk' in os.path.dirname(inspect.getfile(arc))"`.
- **Success Criteria**: Single source of truth; the "two SDK copies" gotcha is eliminated.

### M0.6: Migrate & Consolidate Legacy SDK Tests
- **Files**: `arc-sdk/tests/` (from `sdk/tests/`).
- **Goal**: Port `sdk/tests` coverage onto the canonical package and delete duplicates.
- **Test**: `cd arc-sdk && pytest`.
- **Success Criteria**: Full legacy behaviour covered by the canonical suite before `sdk/` deletion.

### M0.7: Adaptive Planner (first middleware) [COMPLETED]
- **Files**: `arc-sdk/arc/runtime/planner/__init__.py` + `default.py` (new), `arc-sdk/arc/types.py` (ExecutionPlan + strategy enums + `plan_created` event), `arc-sdk/arc/_runtime.py`, `arc-sdk/arc/_facade.py`, `arc-sdk/arc/__init__.py`, `arc-sdk/tests/test_planner.py`, `arc-sdk/examples/05_adaptive_planner.py`.
- **Goal**: Before every request reaches the model, ARC produces a provider-independent `ExecutionPlan` (reasoning strategy, thinking budget, context budget, retrieval strategy, tool strategy, verification strategy, recovery policy). The `AdaptivePlanner` is installed as the **first (outermost) middleware**; it stores the plan on the request and emits `plan_created`. Downstream stages follow it — ARC enforces `verification_strategy` (skip/standard/strict) and `recovery_policy` (none/checkpoint/retry_once) directly; the remaining strategies are recorded on the step and surfaced via events for provider adapters/middleware to apply. Streams are planned too (planner invoked directly, since streams bypass the onion). Planner is swappable (`ARC(planner=...)` / `arc.planner = ...`) and previewable (`arc.plan(**request)`).
- **Provider independence**: the planner reads only cross-provider signals (`messages`, `tools`, `max_tokens`, ARC `context_sources`) and never emits provider-specific request keys; `RETRY_ONCE` is chosen only when `auto_recover` is enabled (a retry re-bills the model).
- **Test**: `cd arc-sdk && pytest` (16 new planner tests; 85 total passing) — heuristic mappings, thinking-budget cap, retrieval scaling, first-middleware ordering, `plan_created` event, plan-driven retry vs checkpoint, streaming planned, custom/swappable planner.
- **Success Criteria**: `arc.plan(...)` returns a full plan without a model call; the plan governs verification + recovery on every intercepted request.

### M0.8: Production Runtime Pipeline (graph-driven, event-subscribed) [COMPLETED]
- **Files**: `arc-sdk/arc/runtime/graph/__init__.py` + `builder.py` + `bus.py` + `executor.py` + `services.py` (new), `arc-sdk/arc/_runtime.py` (rewired onto the graph), `arc-sdk/arc/types.py` (`graph_built` event), `arc-sdk/arc/_facade.py` (`arc.graph()` preview), `arc-sdk/arc/__init__.py` + `arc/runtime/__init__.py` (exports), `arc-sdk/tests/test_pipeline.py`, `arc-sdk/examples/06_execution_graph.py`.
- **Goal**: Every model request now executes through a **planner-generated `ExecutionGraph`** — the source of truth for which stages run (firewall → dispatch → record → verify? → recover? → replay, derived entirely from the plan). An `EventDrivenGraphExecutor` walks the graph and publishes events on an in-process `GraphBus`; the runtime services (firewall, recorder, verifier, recovery, replay) **subscribe** to those events and coordinate only through a shared `ExecutionContext` — they no longer call one another directly. Covers sync + async, streaming (context-manager and low-level `stream=True`), tool use, and MCP (`beta.messages`). Response objects and request kwargs are never mutated; the Anthropic SDK is untouched.
- **Design notes**: middleware remains the outer onion (the planner is the first middleware and *generates* the graph); the five internal engines were inverted to event subscribers. The recovery retry (RETRY_ONCE) is applied by the executor when the recover node requests it. `arc.graph(**request)` previews the graph with no model call; a `graph_built` event carries the node list.
- **Public API unchanged**: `from arc import ARC; client = ARC(Anthropic()); client.messages.create(...)` — everything else automatic.
- **Test**: `cd arc-sdk && pytest` (13 new pipeline tests; **148 total passing**, all prior behaviour preserved) — graph derived from plan (skip/verify/recover node presence), streaming graph omits recover, provider-independent graph, ordered executor events, services-subscribe-not-call (verifier untouched when no verify node), `graph_built` event, graph shape recorded on the step, end-to-end sync/async/stream/retry/failure through the graph.
- **Success Criteria**: the execution graph governs runtime behaviour for every model request; services react to graph events rather than direct calls; public API and all existing tests remain green.

### M0.9: Enterprise Prompt Firewall Upgrade [COMPLETED]
- **Files**: `arc-sdk/arc/runtime/firewall/prompt_firewall.py` (new), `arc-sdk/arc/runtime/firewall/detector.py` (new), `arc-sdk/arc/runtime/firewall/detectors/*.py` (new), `arc-sdk/arc/runtime/firewall/default.py`, `arc-sdk/arc/runtime/firewall/__init__.py`, `arc-sdk/arc/types.py`, `arc-sdk/arc/runtime/graph/services.py`, `arc/backend/core/context_firewall.py`, `arc-sdk/tests/test_prompt_firewall.py`.
- **Goal**: Upgraded Context Firewall into a pluggable **Prompt Firewall**. Inspects all 6 input targets (System prompts, Messages, Tool outputs, Retrieved documents, Memory, Attachments) across 8 pluggable detectors (Prompt Injection, Jailbreak, PII, Secrets, Recursive Prompting, Prompt Leakage, Context Explosion, Duplicate Context). Sanitizes request payload before dispatching to the provider adapter. Maintains 100% backward compatibility for `ContextFirewall`.
- **Test**: `cd arc-sdk && python -m pytest` (**202 total passing**).
- **Success Criteria**: Sanitized payload reaches provider dispatch; PII & Secrets redacted; prompt injection/jailbreak/leakage neutralized; duplicate context deduplicated; 202 tests green.

### M0.10: Hardened Event Bus [COMPLETED]
- **Files**: `arc-sdk/arc/runtime/events/hardened.py` (new), `arc-sdk/arc/runtime/events/circuit_breaker.py` (new), `arc-sdk/arc/runtime/events/dlq.py` (new), `arc-sdk/arc/runtime/events/metrics.py` (new), `arc-sdk/arc/runtime/events/default.py`, `arc-sdk/arc/runtime/events/__init__.py`, `arc-sdk/arc/types.py`, `arc-sdk/tests/test_hardened_event_bus.py`.
- **Goal**: Implemented resilient Hardened Event Bus providing complete Fault Isolation (subscribers can never crash model execution), Timeouts (per-subscriber execution limits), Retries (exponential backoff), Async Dispatch (non-blocking task dispatch), Backpressure (bounded queues), Dead Letter Queue (DLQ for permanently failed event subscriber dispatches), Circuit Breakers (per-subscriber trip states `CLOSED`, `OPEN`, `HALF_OPEN`), and live Metrics (`EventBusStats`).
- **Test**: `cd arc-sdk && python -m pytest` (**208 total passing**).
- **Success Criteria**: Bad, crashing, slow, or hanging subscribers never affect model execution or break runtime flow; DLQ captures permanent failures; 208 tests green.

### M0.11: Master Production README & Devfolio Submission Documentation [COMPLETED]
- **Files**: `README.md`, `TODO.md`.
- **Goal**: Authored production-level `README.md` with complete system architecture diagrams, multi-engine Mermaid flowcharts, tech stack breakdown, quickstart guides, python SDK examples, and Devfolio Push to Prod Hackathon submission requirements.
- **Test**: Rendered and validated Markdown syntax and relative image links (`ptp_ss/`).
- **Success Criteria**: 100% submission requirements fulfilled; architectural diagrams and engine flowcharts verified.



