"""SCRATCH ONLY -- deliberate failure, proving the CI gate can go red.

This file exists only on the throwaway branch ci/red-proof-nxxf and is
never merged. It trips two independent gates at once:

  * pytest  -- the assertion below is false
  * ruff    -- `deliberately_undefined_name` is F821 (undefined name)
"""


def test_ci_can_actually_fail():
    assert 1 == 2, "deliberate failure: proving the CI gate is not decorative"


def test_ci_lint_can_actually_fail():
    assert deliberately_undefined_name  # noqa: B018  -- F821 on purpose
