"""attest: fast, precise, evidence-first AI code review."""

from importlib.metadata import PackageNotFoundError, version

# One hand-written version, in `pyproject.toml`. `v0.1.0-rc.2` shipped a wheel
# whose metadata said `0.1.0rc2` while this string said `0.1.0rc1`, because the
# number lived in two files and a bump reached one of them (D-193). A source
# tree that was never installed has no metadata and says so, rather than
# guessing a number.
try:
    __version__ = version("attest")
except PackageNotFoundError:  # pragma: no cover - an uninstalled checkout
    __version__ = "0+uninstalled"
