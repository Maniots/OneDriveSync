"""
tests/test_robocopy.py

Tests for src.robocopy_manager: verifies that built commands NEVER
contain destructive flags (/MIR, /PURGE, /MOV, /MOVE), that dry-run
mode adds the list-only flag, and that the defense-in-depth safety
assertion correctly rejects a command it did not build itself.

These tests only exercise command *construction*, not actual execution
(robocopy is a Windows-only executable and is not invoked here).

Run with: pytest tests/test_robocopy.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config import RobocopySettings
from src.exceptions import RobocopyExecutionError
from src.robocopy_manager import RobocopyManager


FORBIDDEN_FLAGS = {"/mir", "/purge", "/mov", "/move"}


@pytest.fixture()
def manager() -> RobocopyManager:
    return RobocopyManager(RobocopySettings(), dry_run=False)


def test_build_command_never_contains_destructive_flags(manager: RobocopyManager) -> None:
    command = manager.build_command(
        Path(r"C:\Users\john\OneDrive\PCSync\AppData\Roaming\EldenRing"),
        Path(r"C:\Users\john\AppData\Roaming\EldenRing"),
    )
    lowered = {arg.lower() for arg in command}
    assert lowered.isdisjoint(FORBIDDEN_FLAGS)


def test_build_command_includes_source_and_destination(manager: RobocopyManager) -> None:
    source = Path(r"C:\Source")
    destination = Path(r"C:\Destination")
    command = manager.build_command(source, destination)

    assert command[0] == "robocopy"
    assert str(source) in command
    assert str(destination) in command


def test_dry_run_adds_list_only_flag() -> None:
    manager = RobocopyManager(RobocopySettings(), dry_run=True)
    command = manager.build_command(Path(r"C:\Source"), Path(r"C:\Destination"))
    assert "/L" in command


def test_non_dry_run_omits_list_only_flag() -> None:
    manager = RobocopyManager(RobocopySettings(), dry_run=False)
    command = manager.build_command(Path(r"C:\Source"), Path(r"C:\Destination"))
    assert "/L" not in command


def test_multithreading_flag_reflects_settings() -> None:
    settings = RobocopySettings(multithreading=16)
    manager = RobocopyManager(settings, dry_run=False)
    command = manager.build_command(Path(r"C:\Source"), Path(r"C:\Destination"))
    assert "/MT:16" in command


def test_safety_assertion_rejects_forbidden_flag_defense_in_depth() -> None:
    """Even if a command were somehow built with a destructive flag,
    the safety assertion must refuse to let it through."""
    with pytest.raises(RobocopyExecutionError):
        RobocopyManager._assert_command_is_safe(["robocopy", "C:\\Source", "C:\\Dest", "/MIR"])


def test_retry_and_wait_flags_reflect_settings() -> None:
    settings = RobocopySettings(retry_count=5, retry_wait_seconds=10)
    manager = RobocopyManager(settings, dry_run=False)
    command = manager.build_command(Path(r"C:\Source"), Path(r"C:\Destination"))
    assert "/R:5" in command
    assert "/W:10" in command