# FORGE — Ghi chú nghiên cứu kiến trúc và quyết định tích hợp

**Ngày rà soát:** 13-11-2026  
**Nền tảng được kiểm tra:** `FORGE_FIXED_20261113 - Copy.zip`  
**Phạm vi thực hiện:** bổ sung vertical slice G1 — Motion Studio 3D, không thay thế Agent Core.

## 1. Kết luận thiết kế

FORGE nên được tổ chức thành ba lớp độc lập nhưng liên kết qua hợp đồng dữ liệu:

1. **Agent Runtime (Python):** tiếp nhận mission, Planner tạo DAG, Scheduler chạy skill, SQLite lưu tiến độ và artifact.
2. **Motion Studio (React + Three.js):** đọc/ghi một `Scene3DSpec` JSON, cho phép người dùng quan sát và chỉnh sửa thế giới 3D.
3. **Render Engine (Remotion + @remotion/three):** đọc chính `Scene3DSpec` đó và dựng video theo frame.

Hợp đồng scene được lưu tại `workspace/projects/<project_id>/scene.json`. Preview và Remotion dùng chung component `motion_studio/shared/SceneWorld.tsx`; thời gian animation được tính từ `frame` và `fps`, không dựa vào đồng hồ thực. Đây là ranh giới quan trọng để timeline có thể tua tới bất kỳ frame nào và render có thể lặp lại.

## 2. Nghiên cứu agent cloud và mã nguồn mở

### Anthropic — Building effective agents

Bài viết phân biệt workflow (luồng điều phối được định nghĩa trước) với agent (model tự quyết định bước tiếp theo và công cụ). Các hệ thống nên bắt đầu từ kiến trúc đơn giản; tăng tính tự chủ khi thực sự cần. Agent cần quan sát kết quả thực thi thật, có điều kiện dừng, và có điểm chuyển quyền cho con người khi cần.

Ứng dụng vào FORGE: giữ DAG workflow cho phần có cấu trúc như `create_3d_scene -> render_3d_scene`; không tạo thêm hàng loạt agent con. Để Planner chọn skill dựa trên kết quả thật và để Scheduler là nguồn sự thật về trạng thái.

Nguồn: https://www.anthropic.com/research/building-effective-agents

### OpenAI Agents SDK — primitives và run loop

Tài liệu mô tả các khối Agent, tool, handoff, guardrail, session và tracing. Một run lặp qua các bước: gọi model, kiểm tra output, thực thi tool call hoặc handoff, tiếp tục cho tới khi có điểm dừng. Tracing ghi lại model call, tool, handoff và guardrail.

Ứng dụng vào FORGE: không chuyển đổi ngay sang Agents SDK vì FORGE đã có Coordinator/Scheduler/SQLite và hiện chạy model qua Ollama. Thay vào đó, áp dụng các nguyên tắc tương đương: skill manifest có input contract, trạng thái task rõ, lưu event/execution, ràng buộc quyền và ghi lại artifact. Handoff đa-agent chưa được cài trong bản này.

Nguồn:
- https://developers.openai.com/tracks/building-agents
- https://developers.openai.com/api/docs/guides/agents/running-agents
- https://openai.github.io/openai-agents-python/tracing/

### LangGraph — persistence và interrupt

LangGraph tách checkpoint trạng thái luồng hiện tại khỏi store dài hạn; interrupt có thể tạm dừng để chờ input bên ngoài rồi resume từ checkpoint.

Ứng dụng vào FORGE: tiếp tục dùng SQLite hiện có; cần có roadmap riêng cho resume idempotent và approval pause/resume. Không giả định checkpoint đơn giản đồng nghĩa có thể chạy lại side-effect an toàn.

Nguồn:
- https://docs.langchain.com/oss/python/langgraph/persistence
- https://docs.langchain.com/oss/python/langgraph/interrupts

### OpenHands — runtime cô lập

OpenHands sử dụng mô hình client/server với runtime trong Docker, action executor, event stream và cơ chế agent/action/observation. Môi trường thực thi riêng là một lớp bảo vệ quan trọng, không chỉ là kiểm tra đường dẫn trong ứng dụng.

Ứng dụng vào FORGE: giữ Python execution tắt mặc định và không tuyên bố workspace là sandbox. Một giai đoạn tiếp theo nên đặt code chưa tin cậy trong Windows Sandbox/VM/isolated container, không chạy trực tiếp bằng quyền tài khoản Windows.

Nguồn: https://docs.openhands.dev/openhands/usage/architecture/runtime

## 3. Nghiên cứu 3D và video

