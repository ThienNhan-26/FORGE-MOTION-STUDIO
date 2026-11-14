from __future__ import annotations
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, TextArea, RichLog, Static, DataTable
from rich.text import Text
from core.coordinator import Coordinator
from core.skill_registry import SkillRegistry
from storage.database import init_db, get_all_tasks, get_events_since, get_latest_event_id


class CommandCenter(App):
    BINDINGS = [("ctrl+enter", "submit_mission", "Send mission")]

    TITLE = "FORGE — Local Agent Command Center"
    SUB_TITLE = "Mission Control / Ollama Runtime"
    CSS = """
    Screen { background: #0a0f18; color: #dce6f2; }
    Header { background: #111a28; color: #e4eaf4; }
    Footer { background: #111a28; color: #9fb0c5; }
    #layout { height: 1fr; padding: 1; }
    #sidebar { width: 38%; min-width: 34; border: round #2b3b52; padding: 1; background: #0f1724; }
    #main { width: 1fr; margin-left: 1; }
    .section-title { color: #8faeff; text-style: bold; height: 1; margin-bottom: 1; }
    #brand { color: #a99aff; text-style: bold; height: 2; }
    #subtitle { color: #63d6b0; height: 2; }
    #stats { height: 8; border: round #2b3b52; padding: 1; margin-bottom: 1; }
    #task-table { height: 1fr; border: round #2b3b52; background: #0c1420; }
    #console { height: 1fr; border: round #2b3b52; padding: 1; background: #0b121d; }
    #mission-input { height: 7; min-height: 5; margin-top: 1; border: round #607da8; background: #111a28; }
    """

    def __init__(self):
        super().__init__()
        self.coordinator: Coordinator | None = None
        self.event_cursor = 0
        self._refreshing = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="layout"):
            with Vertical(id="sidebar"):
                yield Static("◆  F O R G E", id="brand")
                yield Static("LOCAL AGENT ORCHESTRATION  •  TUI", id="subtitle")
                with Vertical(id="stats"):
                    yield Static("SYSTEM STATUS", classes="section-title")
                    yield Static("Missions / Tasks: starting...", id="stat-total")
                    yield Static("Running: 0  |  Completed: 0", id="stat-state")
                    yield Static("Failed / Blocked: 0", id="stat-failed")
                yield Static("MISSION TASK GRAPH", classes="section-title")
                yield DataTable(id="task-table", zebra_stripes=True)
            with Vertical(id="main"):
                yield Static("LIVE RUNTIME CONSOLE", classes="section-title")
                yield RichLog(id="console", wrap=True, markup=False, highlight=False, max_lines=5000)
                yield TextArea(placeholder="Nhập nhiệm vụ nhiều dòng...  Enter: xuống dòng | Ctrl+Enter: gửi | /help: trợ giúp", id="mission-input", soft_wrap=True, show_line_numbers=False)
        yield Footer()

    def on_mount(self) -> None:
        console = self.query_one("#console", RichLog)
        table = self.query_one("#task-table", DataTable)
        table.add_columns("ID", "STATUS", "SKILL", "TASK")
        try:
            init_db()
            self.event_cursor = get_latest_event_id()
            self.coordinator = Coordinator()
            skills = ", ".join(sorted(SkillRegistry.get_manifests()[i]["name"] for i in range(len(SkillRegistry.get_manifests()))))
            console.write(Text("FORGE runtime initialized.", style="bold #a99aff"))
            console.write(Text(f"Skills: {skills or 'none'}"))
            console.write(Text("Nhập yêu cầu trực tiếp vào ô bên dưới. Scheduler sẽ chạy nền; giao diện tự cập nhật."))
            for issue in SkillRegistry.get_errors():
                console.write(Text(f"[PLUGIN ERROR] {issue}", style="bold red"))
        except Exception as exc:
            console.write(Text(f"Không khởi tạo được FORGE: {exc}", style="bold red"))
        self.set_interval(0.8, self.refresh_data)
        self.query_one("#mission-input", TextArea).focus()
        self.refresh_data()

    def action_submit_mission(self) -> None:
        """Submit the multiline mission editor; Enter remains a newline."""
        editor = self.query_one("#mission-input", TextArea)
        raw = editor.text.strip()
        if not raw:
            return
        editor.text = ""
        console = self.query_one("#console", RichLog)
        if raw.startswith("/") and "\n" not in raw:
            self._handle_command(raw)
            editor.focus()
            return
        if not self.coordinator:
            console.write(Text("FORGE chưa khởi tạo được; xem lỗi ở console phía trên.", style="bold red"))
            editor.focus()
            return
        try:
            mission_id = self.coordinator.submit_mission(raw)
            console.write(Text(f"\n> {raw}", style="bold #79a9ff"))
            console.write(Text(f"Mission {mission_id} đã được đưa vào hàng xử lý. TUI không bị khóa."))
        except Exception as exc:
            console.write(Text(f"Không gửi được nhiệm vụ: {exc}", style="bold red"))
        editor.focus()
        self.refresh_data()

    def _handle_command(self, command: str) -> None:
        console = self.query_one("#console", RichLog)
        cmd = command.split()[0].lower()
        if cmd == "/help":
            console.write(Text("Lệnh: /help  /tasks  /status  /clear  /quit"))
            console.write(Text("Soạn nhiệm vụ nhiều dòng: Enter xuống dòng, Ctrl+Enter gửi."))
        elif cmd == "/clear":
            console.clear()
        elif cmd == "/tasks":
            self.refresh_data()
            console.write(Text("Đã làm mới danh sách task."))
        elif cmd == "/status":
            rows = get_all_tasks()
            console.write(Text(f"Tổng task hiện có: {len(rows)}"))
            for row in rows[:20]:
                console.write(Text(f"{row['task_id']}  {row['status']}  {row['title']}"))
        elif cmd == "/quit":
            self.exit()
        else:
            console.write(Text("Lệnh không hợp lệ. Gõ /help để xem trợ giúp."))

    def refresh_data(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        try:
            rows = get_all_tasks(limit=150)
            table = self.query_one("#task-table", DataTable)
            table.clear(columns=False)
            counts = {"RUNNING": 0, "COMPLETED": 0, "FAILED": 0, "BLOCKED": 0, "WAITING_APPROVAL": 0, "CREATED": 0}
            for row in rows:
                status = str(row["status"] or "UNKNOWN")
                counts[status] = counts.get(status, 0) + 1
                title = str(row["title"] or "")
                if len(title) > 42:
                    title = title[:39] + "..."
                table.add_row(str(row["task_id"]), status, str(row["skill_name"] or ""), title, key=str(row["task_id"]))
            self.query_one("#stat-total", Static).update(f"Tasks: {len(rows)}  |  Active: {counts['RUNNING'] + counts['CREATED']}")
            self.query_one("#stat-state", Static).update(f"Running: {counts['RUNNING']}  |  Completed: {counts['COMPLETED']}")
            self.query_one("#stat-failed", Static).update(f"Failed: {counts['FAILED']}  |  Blocked: {counts['BLOCKED']}  |  Review: {counts['WAITING_APPROVAL']}")
            events = get_events_since(self.event_cursor, limit=250)
            console = self.query_one("#console", RichLog)
            for item in events:
                level = str(item["level"] or "INFO")
                style = "bold red" if level in {"ERROR", "WARN"} else ("bold green" if level == "SUCCESS" else "#cbd5e1")
                prefix = f"[{level}] "
                console.write(Text(prefix + str(item["message"]), style=style))
                self.event_cursor = int(item["id"])
        except Exception as exc:
            self.query_one("#console", RichLog).write(Text(f"Refresh error: {exc}", style="red"))
        finally:
            self._refreshing = False


if __name__ == "__main__":
    CommandCenter().run()
