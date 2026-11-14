from __future__ import annotations
import json
import shutil
import subprocess
from pathlib import Path
from core.task import ExecutionResult, ExecutionStatus
from config import REMOTION_TEMPLATE_DIR, WORKSPACE_DIR
from production.remotion.spec_validator import SpecValidator


class RemotionAdapter:
    @staticmethod
    def render_video_file(spec_filename: str, task_id: str) -> ExecutionResult:
        spec_path = (WORKSPACE_DIR / spec_filename).resolve()
        try:
            spec_path.relative_to(WORKSPACE_DIR.resolve())
        except ValueError:
            return ExecutionResult(ExecutionStatus.DENIED, "Spec phải nằm trong workspace.")
        try:
            spec = SpecValidator.validate(spec_path)
            return RemotionAdapter.render_video(spec.model_dump(), task_id)
        except Exception as exc:
            return ExecutionResult(ExecutionStatus.FAILED, f"Không đọc được VideoSpec: {exc}")

    @staticmethod
    def render_video(spec_data: dict, task_id: str) -> ExecutionResult:
        try:
            spec = SpecValidator.validate(spec_data)
        except Exception as exc:
            return ExecutionResult(ExecutionStatus.FAILED, f"VideoSpec không hợp lệ: {exc}")

        template = REMOTION_TEMPLATE_DIR
        package_json = template / "package.json"
        cli = template / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
        node = shutil.which("node")
        if not package_json.is_file():
            return ExecutionResult(ExecutionStatus.FAILED, f"Không tìm thấy Remotion template: {template}")
        if not node:
            return ExecutionResult(ExecutionStatus.FAILED, "Không tìm thấy Node.js trong PATH.")
        if not cli.is_file():
            return ExecutionResult(ExecutionStatus.FAILED, "Thiếu node_modules Remotion. Chạy scripts\\setup.ps1 hoặc npm install trong adapters\\remotion_template.")

        safe_task = "".join(c for c in str(task_id) if c.isalnum() or c in "-_-")[:48] or "task"
        out_dir = WORKSPACE_DIR / "projects" / spec.project_id / "renders"
        runtime_dir = WORKSPACE_DIR / ".forge_runtime" / safe_task
        out_dir.mkdir(parents=True, exist_ok=True)
        runtime_dir.mkdir(parents=True, exist_ok=True)
        props_path = runtime_dir / "props.json"
        output_path = out_dir / f"{safe_task}_final.mp4"
        props_path.write_text(json.dumps({"video": spec.model_dump()}, ensure_ascii=False), encoding="utf-8")

        command = [node, str(cli), "render", "DynamicVideo", str(output_path), f"--props={props_path}"]
        try:
            result = subprocess.run(command, cwd=str(template), capture_output=True, text=True, timeout=1800, check=False)
        except subprocess.TimeoutExpired:
            return ExecutionResult(ExecutionStatus.FAILED, "Remotion render vượt quá 30 phút.")
        except Exception as exc:
            return ExecutionResult(ExecutionStatus.FAILED, f"Không thể khởi chạy Remotion: {exc}")
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "Không có log")[-6000:]
            return ExecutionResult(ExecutionStatus.FAILED, f"Remotion exit={result.returncode}:\n{details}")
        if not output_path.is_file() or output_path.stat().st_size < 1024:
            return ExecutionResult(ExecutionStatus.FAILED, "QA: Remotion không tạo được MP4 hợp lệ.")
        return ExecutionResult(
            ExecutionStatus.SUCCESS,
            f"Đã render '{spec.title}' ({len(spec.scenes)} cảnh, {sum(s.duration_seconds for s in spec.scenes)} giây).",
            exit_code=0, evidence=str(output_path),
        )
