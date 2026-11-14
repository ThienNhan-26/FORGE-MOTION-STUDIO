"""Repair Loop tests for PythonTaskSkill.

Test Plan v3 (v2) — Batch 3
Covers: RR-01..RR-04
Uses FakeReviewer with fixed verdict sequences. No Ollama calls.
Runtime is patched via unittest.mock.patch on module-level function.
Includes precise Staging Tracking and Artifact Persistence checks.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch, call

import pytest

from agents.reviewer import ReviewResult
from config import WORKSPACE_DIR
from core.task import ExecutionResult, ExecutionStatus


# ------------------------------------------------------------------ #
#  Helpers
# ------------------------------------------------------------------ #
class FakeCoder:
    """Records all generate_code calls and returns preset responses."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.call_log: list[dict[str, Any]] = []

    def generate_code(
        self, prompt: str, previous_code: str = "", error: str = ""
    ) -> str:
        self.call_log.append({
            "prompt": prompt,
            "previous_code": previous_code,
            "error": error,
        })
        if not self.responses:
            raise RuntimeError("FakeCoder ran out of preset responses")
        return self.responses.pop(0)


class FakeReviewer:
    """Returns verdicts from a fixed sequence. Can raise on specific call index."""

    def __init__(
        self,
        verdict_sequence: list[str],
        raise_on_call: int | None = None,
    ) -> None:
        self.verdict_sequence = list(verdict_sequence)
        self.raise_on_call = raise_on_call
        self.call_log: list[dict[str, Any]] = []
        self._call_count = 0

    def review_python_task(
        self,
        task_request: str,
        filename: str,
        source_code: str,
        stdout: str,
        exit_code: int,
    ) -> ReviewResult:
        idx = self._call_count
        self._call_count += 1
        self.call_log.append({
            "task_request": task_request,
            "filename": filename,
            "source_code": source_code,
            "stdout": stdout,
            "exit_code": exit_code,
        })
        if self.raise_on_call is not None and idx == self.raise_on_call:
            from agents.reviewer import ReviewerError
            raise ReviewerError("test error")
        if not self.verdict_sequence:
            raise RuntimeError("FakeReviewer ran out of verdicts")
        verdict = self.verdict_sequence.pop(0)
        if verdict == "PASS":
            return ReviewResult(
                verdict="PASS", summary="OK", issues=[], feedback=""
            )
        return ReviewResult(
            verdict="FAIL",
            summary="Not OK",
            issues=["issue"],
            feedback="Fix this",
        )


def _make_runtime_side_effect(results: list[ExecutionResult]):
    """Create side_effect list for patched run_python_script."""
    remaining = list(results)

    def side_effect(filename: str, timeout: int | None = None) -> ExecutionResult:
        if not remaining:
            raise RuntimeError("Fake runtime ran out of preset results")
        return remaining.pop(0)

    return side_effect


def _unique_filename(test_id: str) -> str:
    return f"rr_test_{test_id}_{uuid.uuid4().hex[:8]}.py"


def _cleanup_test_artifact(filename: str) -> None:
    """Safely remove the test artifact file after assertions."""
    target = WORKSPACE_DIR / filename
    if target.exists():
        try:
            target.unlink()
        except Exception as e:
            raise AssertionError(f"Failed to cleanup artifact {filename}: {e}") from e


# ------------------------------------------------------------------ #
#  RR-01: FAIL → Repair → PASS (Happy Path)
# ------------------------------------------------------------------ #
class TestRR01FailRepairPass:
    """Repair loop happy path: FAIL → Coder fixes → PASS → SUCCESS."""

    @patch("skills.python_task.skill.run_python_script")
    def test_happy_path(self, mock_runtime) -> None:
        from skills.python_task.skill import PythonTaskSkill

        filename = _unique_filename("01")
        fake_coder = FakeCoder(['print("wrong")', 'print("correct")'])
        fake_reviewer = FakeReviewer(["FAIL", "PASS"])

        # We track staging files by inspecting what was passed to the runtime
        staged_files = []
        def tracking_side_effect(filename: str, timeout: int | None = None):
            staged_files.append(filename)
            # Return preset results based on how many times we've been called
            count = len(staged_files)
            if count == 1:
                return ExecutionResult(ExecutionStatus.SUCCESS, "wrong\n", exit_code=0)
            return ExecutionResult(ExecutionStatus.SUCCESS, "correct\n", exit_code=0)

        mock_runtime.side_effect = tracking_side_effect

        skill = PythonTaskSkill(coder=fake_coder, reviewer=fake_reviewer)

        try:
            result = skill.execute({"prompt": "In ra CORRECT", "filename": filename})

            assert result.status == ExecutionStatus.SUCCESS
            assert getattr(result, "review_status", None) == "PASS"
            assert len(fake_coder.call_log) == 2
            assert len(fake_reviewer.call_log) == 2
            assert mock_runtime.call_count == 2
            assert getattr(result, "review_rounds", None) == 2

            # PERSISTENCE CHECK
            artifact_path = WORKSPACE_DIR / filename
            assert artifact_path.exists(), f"Artifact {filename} was not persisted"

            # CONTENT CHECK
            content = artifact_path.read_text(encoding="utf-8")
            assert 'print("correct")' in content

            # STAGING CLEANUP CHECK (Precise)
            for sf in staged_files:
                staging_path = WORKSPACE_DIR / sf
                assert not staging_path.exists(), f"Staging file {sf} was not cleaned up"

        finally:
            _cleanup_test_artifact(filename)


