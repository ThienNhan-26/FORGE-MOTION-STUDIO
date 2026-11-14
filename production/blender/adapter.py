import subprocess
import os
import ast
from config import BLENDER_EXECUTABLE, WORKSPACE_DIR
from core.task import ExecutionResult, ExecutionStatus
from execution.permission_engine import PermissionEngine

class BlenderAdapter:
    @staticmethod
    def _is_script_safe(script_path: str) -> bool:
        """Lớp bảo vệ 1: Quét AST (Chỉ chặn các import nguy hiểm)"""
        with open(script_path, "r", encoding="utf-8") as f:
            code = f.read()
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in ["os", "sys", "subprocess", "shutil"]:
                            return False
                elif isinstance(node, ast.ImportFrom):
                    if node.module in ["os", "sys", "subprocess", "shutil"]:
                        return False
        except SyntaxError:
            return False
        return True

    @staticmethod
    def execute_blender_script(script_filename: str, task_id: str) -> ExecutionResult:
        # Lớp bảo vệ 2: Kiểm tra đường dẫn (Chống Path Traversal)
        try:
            script_path = os.path.join(WORKSPACE_DIR, script_filename)
            safe_script_path = PermissionEngine.validate_path(script_path)
            
            # Tạo thư mục output riêng biệt cho task này
            task_out_dir = os.path.join(WORKSPACE_DIR, "projects", "default_project", "tasks", task_id)
            os.makedirs(task_out_dir, exist_ok=True)
            
            blend_path = os.path.join(task_out_dir, "scene.blend")
            image_path = os.path.join(task_out_dir, "render.png")
            
        except Exception as e:
            return ExecutionResult(status=ExecutionStatus.DENIED, output=f"Lỗi đường dẫn: {e}")

        # Lớp bảo vệ 3: AST
        if not BlenderAdapter._is_script_safe(safe_script_path):
            return ExecutionResult(status=ExecutionStatus.DENIED, output="Lỗi bảo mật: Script chứa mã nguy hiểm.")

        try:
            print(f"    🎬 [BLENDER] Đang render Task {task_id}...")
            result = subprocess.run(
                [BLENDER_EXECUTABLE, "-b", "--python", safe_script_path],
                cwd=task_out_dir, # Chạy trong thư mục của task
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                return ExecutionResult(status=ExecutionStatus.FAILED, output=f"Blender báo lỗi:\n{result.stderr}")

            # QA: Kiểm tra file thực tế (Đã sửa theo đúng yêu cầu)
            from production.blender.artifact_validator import ArtifactValidator
            is_valid, qa_msg = ArtifactValidator.validate_render(image_path, blend_path)
            
            if not is_valid:
                return ExecutionResult(status=ExecutionStatus.FAILED, output=f"QA Thất bại: {qa_msg}")

            return ExecutionResult(
                status=ExecutionStatus.SUCCESS, 
                output=f"Render thành công!\n{qa_msg}",
                evidence=image_path
            )
            
        except subprocess.TimeoutExpired:
            return ExecutionResult(status=ExecutionStatus.FAILED, output="Lỗi: Timeout 5 phút.")
        except Exception as e:
            return ExecutionResult(status=ExecutionStatus.FAILED, output=f"Lỗi Adapter: {e}")