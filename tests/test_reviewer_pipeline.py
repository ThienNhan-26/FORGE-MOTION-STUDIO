from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agents.reviewer import ReviewerAgent, ReviewerError, ReviewResult
from core.task import ExecutionResult, ExecutionStatus, Task, TaskStatus
from core.scheduler import TaskScheduler
import skills.python_task.skill as skill_module
from skills.python_task.skill import PythonTaskSkill


class FakeClient:
    def __init__(self, content: str):
        self.content = content

    def chat(self, messages, temperature=0.1, json_mode=False):
        assert json_mode is True
        return self.content


class FakeCoder:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def generate_code(self, prompt, previous_code="", error=""):
        self.calls += 1
        if not self.outputs:
            raise AssertionError("FakeCoder hết code mẫu")
        return self.outputs.pop(0)


class FakeReviewer:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def review_python_task(self, **kwargs):
        self.calls += 1
        if not self.results:
            raise AssertionError("FakeReviewer hết kết quả mẫu")
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class ReviewerPipelineTests(unittest.TestCase):
    def test_reviewer_parses_valid_pass(self):
        agent = ReviewerAgent(FakeClient(json.dumps({
            "verdict": "PASS", "summary": "Đúng yêu cầu", "issues": [], "feedback": ""
        }, ensure_ascii=False)))
        result = agent.review_python_task("in 2 out 4", "x.py", "print(4)", "4\n", 0)
        self.assertEqual(result.verdict, "PASS")

    def test_reviewer_rejects_inconsistent_pass_with_issues(self):
        agent = ReviewerAgent(FakeClient(json.dumps({
            "verdict": "PASS", "summary": "Looks okay", "issues": ["Wrong output"], "feedback": "Fix output"
        })))
        result = agent.review_python_task("test", "x.py", "print(2)", "2\n", 0)
        self.assertEqual(result.verdict, "FAIL")

    def test_skill_runs_review_and_returns_pass(self):
        old_enabled = skill_module.FORGE_ENABLE_PYTHON_EXECUTION
        skill_module.FORGE_ENABLE_PYTHON_EXECUTION = True
        filename = "_review_pipeline_test_pass.py"
        target = skill_module.PermissionEngine.ensure_parent(filename)
        if target.exists():
            target.unlink()
        try:
            coder = FakeCoder(['print("verified")'])
            reviewer = FakeReviewer([ReviewResult("PASS", "Meets request", [], "")])
            skill = PythonTaskSkill(coder=coder, reviewer=reviewer)
            result = skill.execute({"prompt": "Print verified", "filename": filename, "task_id": "unit-pass"})
            self.assertEqual(result.status, ExecutionStatus.SUCCESS)
            self.assertEqual(result.review_status, "PASS")
            self.assertEqual(reviewer.calls, 1)
        finally:
            if target.exists():
                target.unlink()
            skill_module.FORGE_ENABLE_PYTHON_EXECUTION = old_enabled

    def test_skill_corrects_once_after_review_fail(self):
        old_enabled = skill_module.FORGE_ENABLE_PYTHON_EXECUTION
        skill_module.FORGE_ENABLE_PYTHON_EXECUTION = True
        filename = "_review_pipeline_test_fix.py"
        target = skill_module.PermissionEngine.ensure_parent(filename)
        if target.exists():
            target.unlink()
        try:
            coder = FakeCoder(['print("first")', 'print("fixed")'])
            reviewer = FakeReviewer([
                ReviewResult("FAIL", "Output did not satisfy expected format", ["Wrong output"], "Print fixed"),
                ReviewResult("PASS", "Corrected output", [], ""),
            ])
            skill = PythonTaskSkill(coder=coder, reviewer=reviewer)
            result = skill.execute({"prompt": "Print fixed", "filename": filename, "task_id": "unit-fix"})
            self.assertEqual(result.status, ExecutionStatus.SUCCESS)
            self.assertEqual(result.review_status, "PASS")
            self.assertEqual(reviewer.calls, 2)
            self.assertEqual(coder.calls, 2)
            self.assertIn("fixed", result.output)
        finally:
            if target.exists():
                target.unlink()
            skill_module.FORGE_ENABLE_PYTHON_EXECUTION = old_enabled

    def test_scheduler_persists_reviewer_verdict_separately(self):
        skill = SimpleNamespace(
            manifest=SimpleNamespace(name="python_task"),
            execute=lambda params: ExecutionResult(
                ExecutionStatus.SUCCESS,
                "runtime PASS; reviewer PASS",
                exit_code=0,
                evidence="workspace/demo.py",
                review_status="PASS",
                review_summary="Meets requirements",
                review_rounds=1,
            ),
        )
        task = Task(
            task_id="mission_t1",
            title="Test reviewer persistence",
            skill_name="python_task",
            status=TaskStatus.CREATED,
            input_data={"prompt": "test"},
        )
        log_calls = []
        emitted = []
        with patch("core.scheduler.SkillRegistry.get_skill", return_value=skill), \
             patch("core.scheduler.save_task"), \
             patch("core.scheduler.save_checkpoint"), \
             patch("core.scheduler.emit_event"), \
             patch("core.scheduler.log_execution", side_effect=lambda *args: log_calls.append(args)):
            scheduler = TaskScheduler(event_sink=lambda *args: emitted.append(args))
            success = scheduler._execute_task(task, "mission")

        self.assertTrue(success)
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(len(log_calls), 2)
        self.assertEqual(log_calls[0][1], "SkillRunner")
        self.assertEqual(log_calls[1][1], "Reviewer")
        self.assertEqual(log_calls[1][4], "PASS")
        self.assertTrue(any("Reviewer PASS" in event[0] for event in emitted))

    def test_reviewer_error_fails_closed(self):
        old_enabled = skill_module.FORGE_ENABLE_PYTHON_EXECUTION
        skill_module.FORGE_ENABLE_PYTHON_EXECUTION = True
        filename = "_review_pipeline_test_error.py"
        target = skill_module.PermissionEngine.ensure_parent(filename)
        if target.exists():
            target.unlink()
        try:
            skill = PythonTaskSkill(
                coder=FakeCoder(['print("ran")']),
                reviewer=FakeReviewer([RuntimeError("review endpoint unavailable")]),
            )
            result = skill.execute({"prompt": "Print ran", "filename": filename, "task_id": "unit-error"})
            self.assertEqual(result.status, ExecutionStatus.FAILED)
            self.assertEqual(result.review_status, "ERROR")
        finally:
            if target.exists():
                target.unlink()
            skill_module.FORGE_ENABLE_PYTHON_EXECUTION = old_enabled


if __name__ == "__main__":
    unittest.main(verbosity=2)
