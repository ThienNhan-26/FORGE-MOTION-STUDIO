"""Parser and Trailing Garbage tests for ReviewerAgent.

Test Plan v3 — Batch 1
Covers: JT-01..JT-05, TG-01..TG-03
All tests are deterministic. No Ollama calls. No Python execution.
"""
from __future__ import annotations

import pytest

from agents.reviewer import ReviewerAgent, ReviewerError


# ------------------------------------------------------------------ #
#  JT-01: Minimal Valid JSON — Parser Layer
# ------------------------------------------------------------------ #
class TestJT01MinimalValidJSON:
    """_extract_json() parses minimal JSON and returns correct dict."""

    def test_returns_dict_with_verdict(self) -> None:
        result = ReviewerAgent._extract_json('{"verdict": "PASS"}')
        assert isinstance(result, dict)
        assert result["verdict"] == "PASS"

    def test_no_extra_keys_added_by_parser(self) -> None:
        result = ReviewerAgent._extract_json('{"verdict": "PASS"}')
        assert set(result.keys()) == {"verdict"}


# ------------------------------------------------------------------ #
#  JT-02: FAIL Without Reason — Full Method Validation
# ------------------------------------------------------------------ #
class TestJT02FailWithoutReason:
    """review_python_task() rejects FAIL with no feedback/issues after defaults."""

    def test_raises_reviewer_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        agent = ReviewerAgent.__new__(ReviewerAgent)

        # Mock OllamaClient.chat to return FAIL without reason
        class FakeLLM:
            def chat(self, messages, temperature=0.0, json_mode=False):
                return '{"verdict": "FAIL"}'

        agent.llm = FakeLLM()

        with pytest.raises(ReviewerError, match="FAIL.*không nêu"):
            agent.review_python_task(
                task_request="test",
                filename="test.py",
                source_code="print(1)",
                stdout="1\n",
                exit_code=0,
            )


# ------------------------------------------------------------------ #
#  JT-03: Missing Verdict — Full Method Validation
# ------------------------------------------------------------------ #
class TestJT03MissingVerdict:
    """review_python_task() rejects missing or empty verdict."""

    def test_raises_reviewer_error_for_missing_verdict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = ReviewerAgent.__new__(ReviewerAgent)

        class FakeLLM:
            def chat(self, messages, temperature=0.0, json_mode=False):
                return '{"summary": "some text", "issues": [], "feedback": "ok"}'

        agent.llm = FakeLLM()

        with pytest.raises(ReviewerError, match="verdict"):
            agent.review_python_task(
                task_request="test",
                filename="test.py",
                source_code="print(1)",
                stdout="1\n",
                exit_code=0,
            )


# ------------------------------------------------------------------ #
#  JT-04: Contradictory PASS + Issues — Fail-Closed Downgrade
# ------------------------------------------------------------------ #
class TestJT04ContradictoryPassWithIssues:
    """PASS verdict with non-empty issues is downgraded to FAIL."""

    def test_downgrades_to_fail(self) -> None:
        agent = ReviewerAgent.__new__(ReviewerAgent)

        class FakeLLM:
            def chat(self, messages, temperature=0.0, json_mode=False):
                return (
                    '{"verdict":"PASS","summary":"ok",'
                    '"issues":["missing error handling"],"feedback":""}'
                )

        agent.llm = FakeLLM()

        result = agent.review_python_task(
            task_request="test",
            filename="test.py",
            source_code="print(1)",
            stdout="1\n",
            exit_code=0,
        )
        assert result.verdict == "FAIL"
        assert "missing error handling" in result.issues
        assert result.feedback  # must not be empty after downgrade


# ------------------------------------------------------------------ #
#  JT-05: Not JSON At All — Parser Layer
# ------------------------------------------------------------------ #
class TestJT05NotJsonAtAll:
    """_extract_json() rejects non-JSON input."""

    def test_raises_reviewer_error(self) -> None:
        with pytest.raises(ReviewerError, match="không trả về JSON"):
            ReviewerAgent._extract_json("I think the code is fine.")


# ------------------------------------------------------------------ #
#  TG-01: Trailing Whitespace After JSON
# ------------------------------------------------------------------ #
class TestTG01TrailingWhitespace:
    """Parser accepts whitespace after JSON object."""

    def test_parses_successfully(self) -> None:
        raw = '{"verdict":"PASS","summary":"ok","issues":[],"feedback":""}   \n\n  '
        result = ReviewerAgent._extract_json(raw)
        assert isinstance(result, dict)
        assert result["verdict"] == "PASS"


# ------------------------------------------------------------------ #
#  TG-02: Two Consecutive JSON Objects — FINDING TEST
# ------------------------------------------------------------------ #
class TestTG02TwoConsecutiveJsonObjects:
    """FINDING TEST: Determine behavior when two JSON objects appear.

    This is NOT a pass/fail test. It documents current behavior.
    Risk: first object wins silently; second object (possibly FAIL) is lost.
    """

    def test_documents_current_behavior(self) -> None:
        raw = (
            '{"verdict":"PASS","summary":"ok","issues":[],"feedback":""} '
            '{"verdict":"FAIL","summary":"bug","issues":["x"],"feedback":"fix"}'
        )
        result = ReviewerAgent._extract_json(raw)
        # Document: which object was selected?
        # Expected current behavior: first object (PASS) wins.
        # If this assertion ever changes, trailing garbage detection was added.
        assert result["verdict"] == "PASS", (
            "FINDING: raw_decode selected first object. "
            "Second FAIL object was silently discarded. "
            "This is a known risk for Phase 2."
        )


# ------------------------------------------------------------------ #
#  TG-03: Extra Fields in JSON
# ------------------------------------------------------------------ #
class TestTG03ExtraFields:
    """Parser ignores extra fields not in schema."""

    def test_parses_and_ignores_extra(self) -> None:
        raw = '{"verdict":"PASS","summary":"ok","issues":[],"feedback":"","confidence":0.95}'
        result = ReviewerAgent._extract_json(raw)
        assert result["verdict"] == "PASS"
        # Extra field exists in parsed dict but will be ignored by .get()
        assert "confidence" in result
