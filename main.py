from __future__ import annotations
import argparse
import json
import shutil
import sys
import urllib.request
from config import ROOT_DIR, WORKSPACE_DIR, STORAGE_DIR, REMOTION_TEMPLATE_DIR, OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_CODER_MODEL
from core.coordinator import Coordinator
from core.skill_registry import SkillRegistry
from storage.database import init_db


def doctor() -> int:
    print("FORGE SYSTEM CHECK")
    print(f"Project root : {ROOT_DIR}")
    print(f"Workspace    : {WORKSPACE_DIR}")
    print(f"Database     : {STORAGE_DIR / 'forge.db'}")
    print(f"Ollama URL   : {OLLAMA_BASE_URL}")
    print(f"Planner model: {OLLAMA_MODEL}")
    print(f"Coder model  : {OLLAMA_CODER_MODEL}")
    print(f"Node         : {shutil.which('node') or 'NOT FOUND'}")
    print(f"FFmpeg       : {shutil.which('ffmpeg') or 'NOT FOUND'}")
    print(f"Remotion dir : {REMOTION_TEMPLATE_DIR}")
    print(f"Remotion CLI : {(REMOTION_TEMPLATE_DIR / 'node_modules' / '@remotion' / 'cli' / 'remotion-cli.js').exists()}")
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
            names = {item.get("name", "") for item in payload.get("models", [])}
            print(f"Ollama API   : ONLINE ({response.status})")
            print(f"Planner model: {'FOUND' if OLLAMA_MODEL in names else 'NOT FOUND'}")
            print(f"Coder model  : {'FOUND' if OLLAMA_CODER_MODEL in names else 'NOT FOUND'}")
    except Exception as exc:
        print(f"Ollama API   : OFFLINE ({exc})")
    SkillRegistry.discover_skills(force=True)
    print("Skills       : " + (", ".join(sorted(SkillRegistry._skills)) or "NONE"))
    for issue in SkillRegistry.get_errors():
        print(f"Plugin error : {issue}")
    init_db()
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    return 0 if SkillRegistry._skills else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="FORGE local multi-agent runtime")
    parser.add_argument("--doctor", action="store_true", help="Kiểm tra môi trường cài đặt")
    parser.add_argument("--headless", metavar="MISSION", help="Chạy một mission trong terminal, không mở TUI")
    parser.add_argument("--list-skills", action="store_true", help="Liệt kê skill đã nạp")
    args = parser.parse_args()

    init_db()
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    SkillRegistry.discover_skills(force=True)
    if args.doctor:
        return doctor()
    if args.list_skills:
        for manifest in SkillRegistry.get_manifests():
            print(f"- {manifest['name']} v{manifest['version']}: {manifest['description']}")
        for issue in SkillRegistry.get_errors():
            print(f"PLUGIN ERROR: {issue}")
        return 0
    if args.headless:
        coordinator = Coordinator()
        mission_id, tasks, success = coordinator.execute_sync(args.headless)
        print(f"\nMission {mission_id}: {'COMPLETED' if success else 'FAILED'}")
        for task in tasks:
            print(f"[{task.status.value}] {task.task_id} — {task.title}")
            if task.error:
                print(f"  {task.error}")
            if task.artifact_path:
                print(f"  Artifact: {task.artifact_path}")
        return 0 if success else 1
    try:
        from control.command_center import CommandCenter
    except ImportError as exc:
        print("Không tìm thấy Textual. Chạy: python -m pip install -r requirements.txt", file=sys.stderr)
        print(f"Chi tiết: {exc}", file=sys.stderr)
        return 2
    CommandCenter().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
