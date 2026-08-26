# Next Implementation Phase Plan

## Objective

Make ARC a universally distributable Python package that can support multiple AI providers, agent frameworks, IDE integrations, API clients, and credential providers without coupling the core runtime to Anthropic.

## Release Direction

- **Canonical implementation:** `arc-sdk/`
- **Requested distribution name:** `agent-core`
- **Compatibility import:** `import arc`
- **Universal scope:** AI providers, agent frameworks, IDEs, APIs, and API-key providers
- **Credential strategy:** environment/configuration first, followed by pluggable secret backends
- **Compatibility:** preserve existing Anthropic facade calls during migration
- **Publishing source:** only `arc-sdk/`

The requested distribution name must be checked for availability and ownership immediately before publishing.

## Phase 0 — Confirm and Reproduce the Package Error

1. Reproduce the exact upload failure from a clean environment.
2. Capture the Python version, build command, `twine check` output, and PyPI upload response.
3. Confirm the distribution name, import namespace, supported Python versions, and versioning policy.
4. Treat `arc-sdk/` as canonical.
5. Decide whether old package names remain compatibility distributions or only migration aliases.
6. Do not publish multiple distributions containing the same `arc` import namespace.

## Phase 1 — Rectify Python Packaging and Release Hygiene

1. Make `arc-sdk/pyproject.toml` the only authoritative build configuration.
2. Stop using these paths as release inputs:
   - `sdk/pyproject.toml`
   - `sdk/setup.py`
   - `arc/sdk/setup.py`
   - stale generated `*.egg-info` directories
3. Update `arc-sdk/pyproject.toml` with:
   - the approved distribution name
   - one version source
   - accurate metadata
   - optional provider/framework extras
   - release-safe project URLs
4. Build only from `arc-sdk/`.
5. Validate wheel metadata, artifact name, version, import package, CLI entry point, and package contents.
6. Install the wheel into a fresh virtual environment.
7. Add CI release guards for duplicate package trees and unexpected metadata.
8. Align the root README, `arc-sdk/README.md`, examples, and installation commands.
9. Publish to TestPyPI first, validate the uploaded artifact, then publish to PyPI.

## Phase 2 — Define Universal Runtime Contracts

1. Define provider-neutral contracts for:
   - invocation requests
   - invocation results
   - stream events
   - provider capabilities
   - normalized responses
   - provider errors
   - agent targets
   - IDE/API targets
2. Unify the adapter concepts in:
   - `arc-sdk/arc/integrations/__init__.py`
   - `arc-sdk/arc/integrations/adapter.py`
3. Replace graph dispatch typed only as `Dict[str, Any]` with an opaque invocation contract supporting:
   - keyword calls
   - positional calls
   - request objects
   - callable agents
   - HTTP/API operations
   - streaming lifecycles
4. Define normalized schemas for text, tool calls, usage, stop status, structured output, edits, patches, diagnostics, and metadata.
5. Add capability negotiation and adapter registration by stable identifiers.
6. Keep provider-specific fields namespaced and redact credentials before recording.

## Phase 3 — Generalize Runtime Transport and Normalization

1. Refactor `arc-sdk/arc/_transport.py` into a generic interception layer.
2. Support synchronous calls, asynchronous calls, iterators, async iterators, context-manager streams, and async context-manager streams.
3. Move Anthropic-specific behavior into the Anthropic adapter, including:
   - `messages.create`
   - `messages.stream`
   - `beta.messages`
   - `get_final_message()`
   - `text_stream`
4. Refactor `arc-sdk/arc/_runtime.py` so response extraction delegates to registered response adapters.
5. Preserve current public aliases such as `ARC.messages`, `ARC.async_messages`, `ARC.beta`, and `wrap()`.
6. Ensure firewall, recorder, verification, recovery, replay, and events use normalized contracts only.
7. Add redaction tests for API keys, bearer tokens, headers, and secret-bearing metadata.

## Phase 4 — Provider and Credential Portability

1. Implement complete adapters for:
   - Anthropic
   - OpenAI
   - Gemini
   - OpenAI-compatible custom endpoints
   - local inference servers
   - generic HTTP providers
2. Each provider adapter should support request mapping, response normalization, streaming, tools, structured output, errors, and capabilities.
3. Replace the single `provider_api_key` model in `arc-sdk/arc/config.py` with provider-neutral credential configuration.
4. Support API keys, OAuth tokens, service-account references, custom endpoints, headers, organization/project IDs, and timeouts.
5. Add a pluggable secret-provider interface.
6. Resolve credentials only at the integration boundary.
7. Ensure secrets never appear in traces, events, replay data, diagnostics, or exception messages.
8. Make provider selection explicit or infer it from a registered target descriptor.
9. Do not default operational behavior to Anthropic when another provider is configured.

