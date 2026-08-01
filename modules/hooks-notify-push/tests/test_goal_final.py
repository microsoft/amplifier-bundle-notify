"""Tests for the goal_final discriminator when hooks-notify-push listens
directly to orchestrator:complete (independent operation mode).

`goal_final` is a general contract field on the `orchestrator:complete` event
(NOT a /goal-specific concept - see context/EVENTS.md): it signals whether a
given emission is the true end of the user's turn. When this hook is
configured to listen directly to `orchestrator:complete` (bypassing
hooks-notify), it must apply the same filter: skip when `goal_final` is
explicitly False, and treat a missing field as True for backward
compatibility.
"""

from unittest.mock import AsyncMock

import pytest
from amplifier_module_hooks_notify_push import PushConfig, PushNotifyHook


def make_hook() -> tuple[PushNotifyHook, AsyncMock]:
    """Build a PushNotifyHook with its `_send_ntfy` transport mocked out."""
    config = PushConfig(enabled=True, topic="test-topic", debug=True)
    hook = PushNotifyHook(config)
    send_ntfy = AsyncMock(return_value=(True, None))
    hook._send_ntfy = send_ntfy  # type: ignore[method-assign]
    return hook, send_ntfy


@pytest.mark.asyncio
async def test_goal_final_false_suppresses_push_on_raw_event():
    """Intermediate continuation turns (goal_final=False) must not push."""
    hook, send_ntfy = make_hook()

    await hook.handle_event(
        "orchestrator:complete",
        {
            "orchestrator": "loop-streaming",
            "turn_count": 3,
            "status": "success",
            "goal_turn": 2,
            "goal_final": False,
        },
    )

    send_ntfy.assert_not_called()


@pytest.mark.asyncio
async def test_goal_final_true_sends_push_on_raw_event():
    """The final emission of a goal-driven turn (goal_final=True) must push."""
    hook, send_ntfy = make_hook()

    await hook.handle_event(
        "orchestrator:complete",
        {
            "orchestrator": "loop-streaming",
            "turn_count": 5,
            "status": "success",
            "goal_turn": 5,
            "goal_final": True,
        },
    )

    send_ntfy.assert_called_once()


@pytest.mark.asyncio
async def test_goal_final_absent_sends_push_on_raw_event():
    """Orchestrators without goal semantics emit no goal_final - must still push."""
    hook, send_ntfy = make_hook()

    await hook.handle_event(
        "orchestrator:complete",
        {
            "orchestrator": "loop-basic",
            "turn_count": 1,
            "status": "success",
        },
    )

    send_ntfy.assert_called_once()


@pytest.mark.asyncio
async def test_goal_final_irrelevant_on_normalized_event():
    """notify:turn-complete never carries goal_final - always pushes.

    hooks-notify only emits this normalized event once it has already
    determined the turn is final, so the field is absent by construction
    and the default-True behavior applies transparently.
    """
    hook, send_ntfy = make_hook()

    await hook.handle_event(
        "notify:turn-complete",
        {
            "session_id": "abc123",
            "turn_count": 5,
            "status": "success",
            "project": "myproject",
            "message": "Ready for input",
            "notification_sent": True,
        },
    )

    send_ntfy.assert_called_once()
