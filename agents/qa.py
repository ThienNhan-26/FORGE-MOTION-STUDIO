import os
class QAAgent:
    def verify(self, filename: str, dispatcher) -> bool:
        result = dispatcher.execute("run_python_script", {"filename": filename})
        if result.status.value == "SUCCESS":
            return True
        print(f"❌ QA Lỗi: {result.output}")
        return False