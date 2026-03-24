---
bundle:
  name: notify
  version: 0.1.0
  description: Desktop and terminal notifications when assistant turns complete

# Include the desktop notifications behavior by default
includes:
  - bundle: notify:behaviors/desktop-notifications
---

# Notify Bundle

This bundle provides desktop and terminal notifications when the assistant completes a turn and is ready for user input.

## Features

- **Cross-platform support**: macOS, Linux, Windows/WSL
- **SSH-aware**: Uses terminal escape sequences over SSH, desktop notifications locally
- **Terminal bell**: Fires BEL character to highlight background tabs (e.g., WezTerm turns tab yellow)
- **Focus detection**: Optionally suppress notifications when terminal is focused
- **Mobile push**: Optional ntfy.sh integration for mobile devices
- **Extensible**: Emits `notify:turn-complete` event for custom notification handlers

## Quick Start

Include in your bundle:

```yaml
includes:
  - bundle: git+https://github.com/microsoft/amplifier-bundle-notify@main
```

Or include just the behavior:

```yaml
includes:
  - bundle: git+https://github.com/microsoft/amplifier-bundle-notify@main#subdirectory=behaviors/desktop-notifications.yaml
```

## Configuration

The default behavior can be customized via the `hooks-notify` config:

```yaml
hooks:
  - module: hooks-notify
    source: git+https://github.com/microsoft/amplifier-bundle-notify@main#subdirectory=modules/hooks-notify
    config:
      enabled: true
      method: auto          # "auto", "terminal", or "desktop"
      title: "Amplifier"
      subtitle: "cwd"       # "cwd", "git", or custom string
      suppress_if_focused: true
      min_iterations: 1
      show_iteration_count: true
      sound: false
      bell: true            # Terminal bell for tab highlighting
```

## Disabling Notifications

**Environment variable** (easiest):
```bash
AMPLIFIER_NOTIFY=false amplifier run "..."
```

**Settings override** (`~/.amplifier/settings.yaml`):
```yaml
hooks:
  - module: hooks-notify
    config:
      enabled: false
```

**Profile exclusion**:
```yaml
exclude:
  hooks: [hooks-notify]
```

## Extending

See [docs/EXTENDING.md](docs/EXTENDING.md) for guidance on creating custom notification handlers (Slack, Teams, webhooks, etc.).

## Events

This bundle emits the `notify:turn-complete` event after sending notifications:

```python
{
    "session_id": "...",
    "turn_count": 3,
    "status": "success",
    "project": "my-project",
    "message": "Ready (3 iterations)",
    "notification_sent": True,
}
```

Custom hooks can listen to this event instead of parsing `orchestrator:complete` directly.

## Mobile Push Notifications

For mobile devices (Termius, JuiceSSH) where terminal escape sequences don't work, use the push notifications behavior:

```yaml
includes:
  - bundle: git+https://github.com/microsoft/amplifier-bundle-notify@main#subdirectory=behaviors/push-notifications.yaml
```

**Setup:**

1. Set your ntfy.sh topic:
   ```bash
   export AMPLIFIER_NTFY_TOPIC="your-secret-topic"
   ```

2. Install the [ntfy app](https://ntfy.sh/) on your phone and subscribe to your topic

See [modules/hooks-notify-push/README.md](modules/hooks-notify-push/README.md) for full configuration options.
