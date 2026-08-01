"""Notify Hook - System notifications when assistant turns complete.

Fires notifications when the orchestrator completes a turn, signaling that
the assistant is ready for user input.

Notification Methods:
- terminal: OSC escape sequences (works over SSH!)
- desktop: Native OS notifications (macOS, Linux, Windows/WSL)
- auto: Terminal if SSH detected, otherwise desktop

Terminal notifications use OSC 9/777 escape sequences that modern terminals
like WezTerm, iTerm2, and Ghostty interpret as notification requests. This
works transparently over SSH because the sequences are just printed to stdout.

Environment Variables:
    AMPLIFIER_NOTIFY: Set to "false", "0", "no", or "off" to disable notifications.
                      Config `enabled` setting takes precedence over this env var.

Configuration:
    enabled: bool (default: True) - Enable/disable notifications
    method: str (default: "auto") - "auto", "terminal", or "desktop"
    title: str (default: "Amplifier") - Notification title
    subtitle: str (default: "cwd") - Subtitle source:
        - "cwd": Last segment of current working directory
        - "git": Git repository name (falls back to cwd)
        - Any other string: Used as literal subtitle
    suppress_if_focused: bool (default: False) - Skip notification if terminal appears focused
    min_iterations: int (default: 1) - Minimum loop iterations to trigger
    show_iteration_count: bool (default: True) - Show iteration count in message
    sound: bool (default: False) - Play sound with notification (macOS desktop only)
"""

import logging
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from typing import Any

from amplifier_core import HookResult

logger = logging.getLogger(__name__)


class Platform(str, Enum):
    """Supported notification platforms."""

    MACOS = "macos"
    LINUX = "linux"
    WSL = "wsl"
    WINDOWS = "windows"
    UNKNOWN = "unknown"


class NotifyMethod(str, Enum):
    """Notification delivery methods."""

    AUTO = "auto"
    TERMINAL = "terminal"
    DESKTOP = "desktop"


@dataclass
class NotifyConfig:
    """Configuration for notification hooks."""

    enabled: bool = True
    method: str = "auto"  # "auto", "terminal", "desktop"
    title: str = "Amplifier"  # Notification title
    subtitle: str = "cwd"  # "cwd", "git", or custom string (for project name)
    suppress_if_focused: bool = False  # Skip if terminal appears focused
    min_iterations: int = 1
    show_iteration_count: bool = True
    sound: bool = False
    bell: bool = True  # Send terminal bell (\x07) alongside notification (tab highlight)
    debug: bool = False
    # Message content options
    show_device: bool = True  # Show device/hostname in notification
    show_project: bool = True  # Show project name in notification
    show_preview: bool = True  # Show preview of last assistant message
    preview_length: int = 100  # Max characters for preview
    # Events to notify on (can be extended)
    events: list[str] = field(default_factory=lambda: ["orchestrator:complete"])


def detect_platform() -> Platform:
    """Detect the current platform."""
    system = platform.system()

    if system == "Darwin":
        return Platform.MACOS
    if system == "Linux":
        # Check if running in WSL
        try:
            with open("/proc/version") as f:
                if "microsoft" in f.read().lower():
                    return Platform.WSL
        except Exception:
            pass
        return Platform.LINUX
    if system == "Windows":
        return Platform.WINDOWS
    return Platform.UNKNOWN


def is_ssh_session() -> bool:
    """Detect if we're running in an SSH session."""
    # SSH_CLIENT or SSH_TTY are set when connected via SSH
    return bool(os.environ.get("SSH_CLIENT") or os.environ.get("SSH_TTY"))


def is_terminal_interactive() -> bool:
    """Check if stdout is connected to a terminal."""
    return sys.stdout.isatty()


def is_inside_tmux() -> bool:
    """Check if running inside tmux."""
    return bool(os.environ.get("TMUX"))


def detect_terminal_emulator() -> str | None:
    """Detect which terminal emulator we're running in.

    Returns terminal name or None if unknown.
    """
    # TERM_PROGRAM is set by many modern terminals
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    if term_program:
        return term_program  # "wezterm", "iterm.app", "apple_terminal", etc.

    # WezTerm also sets WEZTERM_EXECUTABLE
    if os.environ.get("WEZTERM_EXECUTABLE"):
        return "wezterm"

    # iTerm2 sets ITERM_SESSION_ID
    if os.environ.get("ITERM_SESSION_ID"):
        return "iterm2"

    # Ghostty sets GHOSTTY_RESOURCES_DIR
    if os.environ.get("GHOSTTY_RESOURCES_DIR"):
        return "ghostty"

    # Check TERM for hints (less reliable)
    term = os.environ.get("TERM", "")
    if "kitty" in term:
        return "kitty"

    return None


