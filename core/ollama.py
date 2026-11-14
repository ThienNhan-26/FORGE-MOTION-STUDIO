"""Small Ollama client using only the Python standard library."""
from __future__ import annotations
import json
import threading
import urllib.error
import urllib.request
from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    _request_lock = threading.Semaphore(1)  # Avoid competing large model loads on local hardware.
    def __init__(self, model: str | None = None, timeout: int | None = None):
        self.model = model or OLLAMA_MODEL
        self.timeout = timeout or OLLAMA_TIMEOUT
        self.url = f"{OLLAMA_BASE_URL}/api/chat"

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.1, json_mode: bool = False) -> str:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._request_lock:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")[:1200]
            raise OllamaError(f"Ollama trả HTTP {exc.code} cho model '{self.model}': {details}") from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise OllamaError(
                f"Không kết nối được Ollama tại {OLLAMA_BASE_URL}. "
                f"Hãy mở Ollama và thử lại. Chi tiết: {reason}"
            ) from exc
        except TimeoutError as exc:
            raise OllamaError(f"Ollama quá thời gian chờ ({self.timeout}s).") from exc
        except Exception as exc:
            raise OllamaError(f"Phản hồi Ollama không hợp lệ: {exc}") from exc
        content = data.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaError("Ollama trả về nội dung rỗng.")
        return content.strip()