## Phase 5 — Universal Agent, Framework, IDE, and API Integrations

1. Replace `_FRAMEWORK_CHECKS` in `arc-sdk/arc/_agent.py` with a target detector registry.
2. Return target kind, provider, capabilities, invocation methods, and adapter from detection.
3. Preserve `arc_framework` as a compatibility field.
4. Define an `AgentAdapter` contract for sync/async execution, streaming, nested events, tools, normalization, and cancellation.
5. Migrate adapters for:
   - LangGraph
   - CrewAI
   - AutoGen
   - OpenHands
   - OpenAI Agents
   - Anthropic
   - generic Python agents
6. Add support for arbitrary Python callables and agent objects.
7. Define a versioned IDE event protocol for VS Code, JetBrains, Cursor, Continue, and web IDE integrations.
8. Support normalized IDE events for model requests, agent runs, tools, edits, diagnostics, and sessions.
9. Define generic API boundaries for REST, WebSocket, webhooks, OpenAI-compatible HTTP, and MCP operations.
10. Add correlation, session, and span identifiers across agents, providers, tools, IDEs, APIs, and the backend.

## Phase 6 — Backend and Control-Plane Alignment

1. Port neutral contracts into `arc/backend/api/schemas.py`, storage models, websocket events, and route payloads.
2. Replace Claude-specific persisted fields with provider/target-neutral fields while retaining migration aliases.
3. Refactor:
   - `arc/backend/core/arc_runtime.py`
   - `arc/backend/core/context_firewall.py`
   - provider-facing backend code
4. Inject adapter, credential, and configuration services instead of constructing Anthropic clients directly.
5. Add provider, agent, IDE, API, session, span, and correlation metadata to traces, checkpoints, conflicts, and recovery events.
6. Keep raw payload storage optional and redacted by default.
7. Preserve graceful degradation for unavailable databases, Redis, providers, and offline/demo mode.

## Phase 7 — Compatibility, Verification, and Release

1. Add migration tests for existing `arc` facade calls and the new neutral API.
2. Test providers with mocked SDK objects and no network calls.
3. Test custom OpenAI-compatible endpoints with a local fake transport.
4. Add tests for:
   - sync and async calls
   - all stream lifecycle types
   - tool calls
   - structured output
   - agent wrappers
   - IDE event ingestion
   - API/webhook ingestion
   - retries
   - recovery
   - replay
   - credential redaction
5. Run the SDK test suite from `arc-sdk/`.
6. Run backend tests from `arc/backend/`.
7. Run configured type checks, lint checks, package build checks, and isolated wheel installation checks.
8. Verify that `import arc` resolves only to the canonical package.
9. Update `TODO.md` only after milestones are implemented and verified.
10. Publish the exact validated artifacts to TestPyPI, then production PyPI.
11. Tag the release and document the rollback procedure without overwriting published versions.

## Relevant Files

- `arc-sdk/pyproject.toml`
- `arc-sdk/arc/_facade.py`
- `arc-sdk/arc/_transport.py`
- `arc-sdk/arc/_runtime.py`
- `arc-sdk/arc/_agent.py`
- `arc-sdk/arc/config.py`
- `arc-sdk/arc/integrations/__init__.py`
- `arc-sdk/arc/integrations/adapter.py`
- `arc-sdk/arc/integrations/anthropic/`
- `arc-sdk/arc/integrations/openai/`
- `arc-sdk/arc/integrations/gemini/`
- `arc-sdk/arc/runtime/graph/executor.py`
- `arc-sdk/arc/runtime/verification/`
- `arc-sdk/arc/runtime/firewall/`
- `arc-sdk/tests/`
- `arc/backend/core/arc_runtime.py`
- `arc/backend/core/context_firewall.py`
- `arc/backend/api/schemas.py`
- `TODO.md`
- `PROJECT.md`
- `README.md`

## Verification Checklist

1. Build from `arc-sdk/` with `python -m build`.
2. Run `python -m twine check dist/*`.
3. Inspect wheel metadata and contents.
4. Install the wheel into a fresh virtual environment.
5. Verify `import arc`, `arc.__file__`, and `arc --version`.
6. Run SDK and backend tests.
7. Run mocked provider, agent, IDE, API, streaming, tools, recovery, replay, and redaction tests.
8. Upload only to TestPyPI first.
9. Install and validate the uploaded artifact.
10. Publish to production PyPI only after the local and uploaded artifacts match.

## Important Constraints

- Do not publish from the repository root, `sdk/`, or `arc/sdk/`.
- Do not require every provider SDK as a mandatory dependency.
- Do not store credentials in traces or logs.
- Do not remove compatibility APIs without a migration path.
- Do not implement all providers and IDEs in one milestone.
- Resolve the conflict between `PROJECT.md`, `TODO.md`, and older README instructions before implementation begins.
