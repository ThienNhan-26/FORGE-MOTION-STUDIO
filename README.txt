FORGE MODEL DECOUPLING PATCH
============================

Mục tiêu
--------
Loại bỏ qwen3d-coder khỏi đường thực thi create_3d_scene.
- Nếu Planner cung cấp input_data.scene: validate và lưu, không gọi LLM.
- Nếu Planner cung cấp prompt + project_id: dùng model Planner hiện tại
  (OLLAMA_MODEL / gemma4-e4b-local) để sinh SceneSpec.
- Không sửa Planner, Coder, Reviewer, Scheduler, Ollama models, workspace,
  database, Blender Adapter, Three.js Adapter hoặc Remotion.
- Không xóa agents/three_d_specialist.py hay model khỏi Ollama; chỉ bảo đảm
  create_3d_scene không import hoặc gọi agent/model đó.

Cài đặt
-------
1. Giải nén ZIP trực tiếp vào:
   D:\FORGE_MOTION_STUDIO_G1_FINAL
2. Chạy PowerShell tại thư mục gốc:
   powershell -ExecutionPolicy Bypass -File .\APPLY.ps1

Script tạo backup các file bị thay thế trong backups\model_decoupling_<timestamp>.
Nó không ghi đè file khác ngoài hai file create_3d_scene đã liệt kê.

Kiểm tra
--------
.\.venv\Scripts\python.exe -m compileall -q skills
.\.venv\Scripts\python.exe -m pytest -q tests/test_create_3d_scene_without_specialist.py
.\.venv\Scripts\python.exe main.py --doctor

Lưu ý về làm phim
-----------------
Đây là bước gỡ dependency chậm và khôi phục đường tạo SceneSpec ổn định.
SceneSpec hiện tại vẫn chỉ hỗ trợ các object kind cơ bản và animation
none/float/rotate/pulse. Chưa có rigging, animation clips, behavior graph,
timeline đa đối tượng hoặc continuity giữa shot. Những năng lực đó sẽ được
bổ sung trong các patch tiếp theo; không được coi patch này là hoàn thành
Asset Generation / Film Production.
