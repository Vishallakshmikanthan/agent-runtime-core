# ARC SDK — Agent Runtime Core

A provider-agnostic **reliability runtime** for AI agents. ARC sits between your
application and your model provider and gives every agent step three
guarantees:

1. **Context Firewall** — score, filter, and provenance-tag context before it
   reaches the model.
2. **Flight Recorder** — record every LLM/tool step for deterministic replay.
3. **Recovery Engine** — checkpoint state and self-heal after failures.

> **Status:** the **Anthropic interception transport is live** (`ARC(client)` →
> `arc.messages.create(...)`), along with the recorder, firewall, event bus,
> verifier, recovery, and replay engines and the middleware/plugin/event
> extension points. `wrap()` and `run()` remain typed stubs for a later
> milestone.

## Install

```bash
pip install agent-core

# with a provider adapter
pip install "agent-core[anthropic]"
pip install "agent-core[all]"
```

## Quickstart — intercept every Anthropic request

Wrap your existing client once. Keep writing normal Anthropic SDK code; ARC
runs each request through its pipeline and returns the SDK's response
**unchanged** (streaming, tool calls, extended thinking, and MCP all pass
through untouched).

```python
from anthropic import Anthropic
from arc import ARC

client = Anthropic()
arc = ARC(client)

response = arc.messages.create(
    model="claude-opus-4-8",
    max_tokens=16000,
    messages=[{"role": "user", "content": "Hello"}],
```

MCP / betas flow through the beta namespace unchanged:
arc.beta.messages.create(
    model="claude-opus-4-8", max_tokens=1024,
    messages=[{"role": "user", "content": "..."}],
    mcp_servers=[{"type": "url", "name": "svc", "url": "https://mcp.example/sse"}],
    betas=["mcp-client-2025-11-20"],
)

# Read back what the transport recorded:
arc.trace()          # recorded steps
arc.verify()         # firewall/confidence verification
arc.replay()         # deterministic timeline
arc.recover()        # recovery plan
arc.dashboard_url    # live session URL
```

Every request automatically flows through:

```
ARC Runtime → Middleware → Context Firewall → Event Bus → Flight Recorder
  → Verification → Recovery → Anthropic SDK → Response → Replay Store → Dashboard
```

The Anthropic SDK is never modified; request kwargs and response objects are
never mutated.

## Public API

`ARC()` is the single entrypoint. Its surface:

| Method | Purpose |
| --- | --- |
| `wrap(client)` | Wrap a provider/agent client for transparent protection |
| `run(target, ...)` | Execute a callable/agent once under protection |
| `trace(session_id)` | Fetch recorded execution steps |
| `recover(session_id)` | Compute/apply a recovery plan |
| `verify(session_or_trace, rules)` | Check compliance via the Context Firewall |
| `replay(session_id)` | Get a deterministic replay timeline |
| `inspect(session_id)` | Fetch the session record and telemetry |
| `middleware(mw)` | Register a request/response interceptor (also a decorator) |
| `plugin(plugin)` | Register a lifecycle plugin (also a decorator) |
| `event(name)` | Decorator to subscribe a handler to a runtime event |

## Extension points

```python
@arc.middleware
def timing(request, call_next):
    response = call_next(request)
    return response

@arc.plugin
class MetricsPlugin:
    name = "metrics"
    def setup(self, arc): ...
    def teardown(self, arc): ...

@arc.event("step_recorded")
def on_step(event):
    print(event.type, event.payload)
```

## Package layout

```
arc/
├── __init__.py         # public exports
├── _facade.py          # the ARC facade
├── config.py           # ARCConfig
├── types.py            # data contracts + extension interfaces
├── exceptions.py       # exception hierarchy
├── runtime/            # engine interfaces (scheduler, recovery, verifier,
│                       #   firewall, recorder, plugins, middleware, events)
├── integrations/       # provider + framework adapters
├── mcp/                # Model Context Protocol router
└── cli/                # `arc` console script
```

## Typing

The package is PEP 561 typed (`py.typed`) and checked with `mypy --strict`.

## License

MIT — see [LICENSE](./LICENSE).
