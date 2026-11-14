from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from agents.reviewer import ReviewerAgent, ReviewResult
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


def successful_write(filename, content):
    return ExecutionResult(ExecutionStatus.SUCCESS, f"staged {filename}")


def successful_runtime(filename):
    return ExecutionResult(
        ExecutionStatus.SUCCESS,
        "verified output",
        exit_code=0,
        evidence=filename,
    )


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
        coder = FakeCoder(['print("verified")'])
        reviewer = FakeReviewer([ReviewResult("PASS", "Meets request", [], "")])
        skill = PythonTaskSkill(coder=coder, reviewer=reviewer)
        with patch.object(skill_module, "write_file", side_effect=successful_write), \
             patch.object(skill_module, "run_python_script", side_effect=successful_runtime):
            result = skill.execute({"prompt": "Print verified", "filename": "verified.py", "task_id": "unit-pass"})
        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(result.review_status, "PASS")
        self.assertEqual(reviewer.calls, 1)
        self.assertEqual(coder.calls, 1)

    def test_skill_corrects_once_after_review_fail(self):
        coder = FakeCoder(['print("first")', 'print("fixed")'])
        reviewer = FakeReviewer([
            ReviewResult("FAIL", "Output did not satisfy expected format", ["Wrong output"], "Print fixed"),
            ReviewResult("PASS", "Corrected output", [], ""),
        ])
        skill = PythonTaskSkill(coder=coder, reviewer=reviewer)
        with patch.object(skill_module, "write_file", side_effect=successful_write), \
             patch.object(skill_module, "run_python_script", side_effect=successful_runtime), \
             patch.object(skill_module, "FORGE_MAX_REVIEW_ROUNDS", 1):
            result = skill.execute({"prompt": "Print fixed", "filename": "fixed.py", "task_id": "unit-fix"})
        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(result.review_status, "PASS")
        self.assertEqual(reviewer.calls, 2)
        self.assertEqual(coder.calls, 2)
        self.assertIn("Reviewer PASS", result.output)

    def test_reviewer_error_fails_closed(self):
        skill = PythonTaskSkill(
            coder=FakeCoder(['print("ran")']),
            reviewer=FakeReviewer([RuntimeError("review endpoint unavailable")]),
        )
        with patch.object(skill_module, "write_file", side_effect=successful_write), \
             patch.object(skill_module, "run_python_script", side_effect=successful_runtime):
            result = skill.execute({"prompt": "Print ran", "filename": "ran.py", "task_id": "unit-error"})
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(result.review_status, "ERROR")

    def test_runtime_failure_never_calls_reviewer_or_returns_success(self):
        reviewer = FakeReviewer([ReviewResult("PASS", "Must not be used", [], "")])
        skill = PythonTaskSkill(coder=FakeCoder(['raise RuntimeError("boom")']), reviewer=reviewer)
        failed_runtime = ExecutionResult(ExecutionStatus.FAILED, "runtime error", exit_code=1)
        with patch.object(skill_module, "write_file", side_effect=successful_write), \
             patch.object(skill_module, "run_python_script", return_value=failed_runtime), \
             patch.object(skill_module, "FORGE_MAX_REPAIR_ROUNDS", 0):
            result = skill.execute({"prompt": "Fail at runtime", "filename": "bad.py"})
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(reviewer.calls, 0)

    def test_review_failure_after_budget_never_returns_success(self):
        reviewer = FakeReviewer([
            ReviewResult("FAIL", "Still incorrect", ["wrong output"], "Fix it"),
            ReviewResult("FAIL", "Still incorrect", ["wrong output"], "Fix it"),
        ])
        coder = FakeCoder(["print('one')", "print('two')"])
        skill = PythonTaskSkill(coder=coder, reviewer=reviewer)
        with patch.object(skill_module, "write_file", side_effect=successful_write), \
             patch.object(skill_module, "run_python_script", side_effect=successful_runtime), \
             patch.object(skill_module, "FORGE_MAX_REVIEW_ROUNDS", 1):
            result = skill.execute({"prompt": "Do the task", "filename": "not-approved.py"})
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(result.review_status, "FAIL")
        self.assertEqual(reviewer.calls, 2)

    def test_scheduler_persists_reviewer_verdict_separately(self):
        skill = type("FakeSkill", (), {
            "manifest": type("Manifest", (), {"name": "python_task"})(),
            "execute": lambda self, params: ExecutionResult(
                ExecutionStatus.SUCCESS,
                "runtime PASS; reviewer PASS",
                exit_code=0,
                evidence="workspace/demo.py",
                review_status="PASS",
                review_summary="Meets requirements",
                review_rounds=1,
            ),
        })()
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
