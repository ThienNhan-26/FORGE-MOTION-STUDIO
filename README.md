# FORGE — Local Agent Runtime (TUI Edition)

FORGE là bộ điều phối agent chạy trên máy cá nhân. Người dùng nhập nhiệm vụ trực tiếp trong terminal UI; Planner phân rã thành DAG; Scheduler thực thi các skill đã đăng ký; trạng thái và log được lưu trong SQLite để giao diện cập nhật liên tục.

> **Đây là bản tích hợp chạy local đầu tiên, không phải hệ điều hành AI tự trị không giới hạn.** Hệ thống chỉ thực hiện được những việc mà các skill hiện có hỗ trợ. Không có skill cho một thao tác thì Planner phải báo không thể lập kế hoạch cho thao tác đó.

## 1. Kiến trúc hiện tại

```text
User mission
    │
    ▼
Textual Command Center (background submission + live polling)
    │
    ▼
Coordinator ── creates mission / starts worker
    │
    ▼
PlannerAgent ── Ollama /api/chat ── JSON task DAG
    │
    ▼
TaskScheduler ── dependency check / bounded parallelism
    │
    ├── SkillRegistry ── write_file / python_task / run_python
    │                 ├─ render_video (2D Remotion)
    │                 └─ create_3d_scene → render_3d_scene (Motion Studio)
    │
    ▼
SQLite events, tasks, executions, checkpoints
```

Các nguyên tắc tích hợp:

- **Không khóa giao diện:** TUI gửi mission cho worker nền và đọc event từ SQLite.
- **Scheduler không chứa logic từng tool:** scheduler gọi `skill.execute(input_data)` theo manifest; skill mới được thêm bằng plugin trong `skills/`.
- **Đường dẫn tương đối theo project:** không còn bắt buộc đặt project tại `D:\FORGE`; có thể giải nén ở nơi khác hoặc cấu hình bằng `.env`.
- **Lưu trạng thái:** SQLite ghi mission, task, event, executions và checkpoints.
- **Hai vai trò model:** Planner và Coder có cấu hình Ollama riêng; mặc định Planner dùng `gpt-oss-20b-mxfp4:latest`, Coder dùng `qwen2.5-coder:7b`.
- **Giới hạn tải:** chỉ một mission được lập kế hoạch/thực thi tại một thời điểm; task độc lập bên trong mission có thể chạy song song theo `FORGE_MAX_WORKERS`. Các lệnh gọi LLM được tuần tự hóa để tránh tranh chấp bộ nhớ model local.
- **Dependency rõ ràng:** task lỗi làm các task phụ thuộc bị BLOCKED; graph không thể tiến triển được đánh dấu thay vì lặp vô hạn.
- **Phục hồi thận trọng:** task còn RUNNING từ phiên trước được đánh dấu FAILED và ghi log. FORGE không tự chạy lại thao tác có thể gây side-effect khi chưa biết nó đã thực hiện đến đâu.

## 2. Yêu cầu hệ thống

- Windows 10/11 64-bit.
- Python 3.10 trở lên.
- Ollama đã cài và đang chạy.
- Model local đã tải về trong Ollama. Model Planner mặc định là `gpt-oss-20b-mxfp4:latest`, model Coder mặc định là `qwen2.5-coder:7b`; sửa `OLLAMA_MODEL` và `OLLAMA_CODER_MODEL` đúng chính xác theo `ollama list` trên máy của bạn.
- Node.js tương thích với `package.json` của Remotion (template hiện cho phép Node 20.19+, 22.13+ hoặc 24+). Node 26 cũng thuộc nhánh `>=24`.
- FFmpeg nằm trong PATH để Remotion encode video.

Remotion là phần tùy chọn. TUI và các skill Python vẫn có thể chạy khi Node/Remotion chưa cài; skill render video sẽ trả lỗi cấu hình rõ ràng.

## 3. Cài đặt trên Windows PowerShell

