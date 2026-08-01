# Amplifier Events for Notifications

This document describes the Amplifier events relevant to notification hooks.

## Turn Completion Events

### `orchestrator:complete`

**The primary event for turn completion notifications.**

Emitted when the orchestrator finishes processing a user prompt and is ready for the next input.

```python
await hooks.emit(
    "orchestrator:complete",
    {
        "orchestrator": "loop-streaming",
        "turn_count": 3,
        "status": "success",
        "goal_turn": None,
        "goal_final": True
    }
)
```

| Field | Type | Description |
|-------|------|-------------|
| `orchestrator` | str | Name of the orchestrator module |
| `turn_count` | int | Number of LLM iterations in this turn |
| `status` | str | "success" or "incomplete" |
| `goal_turn` | int \| None | Which continuation iteration this emission belongs to, when the orchestrator runs multiple internal iterations to satisfy a single user prompt. `None` when no such continuation is active. |
| `goal_final` | bool | Whether this emission is the true end of the user's turn. `False` on an intermediate continuation iteration (more work follows); `True` on the one emission that corresponds to a finished user turn. **Absent** on orchestrators that don't implement continuation iterations - consumers must treat a missing field as `True` (every emission is final). |

**Consumer guidance:** any hook that treats `orchestrator:complete` as "the turn is
done, notify/act now" must check `goal_final` and skip when it is explicitly
`False`. This is not specific to any one orchestrator or feature - it's the
general signal for "is this turn actually over" on this event. Treat a missing
`goal_final` as `True` for backward compatibility with orchestrators that don't
emit it.

**Emitted by:**
- `loop-basic` ✅ (no `goal_turn`/`goal_final` - always final)
- `loop-streaming` ✅ (emits `goal_turn`/`goal_final` when continuation iterations are active)

### `prompt:complete`

Alternative event for prompt processing completion.

```python
await hooks.emit(
    "prompt:complete",
    {
        "response_preview": "I've completed...",
        "length": 1234
    }
)
```

**Emitted by:**
- `loop-basic` ✅
- `loop-streaming` ❌ (not emitted)

**Recommendation:** Use `orchestrator:complete` for broader compatibility.

## Session Events

### `session:start`

Emitted when a session begins.

```python
await hooks.emit("session:start", {"prompt": "Hello"})
```

### `session:end`

Emitted when a session ends.

```python
await hooks.emit("session:end", {})
```

## Error Events

### `tool:error`

Emitted when a tool execution fails.

```python
await hooks.emit(
    "tool:error",
    {
        "tool_name": "bash",
        "error": "Command failed with exit code 1",
        "tool_call_id": "call_123"
    }
)
```

### `provider:error`

Emitted when an LLM provider call fails.

```python
await hooks.emit(
    "provider:error",
    {
        "provider": "anthropic",
        "error": "Rate limit exceeded"
    }
)
```

## Streaming Events

### `content_block:start` / `content_block:delta` / `content_block:end`

For real-time streaming UI updates (not typically used for notifications).

## Event Selection Guide

| Use Case | Recommended Event |
|----------|-------------------|
| "Assistant ready for input" | `orchestrator:complete` |
| "Long operation finished" | `orchestrator:complete` with `turn_count` filter |
| "Tool execution failed" | `tool:error` |
| "Session finished" | `session:end` |
| "LLM error occurred" | `provider:error` |

## Hook Priority

When registering notification hooks, use a high priority number (runs later) so core functionality executes first:

```python
coordinator.hooks.register(
    "orchestrator:complete",
    handler,
    priority=100  # High number = runs after priority=10 hooks
)
```
