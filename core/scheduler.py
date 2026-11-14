from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable
from core.task import Task, TaskStatus, ExecutionStatus
from core.skill_registry import SkillRegistry
from config import FORGE_MAX_WORKERS
from storage.database import save_task, emit_event, save_checkpoint, save_mission, log_execution


class TaskScheduler:
    def __init__(self, event_sink: Callable | None = None, max_workers: int | None = None):
        self.event_sink = event_sink
        self.max_workers = max_workers or FORGE_MAX_WORKERS

    def _emit(self, message: str, level: str, mission_id: str, task_id: str = "") -> None:
        emit_event(message, level, mission_id, task_id)
        if self.event_sink:
            try:
                self.event_sink(message, level, mission_id, task_id)
            except Exception:
                pass

    def run_graph(self, tasks: list[Task], mission_id: str = "") -> bool:
        by_id = {task.task_id: task for task in tasks}
        if len(by_id) != len(tasks):
            raise ValueError("Task graph có task_id trùng nhau.")
        for task in tasks:
            task.mission_id = mission_id or task.mission_id
            unknown = set(task.dependencies) - set(by_id)
            if unknown:
                raise ValueError(f"Task {task.task_id} có dependency không tồn tại: {', '.join(sorted(unknown))}")
            save_task(task)
        pending = set(by_id)
        failed_any = False
        self._emit(f"Scheduler bắt đầu: {len(tasks)} task, tối đa {self.max_workers} luồng song song.", "INFO", mission_id)

        while pending:
            # Block downstream nodes as soon as one dependency has failed/blocked.
            for task_id in list(pending):
                task = by_id[task_id]
                dependency_states = [by_id[d].status for d in task.dependencies]
                if any(state in {TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.WAITING_APPROVAL} for state in dependency_states):
                    task.status = TaskStatus.BLOCKED
                    task.error = "Một dependency không hoàn thành thành công."
                    save_task(task)
                    pending.remove(task_id)
                    failed_any = True
                    self._emit(f"Task {task.task_id} bị BLOCKED vì dependency thất bại.", "WARN", mission_id, task.task_id)

            ready = [by_id[task_id] for task_id in pending
                     if all(by_id[d].status == TaskStatus.COMPLETED for d in by_id[task_id].dependencies)]
            if not ready:
                if pending:
                    for task_id in list(pending):
                        task = by_id[task_id]
                        task.status = TaskStatus.BLOCKED
                        task.error = "Dependency graph bị chu trình hoặc không thể giải quyết."
                        save_task(task)
                        pending.remove(task_id)
                        failed_any = True
                    self._emit("Phát hiện chu trình hoặc graph không thể tiến triển; các task còn lại bị BLOCKED.", "ERROR", mission_id)
                break

            with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="forge-task") as pool:
                futures = {pool.submit(self._execute_task, task, mission_id): task for task in ready}
                for future in as_completed(futures):
                    task = futures[future]
                    try:
                        success = future.result()
                    except Exception as exc:
                        success = False
                        task.status = TaskStatus.FAILED
                        task.error = str(exc)
                        save_task(task)
                        self._emit(f"Lỗi Scheduler ở task {task.task_id}: {exc}", "ERROR", mission_id, task.task_id)
                    pending.discard(task.task_id)
                    failed_any = failed_any or not success
        return not failed_any and all(task.status == TaskStatus.COMPLETED for task in tasks)

    def _execute_task(self, task: Task, mission_id: str) -> bool:
        task.status = TaskStatus.RUNNING
        save_task(task)
        self._emit(f"▶ [{task.task_id}] {task.title} — skill: {task.skill_name}", "INFO", mission_id, task.task_id)
        skill = SkillRegistry.get_skill(task.skill_name)
        if skill is None:
            task.status = TaskStatus.FAILED
            task.error = f"Không tìm thấy skill '{task.skill_name}'."
            save_task(task)
            self._emit(task.error, "ERROR", mission_id, task.task_id)
            return False
        params = dict(task.input_data)
        params.setdefault("description", task.description)
        params["task_id"] = task.task_id
        try:
            result = skill.execute(params)
            import json
            log_execution(task.task_id, "SkillRunner", skill.manifest.name,
                          json.dumps(params, ensure_ascii=False, default=str)[:4000],
                          result.status.value, result.output)

            # Persist Reviewer verdict separately so Mission history shows
            # execution and independent review as distinct evidence records.
            review_status = getattr(result, "review_status", None)
            if review_status:
                review_summary = getattr(result, "review_summary", "") or "Không có review summary."
                review_rounds = getattr(result, "review_rounds", 0)
                review_arguments = json.dumps(
                    {"review_rounds": review_rounds, "skill": skill.manifest.name},
                    ensure_ascii=False,
                )
                log_execution(
                    task.task_id, "Reviewer", "independent_review",
                    review_arguments, review_status, review_summary,
                )
                review_level = "SUCCESS" if review_status == "PASS" else "ERROR"
                self._emit(
                    f"Reviewer {review_status} [{task.task_id}] sau {review_rounds} lượt: {review_summary[:500]}",
                    review_level, mission_id, task.task_id,
                )

            task.result = result.output
            task.artifact_path = result.evidence or task.artifact_path
            if result.status == ExecutionStatus.SUCCESS:
                task.status = TaskStatus.COMPLETED
                task.error = ""
                save_task(task)
                save_checkpoint(task.task_id, "skill_completed", task.artifact_path)
                self._emit(f"✓ [{task.task_id}] Hoàn thành. {result.output[:500]}", "SUCCESS", mission_id, task.task_id)
                return True
            if result.status == ExecutionStatus.APPROVAL_REQUIRED:
                task.status = TaskStatus.WAITING_APPROVAL
            else:
                task.status = TaskStatus.FAILED
            task.error = result.output
            save_task(task)
            self._emit(f"✗ [{task.task_id}] {result.status.value}: {result.output[:800]}", "ERROR", mission_id, task.task_id)
            return False
        except Exception as exc:
            try:
                log_execution(task.task_id, "SkillRunner", task.skill_name, "{}", "FAILED", str(exc))
            except Exception:
                pass
            task.status = TaskStatus.FAILED
            task.error = str(exc)
            task.result = str(exc)
            save_task(task)
            self._emit(f"✗ [{task.task_id}] Ngoại lệ: {exc}", "ERROR", mission_id, task.task_id)
            return False
