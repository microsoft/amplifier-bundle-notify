"""SCRATCH ONLY -- deliberate failure, proving the second module's job runs."""


def test_ci_can_actually_fail():
    assert 1 == 2, "deliberate failure: proving hooks-notify-push tests execute"
