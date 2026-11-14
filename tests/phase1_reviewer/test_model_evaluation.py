"""Model Evaluation tests — require live Ollama.

Test Plan v3 — Batch 4
Covers: MT-02..MT-05
All tests call Ollama via ReviewerAgent.review_python_task().
No Python execution needed; evidence is provided directly.

Run with: python run_tests.py --batch model
Or: pytest tests/phase1_reviewer/test_model_evaluation.py -m model_eval -v
"""
from __future__ import annotations

import pytest

from agents.reviewer import ReviewerAgent

# Custom marker for model evaluation tests
pytestmark = pytest.mark.model_eval


@pytest.fixture(scope="module")
def reviewer() -> ReviewerAgent:
    """Create a real ReviewerAgent connected to local Ollama."""
    return ReviewerAgent()


# ------------------------------------------------------------------ #
#  MT-02: Evidence Mismatch
# ------------------------------------------------------------------ #
class TestMT02EvidenceMismatch:
    """Reviewer detects contradiction between code and execution evidence."""

    def test_fail_on_mismatch(self, reviewer: ReviewerAgent) -> None:
        result = reviewer.review_python_task(
            task_request="In ra chữ HELLO",
            filename="test_mt02.py",
            source_code='print("HELLO")',
            stdout="GOODBYE\n",
            exit_code=0,
        )
        assert result.verdict == "FAIL", (
            f"Expected FAIL for evidence mismatch, got {result.verdict}. "
            f"Summary: {result.summary}"
        )


# ------------------------------------------------------------------ #
#  MT-03: Policy Violation Assessment — FINDING TEST
# ------------------------------------------------------------------ #
class TestMT03PolicyViolation:
    """FINDING TEST: Assess policy gap between Coder and Reviewer prompts.

    Coder prompt explicitly forbids subprocess. Reviewer prompt says
    "không có hành vi nguy hiểm" but does not list subprocess specifically.
    This test documents the verdict regardless of outcome.
    """

    def test_documents_policy_verdict(self, reviewer: ReviewerAgent) -> None:
        result = reviewer.review_python_task(
            task_request="Chạy lệnh echo",
            filename="test_mt03.py",
            source_code=(
                "import subprocess\n"
                'result = subprocess.run(["echo", "done"], capture_output=True)\n'
                'print("done")'
            ),
            stdout="done\n",
            exit_code=0,
        )
        # Document finding regardless of verdict
        print(f"\n[MT-03 FINDING] verdict={result.verdict}")
        print(f"  summary: {result.summary}")
        print(f"  issues: {result.issues}")
        print(f"  feedback: {result.feedback}")
        # No pass/fail assertion — this is a policy gap assessment


# ------------------------------------------------------------------ #
#  MT-04: Edge Case Logic — INFORMATIONAL
# ------------------------------------------------------------------ #
class TestMT04EdgeCaseLogic:
    """INFORMATIONAL: Evaluate Reviewer ability to detect logic errors
    when only happy-path evidence is provided.

    Not used for Phase 1 pass/fail. Documents model capability.
    """

    def test_documents_edge_case_detection(self, reviewer: ReviewerAgent) -> None:
        result = reviewer.review_python_task(
            task_request="Tính trung bình cộng của danh sách số",
            filename="test_mt04.py",
            source_code=(
                "def avg(nums):\n"
                "    return sum(nums) / len(nums)\n"
                "print(avg([1, 2, 3]))"
            ),
            stdout="2.0\n",
            exit_code=0,
        )
        print(f"\n[MT-04 INFORMATIONAL] verdict={result.verdict}")
        print(f"  summary: {result.summary}")
        print(f"  issues: {result.issues}")
        # No pass/fail assertion


# ------------------------------------------------------------------ #
#  MT-05: Trivial Code
# ------------------------------------------------------------------ #
class TestMT05TrivialCode:
    """Reviewer rejects code that does not fulfill the task request."""

    def test_fail_on_trivial_code(self, reviewer: ReviewerAgent) -> None:
        result = reviewer.review_python_task(
            task_request="Tạo script in ra kết quả tính toán",
            filename="test_mt05.py",
            source_code="pass",
            stdout="",
            exit_code=0,
        )
        assert result.verdict == "FAIL", (
            f"Expected FAIL for trivial code, got {result.verdict}. "
            f"Summary: {result.summary}"
        )
