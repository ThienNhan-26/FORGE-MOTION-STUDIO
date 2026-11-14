# FORGE 3D Specialist integration patch
# Replaces the old create_3d_scene prompt rule in agents/planner.py.
$ErrorActionPreference = "Stop"
$root = (Get-Location).Path
$plannerPath = Join-Path $root "agents\planner.py"
if (!(Test-Path $plannerPath)) { throw "Không tìm thấy agents\planner.py. Hãy chạy tại thư mục gốc FORGE." }

$content = Get-Content -Raw -Encoding UTF8 $plannerPath
$old = '- create_3d_scene: input_data.scene phải là một object Scene3DSpec v1 hoàn chỉnh để tạo thế giới 3D trong Motion Studio. Các trường cấp cao: project_id, title, style (hiện chỉ hỗ trợ low_poly), width, height, fps, duration_seconds, environment, camera, objects. Camera gồm position, end_position, target, end_target (mỗi giá trị là mảng 3 số), fov và motion (none|push_in|orbit). Mỗi object gồm id duy nhất an toàn, name, kind (island|tree|pine|house|cloud|rock|crystal|cube|sphere), position/rotation/scale (mảng 3 số), color #RRGGBB, visible và animation (none|float|rotate|pulse). Giới hạn tối đa 250 objects.'
$new = '- create_3d_scene: KHÔNG tự sinh SceneSpec. Hãy giao phần thiết kế thế giới cho 3D Specialist bằng input_data gồm project_id (ASCII letters/numbers/_/-) và prompt (mô tả thế giới, bố cục, vật thể, màu sắc, camera, chuyển động). 3D Specialist sẽ sinh JSON SceneSpec v1, Pydantic validate và lưu scene.json. Nếu người dùng yêu cầu tạo và xuất video 3D, tạo create_3d_scene trước rồi render_3d_scene phụ thuộc vào task đó.'
if ($content.Contains($old)) {
    $backupDir = Join-Path $root ("backups\three_d_specialist_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    Copy-Item $plannerPath (Join-Path $backupDir "planner.py")
    $content = $content.Replace($old, $new)
    Set-Content -Path $plannerPath -Value $content -Encoding UTF8
    Write-Host "Đã cập nhật Planner. Backup: $backupDir"
} elseif ($content.Contains("KHÔNG tự sinh SceneSpec")) {
    Write-Host "Planner đã có quy tắc 3D Specialist; bỏ qua patch."
} else {
    throw "Không tìm thấy đúng quy tắc create_3d_scene cũ. Dừng để tránh sửa nhầm planner.py."
}
