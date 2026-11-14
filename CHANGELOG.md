# Changelog

## FORGE Integrated TUI Build

- Replaced machine-specific absolute paths with project-relative configuration and `.env` overrides.
- Added native Ollama chat client and strict Planner JSON normalization.
- Added mission coordinator with background submission and mission-scoped task IDs.
- Reworked scheduler for bounded parallelism, dependency blocking, explicit task states and event logging.
- Added plugin discovery from `skills/*/manifest.json` + `skill.py` with duplicate-name checks.
- Added built-in `write_file`, `python_task` (opt-in execution + bounded repair), and `render_video` skills.
- Reworked Remotion adapter to validate typed specs, isolate task props, use Node CLI directly and verify output.
- Added SQLite migrations, event log and conservative interrupted-task handling.
- Replaced command parsing UI with direct natural-language mission input and live task/event refresh.
- Added PowerShell setup/run/doctor scripts, Vietnamese documentation and isolated core tests.
- Archived pre-integration DB/specs/tests for reference instead of loading stale sample tasks into the new runtime.

## 2026-11-13 — G1 Motion Studio foundation

- Added validated SceneSpec v1 contract and a Floating Island demo scene.
- Added local React/Three.js/React Three Fiber browser editor with scene hierarchy, viewport controls, inspector, timeline scrub/play, local save and asynchronous MP4 render job status.
- Added shared `SceneWorld` component for browser Preview and Remotion `ThreeCanvas` render.
- Added `create_3d_scene` and `render_3d_scene` skills and Planner instructions for create → render DAG.
- Added local-only Python API server and PowerShell launcher/setup integration.
- Preserved the existing Agent Core and 2D Remotion composition.