def supports_osc_notifications() -> bool:
    """Check if the terminal likely supports OSC 9/777 notifications.

    Returns True if:
    - Running in a known-supporting terminal (WezTerm, iTerm2, Ghostty, Kitty)
    - Connected via SSH (assume remote terminal can interpret OSC)
    - In WSL (likely connected to Windows terminal)
    - Inside tmux (passthrough will forward to outer terminal)

    Note: We don't strictly require isatty() because:
    - SSH sessions have SSH_TTY set even if our stdout is piped
    - tmux sessions have TMUX set even if our stdout is piped
    - The outer terminal can still receive OSC sequences via passthrough
    """
    # SSH session - assume remote terminal supports OSC notifications
    # SSH_TTY indicates there's a TTY on the SSH connection, even if
    # our process's stdout is piped through amplifier
    if is_ssh_session():
        return True

    # Inside tmux - can use passthrough to reach outer terminal
    if is_inside_tmux():
        return True

    # Known terminals that support OSC notifications
    terminal = detect_terminal_emulator()
    supporting_terminals = {"wezterm", "iterm2", "iterm.app", "ghostty", "kitty"}
    if terminal and terminal in supporting_terminals:
        return True

    # WSL - likely connected to Windows Terminal or similar
    try:
        with open("/proc/version") as f:
            if "microsoft" in f.read().lower():
                return True
    except Exception:
        pass

    # Fallback: require interactive terminal
    return is_terminal_interactive()


def is_inside_screen() -> bool:
    """Check if running inside GNU screen."""
    return bool(os.environ.get("STY"))


def wrap_for_tmux(sequence: str) -> str:
    """Wrap an escape sequence for tmux passthrough.

    tmux intercepts escape sequences by default. To pass them through
    to the outer terminal, we wrap them in DCS (Device Control String):

    ESC P tmux; ESC <sequence> ST

    Where ST is ESC \\ (String Terminator)

    Note: Requires tmux 3.3+ with allow-passthrough enabled, or tmux 3.4+
    where passthrough is on by default for new sessions.
    """
    # DCS tmux; ESC <escaped_sequence> ST
    # The inner escape sequences need their ESC bytes doubled
    escaped = sequence.replace("\x1b", "\x1b\x1b")
    return f"\x1bPtmux;{escaped}\x1b\\"


def wrap_for_screen(sequence: str) -> str:
    """Wrap an escape sequence for GNU screen passthrough.

    Similar to tmux, screen intercepts escape sequences.
    """
    # DCS <sequence> ST
    return f"\x1bP{sequence}\x1b\\"


# =============================================================================
# Terminal Notifications (OSC Escape Sequences)
# =============================================================================


def get_tty_for_output() -> tuple[str | None, str | None]:
    """Get the best file descriptor for writing OSC sequences.

    Returns:
        Tuple of (file_path_or_None, description)
        - For tmux: /dev/tty (tmux pane's PTY, not SSH_TTY)
        - For SSH (no tmux): SSH_TTY device
        - For interactive terminal: None (use stdout)
        - Otherwise: None with error description
    """
    # Inside tmux - use /dev/tty (the tmux pane's PTY)
    # NOT SSH_TTY, which is the SSH connection's PTY that tmux reads from
    if is_inside_tmux():
        if os.path.exists("/dev/tty"):
            try:
                with open("/dev/tty", "w") as f:
                    pass
                return "/dev/tty", "tmux pane TTY (/dev/tty)"
            except (IOError, OSError):
                pass

    # SSH session (no tmux) - use SSH_TTY directly to bypass piped stdout
    ssh_tty = os.environ.get("SSH_TTY")
    if ssh_tty and os.path.exists(ssh_tty):
        return ssh_tty, f"SSH TTY ({ssh_tty})"

    # Check if stdout is a TTY
    if sys.stdout.isatty():
        return None, "stdout"  # None means use stdout

    # Try /dev/tty as fallback (controlling terminal)
    if os.path.exists("/dev/tty"):
        try:
            # Test if we can open it
            with open("/dev/tty", "w") as f:
                pass
            return "/dev/tty", "controlling terminal"
        except (IOError, OSError):
            pass

    return None, "no terminal available"


