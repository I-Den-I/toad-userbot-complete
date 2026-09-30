"""Telegram userbot that automates the @toadbot game in a single chat."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("toad-userbot")
except PackageNotFoundError:  # pragma: no cover - source tree without an installed package
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
