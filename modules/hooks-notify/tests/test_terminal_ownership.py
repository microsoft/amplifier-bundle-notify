"""Tests that notify only ever writes to a terminal this process owns.

Regression coverage for the mid-turn bell: an interactive Amplifier session
shells out via the bash tool to a nested `amplifier run`. That child is a
genuine *root* session (`parent_id` is None) and its turn legitimately
completes while the parent is still mid-turn, so neither the sub-session guard
nor the `goal_final` guard applies to it.

The child is correctly detached - it has no controlling terminal, so opening
/dev/tty fails with ENXIO. But it *inherits* SSH_TTY and TMUX through the
environment, and those are plain strings. Resolving the output terminal from
them let the child open its parent's PTY by path and ring the bell there,
mid-turn, in a session it does not own.

The invariant under test: an inherited environment variable proves a terminal
exists somewhere in this process's ancestry, never that the terminal belongs
to this process. Ownership is decided by /dev/tty, nothing else.
"""

import sys

import pytest
from amplifier_module_hooks_notify import (
    get_tty_for_output,
    owns_controlling_terminal,
    send_bell,
)

MODULE = "amplifier_module_hooks_notify"

# A path that reliably exists, standing in for the SSH_TTY device node so the
# tests exercise the ownership gate rather than an existence check.
EXISTING_TTY_PATH = "/dev/null"


@pytest.fixture
def detached(monkeypatch):
    """Simulate a process with no controlling terminal (the nested run)."""
    monkeypatch.setattr(f"{MODULE}.owns_controlling_terminal", lambda: False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)


@pytest.fixture
def attached(monkeypatch):
    """Simulate a process that owns its controlling terminal (interactive)."""
    monkeypatch.setattr(f"{MODULE}.owns_controlling_terminal", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)


def test_owns_controlling_terminal_false_when_dev_tty_unopenable(monkeypatch):
    """ENXIO on /dev/tty is exactly how a detached subprocess presents."""
    real_open = open

    def fake_open(path, *args, **kwargs):
        if path == "/dev/tty":
            raise OSError(6, "No such device or address")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)

    assert owns_controlling_terminal() is False


def test_owns_controlling_terminal_true_when_dev_tty_openable(monkeypatch):
    """A process that can open /dev/tty owns a terminal and may write to it."""
    real_open = open

    def fake_open(path, *args, **kwargs):
        if path == "/dev/tty":
            return real_open("/dev/null", *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)

    assert owns_controlling_terminal() is True


def test_inherited_ssh_tty_is_not_used_without_ownership(monkeypatch, detached):
    """THE REGRESSION: inherited SSH_TTY must not resolve to a terminal.

    Before the fix this returned the parent's PTY by path, so a nested
    `amplifier run` rang the bell in the session that spawned it.
    """
    monkeypatch.setenv("SSH_TTY", EXISTING_TTY_PATH)
    monkeypatch.delenv("TMUX", raising=False)

    path, desc = get_tty_for_output()

    assert path is None
    assert desc == "no terminal available"


def test_inherited_tmux_is_not_used_without_ownership(monkeypatch, detached):
    """TMUX is inherited too - being "inside tmux" does not confer ownership."""
    monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,123,0")
    monkeypatch.delenv("SSH_TTY", raising=False)

    path, desc = get_tty_for_output()

    assert path is None
    assert desc == "no terminal available"


def test_ssh_tty_still_used_when_process_owns_terminal(monkeypatch, attached):
    """The interactive SSH case must keep working - this is not a kill switch."""
    monkeypatch.setenv("SSH_TTY", EXISTING_TTY_PATH)
    monkeypatch.delenv("TMUX", raising=False)

    path, desc = get_tty_for_output()

    assert path == EXISTING_TTY_PATH
    assert desc == f"SSH TTY ({EXISTING_TTY_PATH})"


def test_tmux_pane_still_used_when_process_owns_terminal(monkeypatch, attached):
    """The interactive tmux case must keep working."""
    monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,123,0")
    monkeypatch.setenv("SSH_TTY", EXISTING_TTY_PATH)

    path, desc = get_tty_for_output()

    assert path == "/dev/tty"
    assert desc == "tmux pane TTY (/dev/tty)"


def test_stdout_tty_still_used_when_it_is_the_terminal(monkeypatch):
    """stdout is not gated on ownership.

    If stdout is a terminal, that is already where every byte this process
    writes ends up - so a bell there is not hijacking anyone else's display.
    """
    monkeypatch.setattr(f"{MODULE}.owns_controlling_terminal", lambda: False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("SSH_TTY", raising=False)
    monkeypatch.delenv("TMUX", raising=False)

    path, desc = get_tty_for_output()

    assert path is None
    assert desc == "stdout"


def test_send_bell_is_a_noop_without_a_terminal(monkeypatch, detached):
    """End of the chain: no owned terminal means no BEL byte is written."""
    monkeypatch.setenv("SSH_TTY", EXISTING_TTY_PATH)
    monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,123,0")

    def explode(*args, **kwargs):
        raise AssertionError("send_bell must not open a terminal it does not own")

    monkeypatch.setattr("builtins.open", explode)

    sent, detail = send_bell()

    assert sent is False
    assert detail == "No terminal available for bell"