def send_terminal_notification(
    message: str,
    title: str = "Amplifier",
    subtitle: str | None = None,
) -> tuple[bool, str | None]:
    """Send notification via terminal OSC escape sequences.

    Works over SSH because these are written directly to the TTY device,
    bypassing any stdout piping by the parent process.

    Supports:
    - OSC 9: Simple notification (iTerm2, WezTerm, ConEmu)
    - OSC 777: Notification with title (rxvt-unicode, Ghostty, WezTerm)
    - tmux passthrough: Wraps sequences for tmux compatibility
    - screen passthrough: Wraps sequences for GNU screen compatibility

    Args:
        message: Notification message
        title: Notification title
        subtitle: Optional subtitle (included in message)

    Returns:
        Tuple of (success, error_message)
    """
    tty_path, tty_desc = get_tty_for_output()

    # If tty_path is None and tty_desc indicates an error, fail
    if tty_path is None and tty_desc == "no terminal available":
        return False, "No terminal available for OSC output"

    try:
        # Build the full message
        if subtitle:
            full_message = f"{subtitle}: {message}"
        else:
            full_message = message

        # Escape special characters
        title = title.replace("\\", "\\\\").replace(";", "")
        full_message = full_message.replace("\\", "\\\\").replace(";", "")

        # OSC 777 - notification with title (WezTerm, Ghostty)
        # Format: ESC ] 777 ; notify ; title ; body ST
        # Using ST (\x1b\\) instead of BEL (\x07) per WezTerm docs
        osc_777 = f"\x1b]777;notify;{title};{full_message}\x1b\\"

        # OSC 9 - simple notification (iTerm2 style, fallback)
        # Format: ESC ] 9 ; message ST
        osc_9 = f"\x1b]9;{title}: {full_message}\x1b\\"

        # Wrap for terminal multiplexers if needed
        in_tmux = is_inside_tmux()
        in_screen = is_inside_screen()

        if in_tmux:
            # tmux passthrough: wrap sequences so they reach the outer terminal
            osc_777 = wrap_for_tmux(osc_777)
            osc_9 = wrap_for_tmux(osc_9)
        elif in_screen:
            osc_777 = wrap_for_screen(osc_777)
            osc_9 = wrap_for_screen(osc_9)

        # Write to the appropriate output
        # Only send OSC 777 (the richer format with separate title/body)
        # OSC 9 is a simpler format - no need to send both as modern terminals
        # understand OSC 777 and sending both causes duplicate notifications
        if tty_path:
            # Write directly to TTY device
            with open(tty_path, "w") as tty:
                tty.write(osc_777)
                tty.flush()
        else:
            # Use stdout
            sys.stdout.write(osc_777)
            sys.stdout.flush()

        multiplexer = "tmux" if in_tmux else ("screen" if in_screen else None)
        detail = (
            f"via {multiplexer} passthrough to {tty_desc}"
            if multiplexer
            else f"to {tty_desc}"
        )
        return True, detail
    except Exception as e:
        return False, str(e)


def send_bell() -> tuple[bool, str | None]:
    """Send terminal bell (BEL character) for tab highlighting.

    Works universally — any terminal, any SSH chain, even dumb terminals.
    In WezTerm with the amplifier-cli-tools bell handler, this turns the
    background tab yellow until the user switches to it.
    """
    tty_path, tty_desc = get_tty_for_output()
    if tty_path is None and tty_desc == "no terminal available":
        return False, "No terminal available for bell"
    try:
        bell = "\x07"
        if tty_path:
            with open(tty_path, "w") as tty:
                tty.write(bell)
                tty.flush()
        else:
            sys.stdout.write(bell)
            sys.stdout.flush()
        return True, f"bell to {tty_desc}"
    except Exception as e:
        return False, str(e)


# =============================================================================
# Desktop Notifications (Native OS)
# =============================================================================


def _escape_quotes(text: str) -> str:
    """Escape quotes for shell commands."""
    return text.replace('"', '\\"').replace("'", "\\'")