Giải nén toàn bộ ZIP vào thư mục, ví dụ `D:\FORGE`. Mở PowerShell tại thư mục đó:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
```

Script sẽ tạo `.venv`, cài thư viện Python, tạo `.env` nếu chưa có, sau đó chạy `npm install` trong Remotion template và Motion Studio; frontend Motion Studio được build tự động nếu cài dependencies thành công.

Sau đó mở Ollama và kiểm tra model:

```powershell
ollama list
```

Sửa `.env` nếu model local của bạn có tên khác. Planner và Coder là hai vai trò riêng; các model cần có sẵn trong `ollama list`:

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=ten-model-planner
OLLAMA_CODER_MODEL=ten-model-coder
```

Chạy kiểm tra:

```powershell
.\scripts\doctor.ps1
```

Khởi động TUI:

```powershell
.\scripts\run.ps1
```

## 4. Sử dụng TUI

Nhập yêu cầu tự nhiên vào ô cuối màn hình và nhấn Enter. Ví dụ:

```text
Tạo một file hello.py in ra lời chào FORGE và giải thích ngắn gọn cách chạy.
```

Hoặc yêu cầu tạo video motion graphic nhiều cảnh khi Remotion đã được cài.

Lệnh TUI:

- `/help` — trợ giúp.
- `/tasks` — làm mới danh sách task.
- `/status` — in trạng thái task gần đây.
- `/clear` — xóa console.
- `/quit` — thoát.

Dòng không bắt đầu bằng `/` luôn được xem là mission mới.

Chạy headless để thử từ PowerShell:

```powershell
.\.venv\Scripts\python.exe main.py --headless "Tạo file note.txt với nội dung FORGE online"
```

Liệt kê skill:

```powershell
.\.venv\Scripts\python.exe main.py --list-skills
```

## 5. Python execution và an toàn

Skill `python_task` có thể yêu cầu Coder sinh script Python, chạy script đó, nhận stdout/stderr và yêu cầu Coder sửa lỗi tối đa `FORGE_MAX_REPAIR_ROUNDS` lần. Skill `run_python` chạy một file `.py` đã tồn tại để dùng trong DAG nhiều bước.

**Mặc định tính năng này đang tắt.** Để bật, sửa `.env`:

```env
FORGE_ENABLE_PYTHON_EXECUTION=true
```

Cần hiểu giới hạn bảo mật: FORGE kiểm tra đường dẫn file script nằm trong `workspace`, chạy bằng subprocess với timeout, nhưng đây **không phải sandbox cấp hệ điều hành**. Một chương trình Python có thể thực hiện nhiều thao tác mà quyền tài khoản Windows hiện tại cho phép. Chỉ bật khi bạn tin cậy model, prompt và môi trường làm việc; nên dùng tài khoản Windows riêng hoặc VM khi thử nghiệm mã chưa tin cậy. Bản này không tự cài thư viện, không tự chạy lệnh PowerShell/cmd, và không có quyền truy cập hệ thống tùy ý qua một shell skill.

Skill `write_file` chỉ tạo file mới trong workspace, chặn path traversal và không tự ghi đè file đã tồn tại.

## 6. Remotion: phạm vi và giới hạn

Skill `render_video` nhận `input_data.spec`, kiểm tra bằng Pydantic, ghi props vào thư mục runtime riêng của task và gọi Remotion CLI bằng Node trực tiếp (không sử dụng `shell=True`). Video template hiện hỗ trợ:

- Nhiều scene nối tiếp nhau.
- Nền gradient hai màu.
- Camera motion: `none`, `zoom_in`, `zoom_out`, `pan_left`.
- Layer `text` và `particles`.
- 1920×1080, 30 fps theo composition hiện tại.

Nó tạo motion graphic từ cấu trúc scene; **không tự tạo anime footage, ảnh nhân vật, hoạt họa 3D phức tạp hay giọng nói**. Các năng lực đó cần thêm provider/skill và asset pipeline riêng. Blender adapter cũ được giữ làm tài liệu/thử nghiệm, chưa đăng ký là skill hoạt động trong bản này.

## 7. Thêm skill mới

Tạo thư mục `skills/<ten_skill>/` gồm:

- `manifest.json`: name, version, description, input_schema, permissions.
- `skill.py`: một class kế thừa `BaseSkill`, cài đặt `get_manifest()` và `execute(params)`.
- `__init__.py` (khuyến nghị).

Ví dụ tối thiểu:

