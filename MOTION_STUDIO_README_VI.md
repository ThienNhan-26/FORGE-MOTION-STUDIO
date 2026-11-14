# FORGE Motion Studio — Hướng dẫn nhanh

Motion Studio là giao diện 3D chạy local. Nó dùng cùng `Scene3DSpec` JSON với Remotion để Preview và MP4 có chung nguồn dữ liệu.

## Khởi động

1. Cài Python 3.10+, Node.js 20.19+ (Node 22/24/26 đều phù hợp), npm, Ollama và FFmpeg.
2. Bảo đảm máy có kết nối npm registry để cài các package Three.js/Remotion. Từ thư mục gốc FORGE, chạy:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
```

3. Mở Motion Studio:

```powershell
.\scripts\motion-studio.ps1
```

Trình duyệt mở tại `http://127.0.0.1:8765`. Dừng server bằng Ctrl+C. `setup.ps1` chạy `npm install` trong hai package; lockfile sẽ được npm tạo mới từ các phiên bản direct dependency đã ghim trong `package.json`.

## Sử dụng giao diện

- Kéo chuột trái để orbit; cuộn để zoom; nhấp object để chọn.
- Scene Graph ở trái; thư viện ở dưới để thêm cây, nhà, mây, đá, pha lê và primitives.
- Inspector ở phải để sửa position, rotation (đơn vị độ), scale, màu, visibility và animation đơn giản.
- Timeline ở dưới để phát hoặc tua frame.
- `LƯU SCENE` ghi `workspace/projects/<project_id>/scene.json`.
- `RENDER MP4` gửi đúng SceneSpec đó sang Remotion. Video nằm trong `workspace/projects/<project_id>/renders/`.

## Dùng qua FORGE Agent

Planner hiện có hai skill mới:

- `create_3d_scene`: nhận `input_data.scene` là object Scene3DSpec v1, validate và ghi scene JSON.
- `render_3d_scene`: nhận `input_data.project_id`, đọc scene đã có và render MP4.

Khi giao nhiệm vụ, hãy nói rõ muốn tạo scene 3D và xuất MP4. Planner phải lập DAG trong đó render phụ thuộc vào bước tạo scene.

## Scene contract

Mẫu đầy đủ: `examples/floating_island.scene.json`  
Pydantic contract: `contracts/scene3d.py`  
Component dùng chung cho Preview/Render: `motion_studio/shared/SceneWorld.tsx`.

`SceneWorld` animation lấy từ frame index và FPS, không dùng thời gian thực. Preview bật OrbitControls; Remotion tắt controls và lấy frame từ Remotion.

## Giới hạn phiên bản

Đây là G1 foundation: procedural low-poly objects và motion cơ bản. Style presets khác (clay/isometric/cinematic) thuộc G2, chưa được bật trong G1. Chưa có GLB import, asset browser, keyframe tracks độc lập, nhiều shot, physics, audio, voiceover, subtitles hoặc autonomous QA. Nếu scene cần object type không có trong SceneSpec thì Planner không được tuyên bố đã tạo được nó.

## Bảo mật và giấy phép

- API chỉ bind localhost `127.0.0.1`; không expose server ra LAN.
- Plugin trong `skills/` là mã Python được import vào tiến trình FORGE; chỉ thêm plugin tin cậy.
- Python execution mặc định tắt và workspace không phải OS sandbox.
- Remotion là source-available với license riêng, không phải OSI open source. Kiểm tra `https://www.remotion.dev/docs/license` nếu tổ chức dùng thương mại.