# ------------------------------------------------------------------ #
#  RR-02: FAIL → Repair → FAIL → FAILED (Fail-Closed)
# ------------------------------------------------------------------ #
class TestRR02FailRepairFailClosed:
    """Fail-closed when review rounds exhausted. Review cap limits before repair cap."""

    @patch("skills.python_task.skill.run_python_script")
    def test_fail_closed(self, mock_runtime) -> None:
        from skills.python_task.skill import PythonTaskSkill

        filename = _unique_filename("02")
        fake_coder = FakeCoder(['print("w1")', 'print("w2")'])
        fake_reviewer = FakeReviewer(["FAIL", "FAIL"])

        staged_files = []
        def tracking_side_effect(filename: str, timeout: int | None = None):
            staged_files.append(filename)
            count = len(staged_files)
            if count == 1:
                return ExecutionResult(ExecutionStatus.SUCCESS, "w1\n", exit_code=0)
            return ExecutionResult(ExecutionStatus.SUCCESS, "w2\n", exit_code=0)

        mock_runtime.side_effect = tracking_side_effect

        skill = PythonTaskSkill(coder=fake_coder, reviewer=fake_reviewer)

        try:
            result = skill.execute({"prompt": "In ra CORRECT", "filename": filename})

            assert result.status == ExecutionStatus.FAILED
            assert getattr(result, "review_status", None) == "FAIL"
            assert len(fake_coder.call_log) == 2
            assert len(fake_reviewer.call_log) == 2
            assert mock_runtime.call_count == 2
            assert getattr(result, "review_rounds", None) == 2

            # PERSISTENCE CHECK (Even on failure)
            artifact_path = WORKSPACE_DIR / filename
            assert artifact_path.exists(), f"Artifact {filename} was not persisted on failure"

            # STAGING CLEANUP CHECK (Precise)
            for sf in staged_files:
                staging_path = WORKSPACE_DIR / sf
                assert not staging_path.exists(), f"Staging file {sf} was not cleaned up"

        finally:
            _cleanup_test_artifact(filename)


# ------------------------------------------------------------------ #
#  RR-03: Reviewer Exception → Fail-Closed ERROR
# ------------------------------------------------------------------ #
class TestRR03ReviewerException:
    """When Reviewer raises exception, fail-closed with review_rounds=0.

    review_rounds += 1 is AFTER the reviewer call in source code.
    If exception occurs, counter was never incremented.
    """

    @patch("skills.python_task.skill.run_python_script")
    def test_reviewer_exception_fail_closed(self, mock_runtime) -> None:
        from skills.python_task.skill import PythonTaskSkill

        filename = _unique_filename("03")
        fake_coder = FakeCoder(['print("test")'])
        fake_reviewer = FakeReviewer([], raise_on_call=0)

        staged_files = []
        def tracking_side_effect(filename: str, timeout: int | None = None):
            staged_files.append(filename)
            return ExecutionResult(ExecutionStatus.SUCCESS, "test\n", exit_code=0)

        mock_runtime.side_effect = tracking_side_effect

        skill = PythonTaskSkill(coder=fake_coder, reviewer=fake_reviewer)

        try:
            result = skill.execute({"prompt": "test", "filename": filename})

            assert result.status == ExecutionStatus.FAILED
            assert getattr(result, "review_status", None) == "ERROR"
            assert len(fake_coder.call_log) == 1
            assert len(fake_reviewer.call_log) == 1
            assert mock_runtime.call_count == 1
            # KEY ASSERTION: review_rounds=0 because increment is after reviewer call
            assert getattr(result, "review_rounds", None) == 0
            assert "test error" in (getattr(result, "review_summary", "") or "")

            # PERSISTENCE CHECK
            artifact_path = WORKSPACE_DIR / filename
            assert artifact_path.exists(), f"Artifact {filename} was not persisted on error"

            # STAGING CLEANUP CHECK (Precise)
            for sf in staged_files:
                staging_path = WORKSPACE_DIR / sf
                assert not staging_path.exists(), f"Staging file {sf} was not cleaned up"

        finally:
            _cleanup_test_artifact(filename)


# ------------------------------------------------------------------ #
#  RR-04: Early Stop on PASS (No Repair Needed)
# ------------------------------------------------------------------ #
class TestRR04EarlyStopOnPass:
    """Loop stops immediately when Reviewer PASS on first call."""

    @patch("skills.python_task.skill.run_python_script")
    def test_early_stop(self, mock_runtime) -> None:
        from skills.python_task.skill import PythonTaskSkill

        filename = _unique_filename("04")
        fake_coder = FakeCoder(['print("correct")'])
        fake_reviewer = FakeReviewer(["PASS"])

        staged_files = []
        def tracking_side_effect(filename: str, timeout: int | None = None):
            staged_files.append(filename)
            return ExecutionResult(ExecutionStatus.SUCCESS, "correct\n", exit_code=0)

        mock_runtime.side_effect = tracking_side_effect

        skill = PythonTaskSkill(coder=fake_coder, reviewer=fake_reviewer)

        try:
            result = skill.execute({"prompt": "In ra CORRECT", "filename": filename})

            assert result.status == ExecutionStatus.SUCCESS
            assert getattr(result, "review_status", None) == "PASS"
            assert len(fake_coder.call_log) == 1
            assert len(fake_reviewer.call_log) == 1
            assert mock_runtime.call_count == 1
            assert getattr(result, "review_rounds", None) == 1

            # PERSISTENCE CHECK
            artifact_path = WORKSPACE_DIR / filename
            assert artifact_path.exists(), f"Artifact {filename} was not persisted"

            # STAGING CLEANUP CHECK (Precise)
            for sf in staged_files:
                staging_path = WORKSPACE_DIR / sf
                assert not staging_path.exists(), f"Staging file {sf} was not cleaned up"

        finally:
            _cleanup_test_artifact(filename)