```python
from core.skill import BaseSkill, SkillManifest
from core.task import ExecutionResult, ExecutionStatus

class HelloSkill(BaseSkill):
    def get_manifest(self):
        return SkillManifest(
            name="hello",
            description="Demo skill",
            input_schema={"message": "string"},
        )

    def execute(self, params):
        return ExecutionResult(
            ExecutionStatus.SUCCESS,
            f"Hello: {params.get('message', '')}",
        )
```

Registry quét các thư mục skill có cả `manifest.json` và `skill.py`. Plugin là mã Python local được import và thực thi trong process FORGE; chỉ thêm plugin mà bạn đã xem xét và tin cậy. `permissions` hiện là metadata mô tả cho Planner/người vận hành, không phải cơ chế sandbox tự động.

## 8. Dữ liệu và sao lưu

- Database mặc định: `storage/forge.db`.
- Database cũ từ gói review được lưu riêng tại `storage/forge_review_backup.db`; runtime mới không tự nạp các task test cũ.
- Workspace mặc định: `workspace/`.
- Render output: `workspace/projects/<project_id>/renders/`.
- Props/runtime: `workspace/.forge_runtime/<task_id>/`.

Sao lưu `storage/forge.db`, `workspace/` và `.env` trước khi cập nhật bản FORGE. Không chia sẻ `.env` nếu trong tương lai bạn thêm API key hoặc thông tin riêng.

## 9. Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Các test mặc định không gọi Ollama, không render video và không chạy code do model sinh. Có thể cài thêm `requirements-dev.txt` nếu muốn dùng pytest.

## 10. Những gì chưa tuyên bố là đã hoàn thiện

- Chưa có khả năng cài package tự động; đây là hành vi có rủi ro và cần một package-install skill có approval policy.
- Chưa có browser/computer-use skill, image/video generation provider, Blender production skill, voice pipeline hoặc agent delegation độc lập.
- Chưa có resume tự động cho task bị ngắt giữa chừng; hiện trạng thái được đánh dấu rõ để tránh lặp các thao tác ghi file/render.
- Core, registry, lập kế hoạch giả lập, scheduler, dependency, SQLite migration và workspace path checks đã được unit-test trong môi trường đóng gói. TUI đã được rà soát theo API Textual 8.x nhưng không thể khởi chạy tại môi trường đóng gói vì Textual chưa được cài sẵn và môi trường này không truy cập được PyPI. Cần chạy setup và xác nhận TUI trên Windows.
- Ollama không chạy trong môi trường đóng gói; Remotion `node_modules` cũng chưa được cài trong môi trường này. Vì vậy chưa có kiểm thử end-to-end với model/render thực tế trên máy của bạn.

---

## 11. Motion Studio 3D (G1 foundation)

Bản này bổ sung giao diện browser Motion Studio dùng React + Three.js + React Three Fiber. Scene được lưu thành `workspace/projects/<project_id>/scene.json`. Preview và Remotion dùng cùng `motion_studio/shared/SceneWorld.tsx` và cùng SceneSpec v1, vì vậy animation được tính theo frame/FPS.

Cài dependencies (được `scripts/setup.ps1` tự động thực hiện khi có npm registry): `adapters/remotion_template` và `motion_studio`. `npm install` sẽ tạo lockfile mới tương thích với các package 3D đã thêm. Chạy:

```powershell
.\scripts\motion-studio.ps1
```

Trình duyệt mở `http://127.0.0.1:8765`. Có scene hierarchy, 3D viewport (orbit/zoom/select), inspector (position/rotation/scale/color/visibility), timeline scrub/play và render MP4. Video được lưu dưới `workspace/projects/<project_id>/renders/`.

FORGE Agent có thêm skill `create_3d_scene` và `render_3d_scene`; Planner có hướng dẫn lập DAG create → render. Xem `MOTION_STUDIO_README_VI.md` và `docs_RESEARCH_AND_ARCHITECTURE_VI.md`.

**Giới hạn:** đây là foundation G1, không phải full film editor. Chưa có GLB import, keyframe editor đa track, nhiều shot, asset browser, audio, voiceover, subtitles, physics hoặc QA theo frame. Remotion là source-available với license riêng, không phải OSI open source; kiểm tra license trước khi triển khai thương mại.