### React Three Fiber / Three.js

React Three Fiber đưa scene graph Three.js vào React. Motion Studio dùng R3F cho viewport trình duyệt, `OrbitControls` cho orbit/zoom, và component object riêng để chỉnh transform. Three.js hỗ trợ GLTFLoader/GLTFExporter cho glTF 2.0; bản hiện tại chưa triển khai nhập/xuất GLB.

Nguồn:
- https://r3f.docs.pmnd.rs/getting-started/introduction
- https://threejs.org/docs/pages/GLTFLoader.html
- https://threejs.org/docs/pages/GLTFExporter.html

### Remotion + @remotion/three

`@remotion/three` cung cấp `ThreeCanvas` cho React Three Fiber. `ThreeCanvas` đồng bộ với frame Remotion; tài liệu khuyến nghị animation phải được tính khai báo từ frame thay vì dùng `useFrame()` để timeline scrub và render deterministic. `ThreeCanvas` cần width/height xác định; WebGL server rendering được cấu hình qua Chromium OpenGL renderer `angle`.

Ứng dụng vào FORGE: cùng component `SceneWorld` nhận `scene` và `frame`; Preview thêm OrbitControls, render không mount OrbitControls. Camera/object animation lấy từ frame index.

Nguồn:
- https://www.remotion.dev/docs/three
- https://www.remotion.dev/docs/three-canvas
- https://github.com/remotion-dev/remotion/tree/main/packages/template-three

## 4. Quyết định không đưa thêm framework orchestration vào G1

Trong bản gửi, Planner, DAG Scheduler, Skill Registry và SQLite đã tồn tại; bộ kiểm thử đóng gói sau tích hợp đạt 11/11 pass. Thay toàn bộ bằng OpenAI Agents SDK, LangGraph hoặc một framework khác sẽ tăng bề mặt thay đổi, đồng thời buộc phụ thuộc cloud API không phù hợp mục tiêu chạy Ollama local. G1 chỉ bổ sung hai skill và một studio riêng; Core hiện tại tiếp tục điều phối.

## 5. Giới hạn của bản tích hợp

- Scene primitives hiện có: island, tree/pine, house, cloud, rock, crystal, cube, sphere.
- Có preview orbit/zoom, chọn object, inspector position/rotation/scale/color/visibility/animation.
- Timeline hiện có play/scrub toàn cảnh và camera path đơn giản; chưa phải NLE với keyframe editor độc lập từng track.
- Chưa có import GLB, asset browser, skeletal animation, physics, particles nâng cao, audio, voiceover, subtitles hoặc compositing.
- Renderer không có quyền tạo mesh tùy ý từ văn bản; Planner phải diễn đạt cảnh bằng SceneSpec và các loại object đã hỗ trợ.
- Render cần cài Node dependencies trên máy Windows; bản kiểm tra hiện tại không thể tải npm packages do network registry trong môi trường build bị timeout.
- API server chỉ bind `127.0.0.1`/loopback, nhưng chưa có auth token; không đổi cấu hình để bind ra LAN.
- Python execution vẫn không phải OS sandbox.

## 6. License và lựa chọn thương mại

**Lưu ý quan trọng:** Remotion không được xem là open-source theo định nghĩa OSI; nó là source-available và dùng Remotion License riêng. Trang license hiện tại nêu cá nhân và tổ chức tối đa 3 người thường thuộc Free License, còn các tổ chức khác có thể cần Company License, đặc biệt cho automation/editor. Hãy đọc điều kiện hiện hành trước khi dùng FORGE như một sản phẩm thương mại hoặc dịch vụ tạo video cho khách hàng.

Nguồn:
- https://www.remotion.dev/docs/terms
- https://www.remotion.dev/docs/license/pricing
- https://www.remotion.dev/docs/license/faq

## 7. Hướng phát triển tiếp theo

1. **G1.1:** test thật trên Windows GPU/WebGL + MP4; kiểm tra nhiều frame và so khớp Preview/Render.
2. **G2:** GLB asset pipeline, style presets thật (clay/isometric/cinematic), material/light presets.
3. **G3:** storyboard, nhiều shot, camera keyframes, object keyframes, transitions và timeline edit.
4. **G4:** audio timeline, voiceover, subtitles, sound design và compositing.
5. **G5:** render QA bằng ffprobe + frame sampling + audio checks; chỉ sửa lại khi lỗi có bằng chứng.
6. **Runtime safety:** approval thật và môi trường thực thi cô lập trước khi bật shell/package install/autonomous code execution.
