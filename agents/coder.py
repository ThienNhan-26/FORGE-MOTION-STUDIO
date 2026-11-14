from __future__ import annotations
from core.ollama import OllamaClient
from config import OLLAMA_CODER_MODEL


class CoderAgent:
    def __init__(self, client: OllamaClient | None = None):
        self.llm = client or OllamaClient(model=OLLAMA_CODER_MODEL)

    def generate_code(self, prompt: str, previous_code: str = "", error: str = "") -> str:
        system = (
            "Bạn là kỹ sư Python. Chỉ trả về mã Python thuần, không markdown. "
            "Tạo chương trình rõ ràng, có kiểm tra lỗi, không gọi shell/subprocess, "
            "không truy cập mạng, không đọc/ghi ngoài thư mục làm việc của dự án."
        )
        user = f"YÊU CẦU:\n{prompt}"
        if previous_code:
            user += f"\n\nMÃ CŨ CẦN SỬA:\n{previous_code}"
        if error:
            user += f"\n\nLỖI KHI CHẠY:\n{error}\nHãy sửa nguyên nhân, không chỉ che lỗi."
        content = self.llm.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.1,
        )
        content = content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "````":
                lines = lines[:-1]
            elif lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()
        if not content:
            raise RuntimeError("Coder trả về mã nguồn rỗng.")
        return content
