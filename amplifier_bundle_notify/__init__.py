"""Amplifier Notify Bundle.

Desktop notifications when assistant turns complete.
"""

from pathlib import Path


def get_bundle_path() -> Path:
    """Return the path to the bundle directory.

    Two layouts have to work:

    - **Installed wheel** -- ``pyproject.toml`` force-includes ``bundle.md``,
      ``context/``, ``agents/`` and ``behaviors/`` under this package's
      ``_bundle/`` subdirectory, so the assets sit *beside* this module.
    - **Source / editable / git-clone checkout** -- the assets live at the repo
      root, one level *above* this package, and no ``_bundle/`` exists.

    Probing for ``_bundle/`` picks the right one. Every documented consumption
    path today is ``git+https://``, which lands in the second layout; the first
    only appears once someone pip-installs the built wheel.
    """
    packaged = Path(__file__).parent / "_bundle"
    return packaged if packaged.is_dir() else Path(__file__).parent.parent