def send_macos_notification(
    message: str,
    title: str = "Amplifier",
    subtitle: str | None = None,
    sound: bool = False,
) -> tuple[bool, str | None]:
    """Send notification on macOS using osascript."""
    try:
        message = _escape_quotes(message)
        title = _escape_quotes(title)

        script_parts = [f'display notification "{message}" with title "{title}"']
        if subtitle:
            subtitle = _escape_quotes(subtitle)
            script_parts[0] = (
                f'display notification "{message}" with title "{title}" subtitle "{subtitle}"'
            )
        if sound:
            script_parts[0] += ' sound name "default"'

        result = subprocess.run(
            ["osascript", "-e", script_parts[0]],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0, result.stderr if result.returncode != 0 else None
    except Exception as e:
        return False, str(e)


def send_linux_notification(
    message: str, title: str = "Amplifier", subtitle: str | None = None
) -> tuple[bool, str | None]:
    """Send notification on Linux using notify-send."""
    if not shutil.which("notify-send"):
        return False, "notify-send not found (install libnotify-bin)"

    try:
        display_title = f"{subtitle}" if subtitle else title

        result = subprocess.run(
            ["notify-send", display_title, message],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0, result.stderr if result.returncode != 0 else None
    except Exception as e:
        return False, str(e)


def send_wsl_notification(
    message: str, title: str = "Amplifier", subtitle: str | None = None
) -> tuple[bool, str | None]:
    """Send notification on WSL using Windows PowerShell."""
    try:
        # Escape special characters for PowerShell
        message = message.replace("'", "''").replace('"', '`"')
        title = title.replace("'", "''").replace('"', '`"')

        if subtitle:
            subtitle = subtitle.replace("'", "''").replace('"', '`"')
            ps_script = f"""
                [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
                [Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
                [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

                $APP_ID = '{title}'
                $template = @"
<toast><visual><binding template='ToastText02'>
    <text id='1'>{subtitle}</text>
    <text id='2'>{message}</text>
</binding></visual></toast>
"@
                $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
                $xml.LoadXml($template)
                $toast = New-Object Windows.UI.Notifications.ToastNotification $xml
                [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($APP_ID).Show($toast)
            """
        else:
            ps_script = f"""
                [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
                [Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
                [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

                $APP_ID = '{title}'
                $template = @"
<toast><visual><binding template='ToastText01'>
    <text id='1'>{message}</text>
</binding></visual></toast>
"@
                $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
                $xml.LoadXml($template)
                $toast = New-Object Windows.UI.Notifications.ToastNotification $xml
                [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($APP_ID).Show($toast)
            """

        result = subprocess.run(
            ["powershell.exe", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0, result.stderr if result.returncode != 0 else None
    except Exception as e:
        return False, str(e)


def send_desktop_notification(
    message: str,
    title: str = "Amplifier",
    subtitle: str | None = None,
    sound: bool = False,
) -> tuple[bool, str | None]:
    """Send a desktop notification on the current platform.

    Args:
        message: Main notification message
        title: Notification title
        subtitle: Optional subtitle
        sound: Play sound (macOS only)

    Returns:
        Tuple of (success, error_message)
    """
    plat = detect_platform()

    if plat == Platform.MACOS:
        return send_macos_notification(message, title, subtitle, sound)
    elif plat == Platform.LINUX:
        return send_linux_notification(message, title, subtitle)
    elif plat == Platform.WSL:
        return send_wsl_notification(message, title, subtitle)
    elif plat == Platform.WINDOWS:
        return send_wsl_notification(message, title, subtitle)
    else:
        return False, f"Unsupported platform: {plat}"


# =============================================================================
# Unified Notification Interface
# =============================================================================


def send_notification(
    message: str,
    title: str = "Amplifier",
    subtitle: str | None = None,
    sound: bool = False,
    method: str = "auto",
) -> tuple[bool, str | None]:
    """Send a notification using the specified method.

    Args:
        message: Notification message
        title: Notification title
        subtitle: Optional subtitle
        sound: Play sound (desktop only, macOS only)
        method: "auto", "terminal", or "desktop"

    Returns:
        Tuple of (success, error_message)
    """
    # Determine which method to use
    if method == "terminal":
        use_terminal = True
    elif method == "desktop":
        use_terminal = False
    else:  # auto
        # Use terminal notifications if:
        # - Running in a known-supporting terminal (WezTerm, iTerm2, etc.)
        # - Connected via SSH (assume remote terminal supports OSC)
        # - In WSL (likely connected to Windows Terminal or WezTerm)
        use_terminal = supports_osc_notifications()

    if use_terminal:
        return send_terminal_notification(message, title, subtitle)
    else:
        return send_desktop_notification(message, title, subtitle, sound)


# =============================================================================
# Hook Implementation
# =============================================================================


def get_cwd_name() -> str:
    """Get the last segment of the current working directory."""
    from pathlib import Path

    return Path.cwd().name


def get_git_repo_name() -> str | None:
    """Get the git repository name, or None if not in a git repo.

    Tries in order:
    1. Repo name from remote origin URL
    2. Git toplevel directory name
    """
    from pathlib import Path

    # Try to get git repo name from remote URL
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0 and result.stdout.strip():
            url = result.stdout.strip()
            # Extract repo name from URL (handles .git suffix)
            name = url.rstrip("/").split("/")[-1]
            if name.endswith(".git"):
                name = name[:-4]
            return name
    except Exception:
        pass

    # Try git toplevel directory name
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()).name
    except Exception:
        pass

    return None


def get_device_name() -> str:
    """Get short device/hostname.

    Returns the short hostname (before first dot) for use in notifications.
    """
    import socket

    try:
        hostname = socket.gethostname()
        # Return short name (before first dot)
        return hostname.split(".")[0]
    except Exception:
        return ""


def get_project_name(config_value: str) -> str:
    """Resolve the project name based on config value.

    Args:
        config_value: One of:
            - "cwd": Use last segment of current working directory
            - "git": Use git repo name (falls back to cwd)
            - Any other string: Use as literal value

    Returns:
        The resolved project name string
    """
    if config_value == "cwd":
        return get_cwd_name()
    elif config_value == "git":
        return get_git_repo_name() or get_cwd_name()
    else:
        # Custom string - use as-is
        return config_value


def build_notification_body(
    device: str | None,
    project: str | None,
    content: str,
) -> str:
    """Build notification body with pipe-separated fields.

    Format: <device> | <project> | <content>
    Smart about separators - only shows fields that are populated.

    Args:
        device: Device/hostname (or None to omit)
        project: Project name (or None to omit)
        content: Main content (preview or status)

    Returns:
        Formatted notification body string
    """
    parts = []
    if device:
        parts.append(device)
    if project:
        parts.append(project)
    parts.append(content)

    return " | ".join(parts)


def is_terminal_focused() -> bool | None:
    """Check if the terminal appears to be focused/active.

    Returns:
        True if terminal is focused
        False if terminal is not focused
        None if focus cannot be determined (assume not focused)

    Detection methods by environment:
    - tmux: Check if current pane is active and window is focused
    - macOS: Check if Terminal/iTerm2 is frontmost app (desktop only)
    - Linux X11: Check focused window (requires xdotool)
    - SSH: Cannot determine client-side focus, returns None
    """
    # Inside tmux - check if pane is active
    if is_inside_tmux():
        try:
            # Check if this pane is the active pane in the active window
            # #{pane_active} is 1 if this is the active pane
            # #{window_active} is 1 if this is the active window
            result = subprocess.run(
                ["tmux", "display-message", "-p", "#{pane_active}#{window_active}"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if result.returncode == 0:
                flags = result.stdout.strip()
                # Both must be "1" for the pane to be visible and active
                if flags == "11":
                    # Pane is active, but we can't tell if tmux itself is focused
                    # in the terminal - return None to indicate uncertainty
                    return None
                else:
                    # Pane is not active - definitely should notify
                    return False
        except Exception:
            pass
        return None

    # SSH session without tmux - can't determine client-side focus
    if is_ssh_session():
        return None

    # Local macOS - check if terminal app is frontmost
    plat = detect_platform()
    if plat == Platform.MACOS:
        try:
            # Check if Terminal or iTerm2 is the frontmost application
            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of first application process whose frontmost is true',
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                frontmost = result.stdout.strip().lower()
                terminal_apps = {
                    "terminal",
                    "iterm2",
                    "iterm",
                    "wezterm",
                    "kitty",
                    "alacritty",
                    "ghostty",
                }
                return frontmost in terminal_apps
        except Exception:
            pass

    # Linux with X11 - try xdotool
    elif plat == Platform.LINUX and os.environ.get("DISPLAY"):
        try:
            # Get active window ID
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                window_name = result.stdout.strip().lower()
                # Check if it looks like a terminal
                terminal_keywords = {
                    "terminal",
                    "konsole",
                    "gnome-terminal",
                    "xterm",
                    "kitty",
                    "alacritty",
                    "wezterm",
                    "ghostty",
                }
                return any(kw in window_name for kw in terminal_keywords)
        except Exception:
            pass

    # Cannot determine focus
    return None


async def get_last_assistant_preview(coordinator, max_length: int = 100) -> str | None:
    """Extract a preview of the last assistant message from context.

    Args:
        coordinator: The coordinator instance with mounted context
        max_length: Maximum characters for the preview

    Returns:
        Preview string or None if no assistant message found
    """
    if not coordinator:
        return None

    try:
        # Access the context module via coordinator
        context = coordinator.get("context")
        if not context:
            return None

        # Get messages from context
        messages = await context.get_messages()
        if not messages:
            return None

        # Find last assistant message (iterate backwards)
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if not content:
                    continue

                # Handle content that might be a list (tool calls, etc.)
                if isinstance(content, list):
                    # Extract text from content blocks
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif isinstance(block, str):
                            text_parts.append(block)
                    content = " ".join(text_parts)

                if not content or not isinstance(content, str):
                    continue

                # Clean up the content for notification display
                # Remove leading/trailing whitespace and collapse internal whitespace
                content = " ".join(content.split())

                # Truncate to max_length
                if len(content) > max_length:
                    content = content[: max_length - 3] + "..."

                return content

        return None
    except Exception as e:
        logger.debug(f"Failed to get assistant preview: {e}")
        return None


class NotifyHooks:
    """Hook handlers for system notifications."""

    def __init__(self, config: NotifyConfig, coordinator=None):
        self.config = config
        self.coordinator = coordinator
        self.platform = detect_platform()
        self.is_ssh = is_ssh_session()
        # Pre-compute device and project since they won't change during session
        self.device_name = get_device_name() if config.show_device else None
        self.project_name = (
            get_project_name(config.subtitle) if config.show_project else None
        )

    async def handle_orchestrator_complete(
        self, event: str, data: dict[str, Any]
    ) -> HookResult:
        """Fire notification when orchestrator completes a turn."""
        if not self.config.enabled:
            return HookResult(action="continue")

        # Policy behavior: skip sub-sessions (agents, recipe steps, etc.)
        # Notifications should only fire for root/interactive sessions
        if data.get("parent_id"):
            if self.config.debug:
                logger.debug(
                    f"Skipping notification: sub-session (parent_id={data.get('parent_id')})"
                )
            return HookResult(action="continue")

        # `goal_final` is a general contract field on orchestrator:complete (NOT a
        # /goal-specific concept): it means "this emission is the true end of the
        # user's turn". Any orchestrator that runs multiple internal continuation
        # iterations for a single user prompt can emit orchestrator:complete once
        # per iteration, with goal_final=False on every intermediate emission and
        # goal_final=True only on the one that corresponds to a finished user turn.
        # Notify cares about turn *completion*, so it honors this field generically.
        # Absent means the producing orchestrator has no such concept and every
        # turn it emits is final - treat missing as True for backward compatibility.
        if data.get("goal_final", True) is False:
            if self.config.debug:
                logger.debug(
                    f"Skipping notification: non-final turn (goal_turn={data.get('goal_turn')}, goal_final=False)"
                )
            return HookResult(action="continue")

        # Check if we should suppress due to terminal being focused
        if self.config.suppress_if_focused:
            focused = is_terminal_focused()
            if focused is True:
                if self.config.debug:
                    logger.debug("Skipping notification: terminal is focused")
                return HookResult(action="continue")
            # If focused is False or None, proceed with notification

        turn_count = data.get("turn_count", 0)
        status = data.get("status", "complete")

        # Skip if below minimum iteration threshold
        if turn_count < self.config.min_iterations:
            if self.config.debug:
                logger.debug(
                    f"Skipping notification: turn_count={turn_count} < min_iterations={self.config.min_iterations}"
                )
            return HookResult(action="continue")

        # Build notification message
        # Try to get a preview of the last assistant message
        preview = None
        if self.config.show_preview:
            preview = await get_last_assistant_preview(
                self.coordinator, self.config.preview_length
            )

        # Build content part of message
        if preview:
            content = preview
        elif self.config.show_iteration_count and turn_count > 1:
            content = f"Ready ({turn_count} iterations)"
        else:
            content = "Ready for input"

        # Add status if not success
        if status != "success":
            content = f"{content} [{status}]"

        # Build full message with pipe-separated fields: device | project | content
        message = build_notification_body(
            device=self.device_name,
            project=self.project_name,
            content=content,
        )

        # Send the notification (no subtitle - all info is in the message body now)
        success, error = send_notification(
            message=message,
            title=self.config.title,
            subtitle=None,
            sound=self.config.sound,
            method=self.config.method,
        )

        # Send terminal bell alongside the notification (for tab highlighting)
        if self.config.bell:
            bell_ok, bell_detail = send_bell()
            if self.config.debug:
                if bell_ok:
                    logger.debug(f"Bell sent: {bell_detail}")
                else:
                    logger.debug(f"Bell failed: {bell_detail}")

        if self.config.debug:
            method_used = (
                "terminal"
                if (
                    self.config.method == "terminal"
                    or (self.config.method == "auto" and self.is_ssh)
                )
                else "desktop"
            )
            if success:
                logger.debug(f"Notification sent via {method_used}: {message}")
            else:
                logger.warning(f"Notification failed via {method_used}: {error}")

        # Emit semantic event for other notification hooks to consume
        # This allows downstream hooks to listen to notify:turn-complete instead of
        # orchestrator:complete, getting normalized data without parsing orchestrator internals
        if self.coordinator:
            try:
                await self.coordinator.hooks.emit(
                    "notify:turn-complete",
                    {
                        "session_id": data.get("session_id"),
                        "turn_count": turn_count,
                        "status": status,
                        "project": self.project_name,
                        "message": message,
                        "notification_sent": success,
                    },
                )
            except Exception as e:
                # Don't fail the hook if event emission fails
                logger.debug(f"Failed to emit notify:turn-complete: {e}")

        return HookResult(action="continue")


# Track registered coordinators to prevent duplicate registrations
_registered_coordinators: set[int] = set()


async def mount(coordinator, config: dict | None = None):
    """Mount the notify hooks module.

    Args:
        coordinator: The ModuleCoordinator instance
        config: Optional configuration dict with keys:
            enabled: bool (default: True)
            method: str (default: "auto") - "auto", "terminal", "desktop"
            title: str (default: "Amplifier") - Notification title
            subtitle: str (default: "cwd") - "cwd", "git", or custom string
            suppress_if_focused: bool (default: False) - Skip if terminal focused
            min_iterations: int (default: 1)
            show_iteration_count: bool (default: True)
            sound: bool (default: False)
            debug: bool (default: False)
    """
    # Prevent duplicate registration on same coordinator
    coord_id = id(coordinator)
    if coord_id in _registered_coordinators:
        return {"name": "hooks-notify", "status": "already registered"}
    _registered_coordinators.add(coord_id)

    config = config or {}

    # Check AMPLIFIER_NOTIFY env var for easy disable
    # Config takes precedence over env var
    env_notify = os.environ.get("AMPLIFIER_NOTIFY", "").lower()
    env_enabled = env_notify not in ("false", "0", "no", "off")
    enabled = config.get("enabled", env_enabled)

    notify_config = NotifyConfig(
        enabled=enabled,
        method=config.get("method", "auto"),
        title=config.get("title", "Amplifier"),
        subtitle=config.get("subtitle", "cwd"),
        suppress_if_focused=config.get("suppress_if_focused", False),
        min_iterations=config.get("min_iterations", 1),
        show_iteration_count=config.get("show_iteration_count", True),
        sound=config.get("sound", False),
        debug=config.get("debug", False),
    )

    hooks = NotifyHooks(notify_config, coordinator=coordinator)
    platform_detected = hooks.platform
    is_ssh = hooks.is_ssh

    # Register for orchestrator completion - use high priority number (runs later)
    # so core hooks run first
    coordinator.hooks.register(
        "orchestrator:complete",
        hooks.handle_orchestrator_complete,
        priority=100,
        name="hooks-notify",
    )

    return {
        "name": "hooks-notify",
        "version": "0.3.0",
        "description": "Notifications on turn completion (terminal + desktop)",
        "platform": platform_detected.value,
        "is_ssh": is_ssh,
        "config": {
            "enabled": notify_config.enabled,
            "method": notify_config.method,
            "title": notify_config.title,
            "project_name": hooks.project_name,  # Resolved value
            "device_name": hooks.device_name,  # Resolved value
            "suppress_if_focused": notify_config.suppress_if_focused,
            "min_iterations": notify_config.min_iterations,
        },
    }
