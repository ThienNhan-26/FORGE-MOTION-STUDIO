from __future__ import annotations
from datetime import datetime, timezone
import sqlite3
from config import DB_PATH


class ApprovalManager:
    """Minimal audit trail retained for compatibility with the earlier project."""
    @staticmethod
    def log_approval(task_id: str, action: str, reason: str = "") -> None:
        conn = sqlite3.connect(str(DB_PATH), timeout=30)
        try:
            conn.execute("INSERT INTO approvals(task_id,action,reason,timestamp) VALUES(?,?,?,?)",
                         (task_id, action, reason, datetime.now(timezone.utc).isoformat()))
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def human_approve(task_id: str, reason: str):
        ApprovalManager.log_approval(task_id, "APPROVE_RECORDED", reason)
        return False, "Đã ghi nhận thao tác. Bản này chưa có hàng đợi phê duyệt ghi đè/side-effect; hãy tạo file mới hoặc gửi lại nhiệm vụ sau khi xử lý thủ công."

    @staticmethod
    def human_fail(task_id: str, reason: str):
        ApprovalManager.log_approval(task_id, "FAIL", reason)
        conn = sqlite3.connect(str(DB_PATH), timeout=30)
        try:
            conn.execute("UPDATE tasks SET status='FAILED', error=? WHERE task_id=?", (reason, task_id))
            conn.commit()
        finally:
            conn.close()
        return True, "Đã đánh dấu task thất bại."
