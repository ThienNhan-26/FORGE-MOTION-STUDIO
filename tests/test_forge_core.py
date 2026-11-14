from __future__ import annotations
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import storage.database as database
from agents.planner import PlannerAgent
from core.skill import BaseSkill, SkillManifest
from core.skill_registry import SkillRegistry
from core.scheduler import TaskScheduler
from core.coordinator import Coordinator
from core.task import Task, TaskStatus, ExecutionResult, ExecutionStatus
from execution.permission_engine import PermissionEngine, SecurityViolation


class FakePlannerClient:
    def chat(self, messages, temperature=0.1, json_mode=False):
        return json.dumps({"tasks": [{
            "task_id": "t1", "title": "Create note", "task_type": "GENERAL",
            "skill_name": "write_file", "description": "create note",
            "input_data": {"filename": "note.txt", "content": "FORGE test"}, "dependencies": []
        }]})


class FailingSkill(BaseSkill):
    def get_manifest(self):
        return SkillManifest(name="unit_fail", description="test-only")

    def execute(self, params):
        return ExecutionResult(ExecutionStatus.FAILED, "expected failure")


class ForgeCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_file = self.root / "forge-test.db"
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.db_patch = patch.object(database, "DB_PATH", self.db_file)
        self.storage_patch = patch.object(database, "STORAGE_DIR", self.root)
        self.workspace_patch = patch("execution.permission_engine.WORKSPACE_DIR", self.workspace)
        self.db_patch.start(); self.storage_patch.start(); self.workspace_patch.start()
        database.init_db()
        SkillRegistry.discover_skills(force=True)

    def tearDown(self):
        self.workspace_patch.stop(); self.storage_patch.stop(); self.db_patch.stop()
        self.temp.cleanup()

    def test_skill_registry_loads_expected_plugins(self):
        names = {m["name"] for m in SkillRegistry.get_manifests()}
        self.assertTrue({"write_file", "python_task", "run_python", "render_video", "create_3d_scene", "render_3d_scene"}.issubset(names))

    def test_scene3d_contract_loads_showcase_and_rejects_duplicate_ids(self):
        from contracts.scene3d import Scene3DSpec
        sample = Path(__file__).resolve().parents[1] / "examples" / "floating_island.scene.json"
        raw = json.loads(sample.read_text(encoding="utf-8"))
        spec = Scene3DSpec.model_validate(raw)
        self.assertEqual(spec.duration_seconds, 18)
        self.assertGreaterEqual(len(spec.objects), 8)
        raw["objects"].append(dict(raw["objects"][0]))
        with self.assertRaises(Exception):
            Scene3DSpec.model_validate(raw)

        raw = json.loads(sample.read_text(encoding="utf-8"))
        raw["project_id"] = "../outside"
        with self.assertRaises(Exception):
            Scene3DSpec.model_validate(raw)

        raw = json.loads(sample.read_text(encoding="utf-8"))
        raw["environment"]["fog_far"] = raw["environment"]["fog_near"]
        with self.assertRaises(Exception):
            Scene3DSpec.model_validate(raw)

        raw = json.loads(sample.read_text(encoding="utf-8"))
        raw["objects"][0]["position"] = [float("nan"), 0, 0]
        with self.assertRaises(Exception):
            Scene3DSpec.model_validate(raw)

    def test_motion_studio_project_path_rejects_traversal_and_non_ascii(self):
        import motion_studio.server as motion_server
        with patch.object(motion_server, "WORKSPACE_DIR", self.workspace):
            expected = (self.workspace / "projects" / "safe-project").resolve()
            self.assertEqual(motion_server.safe_project_dir("safe-project"), expected)
            for invalid in ("../escape", "a/b", "tên-dự-án"):
                with self.subTest(project_id=invalid):
                    with self.assertRaises(ValueError):
                        motion_server.safe_project_dir(invalid)

    def test_create_3d_scene_skill_persists_validated_scene(self):
        from contracts.scene3d import Scene3DSpec
        from skills.create_3d_scene.skill import Create3DSceneSkill
        sample = Path(__file__).resolve().parents[1] / "examples" / "floating_island.scene.json"
        raw = json.loads(sample.read_text(encoding="utf-8"))
        raw["project_id"] = "unit-scene"
        with patch("skills.create_3d_scene.skill.WORKSPACE_DIR", self.workspace):
            result = Create3DSceneSkill().execute({"scene": raw})
        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        output = self.workspace / "projects" / "unit-scene" / "scene.json"
        self.assertTrue(output.is_file())
        saved = Scene3DSpec.model_validate_json(output.read_text(encoding="utf-8"))
        self.assertEqual(saved.title, "Floating Island")

    def test_database_migrates_legacy_tasks_table(self):
        legacy_db = self.root / "legacy.sqlite"
        conn = sqlite3.connect(legacy_db)
        conn.execute("CREATE TABLE tasks (task_id TEXT PRIMARY KEY, title TEXT, description TEXT, status TEXT, task_type TEXT, skill_name TEXT, dependencies TEXT, artifact_path TEXT, created_at TEXT)")
        conn.execute("INSERT INTO tasks VALUES ('old1','old task','desc','FAILED','PYTHON','write_file','[]',NULL,'2026-01-01T00:00:00')")
        conn.commit(); conn.close()
        with patch.object(database, "DB_PATH", legacy_db):
            database.init_db()
            conn = sqlite3.connect(legacy_db)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
            row = conn.execute("SELECT task_id,status FROM tasks WHERE task_id='old1'").fetchone()
            conn.close()
        self.assertTrue({"mission_id", "input_data", "result", "error"}.issubset(columns))
        self.assertEqual(row, ("old1", "FAILED"))

    def test_write_file_does_not_overwrite_existing_files(self):
        path = self.workspace / "existing.txt"
        path.write_text("original", encoding="utf-8")
        from skills.write_file.skill import WriteFileSkill
        result = WriteFileSkill().execute({"filename": "existing.txt", "content": "replacement"})
        self.assertEqual(result.status, ExecutionStatus.DENIED)
        self.assertEqual(path.read_text(encoding="utf-8"), "original")

    def test_permission_engine_blocks_parent_traversal(self):
        with self.assertRaises(SecurityViolation):
            PermissionEngine.validate_path("../outside.txt")

    def test_planner_parses_and_normalizes_task_graph(self):
        planner = PlannerAgent(client=FakePlannerClient())
        tasks = planner.create_task_graph("Tạo một file ghi chú")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["skill_name"], "write_file")
        self.assertEqual(tasks[0]["input_data"]["filename"], "note.txt")

    def test_scheduler_executes_skill_and_persists_task(self):
        task = Task(task_id="t1", title="Write note", skill_name="write_file",
                    input_data={"filename": "note.txt", "content": "hello"})
        scheduler = TaskScheduler(max_workers=1)
        success = scheduler.run_graph([task], mission_id="m-test")
        self.assertTrue(success)
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual((self.workspace / "note.txt").read_text(encoding="utf-8"), "hello")
        self.assertEqual(database.get_task("t1")["status"], "COMPLETED")
        executions, checkpoints = database.get_task_history("t1")
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0]["status"], "SUCCESS")
        self.assertEqual(len(checkpoints), 1)

    def test_coordinator_namespaces_task_ids_per_mission(self):
        class FixedPlanner:
            def create_task_graph(self, request):
                return [{
                    "task_id": "t1", "title": request, "task_type": "GENERAL",
                    "skill_name": "write_file", "description": "create",
                    "input_data": {"filename": f"{request}.txt", "content": request},
                    "dependencies": [],
                }]
        coordinator = Coordinator(planner=FixedPlanner())
        first = coordinator._plan_tasks("missionA", "first")
        second = coordinator._plan_tasks("missionB", "second")
        self.assertNotEqual(first[0].task_id, second[0].task_id)
        self.assertTrue(first[0].task_id.startswith("missionA_"))
        self.assertTrue(second[0].task_id.startswith("missionB_"))

    def test_failed_dependency_blocks_downstream(self):
        SkillRegistry._skills["unit_fail"] = FailingSkill()
        first = Task(task_id="a", title="Fail", skill_name="unit_fail")
        second = Task(task_id="b", title="Depends", skill_name="write_file",
                      input_data={"filename": "no.txt", "content": "x"}, dependencies=["a"])
        success = TaskScheduler(max_workers=1).run_graph([first, second], mission_id="m-block")
        self.assertFalse(success)
        self.assertEqual(first.status, TaskStatus.FAILED)
        self.assertEqual(second.status, TaskStatus.BLOCKED)


if __name__ == "__main__":
    unittest.main()
