from __future__ import annotations

import uuid

from agents.coder import CoderAgent
from agents.reviewer import ReviewerAgent
from config import FORGE_MAX_REPAIR_ROUNDS, FORGE_MAX_REVIEW_ROUNDS
from core.skill import BaseSkill, SkillManifest
from core.task import ExecutionResult, ExecutionStatus
from execution.permission_engine import PermissionEngine
from execution.tools.filesystem import write_file
from execution.tools.terminal import run_python_script


class PythonTaskSkill(BaseSkill):
    """Generate, execute, and independently review a Python artifact."""

    def __init__(self, coder: CoderAgent | None = None, reviewer: ReviewerAgent | None = None):
        self.coder = coder or CoderAgent()
        self.reviewer = reviewer or ReviewerAgent()
        super().__init__()

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="python_task",
            version="2.1.0",
            description=(
                "Tạo file Python, chạy qua execution gate và bắt buộc qua "
                "Independent Reviewer trước khi báo thành công."
            ),
            input_schema={"prompt": "string", "filename": "string"},
            permissions=["workspace_write", "python_execute"],
        )

    @staticmethod
    def _persist_artifact(filename: str, code: str) -> ExecutionResult:
        return write_file(filename, code.rstrip() + "\n")

    def execute(self, params: dict) -> ExecutionResult:
        prompt = str(params.get("prompt") or params.get("description") or "").strip()
        filename = str(params.get("filename") or f"task_{params.get('task_id', 'generated')}.py")
        if not prompt:
            return ExecutionResult(ExecutionStatus.FAILED, "Thiếu prompt mô tả chương trình.")
        if not filename.lower().endswith(".py"):
            return ExecutionResult(ExecutionStatus.DENIED, "Tên file phải có đuôi .py.")

        staging_files: list[str] = []
        code = ""
        runtime_repairs = 0
        review_rounds = 0
        last_runtime_output = ""

        try:
            target = PermissionEngine.validate_path(filename)
            if target.exists() and not PermissionEngine.is_yolo():
                return ExecutionResult(
                    ExecutionStatus.DENIED,
                    f"File đã tồn tại: {target}. SAFE không cho ghi đè.",
                )

            code = self.coder.generate_code(prompt)
            while True:
                # Each candidate gets a unique path. This permits bounded repair
                # in SAFE mode without granting general overwrite permission.
                staging_name = f".forge_staging/{uuid.uuid4().hex}.py"
                staging_files.append(staging_name)
                staged = self._persist_artifact(staging_name, code)
                if staged.status != ExecutionStatus.SUCCESS:
                    return staged

                runtime = run_python_script(staging_name)
                last_runtime_output = runtime.output
                if runtime.status == ExecutionStatus.DENIED:
                    saved = self._persist_artifact(filename, code)
                    if saved.status != ExecutionStatus.SUCCESS:
                        return saved
                    return ExecutionResult(
                        ExecutionStatus.DENIED,
                        f"Python execution bị chặn: {runtime.output}",
                        evidence=str(target),
                    )

                if runtime.status != ExecutionStatus.SUCCESS:
                    if runtime_repairs < FORGE_MAX_REPAIR_ROUNDS:
                        runtime_repairs += 1
                        code = self.coder.generate_code(
                            prompt,
                            previous_code=code,
                            error=runtime.output[-5000:],
                        )
                        continue

                    saved = self._persist_artifact(filename, code)
                    if saved.status != ExecutionStatus.SUCCESS:
                        return saved
                    return ExecutionResult(
                        ExecutionStatus.FAILED,
                        f"Runtime thất bại sau {runtime_repairs + 1} lượt.\n{runtime.output}",
                        exit_code=runtime.exit_code,
                        evidence=str(target),
                    )

                try:
                    review = self.reviewer.review_python_task(
                        task_request=prompt,
                        filename=filename,
                        source_code=code,
                        stdout=runtime.output,
                        exit_code=0 if runtime.exit_code is None else runtime.exit_code,
                    )
                    review_rounds += 1
                    verdict = str(getattr(review, "verdict", "")).strip().upper()
                    summary = str(getattr(review, "summary", "")).strip()
                    issues = getattr(review, "issues", [])
                    feedback = str(getattr(review, "feedback", "")).strip()
                    if verdict not in {"PASS", "FAIL"}:
                        raise ValueError("Reviewer trả verdict không hợp lệ.")
                    if not isinstance(issues, list) or any(not isinstance(item, str) for item in issues):
                        raise ValueError("Reviewer trả danh sách issues không hợp lệ.")
                    if verdict == "PASS" and issues:
                        verdict = "FAIL"
                        feedback = feedback or "Reviewer có issue dù verdict là PASS."
                    if verdict == "FAIL" and not (feedback or issues or summary):
                        raise ValueError("Reviewer trả FAIL nhưng không có lý do.")
                except Exception as exc:
                    saved = self._persist_artifact(filename, code)
                    if saved.status != ExecutionStatus.SUCCESS:
                        return saved
                    return ExecutionResult(
                        ExecutionStatus.FAILED,
                        f"Reviewer lỗi; fail-closed, không chấp nhận kết quả. {exc}",
                        exit_code=0,
                        evidence=str(target),
                        review_status="ERROR",
                        review_summary=str(exc),
                        review_rounds=review_rounds,
                    )

                if verdict == "PASS":
                    saved = self._persist_artifact(filename, code)
                    if saved.status != ExecutionStatus.SUCCESS:
                        return saved
                    return ExecutionResult(
                        ExecutionStatus.SUCCESS,
                        f"Runtime PASS. Reviewer PASS sau {review_rounds} lượt. "
                        f"{summary}\n{runtime.output}",
                        exit_code=0,
                        evidence=str(target),
                        review_status="PASS",
                        review_summary=summary or "Reviewer xác nhận đạt yêu cầu.",
                        review_rounds=review_rounds,
                    )

                if review_rounds > FORGE_MAX_REVIEW_ROUNDS:
                    saved = self._persist_artifact(filename, code)
                    if saved.status != ExecutionStatus.SUCCESS:
                        return saved
                    detail = summary or "; ".join(issues)
                    return ExecutionResult(
                        ExecutionStatus.FAILED,
                        f"Reviewer FAIL sau {review_rounds} lượt. {detail}",
                        exit_code=0,
                        evidence=str(target),
                        review_status="FAIL",
                        review_summary=detail,
                        review_rounds=review_rounds,
                    )

                correction = feedback or "\n".join(issues) or summary
                code = self.coder.generate_code(
                    prompt,
                    previous_code=code,
                    error=f"Independent Reviewer yêu cầu sửa:\n{correction}",
                )

        except Exception as exc:
            return ExecutionResult(
                ExecutionStatus.FAILED,
                f"Python task lỗi: {exc}",
                review_status="ERROR" if review_rounds else None,
                review_summary=str(exc) if review_rounds else "",
                review_rounds=review_rounds,
            )
        finally:
            # Remove only unique staging files created by this invocation.
            for staging_name in staging_files:
                try:
                    staged_path = PermissionEngine.validate_path(staging_name)
                    if staged_path.is_file():
                        staged_path.unlink()
                except (OSError, ValueError):
                    pass
