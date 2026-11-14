"""Deterministic Guard and Reviewer Boundary tests.

Test Plan v3 — Batch 2
Covers: DG-01..DG-03, RB-01..RB-02
All tests are deterministic. No Ollama calls. No Python execution.
"""
from __future__ import annotations

import pytest

from agents.reviewer import ReviewerAgent, ReviewerError, ReviewResult


# ------------------------------------------------------------------ #
#  DG-01: Non-Zero Exit Code → Immediate FAIL
# ------------------------------------------------------------------ #
class TestDG01NonZeroExitCode:
    """Reviewer returns FAIL immediately when exit_code != 0, without calling Ollama."""

    def test_returns_fail_without_ollama_call(self) -> None:
        agent = ReviewerAgent.__new__(ReviewerAgent)

        call_count = 0

        class SpyLLM:
            def chat(self, messages, temperature=0.0, json_mode=False):
                nonlocal call_count
                call_count += 1
                return '{"verdict":"PASS"}'  # should never be reached

        agent.llm = SpyLLM()

        result = agent.review_python_task(
            task_request="test",
            filename="test.py",
            source_code="x",
            stdout="error",
            exit_code=1,
        )

        assert isinstance(result, ReviewResult)
        assert result.verdict == "FAIL"
        # Updated to substring check to handle punctuation variations in production code
        assert any("Runtime verification failed" in issue for issue in result.issues)
        assert call_count == 0, "OllamaClient.chat() must NOT be called for non-zero exit"


# ------------------------------------------------------------------ #
#  DG-02: Zero Exit + Empty Stdout
# ------------------------------------------------------------------ #
class TestDG02ZeroExitEmptyStdout:
    """Reviewer does not crash when stdout is empty and exit_code=0."""

    def test_returns_valid_result(self) -> None:
        agent = ReviewerAgent.__new__(ReviewerAgent)

        class FakeLLM:
            def chat(self, messages, temperature=0.0, json_mode=False):
                return '{"verdict":"PASS","summary":"ok","issues":[],"feedback":""}'

        agent.llm = FakeLLM()

        result = agent.review_python_task(
            task_request="test",
            filename="test.py",
            source_code='print("")',
            stdout="",
            exit_code=0,
        )

        assert isinstance(result, ReviewResult)
        assert result.verdict in {"PASS", "FAIL"}


# ------------------------------------------------------------------ #
#  DG-03: stdout=None — Safety Check
# ------------------------------------------------------------------ #
class TestDG03StdoutNone:
    """Verify safe handling of stdout=None after Phase 1 fix."""

    def test_handles_none_gracefully(self) -> None:
        agent = ReviewerAgent.__new__(ReviewerAgent)

        class FakeLLM:
            def chat(self, messages, temperature=0.0, json_mode=False):
                return '{"verdict":"PASS","summary":"ok","issues":[],"feedback":""}'

        agent.llm = FakeLLM()

        # Gọi đúng một lần với stdout=None để kiểm tra xử lý an toàn
        result = agent.review_python_task(
            task_request="test",
            filename="test.py",
            source_code="pass",
            stdout=None,  # type: ignore[arg-type]
            exit_code=0,
        )

        assert isinstance(result, ReviewResult)
        assert result.verdict == "PASS"


# ------------------------------------------------------------------ #
#  RB-01: Source Code Exceeds MAX_SOURCE_CHARS
# ------------------------------------------------------------------ #
class TestRB01ExceedsMaxSourceChars:
    """Reviewer rejects file >30000 chars before calling Ollama."""

    def test_raises_reviewer_error_without_ollama(self) -> None:
        agent = ReviewerAgent.__new__(ReviewerAgent)

        call_count = 0

        class SpyLLM:
            def chat(self, messages, temperature=0.0, json_mode=False):
                nonlocal call_count
                call_count += 1
                return '{"verdict":"PASS"}'

        agent.llm = SpyLLM()

        with pytest.raises(ReviewerError, match="quá dài"):
            agent.review_python_task(
                task_request="test",
                filename="test.py",
                source_code="x" * 30001,
                stdout="ok",
                exit_code=0,
            )

        assert call_count == 0, "Ollama must NOT be called for oversized source"


# ------------------------------------------------------------------ #
#  RB-02: Source Code Exactly at MAX_SOURCE_CHARS
# ------------------------------------------------------------------ #
class TestRB02ExactlyAtMaxSourceChars:
    """Boundary: 30000 chars is accepted (not rejected)."""

    def test_does_not_raise_length_error(self) -> None:
        agent = ReviewerAgent.__new__(ReviewerAgent)

        class FakeLLM:
            def chat(self, messages, temperature=0.0, json_mode=False):
                return '{"verdict":"PASS","summary":"ok","issues":[],"feedback":""}'

        agent.llm = FakeLLM()

        result = agent.review_python_task(
            task_request="test",
            filename="test.py",
            source_code="x" * 30000,
            stdout="ok",
            exit_code=0,
        )

        assert isinstance(result, ReviewResult)
        assert result.verdict == "PASS"