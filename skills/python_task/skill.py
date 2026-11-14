from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from agents.coder import CoderAgent
from agents.reviewer import ReviewerAgent, ReviewResult
from config import (
    FORGE_ENABLE_PYTHON_EXECUTION,
    FORGE_MAX_REPAIR_ROUNDS,
    FORGE_MAX_REVIEW_ROUNDS,
    WORKSPACE_DIR,
)
from core.skill import BaseSkill, SkillManifest
from core.task import ExecutionResult, ExecutionStatus
from execution.permission_engine import PermissionEngine, SecurityViolation


class PythonTaskSkill(BaseSkill):
    def __init__(self, coder: CoderAgent | None = None, reviewer: ReviewerAgent | None = None):
        self.coder = coder or CoderAgent()
        self.reviewer = reviewer or ReviewerAgent()
        super().__init__()

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="python_task",
            version="1.1.0",
            description=(
                "Dùng Coder tạo file .py, thực thi bằng Python, tự sửa lỗi runtime "
                "có giới hạn và yêu cầu Reviewer độc lập xác nhận trước khi hoàn thành."
            ),
            input_schema={"prompt": "string", "filename": "string"},
            permissions=["workspace_write", "python_execute", "independent_review"],
        )

    @staticmethod
    def _run_script(target: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(target)],
            cwd=str(WORKSPACE_DIR),
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

    @staticmethod
    def _combined_output(result: subprocess.CompletedProcess) -> str:
        return (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")

    @staticmethod
    def _review_text(review: ReviewResult) -> str:
        parts = [f"Reviewer {review.verdict}: {review.summary}"]
        if review.issues:
            parts.append("Issues: " + "; ".join(review.issues))
        if review.feedback:
            parts.append("Feedback: " + review.feedback)
        return "\n".join(parts)

    def execute(self, params: dict) -> ExecutionResult:
        if not FORGE_ENABLE_PYTHON_EXECUTION:
            return ExecutionResult(
                ExecutionStatus.DENIED,
                "Python execution đang tắt. Đọc README và đặt FORGE_ENABLE_PYTHON_EXECUTION=true trong .env nếu chấp nhận chạy mã do AI sinh trên máy này.",
            )

        prompt = str(params.get("prompt") or params.get("description") or "").strip()
        filename = str(params.get("filename") or f"task_{params.get('task_id', 'generated')}.py")
        if not prompt:
            return ExecutionResult(ExecutionStatus.FAILED, "Thiếu prompt mô tả chương trình.")
        if not filename.lower().endswith(".py"):
            return ExecutionResult(ExecutionStatus.DENIED, "Tên file phải có đuôi .py.")

        target: Path | None = None
        try:
            target = PermissionEngine.ensure_parent(filename)
            if target.exists():
                return ExecutionResult(
                    ExecutionStatus.APPROVAL_REQUIRED,
                    f"File đã tồn tại, không ghi đè: {target}",
                )

            code = self.coder.generate_code(prompt)
            if not isinstance(code, str) or not code.strip():
                return ExecutionResult(ExecutionStatus.FAILED, "Coder trả về mã nguồn rỗng.")
            target.write_text(code + "\n", encoding="utf-8")

            runtime_repairs = 0
            review_corrections = 0
            review_attempts = 0

            while True:
                run_result = self._run_script(target)
                runtime_output = self._combined_output(run_result)

                if run_result.returncode != 0:
                    if runtime_repairs >= FORGE_MAX_REPAIR_ROUNDS:
                        return ExecutionResult(
                            ExecutionStatus.FAILED,
                            f"Đã thử {runtime_repairs + 1} lượt nhưng chương trình vẫn lỗi.\n{runtime_output[-3000:]}",
                            exit_code=run_result.returncode,
                            evidence=str(target),
                        )
                    code = self.coder.generate_code(
                        prompt,
                        previous_code=code,
                        error=(
                            "LỖI KHI CHẠY CHƯƠNG TRÌNH:\n"
                            + runtime_output[-5000:]
                            + "\nHãy sửa nguyên nhân, không chỉ che lỗi."
                        ),
                    )
                    if not isinstance(code, str) or not code.strip():
                        return ExecutionResult(
                            ExecutionStatus.FAILED,
                            "Coder trả về mã nguồn rỗng trong vòng sửa lỗi runtime.",
                            exit_code=run_result.returncode,
                            evidence=str(target),
                        )
                    target.write_text(code + "\n", encoding="utf-8")
                    runtime_repairs += 1
                    continue

                # Runtime PASS is necessary but not sufficient. The independent
                # Reviewer must also return a valid PASS before the task succeeds.
                review_attempts += 1
                try:
                    review = self.reviewer.review_python_task(
                        task_request=prompt,
                        filename=filename,
                        source_code=code,
                        stdout=runtime_output,
                        exit_code=run_result.returncode,
                    )
                except Exception as exc:
                    summary = f"Runtime PASS nhưng Reviewer không thể xác minh: {exc}"
                    return ExecutionResult(
                        ExecutionStatus.FAILED,
                        summary + "\nKhông đánh dấu task hoàn thành khi thiếu review độc lập.",
                        exit_code=run_result.returncode,
                        evidence=str(target),
                        review_status="ERROR",
                        review_summary=summary,
                        review_rounds=review_attempts,
                    )

                review_text = self._review_text(review)
                if review.verdict == "PASS":
                    return ExecutionResult(
                        ExecutionStatus.SUCCESS,
                        (
                            f"Chương trình chạy thành công (runtime repairs: {runtime_repairs}).\n"
                            f"{runtime_output[-2500:]}\n\n{review_text}"
                        ),
                        exit_code=0,
                        evidence=str(target),
                        review_status="PASS",
                        review_summary=review_text,
                        review_rounds=review_attempts,
                    )

                if review_corrections >= FORGE_MAX_REVIEW_ROUNDS:
                    return ExecutionResult(
                        ExecutionStatus.FAILED,
                        (
                            f"Chương trình chạy được nhưng Reviewer từ chối sau "
                            f"{review_attempts} lượt review.\n{review_text}\n"
                            f"Bằng chứng runtime:\n{runtime_output[-2000:]}"
                        ),
                        exit_code=0,
                        evidence=str(target),
                        review_status="FAIL",
                        review_summary=review_text,
                        review_rounds=review_attempts,
                    )

                correction_request = (
                    "REVIEWER ĐỘC LẬP ĐÃ TỪ CHỐI SẢN PHẨM. Hãy sửa code theo các phát hiện sau; "
                    "giữ nguyên các phần đúng và không được chỉ che giấu issue.\n"
                    + review_text
                    + "\nBằng chứng chạy hiện tại (exit code 0):\n"
                    + runtime_output[-3000:]
                )
                code = self.coder.generate_code(
                    prompt,
                    previous_code=code,
                    error=correction_request,
                )
                if not isinstance(code, str) or not code.strip():
                    return ExecutionResult(
                        ExecutionStatus.FAILED,
                        "Coder trả về mã nguồn rỗng sau phản hồi Reviewer.",
                        evidence=str(target),
                        review_status="FAIL",
                        review_summary=review_text,
                        review_rounds=review_attempts,
                    )
                target.write_text(code + "\n", encoding="utf-8")
                review_corrections += 1

        except SecurityViolation as exc:
            return ExecutionResult(ExecutionStatus.DENIED, str(exc))
        except subprocess.TimeoutExpired as exc:
            return ExecutionResult(
                ExecutionStatus.FAILED,
                f"Script vượt quá giới hạn 45 giây: {exc}",
                evidence=str(target) if target else None,
            )
        except Exception as exc:
            return ExecutionResult(
                ExecutionStatus.FAILED,
                f"Python task lỗi: {exc}",
                evidence=str(target) if target else None,
            )
