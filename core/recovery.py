"""Conservative startup recovery: interrupted side effects are never replayed blindly."""
from storage.database import recover_interrupted_tasks


class RecoveryManager:
    @staticmethod
    def scan_and_decide() -> int:
        return recover_interrupted_tasks()
