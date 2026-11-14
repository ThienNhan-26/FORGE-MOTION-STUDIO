from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from config import REMOTION_TEMPLATE_DIR, WORKSPACE_DIR
from contracts.scene3d import Scene3DSpec
from core.task import ExecutionResult, ExecutionStatus
from execution.permission_engine import PermissionEngine, SecurityViolation
from execution.tools.filesystem import write_file
from .render_qa import validate_render_output


class ThreeRemotionAdapter:
    """Deterministic 3D render adapter. The browser Preview and Remotion use one SceneSpec."""

    @staticmethod
    def render_scene(scene_data: dict, task_id: str) -> ExecutionResult:
        try:
            spec = Scene3DSpec.model_validate(scene_data)
        except Exception as exc:
            return ExecutionResult(ExecutionStatus.FAILED, f"SceneSpec không hợp lệ: {exc}")

        template = REMOTION_TEMPLATE_DIR
        package_json = template / "package.json"
        cli = template / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
        node = shutil.which("node")
        three_package = template / "node_modules" / "@remotion" / "three" / "package.json"
        if not package_json.is_file():
            return ExecutionResult(ExecutionStatus.FAILED, f"Không tìm thấy Remotion template: {template}")
        if not node:
            return ExecutionResult(ExecutionStatus.FAILED, "Không tìm thấy Node.js trong PATH.")
        if not cli.is_file() or not three_package.is_file():
            return ExecutionResult(
                ExecutionStatus.FAILED,
                "Thiếu @remotion/three hoặc Remotion dependencies. Chạy .\\scripts\\setup.ps1 để cài dependencies.",
            )

        safe_task = re.sub(r"[^A-Za-z0-9_-]", "_", str(task_id))[:48] or "task"
        props_rel = f".forge_runtime/{safe_task}/scene3d-props.json"
        output_rel = f"projects/{spec.project_id}/renders/{safe_task}_3d.mp4"
        qa_rel = f"projects/{spec.project_id}/renders/{safe_task}_3d.qa.json"
        try:
            props_path = PermissionEngine.ensure_parent(props_rel)
            output_path = PermissionEngine.authorize_write(
                output_rel, overwrite=PermissionEngine.is_yolo()
            )
            qa_path = PermissionEngine.authorize_write(
                qa_rel, overwrite=PermissionEngine.is_yolo()
            )
            props_result = write_file(
                props_rel,
                json.dumps({"scene": spec.model_dump(mode="json")}, ensure_ascii=False),
            )
            if props_result.status != ExecutionStatus.SUCCESS:
                return props_result
        except (OSError, SecurityViolation) as exc:
            status = ExecutionStatus.DENIED if isinstance(exc, SecurityViolation) else ExecutionStatus.FAILED
            return ExecutionResult(status, f"Không thể chuẩn bị dữ liệu render: {exc}")

        command = [node, str(cli), "render", "ThreeDScene", str(output_path), f"--props={props_path}"]
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
            return ExecutionResult(ExecutionStatus.FAILED, "Remotion 3D render vượt quá 60 phút.")
        except Exception as exc:
            return ExecutionResult(ExecutionStatus.FAILED, f"Không thể khởi chạy Remotion 3D: {exc}")

        if result.returncode != 0:
            details = (result.stderr or result.stdout or "Không có log")[-8000:]
            return ExecutionResult(ExecutionStatus.FAILED, f"Remotion 3D exit={result.returncode}:\n{details}", exit_code=result.returncode)
        if not output_path.is_file() or output_path.stat().st_size < 1024:
            return ExecutionResult(ExecutionStatus.FAILED, "QA cơ bản: Remotion chưa tạo được MP4 có kích thước hợp lệ.")

        # FORGE_G1_RENDER_QA_V1
        qa_report = validate_render_output(output_path, spec)
        try:
            qa_save = write_file(qa_rel, json.dumps(qa_report, ensure_ascii=False, indent=2))
            if qa_save.status != ExecutionStatus.SUCCESS:
                return ExecutionResult(qa_save.status, f"Không thể lưu Render QA report: {qa_save.output}", evidence=str(output_path))
        except OSError as exc:
            return ExecutionResult(
                ExecutionStatus.FAILED,
                f"Render QA report could not be saved: {exc}",
                exit_code=1,
                evidence=str(output_path),
            )

        if not qa_report.get("passed"):
            return ExecutionResult(
                ExecutionStatus.FAILED,
                f"Remotion rendered an MP4, but visual QA failed: {qa_report.get('error', 'unknown QA error')} Report: {qa_path}",
                exit_code=1,
                evidence=str(output_path),
            )

        return ExecutionResult(
            ExecutionStatus.SUCCESS,
            f"Đã render 3D '{spec.title}' ({len(spec.objects)} objects, {spec.duration_seconds}s, {spec.width}x{spec.height}@{spec.fps}). QA: {qa_report['summary']} Report: {qa_path}",
            exit_code=0,
            evidence=str(output_path),
        )
