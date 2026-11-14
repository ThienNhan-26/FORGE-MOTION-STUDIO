
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from config import REMOTION_TEMPLATE_DIR, WORKSPACE_DIR
from contracts.scene3d import Scene3DSpec
from core.task import ExecutionResult, ExecutionStatus
from .render_qa import validate_render_output
from .scene_validator import SceneValidator


class ThreeRemotionAdapter:
    """Deterministic 3D render adapter with a pre-render validation gate."""

    @staticmethod
    def render_scene(scene_data: dict, task_id: str) -> ExecutionResult:
        # ---------------------------------------------------------
        # 1. Validate SceneSpec contract
        # ---------------------------------------------------------
        try:
            spec = Scene3DSpec.model_validate(scene_data)
        except Exception as exc:
            return ExecutionResult(
                ExecutionStatus.FAILED,
                f"SceneSpec không hợp lệ: {exc}",
                exit_code=1,
            )

        # ---------------------------------------------------------
        # 2. Prepare safe project paths
        # ---------------------------------------------------------
        safe_task = re.sub(
            r"[^A-Za-z0-9_-]",
            "_",
            str(task_id),
        )[:48] or "task"

        project_dir = (WORKSPACE_DIR / "projects" / spec.project_id).resolve()
        workspace = WORKSPACE_DIR.resolve()

        try:
            project_dir.relative_to(workspace)
        except ValueError:
            return ExecutionResult(
                ExecutionStatus.DENIED,
                "Project nằm ngoài workspace.",
                exit_code=1,
            )

        out_dir = project_dir / "renders"
        runtime_dir = workspace / ".forge_runtime" / safe_task

        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return ExecutionResult(
                ExecutionStatus.FAILED,
                f"Không thể tạo thư mục render: {exc}",
                exit_code=1,
            )

        output_path = out_dir / f"{safe_task}_3d.mp4"
        validation_path = output_path.with_suffix(".validation.json")
        qa_path = output_path.with_suffix(".qa.json")

        # ---------------------------------------------------------
        # 3. G1.2 Scene Validation Gate
        # ---------------------------------------------------------
        try:
            validation_report = SceneValidator.validate(spec)
            validation_path.write_text(
                json.dumps(
                    validation_report,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as exc:
            return ExecutionResult(
                ExecutionStatus.FAILED,
                f"Scene Validator gặp lỗi: {exc}",
                exit_code=1,
                evidence=str(validation_path),
            )

        if not validation_report.get("passed", False):
            errors = validation_report.get("errors", [])
            error_summary = "; ".join(
                f"{item.get('code', 'UNKNOWN')}: "
                f"{item.get('message', '')}"
                for item in errors
            )

            return ExecutionResult(
                ExecutionStatus.FAILED,
                (
                    "Scene Validation Gate BLOCKED render. "
                    f"{error_summary} "
                    f"Report: {validation_path}"
                ),
                exit_code=1,
                evidence=str(validation_path),
            )

        warning_count = len(validation_report.get("warnings", []))

        # ---------------------------------------------------------
        # 4. Verify Remotion environment
        # ---------------------------------------------------------
        template = REMOTION_TEMPLATE_DIR
        package_json = template / "package.json"
        cli = (
            template
            / "node_modules"
            / "@remotion"
            / "cli"
            / "remotion-cli.js"
        )
        three_package = (
            template
            / "node_modules"
            / "@remotion"
            / "three"
            / "package.json"
        )

        node = shutil.which("node")

        if not package_json.is_file():
            return ExecutionResult(
                ExecutionStatus.FAILED,
                f"Không tìm thấy Remotion template: {template}",
                exit_code=1,
                evidence=str(validation_path),
            )

        if not node:
            return ExecutionResult(
                ExecutionStatus.FAILED,
                "Không tìm thấy Node.js trong PATH.",
                exit_code=1,
                evidence=str(validation_path),
            )

        if not cli.is_file() or not three_package.is_file():
            return ExecutionResult(
                ExecutionStatus.FAILED,
                (
                    "Thiếu @remotion/three hoặc Remotion dependencies. "
                    "Kiểm tra scripts/setup.ps1."
                ),
                exit_code=1,
                evidence=str(validation_path),
            )

        # ---------------------------------------------------------
        # 5. Prepare render input
        # ---------------------------------------------------------
        try:
            runtime_dir.mkdir(parents=True, exist_ok=True)

            props_path = runtime_dir / "scene3d-props.json"
            props_path.write_text(
                json.dumps(
                    {"scene": spec.model_dump(mode="json")},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            return ExecutionResult(
                ExecutionStatus.FAILED,
                f"Không thể chuẩn bị dữ liệu render: {exc}",
                exit_code=1,
                evidence=str(validation_path),
            )

        command = [
            node,
            str(cli),
            "render",
            "ThreeDScene",
            str(output_path),
            f"--props={props_path}",
        ]

        # ---------------------------------------------------------
        # 6. Render with Remotion
        # ---------------------------------------------------------
        try:
            result = subprocess.run(
                command,
                cwd=str(template),
                capture_output=True,
                text=True,
                timeout=3600,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                ExecutionStatus.FAILED,
                "Remotion 3D render vượt quá 60 phút.",
                exit_code=1,
                evidence=str(validation_path),
            )
        except Exception as exc:
            return ExecutionResult(
                ExecutionStatus.FAILED,
                f"Không thể khởi chạy Remotion 3D: {exc}",
                exit_code=1,
                evidence=str(validation_path),
            )

        if result.returncode != 0:
            details = (
                result.stderr or result.stdout or "Không có log"
            )[-8000:]

            return ExecutionResult(
                ExecutionStatus.FAILED,
                (
                    f"Remotion 3D exit={result.returncode}:\n"
                    f"{details}"
                ),
                exit_code=result.returncode,
                evidence=str(validation_path),
            )

        if not output_path.is_file() or output_path.stat().st_size < 1024:
            return ExecutionResult(
                ExecutionStatus.FAILED,
                "Remotion chưa tạo được MP4 có kích thước hợp lệ.",
                exit_code=1,
                evidence=str(validation_path),
            )

        # ---------------------------------------------------------
        # 7. Existing visual Render QA — unchanged
        # ---------------------------------------------------------
        qa_report = validate_render_output(output_path, spec)

        try:
            qa_path.write_text(
                json.dumps(
                    qa_report,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            return ExecutionResult(
                ExecutionStatus.FAILED,
                f"Không thể lưu Render QA report: {exc}",
                exit_code=1,
                evidence=str(output_path),
            )

        if not qa_report.get("passed"):
            return ExecutionResult(
                ExecutionStatus.FAILED,
                (
                    "Remotion đã tạo MP4 nhưng Visual QA thất bại: "
                    f"{qa_report.get('error', 'unknown QA error')} "
                    f"Report: {qa_path}"
                ),
                exit_code=1,
                evidence=str(output_path),
            )

        # ---------------------------------------------------------
        # 8. Final evidence
        # ---------------------------------------------------------
        warning_note = (
            f" Scene warnings: {warning_count}."
            if warning_count
            else " Scene validation: clean."
        )

        return ExecutionResult(
            ExecutionStatus.SUCCESS,
            (
                f"Đã render 3D '{spec.title}' "
                f"({len(spec.objects)} objects, "
                f"{spec.duration_seconds}s, "
                f"{spec.width}x{spec.height}@{spec.fps})."
                f"{warning_note} "
                f"Validation: {validation_path}. "
                f"QA: {qa_report.get('summary', 'passed')} "
                f"Report: {qa_path}"
            ),
            exit_code=0,
            evidence=str(output_path),
        )
