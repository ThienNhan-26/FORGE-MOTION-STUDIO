from __future__ import annotations

import json
import os
import re
import threading
import tempfile
import uuid
import webbrowser
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(ROOT))

from config import WORKSPACE_DIR  # noqa: E402
from contracts.scene3d import Scene3DSpec  # noqa: E402
from core.task import ExecutionStatus  # noqa: E402
from production.remotion.three_adapter import ThreeRemotionAdapter  # noqa: E402

DIST_DIR = Path(__file__).resolve().parent / "dist"
SAMPLE_SCENE = ROOT / "examples" / "floating_island.scene.json"
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def safe_project_dir(project_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", project_id or ""):
        raise ValueError("project_id chỉ được chứa chữ, số, gạch ngang và gạch dưới")
    base = (WORKSPACE_DIR / "projects").resolve()
    destination = (base / project_id).resolve()
    destination.relative_to(base)
    return destination


def read_scene(project_id: str) -> dict:
    project_dir = safe_project_dir(project_id)
    scene_file = (project_dir / "scene.json").resolve()
    try:
        scene_file.relative_to(project_dir)
    except ValueError as exc:
        raise ValueError("scene.json trỏ ra ngoài thư mục project.") from exc
    if scene_file.is_file():
        raw = json.loads(scene_file.read_text(encoding="utf-8"))
    else:
        raw = json.loads(SAMPLE_SCENE.read_text(encoding="utf-8"))
        raw["project_id"] = project_id
        if project_id != "floating-island":
            raw["title"] = project_id.replace("-", " ").title()
    return Scene3DSpec.model_validate(raw).model_dump(mode="json")


def write_scene(raw: dict) -> tuple[Scene3DSpec, Path]:
    spec = Scene3DSpec.model_validate(raw)
    project_dir = safe_project_dir(spec.project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    target = project_dir / "scene.json"
    fd, temp_name = tempfile.mkstemp(prefix=".scene-", suffix=".tmp", dir=str(project_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(spec.model_dump(mode="json"), ensure_ascii=False, indent=2))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return spec, target


def run_render(job_id: str, scene_data: dict) -> None:
    with JOBS_LOCK:
        JOBS[job_id]["status"] = "RUNNING"
        JOBS[job_id]["started_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = ThreeRemotionAdapter.render_scene(scene_data, f"motion-{job_id}")
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "COMPLETED" if result.status == ExecutionStatus.SUCCESS else "FAILED"
            JOBS[job_id]["output"] = result.output
            JOBS[job_id]["evidence"] = result.evidence
            JOBS[job_id]["error"] = "" if result.status == ExecutionStatus.SUCCESS else result.output
            JOBS[job_id]["exit_code"] = result.exit_code
            JOBS[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "FAILED"
            JOBS[job_id]["error"] = str(exc)
            JOBS[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()


class MotionStudioHandler(SimpleHTTPRequestHandler):
    server_version = "FORGE-MotionStudio/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST_DIR), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[Motion Studio] {self.address_string()} - {fmt % args}")

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 4 * 1024 * 1024:
            raise ValueError("Request body rỗng hoặc vượt quá giới hạn 4 MB.")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body phải là object.")
        return payload

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send_json({"ok": True, "service": "FORGE Motion Studio", "api_version": 1})
            return
        if parsed.path == "/api/scene":
            project_id = parse_qs(parsed.query).get("project_id", ["floating-island"])[0]
            try:
                self._send_json(read_scene(project_id))
            except Exception as exc:
                self._send_json({"error": str(exc)}, 400)
            return
        if parsed.path == "/api/projects":
            root = WORKSPACE_DIR / "projects"
            rows = []
            if root.is_dir():
                for folder in sorted(root.iterdir()):
                    if folder.is_dir() and (folder / "scene.json").is_file():
                        rows.append({"project_id": folder.name, "scene_path": str(folder / "scene.json")})
            self._send_json({"projects": rows})
            return
        if parsed.path.startswith("/api/jobs/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if job is not None:
                    self._send_json(dict(job))
                else:
                    self._send_json({"error": "Không tìm thấy render job trong phiên server hiện tại."}, 404)
            return
        if not (DIST_DIR / "index.html").is_file():
            body = (
                "<!doctype html><meta charset='utf-8'><title>FORGE Motion Studio</title>"
                "<style>body{background:#0b121a;color:#d9e8ef;font:16px Segoe UI;padding:48px}code{color:#82dfe4}</style>"
                "<h1>FORGE Motion Studio chưa được build</h1>"
                "<p>Chạy <code>npm install</code> và <code>npm run build</code> trong thư mục <code>motion_studio</code>, "
                "sau đó khởi động lại scripts\\motion-studio.ps1.</p>"
            ).encode("utf-8")
            self.send_response(503)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in {"/api/scene", "/api/render"}:
            self._send_json({"error": "Endpoint không tồn tại."}, 404)
            return
        try:
            raw = self._read_json()
            spec, scene_path = write_scene(raw)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 400)
            return

        if parsed.path == "/api/scene":
            self._send_json({"ok": True, "path": str(scene_path), "object_count": len(spec.objects)})
            return

        job_id = uuid.uuid4().hex[:12]
        with JOBS_LOCK:
            active_jobs = [item for item in JOBS.values() if item.get("status") in {"QUEUED", "RUNNING"}]
            if active_jobs:
                self._send_json({"error": "Một render job khác đang chạy. Hãy đợi job đó kết thúc."}, 409)
                return
            JOBS[job_id] = {
                "job_id": job_id,
                "status": "QUEUED",
                "project_id": spec.project_id,
                "title": spec.title,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "output": "",
                "error": "",
                "evidence": None,
            }
        worker = threading.Thread(target=run_render, args=(job_id, spec.model_dump(mode="json")), daemon=True, name=f"forge-render-{job_id}")
        worker.start()
        self._send_json({"job_id": job_id, "status": "QUEUED", "scene_path": str(scene_path) }, 202)


def main() -> None:
    host = os.getenv("FORGE_MOTION_STUDIO_HOST", "127.0.0.1")
    port = int(os.getenv("FORGE_MOTION_STUDIO_PORT", "8765"))
    if host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("Motion Studio API chỉ được bind vào loopback để tránh mở workspace ra mạng.")
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), MotionStudioHandler)
    url = f"http://127.0.0.1:{port}"
    print("=" * 60)
    print("FORGE MOTION STUDIO — LOCAL 3D SCENE EDITOR")
    print(f"Preview: {url}")
    print(f"Workspace: {WORKSPACE_DIR}")
    print("Press Ctrl+C to stop.")
    print("=" * 60)
    if os.getenv("FORGE_MOTION_STUDIO_NO_BROWSER", "0") != "1":
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print("\nStopping Motion Studio...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
