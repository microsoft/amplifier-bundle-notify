"""Tests for the goal_final / goal_turn discriminator on orchestrator:complete.

`goal_final` is a general contract field on the `orchestrator:complete` event
(NOT a /goal-specific concept - see context/EVENTS.md): it signals whether a
given emission is the true end of the user's turn. Notify must skip when it
is explicitly False, and treat a missing field as True for backward
compatibility with orchestrators that never adopt goal semantics.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from amplifier_module_hooks_notify import NotifyConfig, NotifyHooks


def make_hooks(**config_overrides) -> tuple[NotifyHooks, MagicMock]:
    """Build a NotifyHooks instance with a mock coordinator.

    Disables show_device/show_project so construction doesn't shell out to
    git/hostname lookups, and disables the preview/bell/focus side paths
    that aren't relevant to the goal_final filtering behavior under test.
    """
    config = NotifyConfig(
        show_device=False,
        show_project=False,
        show_preview=False,
        bell=False,
        suppress_if_focused=False,
        debug=True,
        **config_overrides,
    )
    coordinator = MagicMock()
    coordinator.hooks.emit = AsyncMock()
    hooks = NotifyHooks(config, coordinator=coordinator)
    return hooks, coordinator


@pytest.mark.asyncio
async def test_goal_final_false_suppresses_notification(monkeypatch):
    """Intermediate continuation turns (goal_final=False) must not notify."""
    send_notification = MagicMock(return_value=(True, None))
    monkeypatch.setattr(
        "amplifier_module_hooks_notify.send_notification", send_notification
    )

    hooks, coordinator = make_hooks()

    await hooks.handle_orchestrator_complete(
        "orchestrator:complete",
        {
            "orchestrator": "loop-streaming",
            "turn_count": 3,
            "status": "success",
            "goal_turn": 2,
            "goal_final": False,
        },
    )

    send_notification.assert_not_called()
    coordinator.hooks.emit.assert_not_called()


@pytest.mark.asyncio
async def test_goal_final_true_sends_notification(monkeypatch):
    """The final emission of a goal-driven turn (goal_final=True) must notify."""
    send_notification = MagicMock(return_value=(True, None))
    monkeypatch.setattr(
        "amplifier_module_hooks_notify.send_notification", send_notification
    )

    hooks, coordinator = make_hooks()

    await hooks.handle_orchestrator_complete(
        "orchestrator:complete",
        {
            "orchestrator": "loop-streaming",
            "turn_count": 5,
            "status": "success",
            "goal_turn": 5,
            "goal_final": True,
        },
    )

    send_notification.assert_called_once()
    coordinator.hooks.emit.assert_called_once()


@pytest.mark.asyncio
async def test_goal_final_absent_sends_notification(monkeypatch):
    """Orchestrators that never adopt goal semantics emit no goal_final field.

    Absence must mean "yes, notify" - backward compatible with every
    orchestrator that has no continuation-turn concept at all.
    """
    send_notification = MagicMock(return_value=(True, None))
    monkeypatch.setattr(
        "amplifier_module_hooks_notify.send_notification", send_notification
    )

    hooks, coordinator = make_hooks()

    await hooks.handle_orchestrator_complete(
        "orchestrator:complete",
        {
            "orchestrator": "loop-basic",
            "turn_count": 1,
            "status": "success",
        },
    )

    send_notification.assert_called_once()
    coordinator.hooks.emit.assert_called_once()
