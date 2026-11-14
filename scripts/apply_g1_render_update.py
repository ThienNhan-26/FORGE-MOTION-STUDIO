from __future__ import annotations

import ast
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / 'motion_studio' / 'shared' / 'SceneWorld.tsx'
COMPOSITION = ROOT / 'adapters' / 'remotion_template' / 'src' / 'Scene3DComposition.tsx'
ROOT_TSX = ROOT / 'adapters' / 'remotion_template' / 'src' / 'Root.tsx'
ADAPTER = ROOT / 'production' / 'remotion' / 'three_adapter.py'
QA_SOURCE = Path(__file__).resolve().parents[1] / 'production' / 'remotion' / 'render_qa.py'
MARKER = 'FORGE_G1_RENDER_QA_V1'


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected one occurrence, found {count}')
    return text.replace(old, new, 1)


def patch_scene(text: str) -> str:
    if 'FORGE_SINGLE_CAMERA_OWNER_V1' in text:
        return text
    text = text.replace(
        "import React, { Fragment, useLayoutEffect, useMemo } from 'react';",
        "import React, { Fragment, useMemo } from 'react';",
    )
    text = text.replace(
        "import { OrbitControls } from '@react-three/drei';",
        "import { OrbitControls, PerspectiveCamera } from '@react-three/drei';",
    )
    text = text.replace(
        "import { Euler, Object3D, PerspectiveCamera, Vector3 } from 'three';",
        "import { Euler, Object3D, Vector3 } from 'three';",
    )
    text = text.replace("import { useThree } from '@react-three/fiber';\n", '')
    rig_start = text.find('function SceneCameraRig(')
    if rig_start >= 0:
        rig_end = text.find('\nexport function SceneWorld', rig_start)
        if rig_end < 0:
            raise RuntimeError('Could not identify end of SceneCameraRig')
        text = text[:rig_start] + text[rig_end + 1:]
    text = text.replace(
        '<SceneCameraRig pose={pose} fov={scene.camera.fov} />',
        '<PerspectiveCamera key={`camera-${resetToken}`} makeDefault fov={scene.camera.fov} position={pose.position} rotation={pose.rotation} near={0.1} far={300} />',
    )
    # Base source has PerspectiveCamera from drei already, but a camera prop is removed in composition.
    if "import { OrbitControls, PerspectiveCamera } from '@react-three/drei';" not in text:
        raise RuntimeError('Drei PerspectiveCamera import not resolved')
    if '<PerspectiveCamera key={`camera-${resetToken}`}' not in text:
        raise RuntimeError('Declarative SceneWorld camera not found')
    if 'SceneCameraRig' in text or 'useThree' in text or 'useLayoutEffect' in text:
        raise RuntimeError('Imperative SceneCameraRig remained after patch')
    return text.replace('export function SceneWorld(', '/* FORGE_SINGLE_CAMERA_OWNER_V1 */\nexport function SceneWorld(', 1)


def patch_composition(text: str) -> str:
    if 'camera={{ position: scene.camera.position' in text:
        text = _replace_once(
            text,
            '        camera={{ position: scene.camera.position, fov: scene.camera.fov }}\n',
            '',
            'ThreeCanvas camera prop',
        )
    return text


def patch_adapter(text: str) -> str:
    if MARKER in text:
        return text
    if 'from .render_qa import validate_render_output' not in text:
        text = _replace_once(
            text,
            'from core.task import ExecutionResult, ExecutionStatus\n',
            'from core.task import ExecutionResult, ExecutionStatus\nfrom .render_qa import validate_render_output\n',
            'adapter import anchor',
        )
    success_pattern = r"        return ExecutionResult\(\s*ExecutionStatus\.SUCCESS,.*?evidence=str\(output_path\),\s*\)"
    matches = list(re.finditer(success_pattern, text, flags=re.DOTALL))
    if len(matches) != 1:
        raise RuntimeError(f"adapter SUCCESS block: expected one regex match, found {len(matches)}")
    replacement = """        # FORGE_G1_RENDER_QA_V1
        qa_report = validate_render_output(output_path, spec)
        qa_path = output_path.with_suffix(".qa.json")
        try:
            qa_path.write_text(json.dumps(qa_report, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            return ExecutionResult(
                ExecutionStatus.FAILED,
                f"Render QA report could not be saved: {exc}",
                exit_code=1,
                evidence=str(output_path),
            )

        if not qa_report.get("passed"):
            return ExecutionResult(
                ExecutionStatus.FAILED,
                f"Remotion rendered an MP4, but visual QA failed: {qa_report.get('error', 'unknown QA error')} Report: {qa_path}",
                exit_code=1,
                evidence=str(output_path),
            )

        return ExecutionResult(
            ExecutionStatus.SUCCESS,
            f"Đã render 3D '{spec.title}' ({len(spec.objects)} objects, {spec.duration_seconds}s, {spec.width}x{spec.height}@{spec.fps}). QA: {qa_report['summary']} Report: {qa_path}",
            exit_code=0,
            evidence=str(output_path),
        )"""
    return text[:matches[0].start()] + replacement + text[matches[0].end():]


def main() -> None:
    required = [SCENE, COMPOSITION, ROOT_TSX, ADAPTER]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    if missing:
        raise SystemExit('Project root mismatch; missing: ' + ', '.join(missing))
    # All reads, transformations and syntax checks happen before the first write.
    originals = {p: p.read_text(encoding='utf-8-sig') for p in required}
    scene_new = patch_scene(originals[SCENE])
    comp_new = patch_composition(originals[COMPOSITION])
    adapter_new = patch_adapter(originals[ADAPTER])
    if 'ThreeCanvasProbe' not in originals[ROOT_TSX]:
        print('Note: this project Root.tsx does not register the optional probe composition.')
    ast.parse(adapter_new)
    qa_text = (ROOT / 'production' / 'remotion' / 'render_qa.py').read_text(encoding='utf-8') if (ROOT / 'production' / 'remotion' / 'render_qa.py').is_file() else None
    if qa_text is None:
        raise SystemExit('Copy render_qa.py from this update package to production/remotion/ before running this script.')
    ast.parse(qa_text)
    changed = {SCENE: scene_new, COMPOSITION: comp_new, ADAPTER: adapter_new}
    if all(originals[p] == value for p, value in changed.items()):
        print('Update already applied; no changes made.')
        return

    backup_dir = ROOT / '.forge_backups' / ('g1_render_update_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup_dir.mkdir(parents=True, exist_ok=False)
    for path in changed:
        shutil.copy2(path, backup_dir / (path.name + '.bak'))

    temps: dict[Path, Path] = {}
    try:
        for path, content in changed.items():
            temp = path.with_name(path.name + '.forge_tmp')
            temp.write_text(content, encoding='utf-8')
            temps[path] = temp
        for path, temp in temps.items():
            temp.replace(path)
    except Exception:
        for path in changed:
            backup = backup_dir / (path.name + '.bak')
            if backup.exists():
                shutil.copy2(backup, path)
        for temp in temps.values():
            temp.unlink(missing_ok=True)
        raise

    print('FORGE G1 render update applied.')
    print(f'Backups: {backup_dir}')
    print('Changes: single camera owner, deterministic declarative camera, MP4 visual QA gate.')

if __name__ == '__main__':
    main()
