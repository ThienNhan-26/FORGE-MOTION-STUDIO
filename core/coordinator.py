from __future__ import annotations
import threading
import uuid
from agents.planner import PlannerAgent
from core.scheduler import TaskScheduler
from core.skill_registry import SkillRegistry
from core.task import Task, TaskStatus
from storage.database import init_db, save_mission, save_task, emit_event
from config import FORGE_MAX_ACTIVE_MISSIONS


class Coordinator:
    _mission_semaphore = threading.Semaphore(FORGE_MAX_ACTIVE_MISSIONS)
    def __init__(self, planner: PlannerAgent | None = None):
        init_db()
        SkillRegistry.discover_skills()
        self.planner = planner or PlannerAgent()
        self.scheduler = TaskScheduler()
        self._threads: dict[str, threading.Thread] = {}
        interrupted = 0
        try:
            from storage.database import recover_interrupted_tasks
            interrupted = recover_interrupted_tasks()
        except Exception:
            pass
        if interrupted:
            emit_event(f"Đánh dấu {interrupted} task bị gián đoạn từ phiên trước; không tự chạy lại side-effect.", "WARN")

    def submit_mission(self, user_request: str) -> str:
        request = user_request.strip()
        if not request:
            raise ValueError("Nhiệm vụ không được để trống.")
        mission_id = uuid.uuid4().hex[:10]
        save_mission(mission_id, request, "QUEUED")
        emit_event(f"Đã nhận mission {mission_id}: {request}", "INFO", mission_id)
        thread = threading.Thread(target=self._run_mission, args=(mission_id, request), daemon=True, name=f"forge-mission-{mission_id}")
        self._threads[mission_id] = thread
        thread.start()
        return mission_id

    def execute_sync(self, user_request: str) -> tuple[str, list[Task], bool]:
        request = user_request.strip()
        mission_id = uuid.uuid4().hex[:10]
        save_mission(mission_id, request, "PLANNING")
        tasks = self._plan_tasks(mission_id, request)
        success = self.scheduler.run_graph(tasks, mission_id)
        status = "COMPLETED" if success else "FAILED"
        save_mission(mission_id, request, status, f"{sum(t.status == TaskStatus.COMPLETED for t in tasks)}/{len(tasks)} task hoàn thành")
        return mission_id, tasks, success

    def _plan_tasks(self, mission_id: str, request: str) -> list[Task]:
        emit_event("Planner đang phân tích yêu cầu và xây dựng DAG...", "INFO", mission_id)
        task_data = self.planner.create_task_graph(request)
        # Planner IDs are local to a mission (often t1/t2); namespace them globally for SQLite.
        id_map = {str(item["task_id"]): f"{mission_id}_{item['task_id']}" for item in task_data}
        tasks = [Task(
            task_id=id_map[str(item["task_id"])], title=str(item["title"]),
            description=str(item.get("description", "")), task_type=str(item.get("task_type", "GENERAL")),
            skill_name=str(item["skill_name"]),
            dependencies=[id_map[str(dep)] for dep in item.get("dependencies", [])],
            input_data=dict(item.get("input_data", {})), mission_id=mission_id,
        ) for item in task_data]
        for task in tasks:
            save_task(task)
        emit_event(f"Planner đã tạo {len(tasks)} task: " + ", ".join(t.task_id for t in tasks), "INFO", mission_id)
        return tasks

    def _run_mission(self, mission_id: str, request: str) -> None:
        with self._mission_semaphore:
            save_mission(mission_id, request, "PLANNING")
            try:
                tasks = self._plan_tasks(mission_id, request)
                success = self.scheduler.run_graph(tasks, mission_id)
                status = "COMPLETED" if success else "FAILED"
                summary = f"{sum(t.status == TaskStatus.COMPLETED for t in tasks)}/{len(tasks)} task hoàn thành"
                save_mission(mission_id, request, status, summary)
                emit_event(f"Mission {mission_id} kết thúc: {status} ({summary}).", "SUCCESS" if success else "ERROR", mission_id)
            except Exception as exc:
                save_mission(mission_id, request, "FAILED", str(exc))
                emit_event(f"Mission {mission_id} lỗi: {exc}", "ERROR", mission_id)
            finally:
                self._threads.pop(mission_id, None)
