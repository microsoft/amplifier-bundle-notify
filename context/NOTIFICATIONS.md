# Amplifier Notification System

This document describes the notification system architecture and how to extend it.

## Overview

The notify bundle provides notifications when Amplifier completes assistant turns. This allows users to switch to other tasks while waiting for long-running operations.

**Key Feature: SSH Support via Terminal Notifications**

When you're SSH'd into a remote machine, traditional desktop notifications won't work. The notify bundle solves this with OSC escape sequences that flow through your SSH connection and trigger notifications on your local terminal (WezTerm, iTerm2, etc.).

## Notification Methods

| Method | How It Works | Best For |
|--------|--------------|----------|
| `terminal` | OSC escape sequences to stdout | SSH sessions, remote development |
| `desktop` | Native OS notifications | Local development |
| `auto` | Terminal if SSH detected, else desktop | Most users |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Orchestrator                            │
│                                                              │
│   execute() loop completes                                   │
│           │                                                  │
│           ▼                                                  │
│   hooks.emit("orchestrator:complete", {                      │
│       "orchestrator": "loop-streaming",                      │
│       "turn_count": 3,                                       │
│       "status": "success"                                    │
│   })                                                         │
└─────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    hooks-notify module                       │
│                                                              │
│   handle_orchestrator_complete()                             │
│           │                                                  │
│           ▼                                                  │
│   detect_platform() → Platform.LINUX                         │
│           │                                                  │
│           ▼                                                  │
│   send_notification()                                        │
│           │                                                  │
│           ▼                                                  │
│   notify-send "Ready (3 iterations)"                         │
└─────────────────────────────────────────────────────────────┘
```

## Event: `orchestrator:complete`

This is the canonical event for "assistant turn finished, ready for user input."

### Event Data

| Field | Type | Description |
|-------|------|-------------|
| `orchestrator` | string | Name of orchestrator (e.g., "loop-streaming") |
| `turn_count` | int | Number of LLM iterations in this turn |
| `status` | string | "success" or "incomplete" |
| `goal_turn` | int \| None | Which continuation iteration this emission belongs to, for orchestrators that run multiple internal iterations to satisfy one user prompt. `None` when no such continuation is active. |
| `goal_final` | bool | Whether this emission is the true end of the user's turn - `False` on intermediate continuation iterations, `True` on the one that corresponds to a finished user turn. **Missing on orchestrators without this concept - treat absence as `True`.** Consumers that treat `orchestrator:complete` as "notify/act now" must check this field and skip when it is explicitly `False`. See `EVENTS.md` for the full contract. |

### Emission Points

- **loop-basic**: Emits after final response, before returning
- **loop-streaming**: Emits after streaming completes

## Platform Support

### macOS

Uses `osascript` to send notifications via Notification Center:

```bash
osascript -e 'display notification "Ready" with title "Amplifier"'
```

Features:
- Native Notification Center integration
- Optional sound support
- Subtitle support

### Linux

Uses `notify-send` (libnotify):

```bash
notify-send "Amplifier" "Ready for input"
```

Requirements:
- `libnotify-bin` package (Ubuntu/Debian: `apt install libnotify-bin`)

Features:
- Works with most desktop environments (GNOME, KDE, XFCE, etc.)
- Icon support (not yet implemented)

### Windows/WSL

Uses PowerShell toast notifications:

```powershell
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Amplifier").Show($toast)
```

Features:
- Windows 10/11 toast notifications
- Works from WSL via powershell.exe

## Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | true | Enable/disable notifications |
| `title` | string | "Amplifier" | Notification title |
| `min_iterations` | int | 1 | Minimum iterations to trigger notification |
| `show_iteration_count` | bool | true | Include iteration count in message |
| `sound` | bool | false | Play sound (macOS only) |
| `debug` | bool | false | Enable debug logging |

## Extending the System

### Adding New Events

To notify on additional events, modify the mount function:

```python
def mount(coordinator, config):
    hooks = NotifyHooks(config)
    
    # Existing
    coordinator.hooks.register("orchestrator:complete", hooks.handle_orchestrator_complete)
    
    # New events
    coordinator.hooks.register("tool:error", hooks.handle_tool_error)
    coordinator.hooks.register("session:end", hooks.handle_session_end)
```

### Adding Webhook Support

For mobile push notifications, add a webhook handler:

```python
async def send_webhook(self, event: str, data: dict):
    """Send to webhook for mobile push."""
    if not self.config.webhook_url:
        return
    
    async with aiohttp.ClientSession() as session:
        await session.post(self.config.webhook_url, json={
            "event": event,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        })
```

### Custom Notification Providers

For enterprise integrations (Slack, Teams, etc.):

```python
class SlackNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    async def notify(self, message: str):
        async with aiohttp.ClientSession() as session:
            await session.post(self.webhook_url, json={
                "text": message
            })
```

## Troubleshooting

### Linux: "notify-send not found"

Install libnotify:
```bash
# Ubuntu/Debian
sudo apt install libnotify-bin

# Fedora
sudo dnf install libnotify

# Arch
sudo pacman -S libnotify
```

### macOS: Notifications not appearing

1. Check System Preferences → Notifications → Script Editor
2. Ensure "Allow Notifications" is enabled
3. Try running osascript manually to verify

### WSL: PowerShell errors

1. Ensure powershell.exe is in PATH
2. Check Windows notification settings
3. Verify WSL interop is enabled

### No notification appears

1. Set `debug: true` in config
2. Check logs for errors
3. Verify platform detection is correct
