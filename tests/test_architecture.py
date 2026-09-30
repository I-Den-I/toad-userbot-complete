"""Static guarantees about the code base: stealth rules and layer boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "toad_userbot"

# Anything that would reveal the account "looking" at a chat (see docs/ARCHITECTURE.md §5).
FORBIDDEN_IDENTIFIERS = frozenset(
    {
        "send_read_acknowledge",
        "mark_read",
        "ReadHistoryRequest",
        "ReadMentionsRequest",
        "ReadReactionsRequest",
        "ReadMessageContentsRequest",
        "ReadDiscussionRequest",
        "ReadSavedHistoryRequest",
        "GetMessagesViewsRequest",
        "GetHistoryRequest",
        "UpdateStatusRequest",
        "SetTypingRequest",
        "iter_messages",
        "get_messages",
    }
)
# Methods that are harmless as attribute names but must never be called on the client.
FORBIDDEN_CALLS = frozenset({"action", "conversation"})


def _python_files(root: Path = SRC) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _identifiers(tree: ast.Module) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.alias):
            found.add(node.name.rsplit(".", 1)[-1])
    return found


def _called_methods(tree: ast.Module) -> set[str]:
    return {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }


def _imported_modules(tree: ast.Module) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _package_of(path: Path) -> str:
    return path.relative_to(SRC).parts[0].removesuffix(".py")


@pytest.mark.parametrize("path", _python_files(), ids=lambda path: str(path.relative_to(SRC)))
def test_no_read_or_presence_apis(path: Path) -> None:
    tree = _tree(path)
    used = sorted(
        (_identifiers(tree) & FORBIDDEN_IDENTIFIERS) | (_called_methods(tree) & FORBIDDEN_CALLS)
    )
    assert used == [], f"{path.name} uses forbidden Telegram APIs: {used}"


def test_forbidden_api_detection_works() -> None:
    tree = ast.parse(
        "from telethon.tl.functions.messages import ReadHistoryRequest\n"
        "client.send_read_acknowledge(chat)\n"
        "async with client.action(chat, 'typing'): pass\n"
    )
    assert "ReadHistoryRequest" in _identifiers(tree)
    assert "send_read_acknowledge" in _identifiers(tree)
    assert "action" in _called_methods(tree)


@pytest.mark.parametrize(
    ("library", "allowed_packages"),
    [
        ("telethon", {"telegram"}),
        ("aiosqlite", {"storage"}),
    ],
)
def test_infrastructure_libraries_stay_in_their_adapters(
    library: str, allowed_packages: set[str]
) -> None:
    offenders = [
        str(path.relative_to(SRC))
        for path in _python_files()
        if _package_of(path) not in allowed_packages
        and any(module.split(".")[0] == library for module in _imported_modules(_tree(path)))
    ]
    assert offenders == []


def test_domain_depends_on_nothing_inside_the_project() -> None:
    offenders = [
        str(path.relative_to(SRC))
        for path in _python_files(SRC / "domain")
        if any(
            module.startswith("toad_userbot.") and not module.startswith("toad_userbot.domain")
            for module in _imported_modules(_tree(path))
        )
    ]
    assert offenders == []


@pytest.mark.parametrize("package", ["domain", "recorder", "control", "storage", "system"])
def test_inner_layers_do_not_import_adapters_or_wiring(package: str) -> None:
    forbidden = ("toad_userbot.telegram", "toad_userbot.app")
    offenders = [
        str(path.relative_to(SRC))
        for path in _python_files(SRC / package)
        if any(module.startswith(forbidden) for module in _imported_modules(_tree(path)))
    ]
    assert offenders == []
