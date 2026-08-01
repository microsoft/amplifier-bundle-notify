"""Push Notifications Hook - Mobile/remote notifications via ntfy.sh.

Sends push notifications when the assistant completes a turn, perfect for
mobile devices (Termius, JuiceSSH) where terminal escape sequences don't work.

This hook listens to the `notify:turn-complete` event emitted by hooks-notify,
or can listen directly to `orchestrator:complete` for independent operation.

Supported Services:
- ntfy.sh (default) - Free, open-source, no signup required

SECURITY NOTE:
    ntfy.sh topics are PUBLIC - anyone who knows your topic can read your
    notifications. The topic is treated as a secret and should be stored in
    ~/.amplifier/keys.env, NOT in settings.yaml.

Environment Variables:
    AMPLIFIER_NTFY_TOPIC: ntfy.sh topic (REQUIRED - stored in keys.env)
    AMPLIFIER_NTFY_SERVER: ntfy.sh server URL (default: https://ntfy.sh)
    AMPLIFIER_NOTIFY_PUSH_ENABLED: Set to "false" to disable (default: true)

Configuration (settings.yaml - non-secret options only):
    enabled: bool (default: True) - Enable/disable push notifications
    service: str (default: "ntfy") - Push service to use ("ntfy")
    server: str (default: "https://ntfy.sh") - ntfy.sh server URL
    priority: str (default: "default") - Message priority (min, low, default, high, urgent)
    tags: list[str] (default: ["robot"]) - Emoji tags for the notification
    listen_event: str (default: "notify:turn-complete") - Event to listen to
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from amplifier_core import HookResult

logger = logging.getLogger(__name__)

# Track registered coordinators to prevent duplicate registration
_registered_coordinators: set[int] = set()


@dataclass
class PushConfig:
    """Configuration for push notifications."""

    enabled: bool = True
    service: str = "ntfy"
    topic: str = ""
    server: str = "https://ntfy.sh"
    priority: str = "default"
    tags: list[str] = field(default_factory=lambda: ["robot"])
    listen_event: str = "notify:turn-complete"
    include_project: bool = True
    include_iteration_count: bool = True
    debug: bool = False


class PushNotifyHook:
    """Hook handler for push notifications."""

    def __init__(self, config: PushConfig):
        self.config = config
        self._session = None

    async def _get_session(self):
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            import aiohttp

            self._session = aiohttp.ClientSession()
        return self._session

    async def _send_ntfy(self, title: str, message: str) -> tuple[bool, str | None]:
        """Send notification via ntfy.sh."""
        if not self.config.topic:
            return False, "No topic configured"

        url = f"{self.config.server.rstrip('/')}/{self.config.topic}"

        headers = {
            "Title": title,
            "Priority": self.config.priority,
        }

        if self.config.tags:
            headers["Tags"] = ",".join(self.config.tags)

        try:
            session = await self._get_session()
            async with session.post(
                url, data=message.encode(), headers=headers
            ) as resp:
                if resp.status == 200:
                    return True, None
                else:
                    body = await resp.text()
                    return False, f"HTTP {resp.status}: {body[:100]}"
        except Exception as e:
            return False, str(e)

    async def handle_event(self, event: str, data: dict[str, Any]) -> HookResult:
        """Handle notification event."""
        if not self.config.enabled:
            return HookResult(action="continue")

        # Skip sub-agent completions
        if data.get("parent_id"):
            return HookResult(action="continue")

        # `goal_final` is a general contract field on orchestrator:complete (NOT a
        # /goal-specific concept): it means "this emission is the true end of the
        # user's turn". This only matters when listening directly to
        # orchestrator:complete (independent operation mode) - notify:turn-complete
        # is already final by construction, and its data never carries this key, so
        # the check is a no-op on that path. Absent means the producing orchestrator
        # has no such concept and every turn it emits is final - treat missing as
        # True for backward compatibility.
        if data.get("goal_final", True) is False:
            if self.config.debug:
                logger.debug(
                    f"Skipping push: non-final turn (goal_turn={data.get('goal_turn')}, goal_final=False)"
                )
            return HookResult(action="continue")

        # Build notification content
        if event == "notify:turn-complete":
            # Semantic event from hooks-notify - use pre-computed values
            project = data.get("project", "Amplifier")
            message = data.get("message", "Ready for input")
            title = f"{project}" if self.config.include_project else "Amplifier"
        else:
            # Raw orchestrator:complete event
            turn_count = data.get("turn_count", 0)
            status = data.get("status", "unknown")

            title = "Amplifier"
            if status == "success":
                if self.config.include_iteration_count and turn_count > 1:
                    message = f"Ready ({turn_count} iterations)"
                else:
                    message = "Ready for input"
            else:
                message = f"Completed with status: {status}"

        # Send via configured service
        if self.config.service == "ntfy":
            success, error = await self._send_ntfy(title, message)
        else:
            success, error = False, f"Unknown service: {self.config.service}"

        if self.config.debug:
            if success:
                logger.debug(
                    f"Push notification sent via {self.config.service}: {message}"
                )
            else:
                logger.warning(f"Push notification failed: {error}")

        return HookResult(action="continue")

    async def cleanup(self):
        """Clean up resources."""
        if self._session and not self._session.closed:
            try:
                await asyncio.shield(self._session.close())
            except asyncio.CancelledError:
                pass  # Swallow cancellation during cleanup


async def mount(coordinator, config: dict | None = None):
    """Mount the push notification hook.

    Args:
        coordinator: The Amplifier coordinator instance
        config: Hook configuration dict with keys:
            enabled: bool (default: True)
            service: str (default: "ntfy")
            topic: str (required for ntfy, or use AMPLIFIER_NTFY_TOPIC)
            server: str (default: "https://ntfy.sh")
            priority: str (default: "default") - min, low, default, high, urgent
            tags: list[str] (default: ["robot"])
            listen_event: str (default: "notify:turn-complete")
            include_project: bool (default: True)
            include_iteration_count: bool (default: True)
            debug: bool (default: False)
    """
    # Prevent duplicate registration
    coord_id = id(coordinator)
    if coord_id in _registered_coordinators:
        return {"name": "hooks-notify-push", "status": "already registered"}
    _registered_coordinators.add(coord_id)

    config = config or {}

    # Check env var for easy disable
    env_push = os.environ.get("AMPLIFIER_NOTIFY_PUSH_ENABLED", "").lower()
    env_enabled = env_push not in ("false", "0", "no", "off")
    enabled = config.get("enabled", env_enabled)

    # SECURITY: Topic MUST come from env var only (stored in keys.env)
    # Never accept topic from config (settings.yaml) - it's a secret
    topic = os.environ.get("AMPLIFIER_NTFY_TOPIC", "")

    # Get server from config or env var (server URL is not secret)
    server = config.get("server", "") or os.environ.get(
        "AMPLIFIER_NTFY_SERVER", "https://ntfy.sh"
    )

    # Parse tags
    tags = config.get("tags", ["robot"])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]

    push_config = PushConfig(
        enabled=enabled,
        service=config.get("service", "ntfy"),
        topic=topic,
        server=server,
        priority=config.get("priority", "default"),
        tags=tags,
        listen_event=config.get("listen_event", "notify:turn-complete"),
        include_project=config.get("include_project", True),
        include_iteration_count=config.get("include_iteration_count", True),
        debug=config.get("debug", False),
    )

    # Warn if no topic configured
    if not push_config.topic and push_config.enabled:
        logger.warning(
            "hooks-notify-push: No topic configured. "
            "Set 'topic' in config or AMPLIFIER_NTFY_TOPIC env var."
        )
        # Disable to avoid errors
        push_config.enabled = False

    hook = PushNotifyHook(push_config)

    # Register for the configured event
    coordinator.hooks.register(
        push_config.listen_event,
        hook.handle_event,
        priority=110,  # Run after hooks-notify (priority 100)
        name="hooks-notify-push",
    )

    # Return cleanup function to properly close the aiohttp session
    # The hook's cleanup() method closes its lazy-initialized session
    return hook.cleanup
